import json
import math
import sys
import os
import csv
import random
import copy
# import matplotlib.pyplot as plt
from datetime import datetime

# Force the script to look inside the virtual environment for packages
current_dir = os.path.dirname(__file__)
root_dir = os.path.dirname(current_dir)
sys.path.insert(0, os.path.join(root_dir, '.venv', 'Lib', 'site-packages'))

from routeplanner import RoutePlanner
# ================= CONFIGURATION =================
INPUT_FILE = "generated_schedules/cheap_insertion.json"
OUTPUT_FILE = INPUT_FILE[:-5] + "_tabu.json"
TRAJ_FOLDER = "trajectories/standardised_trajectories" 

# Optimization Parameters
MAX_ITERATIONS = 100     # How many swaps to try (Increase for better results)
TABU_TENURE = 15         # How many iterations a move stays banned
NEIGHBORHOOD_SIZE = 20  # How many random swaps to evaluate per iteration

# Operational Constants
SAFE_DISTANCE = 555.0   # Meters
NUM_TUGS = 15
TUG_SPEED_MS = 6.7      # ~12 knots
TUG_BASE_LONLAT = (103.76, 1.29) 

# Initialize RoutePlanner (Global)
router = RoutePlanner("Pasir Panjang Terminal/PPT_terminal.geojson", origin_lat=1.264, origin_lon=103.792)

# ================= DATA HANDLING =================

class TrajectoryCache:
    """Caches CSV data to avoid re-reading files thousands of times."""
    def __init__(self):
        self.cache = {}

    def get_points(self, filename):
        if filename not in self.cache:
            path = os.path.join(TRAJ_FOLDER, filename)
            if not os.path.exists(path):
                # Fail silently or warn?
                return []
            
            points = []
            start_time_ref = None

            try:
                with open(path, 'r') as f:
                    reader = csv.reader(f)
                    next(reader) # Skip Header
                    for row in reader:
                        # Parse Time (Col 16 based on your provided code)
                        try:
                            dt_obj = datetime.strptime(row[16], "%Y-%m-%d %H:%M:%S")
                            t_raw = dt_obj.timestamp()
                        except:
                             # Fallback if format differs
                             t_raw = 0.0

                        if start_time_ref is None: start_time_ref = t_raw
                        t_rel = t_raw - start_time_ref

                        # Parse Pos (Col 8/9 -> Lat/Lon -> Unity X/Z)
                        # Scaling by 111000 to get meters from degrees
                        x = float(row[9]) * 111000
                        z = float(row[8]) * 111000
                        points.append((t_rel, x, z))
            except Exception as e:
                print(f"Err reading {filename}: {e}")
                return []
            self.cache[filename] = points
        return self.cache[filename]

# Global Cache
traj_cache = TrajectoryCache()

# ================= PHYSICS & SAFETY HELPERS =================

def sample_traj(points, rel_time):
    """Interpolates position at a specific relative time."""
    if not points: return (0,0)
    
    # Boundary checks
    if rel_time <= 0: return points[0][1:]
    if rel_time >= points[-1][0]: return points[-1][1:]

    # Linear Search
    for i in range(len(points)-1):
        t1, x1, z1 = points[i]
        t2, x2, z2 = points[i+1]
        if t1 <= rel_time <= t2:
            if (t2 - t1) == 0: return (x1, z1)
            f = (rel_time - t1) / (t2 - t1)
            return (x1 + (x2 - x1) * f, z1 + (z2 - z1) * f)
    return points[-1][1:]

def check_trajectory_safety(candidate_job, start_time, scheduled_jobs):
    """Checks if candidate job overlaps physically with any already scheduled job."""
    cand_pts = traj_cache.get_points(candidate_job['TrajectoryFile'])
    if not cand_pts: return True
    
    cand_end = start_time + cand_pts[-1][0]

    for other in scheduled_jobs:
        if other['jobId'] == candidate_job['jobId']: continue # Don't check self
        
        other_start = other['predictedStartTime']
        other_pts = traj_cache.get_points(other['TrajectoryFile'])
        if not other_pts: continue
        
        other_end = other_start + other_pts[-1][0]

        # 1. Temporal Check
        if cand_end < other_start or start_time > other_end:
            continue 

        # 2. Spatiotemporal Check
        overlap_start = max(start_time, other_start)
        overlap_end = min(cand_end, other_end)
        
        # Check every 30s to save performance
        t = overlap_start
        while t < overlap_end:
            p1 = sample_traj(cand_pts, t - start_time)
            p2 = sample_traj(other_pts, t - other_start)
            
            dist = math.hypot(p1[0]-p2[0], p1[1]-p2[1])
            if dist < SAFE_DISTANCE:
                return False 
            t += 30

    return True

# ================= CORE EVALUATOR =================

def evaluate_schedule(jobs, assignment_map):
    """
    Simulates the full timeline for a given set of assignments.
    Returns: (Total Wait Time, Full Schedule List)
    """
    
    # 1. Reset Tug Fleet State
    # Convert Base Lon/Lat to Meters
    base_x = TUG_BASE_LONLAT[0] * 111000
    base_z = TUG_BASE_LONLAT[1] * 111000
    
    tug_state = [{'avail': 0.0, 'loc': (base_x, base_z)} for _ in range(NUM_TUGS)]
    
    total_wait = 0.0
    schedule_result = []
    
    # 2. Process Jobs in ETA Order
    # IMPORTANT: Use a consistent sort order
    sorted_jobs = sorted(jobs, key=lambda x: x['eta'])
    
    for job in sorted_jobs:
        job_id = job['jobId']
        # assignment_map is { 'JOB_001': [0, 1] } (list of Tug Indices)
        assigned_indices = assignment_map.get(job_id, [])
        
        # Load Job Details
        pts = traj_cache.get_points(job['TrajectoryFile'])
        start_loc = pts[0][1:] if pts else (0,0)
        end_loc = pts[-1][1:] if pts else (0,0)
        duration = pts[-1][0] if pts else 3600

        # A. Calculate Arrival of assigned tugs
        arrival_times = []
        for t_idx in assigned_indices:
            tug = tug_state[t_idx]
            
            # Use ROUTE PLANNER for distance
            dist = router.get_safe_distance(tug['loc'], start_loc)
            travel_time = dist / TUG_SPEED_MS
            
            # Tug ready time = Available Time + Travel Time (clamped by Job ETA)
            ready_at = max(tug['avail'] + travel_time, job['eta'])
            arrival_times.append(ready_at)
            
        # B. Resource Ready Time (When the LAST tug arrives)
        if not arrival_times:
            resource_ready = job['eta'] # Should not happen
        else:
            resource_ready = max(arrival_times)
            
        # C. Safety Check (Push forward if trajectory conflict)
        safe_start = resource_ready
        
        # Loop until safe (Timeout at +24 hours to prevent infinite loop)
        attempts = 0
        while not check_trajectory_safety(job, safe_start, schedule_result):
            safe_start += 60 # Push 1 min
            attempts += 1
            if attempts > 1440:
                # penalise solution heavily
                safe_start += 100000
                break 
            
        # D. Commit & Update State
        finish_time = safe_start + duration
        wait = safe_start - job['eta']
        total_wait += wait
        
        for t_idx in assigned_indices:
            tug_state[t_idx]['avail'] = finish_time
            tug_state[t_idx]['loc'] = end_loc
            
        # Store result
        res_job = copy.deepcopy(job)
        res_job['predictedStartTime'] = safe_start
        res_job['predictedWait'] = wait
        schedule_result.append(res_job)
        
    return total_wait, schedule_result

# ================= TABU SEARCH LOGIC =================
def generate_initial_solution(jobs):
    """
    Creates a valid initial assignment.
    For simplicity, we just assign random tugs. 
    (Or you could put your Greedy Insertion logic here for a 'hot start')
    """
    assignment = {}
    all_tugs = list(range(NUM_TUGS))
    for job in jobs:
        req = job['tugsRequired']
        # Random Sample
        assignment[job['jobId']] = random.sample(all_tugs, req)
    return assignment

def load_warm_start_solution(jobs):
    """
    Parses the existing schedule from the input JSON to create the initial assignment.
    """
    assignment = {}
    
    # Check if the input actually has assignments
    if 'tugImos' not in jobs[0]:
        print("Warning: Input file has no existing assignments. Falling back to Random.")
        return generate_initial_solution(jobs)

    for job in jobs:
        job_id = job['jobId']
        
        # Extract the IDs: e.g., ["1", "5"]
        tug_ids = job['tugImos'] 
        
        # Convert to 0-based Indices: "1" -> 0, "5" -> 4
        # This matches the internal logic of the Tabu script (range(NUM_TUGS))
        tug_indices = [int(tid) - 1 for tid in tug_ids]
        
        assignment[job_id] = tug_indices
        
    print(f"Successfully loaded Warm Start assignments for {len(jobs)} jobs.")
    return assignment

def run_tabu_search(print_result = False):
    print("--- Starting Tabu Search Optimization (Warm Start) ---")
    
    # 1. Load Data (The output from Cheap Insertion)
    with open(INPUT_FILE, 'r') as f:
        raw_data = json.load(f)
        jobs = raw_data['jobs'] if isinstance(raw_data, dict) else raw_data

    # 2. Initial Solution -> LOAD EXISTING instead of Random
    current_assignment = load_warm_start_solution(jobs)
    
    # Evaluate the starting point to set the baseline
    current_cost, _ = evaluate_schedule(jobs, current_assignment)
    
    best_assignment = copy.deepcopy(current_assignment)
    best_cost = current_cost

    tabu_list = {}

    # --- SETUP VISUALIZATION TRACKERS ---
    ci_baseline_cost = current_cost # The cost we got from cheapest_insertion.py
    best_cost_history = []
    current_cost_history = []
    
    print(f"Initial Cost (From Cheap Insertion): {ci_baseline_cost:.1f}s")

    # 3. Optimization Loop
    for iteration in range(MAX_ITERATIONS):

        # A. Generate Random Neighbors
        candidates = []
        for _ in range(NEIGHBORHOOD_SIZE):
            job = random.choice(jobs)
            job_id = job['jobId']
            
            current_tugs = current_assignment[job_id]
            available_tugs = [t for t in range(NUM_TUGS) if t not in current_tugs]
            
            if not available_tugs: continue
            
            tug_out = random.choice(current_tugs)
            tug_in = random.choice(available_tugs)
            
            move_key = (job_id, tug_in) 
            reverse_move = (job_id, tug_out) # when added to tabu list: don't assign the same job back to the tug we just removed
            
            new_assign = copy.deepcopy(current_assignment)
            new_assign[job_id].remove(tug_out)
            new_assign[job_id].append(tug_in)
            
            candidates.append({
                'assign': new_assign,
                'move': move_key,
                'rev_move': reverse_move,
                # Flag the move as Tabu, but DO NOT discard it yet
                'is_tabu': move_key in tabu_list and tabu_list[move_key] > iteration
            })

        # B. Evaluate Candidates with ASPIRATION CRITERION
        best_candidate = None
        best_candidate_cost = float('inf')
        
        for cand in candidates:
            # We must evaluate the cost first to see if it breaks the global best
            cost, _ = evaluate_schedule(jobs, cand['assign'])
            
            # --- THE ASPIRATION CRITERION LOGIC ---
            # Accept if: Move is NOT Tabu -OR- Cost is strictly better than the global best
            if not cand['is_tabu'] or cost < best_cost:
                if cost < best_candidate_cost:
                    best_candidate_cost = cost
                    best_candidate = cand

        # C. Update State
        if best_candidate:
            current_assignment = best_candidate['assign']
            current_cost = best_candidate_cost
            
            # Place the newly accepted move onto the Tabu List
            tabu_list[best_candidate['rev_move']] = iteration + TABU_TENURE
            
            # Update the global best if necessary
            if current_cost < best_cost:
                best_cost = current_cost
                best_assignment = copy.deepcopy(current_assignment)
                print(f"Iter {iteration}: New Best Cost = {best_cost:.1f}s")

        # --- RECORD DATA FOR PLOTTING ---
        current_cost_history.append(current_cost)
        best_cost_history.append(best_cost)

    # 4. Final Result Generation & Plotting
    print("--- Optimization Complete ---")
    final_cost, final_schedule = evaluate_schedule(jobs, best_assignment)
    
    # === GENERATE THE PLOT ===
    # plt.figure(figsize=(10, 6))
    
    # # Plot CI Baseline
    # plt.axhline(y=ci_baseline_cost, color='r', linestyle='--', linewidth=2, label=f'Cheapest Insertion Baseline ({ci_baseline_cost:.1f}s)')
    
    # # Plot Tabu Search Progress
    # plt.plot(range(MAX_ITERATIONS), current_cost_history, color='lightblue', alpha=0.6, label='Tabu Search (Current Neighborhood Cost)')
    # plt.plot(range(MAX_ITERATIONS), best_cost_history, color='blue', linewidth=2, label='Tabu Search (Global Best Cost)')
    
    # # Formatting
    # plt.title('Objective Function Decrease: CI vs. Tabu Search', fontsize=14, fontweight='bold')
    # plt.xlabel('Optimization Iterations', fontsize=12)
    # plt.ylabel('Total Schedule Cost (Seconds)', fontsize=12)
    # plt.legend(loc='upper right')
    # plt.grid(True, linestyle=':', alpha=0.7)
    
    # # Save the plot
    # plt.tight_layout()
    # plt.savefig('docs/Optimisation_Convergence.png', dpi=300)
    # print("Saved convergence plot to 'Optimisation_Convergence.png'")
    
    # Formatting for Output (Add tugImos as strings)
    export_data = []
    for job in final_schedule:
        # Get the tug INDICES used in the best assignment
        tug_indices = best_assignment[job['jobId']]
        # Convert to Strings "1", "2" (Indices + 1)
        job['tugImos'] = [str(t+1) for t in tug_indices]
        job['assignedTugs'] = job['tugImos']
        export_data.append(job)

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(export_data, f, indent=4)
        
    print(f"Final Cost: {final_cost:.1f}s. Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    # If run from the batch script, override the default filenames
    if len(sys.argv) == 3:
        INPUT_FILE = sys.argv[1]
        OUTPUT_FILE = sys.argv[2]
        
    run_tabu_search(False)
