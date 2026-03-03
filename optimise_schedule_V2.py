import json
import math
import os
import copy
import random
import time

# ================= CONFIGURATION =================
INPUT_FILE = 'eight_tugs_ci.json'
OUTPUT_FILE = INPUT_FILE[:-5] + "_opt.json"
TRAJECTORY_FOLDER = 'standardised_trajectories' 

# Constraints
TOTAL_TUGS = 8          
TUG_SPEED = 6.7          # m/s
SAFETY_DIST = 555.0      # Meters
WAYPOINT_INTERVAL = 10.0 # seconds per row in CSV

# Optimization Settings
TABU_ITERATIONS = 200 
TABU_TENURE = 15
NEIGHBOR_SIZE = 50       # How many swaps to test per iteration

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
        if delta_time < 0 or delta_time > self.duration:
            return None 
        idx = int(delta_time / WAYPOINT_INTERVAL)
        if idx >= len(self.path_points):
            return self.path_points[-1]
        return self.path_points[idx]

class VirtualTug:
    def __init__(self, tug_id):
        self.id = tug_id
        self.avail_time = 0.0
        # Default Start Position (e.g., Pasir Panjang Terminal center)
        self.pos = (103.76 * 111000, 0.0, 1.29 * 111000) 

class DynamicObstacle:
    def __init__(self, id, path, start_time, duration):
        self.id = id
        self.path = path 
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
    path = os.path.join(TRAJECTORY_FOLDER, filename)
    if not os.path.exists(path): return 0, []

    with open(path, 'r', encoding='utf-8-sig') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    if len(lines) < 2: return 0, []
    duration = (len(lines) - 1) * WAYPOINT_INTERVAL
    
    points = []
    for line in lines[1:]:
        cols = line.split(',')
        try:
            # Lat/Lon to Unity Meters (Simple Equirectangular Projection)
            # Adjust indices based on your specific CSV format
            lat = float(cols[8]) 
            lon = float(cols[9])
            points.append((lon * 111000, lat * 111000))
        except: pass
    return duration, points

def dist_sq(p1, p2):
    return (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2

def is_trajectory_safe(candidate_job, proposed_start_time, active_obstacles):
    """ Checks if candidate job collides with any active obstacle """
    candidate_end = proposed_start_time + candidate_job.duration
    
    for obs in active_obstacles:
        obs_end = obs.start_time + obs.duration
        overlap_start = max(proposed_start_time, obs.start_time)
        overlap_end = min(candidate_end, obs_end)
        
        if overlap_start >= overlap_end: continue 

        # Check every point in the overlap window
        t = overlap_start
        while t < overlap_end:
            p_i = candidate_job.get_position_at_delta(t - proposed_start_time)
            p_obs = obs.get_position_at_abs_time(t)
            
            if p_i and p_obs:
                d2 = dist_sq(p_i, p_obs)
                if d2 < (SAFETY_DIST * SAFETY_DIST):
                    return False # COLLISION
            t += WAYPOINT_INTERVAL
            
    return True

# ================= CORE EVALUATOR =================
def evaluate_assignments_with_safety(fixed_job_sequence, assignment_plan, total_tugs):
    """
    Calculates total wait time for a given set of tug assignments.
    Enforces BOTH Resource Availability AND Safety constraints.
    """
    
    # 1. Reset Fleet
    tugs = [VirtualTug(i) for i in range(total_tugs)]
    total_wait_time = 0.0
    job_timings = {}
    
    # 2. Track Active Obstacles (Background traffic + Scheduled jobs)
    active_obstacles = [] 

    # 3. Process Strictly Chronologically
    for job in fixed_job_sequence:
        
        # --- A. RESOURCE CONSTRAINT ---
        # Get the specific tugs assigned by the optimizer
        assigned_ids = assignment_plan[job.id] # List of ints [0, 1]
        
        arrival_times = []
        selected_tug_objs = []
        
        for t_id in assigned_ids:
            tug = tugs[t_id]
            selected_tug_objs.append(tug)
            
            # Calculate Travel Time to Job Start
            if len(job.path_points) > 0:
                start_x, start_z = job.path_points[0]
                dist = math.sqrt((tug.pos[0] - start_x)**2 + (tug.pos[2] - start_z)**2)
                travel_time = dist / TUG_SPEED
            else:
                travel_time = 0
            
            # Earliest this tug is free AND at location
            arrival = tug.avail_time + travel_time
            arrival_times.append(arrival)

        # Job can only start when LAST tug arrives (and after ETA)
        resource_ready_time = max(job.eta, max(arrival_times) if arrival_times else job.eta)
        
        # --- B. SAFETY CONSTRAINT ---
        proposed_start = resource_ready_time
        is_safe = False
        attempts = 0
        
        # Check safety against previous jobs. Delay if unsafe.
        while not is_safe and attempts < 20: 
            if is_trajectory_safe(job, proposed_start, active_obstacles):
                is_safe = True
            else:
                proposed_start += 60.0 # Delay 1 minute
                attempts += 1
        
        # Heavy penalty if still unsafe (forces optimizer to avoid this assignment)
        if not is_safe:
            total_wait_time += 100000.0 

        # --- C. UPDATE STATE ---
        actual_start = proposed_start
        wait = actual_start - job.eta
        total_wait_time += wait
        job_timings[job.id] = actual_start
        
        # Add to obstacles for future jobs
        new_obs = DynamicObstacle(job.id, job.path_points, actual_start, job.duration)
        active_obstacles.append(new_obs)
        
        # Update Tugs (Busy until finish)
        finish_time = actual_start + job.duration
        if len(job.path_points) > 0:
            end_x, end_z = job.path_points[-1]
            for tug in selected_tug_objs:
                tug.avail_time = finish_time
                tug.pos = (end_x, 0, end_z)

    return total_wait_time, job_timings

# ================= OPTIMIZER ENGINE =================
def run_resource_optimizer():
    # 1. Load Data
    if not os.path.exists(INPUT_FILE):
        print("Missing JSON file.")
        return

    with open(INPUT_FILE, 'r') as f:
        raw_data = json.load(f)
        
    all_jobs = []
    print("Loading trajectory data...")
    for entry in raw_data:
        j = Job(entry)
        j.duration, j.path_points = load_csv_data(j.trajectory_file)
        if len(j.path_points) > 0:
            all_jobs.append(j)
            
    # CRITICAL: Sort by ETA (Fixed Sequence)
    all_jobs.sort(key=lambda x: x.eta)

    # 2. Initial Solution (Simple Round Robin)
    # Assign tugs [0,1], [2,3] etc just to get started
    current_assignment = {}
    tug_idx = 0
    for job in all_jobs:
        assigned = []
        for _ in range(job.tugs_req):
            assigned.append(tug_idx % TOTAL_TUGS)
            tug_idx += 1
        current_assignment[job.id] = assigned

    # Evaluate Initial
    best_assignment = copy.deepcopy(current_assignment)
    best_cost, _ = evaluate_assignments_with_safety(all_jobs, current_assignment, TOTAL_TUGS)
    
    print(f"Initial Cost (Total Wait): {best_cost:.1f}s")
    print(f"Running Resource Tabu Search ({TABU_ITERATIONS} iter)...")
    
    tabu_list = [] # Stores (job_id, tug_id_removed, tug_id_added)

    # 3. Tabu Loop
    for i in range(TABU_ITERATIONS):
        best_neighbor_assignment = None
        best_neighbor_cost = float('inf')
        move_made = None
        
        # Generate Neighbors (Swap Tugs)
        # Try 50 random swaps
        for _ in range(NEIGHBOR_SIZE):
            neighbor = copy.deepcopy(current_assignment)
            
            # A. Pick random job
            job_id = random.choice(list(neighbor.keys()))
            current_tugs = neighbor[job_id]
            
            # B. Pick tug to swap OUT
            tug_out = random.choice(current_tugs)
            
            # C. Pick tug to swap IN (must not be in current_tugs)
            candidates = [t for t in range(TOTAL_TUGS) if t not in current_tugs]
            tug_in = random.choice(candidates)
            
            # D. Perform Swap
            current_tugs.remove(tug_out)
            current_tugs.append(tug_in)
            
            # E. Check Tabu
            move = (job_id, tug_out, tug_in)
            is_tabu = move in tabu_list
            
            # F. Evaluate
            cost, _ = evaluate_assignments_with_safety(all_jobs, neighbor, TOTAL_TUGS)
            
            # Aspiration Criteria (Ignore tabu if it's a new global best)
            if (not is_tabu) or (cost < best_cost):
                if cost < best_neighbor_cost:
                    best_neighbor_cost = cost
                    best_neighbor_assignment = neighbor
                    move_made = move

        # Update Current
        if best_neighbor_assignment:
            current_assignment = best_neighbor_assignment
            
            if best_neighbor_cost < best_cost:
                best_cost = best_neighbor_cost
                best_assignment = copy.deepcopy(best_neighbor_assignment)
                print(f"Iter {i}: New Best {best_cost:.1f}s")
            
            # Update Tabu List
            tabu_list.append(move_made)
            if len(tabu_list) > TABU_TENURE:
                tabu_list.pop(0)

    # 4. Export Results
    print("Finalizing schedule...")
    _, final_timings = evaluate_assignments_with_safety(all_jobs, best_assignment, TOTAL_TUGS)
    
    output_data = []
    for job in all_jobs:
        original = next(x for x in raw_data if x['jobId'] == job.id)
        
        # Add Predicted Data
        original['predictedStartTime'] = final_timings[job.id]
        original['predictedWait'] = final_timings[job.id] - job.eta
        
        # CONVERT TUG IDs to STRINGS (0 -> "1") for Unity
        # This allows Unity to dispatch SPECIFIC tugs
        assigned_indices = best_assignment[job.id]
        original['tugImos'] = [str(x + 1) for x in assigned_indices]
        
        output_data.append(original)
        
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output_data, f, indent=4)
    
    print(f"Saved optimized resource schedule to {OUTPUT_FILE}")

if __name__ == "__main__":
    run_resource_optimizer()