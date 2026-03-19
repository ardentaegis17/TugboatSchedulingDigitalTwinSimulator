import json
import math
import os
import csv
import sys
# Force the script to look inside the virtual environment for packages
current_dir = os.path.dirname(__file__)
root_dir = os.path.dirname(current_dir)
sys.path.insert(0, os.path.join(root_dir, '.venv', 'Lib', 'site-packages'))

# ================= CONFIGURATION =================
INPUT_FILE = "generated_schedules/simulation_schedule.json"
OUTPUT_FILE = "generated_schedules/cheap_insertion.json"
TRAJ_FOLDER = "trajectories/standardised_trajectories" # Folder containing your CSVs
from datetime import datetime
from routeplanner import RoutePlanner

# Safety Parameters
SAFE_DISTANCE = 555.0  # Meters (The "Safety Buffer" radius)
NUM_TUGS = 15
TUG_SPEED_MS = 6.7    # ~12 knots
TUG_BASE_LONLAT = (103.76, 1.29) 
# ================= DATA HANDLING =================

router = RoutePlanner("Pasir Panjang Terminal/PPT_terminal.geojson", origin_lat=1.264, origin_lon=103.792)

class TrajectoryCache:
    """Caches CSV data to avoid re-reading files thousands of times."""
    def __init__(self):
        self.cache = {}

    def get_points(self, filename):
        if filename not in self.cache:
            path = os.path.join(TRAJ_FOLDER, filename)
            if not os.path.exists(path):
                print(f"Warning: Missing file {filename}")
                return []
            
            start_time_ref = None
            points = []

            try:
                with open(path, 'r') as f:
                    reader = csv.reader(f)
                    next(reader) # Skip Header
                    for row in reader:
                        # Parsing Logic (adjust indices based on your CSV)
                        # Time(0), lat(8), lon(9) or Lat/Lon converted
                        
                        dt_obj = datetime.strptime(row[16], "%Y-%m-%d %H:%M:%S")
                        t_raw = dt_obj.timestamp()

                        if start_time_ref is None:
                            start_time_ref = t_raw
                        
                        t_rel = t_raw - start_time_ref

                        # Unity (X,Z) = (Lon,Lat) * 111000
                        x = float(row[9]) 
                        z = float(row[8])
                        points.append((t_rel, x * 111000, z * 111000))
            except Exception as e:
                print(e)
                return []
            self.cache[filename] = points
        return self.cache[filename]

# Global Cache
traj_cache = TrajectoryCache()

# ================= SAFETY LOGIC ========================

def check_trajectory_safety(candidate_job, proposed_start_time, scheduled_jobs):
    """
    SAFETY CONSTRAINT:
    Checks if the candidate's trajectory (shifted to start at proposed_start_time)
    intersects with any ALREADY scheduled job's trajectory.
    """
    
    # 1. Get Candidate Trajectory Points
    cand_points = traj_cache.get_points(candidate_job['TrajectoryFile'])
    if not cand_points: return True # Fail safe: If no file, assume safe (or fail)

    # 2. Iterate through all ALREADY SCHEDULED jobs
    for other_job in scheduled_jobs:
        other_start = other_job['predictedStartTime']
        other_points = traj_cache.get_points(other_job['TrajectoryFile'])
        
        # Optimization: Time Window Check
        # If Job A finishes before Job B starts, no collision possible.
        cand_end = proposed_start_time + cand_points[-1][0]
        other_end = other_start + other_points[-1][0]
        
        if cand_end < other_start or proposed_start_time > other_end:
            continue # Temporally disjoint, safe.

        # 3. Spatiotemporal Check
        # We step through time where they overlap
        overlap_start = max(proposed_start_time, other_start)
        overlap_end = min(cand_end, other_end)
        
        # Step size (e.g., every 10 seconds)
        t = overlap_start
        while t < overlap_end:
            # Get Position of Candidate at time t
            pos_cand = sample_traj(cand_points, t - proposed_start_time)
            
            # Get Position of Other Job at time t
            pos_other = sample_traj(other_points, t - other_start)
            
            # Distance Check
            dist = math.sqrt((pos_cand[0]-pos_other[0])**2 + (pos_cand[1]-pos_other[1])**2)
            
            if dist < SAFE_DISTANCE:
                return False # COLLISION DETECTED!
            
            t += 10 # Check every 10 seconds

    return True # Safe

def sample_traj(points, rel_time):
    """Interpolates position at a specific relative time."""
    # Simple linear search or index lookup
    # Assuming points are sorted by time.
    for i in range(len(points)-1):
        t1, x1, z1 = points[i]
        t2, x2, z2 = points[i+1]
        if t1 <= rel_time <= t2:
            # Lerp
            factor = (rel_time - t1) / (t2 - t1) if (t2-t1) > 0 else 0
            x = x1 + (x2 - x1) * factor
            z = z1 + (z2 - z1) * factor
            return (x, z)
    return points[-1][1:] # Clamp to end

# ================= SCHEDULING ALGORITHM =================

def run_safety_insertion():
    with open(INPUT_FILE, 'r') as f:
        raw_data = json.load(f)
        if isinstance(raw_data, dict): raw_data = raw_data['jobs']

    # Sort by ETA (Priority)
    jobs = sorted(raw_data, key=lambda x: x['eta'])
    
    # Initialise Tugs (Free at t=0)
    tug_availability = [0.0] * NUM_TUGS 
    tug_locations = [(TUG_BASE_LONLAT[0] * 111000, TUG_BASE_LONLAT[1] * 111000)] * NUM_TUGS
    
    scheduled_jobs = [] # To keep track for collision checking

    for job in jobs:
        print(f"Scheduling {job['jobId']}...")
        
        # Load Trajectory Duration
        pts = traj_cache.get_points(job['TrajectoryFile'])
        duration = pts[-1][0] if pts else 3600
        start_loc = pts[0][1:] if pts else (0,0)
        end_loc = pts[-1][1:] if pts else (0,0)

        best_tugs = []
        best_start_time = float('inf')

        # --- STEP 1: Find Resource Availability ---
        # Find the earliest time N tugs can be ready
        # We try to find the combination of N tugs that gives min(max(arrival_times))
        
        # Calculate arrival time for EACH tug to this job
        tug_arrivals = []
        for i in range(NUM_TUGS):
            # check if tug returned to base
            idle_time = job['eta'] - tug_availability[i]
            
            if idle_time > 1800: # 30 mins
                current_loc = (TUG_BASE_LONLAT[0] * 111000, TUG_BASE_LONLAT[1] * 111000)
            else:
                current_loc = tug_locations[i]

            dist = router.get_safe_distance(tug_locations[i], start_loc)
            travel_time = dist / TUG_SPEED_MS
            ready_at = max(tug_availability[i] + travel_time, job['eta'])
            tug_arrivals.append((ready_at, i))
        
        # Sort tugs by who can get there first
        tug_arrivals.sort()
        
        # Pick the best N tugs
        chosen_candidates = tug_arrivals[:job['tugsRequired']]
        resource_ready_time = chosen_candidates[-1][0] # The time the LAST tug arrives
        
        # --- STEP 2: Apply Safety Buffer (Trajectory Check) ---
        # We have a proposed start time. Now we must "push" it forward until it is safe.
        
        safe_start_time = resource_ready_time
        is_safe = False
        
        while not is_safe:
            if check_trajectory_safety(job, safe_start_time, scheduled_jobs):
                is_safe = True
            else:
                # If collision, push start time forward by a step (e.g., 1 min)
                safe_start_time += 60 

        # --- STEP 3: Commit ---
        assigned_ids = [str(c[1]+1) for c in chosen_candidates]
        finish_time = safe_start_time + duration
        
        # Update Tug States
        for arrival_time, tug_idx in chosen_candidates:
            tug_availability[tug_idx] = finish_time
            tug_locations[tug_idx] = end_loc
        
        # Save Result
        job['tugImos'] = assigned_ids
        job['predictedStartTime'] = safe_start_time
        job['predictedWait'] = safe_start_time - job['eta']
        
        scheduled_jobs.append(job)
        # print(f"  -> Start: {safe_start_time:.1f} (Wait: {job['predictedWait']:.1f}s) | Safe: YES")

    print(f"Saving optimised schedule to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump({"jobs": scheduled_jobs}, f, indent=4)

    return scheduled_jobs
    

if __name__ == "__main__":
    # If run from the batch script, override the default filenames
    if len(sys.argv) == 3:
        INPUT_FILE = sys.argv[1]
        OUTPUT_FILE = sys.argv[2]
        
    run_safety_insertion()