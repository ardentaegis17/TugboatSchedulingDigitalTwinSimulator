import json
import math
import os
import copy
import time

# ================= CONFIGURATION =================
INPUT_FILE = 'simulation_schedule.json'
OUTPUT_FILE = 'optimised_schedule.json'
TRAJECTORY_FOLDER = 'standardised_trajectories' 

# Constraints
TOTAL_TUGS = 15          
TUG_SPEED = 6.7          # m/s, about 13 knots
SAFETY_DIST = 555.0      # Delta_safe (Meters)
WAYPOINT_INTERVAL = 10.0 # CSV data resolution (seconds per row)

# Optimization Settings
TABU_ITERATIONS = 200 
TABU_TENURE = 10

# ================= DATA CLASSES =================
class Job:
    def __init__(self, data):
        self.id = data['jobId']
        self.eta = data['eta']
        self.trajectory_file = data['TrajectoryFile']
        self.tugs_req = data['tugsRequired']
        
        # Spatio-Temporal Data
        self.duration = 0.0
        self.path_points = [] # List of (x, z) relative to start

    def get_position_at_delta(self, delta_time):
        """ Returns P_i(t - S_i) """
        if delta_time < 0 or delta_time > self.duration:
            return None # Not active
        
        # Interpolate or Nearest Neighbor
        idx = int(delta_time / WAYPOINT_INTERVAL)
        if idx >= len(self.path_points):
            return self.path_points[-1]
        return self.path_points[idx]

class VirtualTug:
    def __init__(self, tug_id):
        self.id = tug_id
        self.avail_time = 0.0
        self.pos = (103.76 * 111000, 0.0,1.29 * 111000 ) # x, y, z

class DynamicObstacle:
    """ Represents passing containerships of other jobs. """
    def __init__(self, id, path, start_time, duration):
        self.id = id
        self.path = path # List of (x, z)
        self.start_time = start_time
        self.duration = duration
        
    def get_position_at_abs_time(self, t):
        delta = t - self.start_time
        if delta < 0 or delta > self.duration:
            return None
        idx = int(delta / WAYPOINT_INTERVAL)
        if idx >= len(self.path): return self.path[-1]
        return self.path[idx]

# ================= HELPER FUNCTIONS =================
def load_csv_data(filename):
    """ Reads CSV and converts Lat/Lon to Unity X/Z (Meters) """
    path = os.path.join(TRAJECTORY_FOLDER, filename)
    if not os.path.exists(path):
        return 0, []

    with open(path, 'r', encoding='utf-8-sig') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    if len(lines) < 2: return 0, []

    duration = (len(lines) - 1) * WAYPOINT_INTERVAL
    
    # Parse Header
    header = lines[0].lower().split(',')
    try:
        lat_idx = next(i for i, h in enumerate(header) if "latitudedegrees" in h)
        lon_idx = next(i for i, h in enumerate(header) if "longitudedegrees" in h)
    except:
        lat_idx, lon_idx = 8, 9 # Fallback

    points = []
    for line in lines[1:]:
        cols = line.split(',')
        try:
            # Approximate Conversion: 1 deg lat = 111,000m. 1 deg lon = 111,000m (at equator)
            # In Unity: X = Longitude, Z = Latitude
            lat = float(cols[lat_idx])
            lon = float(cols[lon_idx])
            
            points.append((lon * 111000, lat * 111000))
        except:
            pass
    
            
    return duration, points

def dist_sq(p1, p2):
    return (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2

# ================= SAFETY CONSTRAINT CHECKER =================
def is_trajectory_safe(candidate_job, proposed_start_time, active_obstacles):
    """
    Implements: || P_i(t - S_i) - P_{obs}(t) || > Delta_safe
    Checks the candidate job against all currently active obstacles.
    """
    
    # Optimization: Only check time overlap
    candidate_end = proposed_start_time + candidate_job.duration
    
    for obs in active_obstacles:
        # Determine overlap window
        obs_end = obs.start_time + obs.duration
        
        overlap_start = max(proposed_start_time, obs.start_time)
        overlap_end = min(candidate_end, obs_end)
        
        if overlap_start >= overlap_end:
            continue # No time overlap, completely safe relative to this obstacle

        # Check Distance at intervals during the overlap
        # We step through the overlap window
        t = overlap_start
        while t < overlap_end:
            
            # P_i(t - S_i)
            p_i = candidate_job.get_position_at_delta(t - proposed_start_time)
            
            # P_obs(t)
            p_obs = obs.get_position_at_abs_time(t)
            
            if p_i and p_obs:
                d2 = dist_sq(p_i, p_obs)
                if d2 < (SAFETY_DIST * SAFETY_DIST):
                    return False # COLLISION DETECTED
            
            t += WAYPOINT_INTERVAL # Check every waypoint step
            
    return True # Safe against all obstacles

# ================= EVALUATOR =================
def evaluate_schedule(job_sequence, total_tugs, background_traffic):
    tugs = [VirtualTug(i) for i in range(total_tugs)]
    total_wait_time = 0.0
    
    # List of "Running Jobs" that serve as dynamic obstacles for subsequent jobs
    # Treated as DynamicObstacle objects
    active_jobs_as_obstacles = copy.deepcopy(background_traffic) 
    
    job_timings = {}

    for job in job_sequence:
        # 1. Resource Constraint: Find earliest tug availability
        start_pos = (job.path_points[0][0], 0, job.path_points[0][1]) # x,0,z
        end_pos = (job.path_points[-1][0], 0, job.path_points[-1][1])
        
        tug_options = []
        for tug in tugs:
            # Travel dist (3D dist with Y=0)
            d = math.sqrt((tug.pos[0]-start_pos[0])**2 + (tug.pos[2]-start_pos[2])**2)
            travel_time = d / TUG_SPEED
            arrival = tug.avail_time + travel_time
            # Cannot start before ETA
            ready_at = max(job.eta, arrival)
            tug_options.append({'tug': tug, 'ready_at': ready_at})
        
        tug_options.sort(key=lambda x: x['ready_at'])
        if len(tug_options) < job.tugs_req: return float('inf'), {}
        
        selected = tug_options[:job.tugs_req] 
        # Job starts when the LAST required tug arrives (Resource Synchronization)
        proposed_start = max(t['ready_at'] for t in selected)
        
        # 2. Safety Constraint: Check Collisions
        # If collision, delay start time by intervals until safe
        is_safe = False
        attempts = 0
        
        while not is_safe and attempts < 100: # Limit lookahead to prevent infinite loops
            if is_trajectory_safe(job, proposed_start, active_jobs_as_obstacles):
                is_safe = True
            else:
                # COLLISION! Shift start time forward
                proposed_start += 60.0 # Wait 1 minute
                attempts += 1
        
        if not is_safe:
            # If still unsafe after delays, apply huge penalty
            total_wait_time += 100000 
        
        # 3. Finalize Job
        wait = proposed_start - job.eta
        total_wait_time += wait
        job_timings[job.id] = proposed_start
        
        # 4. Add this job to the "Obstacles" list for future jobs in the sequence
        # (Since Tabu evaluates strictly sequentially)
        new_obs = DynamicObstacle(job.id, job.path_points, proposed_start, job.duration)
        active_jobs_as_obstacles.append(new_obs)
        
        # 5. Update Tugs
        finish = proposed_start + job.duration
        for s in selected:
            t = s['tug']
            t.avail_time = finish
            t.pos = (end_pos[0], 0, end_pos[1])

    return total_wait_time, job_timings

# ================= TABU SEARCH ENGINE =================
def run_optimizer():
    # 1. Load JSON
    if not os.path.exists(INPUT_FILE):
        print("Missing JSON file.")
        return

    with open(INPUT_FILE, 'r') as f:
        raw_data = json.load(f)
        
    # 2. Parse Jobs & Trajectories
    all_jobs = []
    print("Loading trajectory data...")
    for entry in raw_data:
        j = Job(entry)
        j.duration, j.path_points = load_csv_data(j.trajectory_file)
        if len(j.path_points) > 0:
            all_jobs.append(j)
    

    background_traffic = []

    # 4. Initial Solution
    current_sched = sorted(all_jobs, key=lambda x: x.eta)
    best_sched = list(current_sched)
    
    initial_cost, _ = evaluate_schedule(current_sched, TOTAL_TUGS, background_traffic)
    best_cost = initial_cost
    
    print(f"Initial Cost: {initial_cost:.1f}s")
    print(f"Running Tabu Search ({TABU_ITERATIONS} iter)...")
    
    tabu_list = []
    
    # 5. Tabu Loop
    for i in range(TABU_ITERATIONS):
        best_neighbor = None
        best_neighbor_cost = float('inf')
        move = None
        
        # Smaller neighborhood search for speed
        window = min(len(all_jobs), 30) 
        for a in range(window):
            for b in range(a+1, min(a+5, len(all_jobs))):
                neighbor = list(current_sched)
                neighbor[a], neighbor[b] = neighbor[b], neighbor[a]
                
                cost, _ = evaluate_schedule(neighbor, TOTAL_TUGS, background_traffic)
                
                is_tabu = (a, b) in tabu_list
                if not is_tabu or cost < best_cost:
                    if cost < best_neighbor_cost:
                        best_neighbor = neighbor
                        best_neighbor_cost = cost
                        move = (a, b)
        
        if best_neighbor:
            current_sched = best_neighbor
            if best_neighbor_cost < best_cost:
                best_cost = best_neighbor_cost
                best_sched = list(best_neighbor)
                print(f"Iter {i}: New Best {best_cost:.1f}s")
            
            tabu_list.append(move)
            if len(tabu_list) > TABU_TENURE: tabu_list.pop(0)

    # 6. Export
    _, final_timings = evaluate_schedule(best_sched, TOTAL_TUGS, background_traffic)
    
    output_data = []
    for job in best_sched:
        original = next(x for x in raw_data if x['jobId'] == job.id)
        original['predictedStartTime'] = final_timings[job.id]
        original['predictedWait'] = final_timings[job.id] - job.eta
        output_data.append(original)
        
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output_data, f, indent=4)
    
    print(f"Saved optimized schedule with safety checks to {OUTPUT_FILE}")

if __name__ == "__main__":
    run_optimizer()