import simpy
import random
import json
import copy
import math

# --- CONFIGURATION ---
SIMULATION_DAYS = 2
SIM_DURATION_MINS = SIMULATION_DAYS * 24 * 60
AVG_INTER_ARRIVAL = 100 
N_TUGS = 4
TABU_ITERATIONS = 50 # Lower for speed during simulation
RANDOM_SEED = 42

random.seed(RANDOM_SEED)

# --- DATA CLASSES ---

class Vessel:
    def __init__(self, id, arrival_tick):
        self.id = id
        self.arrival_tick = arrival_tick
        self.type = random.choices(["ULCV", "Panamax", "Feeder"], weights=[0.2, 0.3, 0.5])[0]
        
        # Rule-Based Requirements
        if self.type == "Feeder":
            self.length = 120
            self.req_tugs = 1
            self.service_duration = 45
        elif self.type == "Panamax":
            self.length = 250
            self.req_tugs = 2
            self.service_duration = 75
        else: # ULCV
            self.length = 400
            self.req_tugs = 3 # For this demo, let's cap at 3 to avoid bottlenecking 4 tugs
            self.service_duration = 120

class Job:
    def __init__(self, id, vessel, start_loc, end_loc):
        self.id = id
        self.vessel = vessel
        self.status = "PENDING" # PENDING, ASSIGNED, COMPLETED
        
        # Assignment Details (Filled by Tabu Search)
        self.assigned_tugs = [] # List of Tug IDs
        self.scheduled_start_time = -1
        
        # Location logic
        self.start_loc = start_loc
        self.end_loc = end_loc

    def to_dict(self):
        return {
            "job_id": self.id,
            "vessel_id": self.vessel.id,
            "arrival_tick": self.vessel.arrival_tick,
            "required_tugs": self.vessel.req_tugs,
            "assigned_tugs": self.assigned_tugs,
            "scheduled_start_time": self.scheduled_start_time,
            "duration": self.vessel.service_duration,
            "start_node": self.start_loc,
            "end_node": self.end_loc
        }

class Tug:
    def __init__(self, id):
        self.id = id
        self.next_free_time = 0 # The time when this tug finishes its current job
        self.loc = "Base"

# --- THE OPTIMIZERS ---

class GreedyScheduler:
    def __init__(self):
        pass

    def solve(self, jobs, tugs, current_time):
        """
        Assigns 'jobs' (list) to 'tugs' (list) respecting required_tugs count.
        Returns a dict: { job_object: [tug_id, tug_id] }
        """
        # 1. Filter capable tugs (Simplified: All tugs are same class)
        available_tugs = sorted(tugs, key=lambda t: t.next_free_time)
        
        # 2. Phase I: Greedy Construction (Earliest Available Tugs)
        # We sort jobs by arrival time (FIFO)
        sorted_jobs = sorted(jobs, key=lambda j: j.vessel.arrival_tick)
        
        schedule = {} # job -> [tug_ids]
        
        # Clone tug states so we don't mess up the simulation yet
        temp_tug_state = {t.id: t.next_free_time for t in tugs}
        
        for job in sorted_jobs:
            needed = job.vessel.req_tugs
            
            # Find the 'needed' tugs that become free earliest
            # Sort tugs by their temp_free_time
            best_tugs = sorted(temp_tug_state.keys(), key=lambda tid: temp_tug_state[tid])[:needed]
            
            if len(best_tugs) < needed:
                # Not enough tugs exist in the fleet! Skip.
                continue
                
            schedule[job] = best_tugs
            
            # Update their virtual free time
            # Start Time = max(Current Time, Job Arrival, Max(Tug Free Times))
            tug_availability = max([temp_tug_state[tid] for tid in best_tugs])
            start_time = max(current_time, job.vessel.arrival_tick, tug_availability)
            finish_time = start_time + job.vessel.service_duration
            
            # Mark these tugs as busy until finish_time
            for tid in best_tugs:
                temp_tug_state[tid] = finish_time
                
        
        return schedule
    

class TabuScheduler:
    def __init__(self, tabu_tenure=5, max_iterations=50):
        self.tabu_tenure = tabu_tenure
        self.max_iterations = max_iterations

    def calculate_cost(self, schedule_map, jobs, tugs, current_time):
        """
        Calculates Total Latency of a specific schedule configuration.
        schedule_map: { job_id: [tug_id_1, tug_id_2] }
        """
        total_latency = 0
        
        # We need a temporary state of when tugs become free
        # Initialize with their CURRENT state from the simulation
        tug_free_times = {t.id: t.next_free_time for t in tugs}
        
        # We must process jobs in time order to calculate cascading delays
        sorted_jobs = sorted(jobs, key=lambda j: j.vessel.arrival_tick)
        
        for job in sorted_jobs:
            assigned_ids = schedule_map.get(job.id, [])
            if not assigned_ids:
                return float('inf') # Invalid solution
                
            # When do these specific tugs become free?
            ready_times = [tug_free_times[tid] for tid in assigned_ids]
            resources_ready_at = max(ready_times)
            
            # Start time logic
            actual_start = max(current_time, job.vessel.arrival_tick, resources_ready_at)
            
            # Latency Cost
            total_latency += (actual_start - job.vessel.arrival_tick)
            
            # Update virtual tug state
            finish_time = actual_start + job.vessel.service_duration
            for tid in assigned_ids:
                tug_free_times[tid] = finish_time
                
        return total_latency

    def get_initial_solution(self, jobs, tugs, current_time):
        """Phase 1: Greedy Heuristic (Earliest Finish Time)"""
        schedule = {}
        # Simple Logic: Just take the first N available tugs for the job
        # (This gives us a valid, but likely suboptimal, starting point)
        
        # Sort tugs by who is free soonest
        sorted_tugs = sorted(tugs, key=lambda t: t.next_free_time)
        
        tug_pool_indices = {i: 0 for i in range(len(jobs))} # distinct pool pointers? No, simplify.
        
        # Very crude allocation to ensure validity
        # In a real constraint solver, this part is harder.
        # Here we just round-robin assign to ensure we satisfy 'req_tugs'
        all_tug_ids = [t.id for t in tugs]
        
        for i, job in enumerate(jobs):
            req = job.vessel.req_tugs
            # Just take the first 'req' tugs from the list, shifted by job index to spread load
            # This ensures validity (tugs exist) but ignores optimality (latency)
            # The Tabu Search will fix the optimality.
            indices = [(k % len(all_tug_ids)) for k in range(i, i + req)]
            schedule[job.id] = [all_tug_ids[k] for k in indices]
            
        return schedule

    def solve(self, jobs, tugs, current_time):
        """Phase 2: The Tabu Search Loop"""
        
        # 1. Generate Valid Initial Solution
        current_schedule = self.get_initial_solution(jobs, tugs, current_time)
        current_cost = self.calculate_cost(current_schedule, jobs, tugs, current_time)
        
        best_schedule = copy.deepcopy(current_schedule)
        best_cost = current_cost
        
        # Tabu List: Stores signature of move -> expiration_iteration
        # Signature: (job_id, tug_id_added)
        tabu_list = {}
        
        print(f"   [Tabu] Initial Cost: {best_cost} mins")

        # 2. Optimization Loop
        for iteration in range(self.max_iterations):
            best_neighbor = None
            best_neighbor_cost = float('inf')
            move_signature = None
            
            # --- Generate Neighborhood (Swaps) ---
            # For every job, try swapping one of its assigned tugs with an unassigned one
            
            all_tug_ids = [t.id for t in tugs]
            
            for job in jobs:
                current_assigned = current_schedule[job.id]
                # Tugs NOT currently working on this job
                available_swaps = [tid for tid in all_tug_ids if tid not in current_assigned]
                
                for tug_out in current_assigned:
                    for tug_in in available_swaps:
                        
                        # Create Candidate Schedule
                        candidate = copy.deepcopy(current_schedule)
                        candidate[job.id].remove(tug_out)
                        candidate[job.id].append(tug_in)
                        
                        # Calculate Cost
                        cost = self.calculate_cost(candidate, jobs, tugs, current_time)
                        
                        # Check Tabu Status
                        is_tabu = False
                        # If we recently added 'tug_in' to 'job', maybe we shouldn't remove it yet?
                        # Or strictly: (job_id, tug_in) is Tabu
                        if (job.id, tug_in) in tabu_list:
                            if tabu_list[(job.id, tug_in)] > iteration:
                                is_tabu = True
                        
                        # Aspiration Criteria: Ignore Tabu if it beats global best
                        if is_tabu and cost >= best_cost:
                            continue
                            
                        # Keep the best neighbor found in this iteration
                        if cost < best_neighbor_cost:
                            best_neighbor = candidate
                            best_neighbor_cost = cost
                            move_signature = (job.id, tug_out) # We mark 'tug_out' as Tabu to add back
            
            # --- Update Current State ---
            if best_neighbor:
                current_schedule = best_neighbor
                current_cost = best_neighbor_cost
                
                # Update Global Best
                if current_cost < best_cost:
                    best_schedule = copy.deepcopy(current_schedule)
                    best_cost = current_cost
                    # print(f"      Iter {iteration}: New Best Cost {best_cost}")
                
                # Add to Tabu List
                # Forbid adding 'tug_out' back to this job for N turns
                tabu_list[move_signature] = iteration + self.tabu_tenure

        print(f"   [Tabu] Final Cost: {best_cost} mins (Improved by {best_cost - self.calculate_cost(self.get_initial_solution(jobs, tugs, current_time), jobs, tugs, current_time)})")
        
        return best_schedule

# --- THE SIMULATION ENGINE ---

class PortSimulation:
    def __init__(self):
        self.env = simpy.Environment()
        self.tugs = [Tug(i+1) for i in range(N_TUGS)]
        self.scheduler = TabuScheduler()
        
        self.pending_queue = []
        self.completed_jobs = [] # This goes to JSON
        
    def traffic_generator(self):
        vessel_id = 0
        while True:
            yield self.env.timeout(random.expovariate(1.0 / AVG_INTER_ARRIVAL))
            vessel_id += 1
            
            # Create Vessel & Job
            vessel = Vessel(vessel_id, int(self.env.now))
            # Direction Logic
            if random.random() > 0.5:
                job = Job(f"JOB_{vessel_id}_IN", vessel, "Anchorage", f"Berth_{random.randint(1,5)}")
            else:
                job = Job(f"JOB_{vessel_id}_OUT", vessel, f"Berth_{random.randint(1,5)}", "Sea")
            
            self.pending_queue.append(job)
            print(f"[{self.env.now:.0f}] New Job: {job.id} (Needs {vessel.req_tugs} tugs)")
            
            # Trigger Scheduling immediately
            self.run_scheduler()

    def run_scheduler(self):
            """
            The Rolling Horizon Trigger.
            Checks if we can schedule any pending jobs with current tugs.
            """
            if not self.pending_queue:
                return

            current_time = int(self.env.now)
            
            # 1. Solve
            # 'assignments' is a dict: { "JOB_ID_STRING": [TugID, TugID], ... }
            assignments = self.scheduler.solve(self.pending_queue, self.tugs, current_time)
            
            # 2. Create a lookup map to find the actual Job Object using the ID string
            # This is the missing link that caused your error
            job_lookup = {j.id: j for j in self.pending_queue}

            # 3. Apply Assignments
            # We iterate over the assignments returned by Tabu Search
            for job_id, assigned_tug_ids in assignments.items():
                
                # Retrieve the actual Job Object from our lookup map
                if job_id not in job_lookup:
                    continue 
                job = job_lookup[job_id] 

                # Calculate start time
                relevant_tugs = [t for t in self.tugs if t.id in assigned_tug_ids]
                
                # Safety check: if for some reason tugs aren't found
                if not relevant_tugs: 
                    continue

                tug_availabilities = [t.next_free_time for t in relevant_tugs]
                
                # Determine when the job can actually start
                start_time = max(current_time, job.vessel.arrival_tick, max(tug_availabilities))
                finish_time = start_time + job.vessel.service_duration
                
                # Update JOB Status
                job.status = "ASSIGNED"
                job.assigned_tugs = assigned_tug_ids
                job.scheduled_start_time = start_time
                
                # Update TUG Status (Reserve them)
                for tug in relevant_tugs:
                    tug.next_free_time = finish_time
                    tug.loc = job.end_loc # Teleport location for now
                
                # Move from Pending to Completed (Planned)
                self.completed_jobs.append(job)
                
                # Remove from pending queue so we don't schedule it again
                if job in self.pending_queue:
                    self.pending_queue.remove(job)
                
                print(f"   -> Scheduled {job.id}: Start {start_time} | Tugs {assigned_tug_ids}")

    def run(self):
        self.env.process(self.traffic_generator())
        self.env.run(until=SIM_DURATION_MINS)

# --- EXECUTION ---

if __name__ == "__main__":
    print(f"--- Running Integrated Engine ({N_TUGS} Tugs) ---")
    sim = PortSimulation()
    sim.run()
    
    # Export
    output_data = {
        "meta": {"total_jobs": len(sim.completed_jobs)},
        "schedule": [j.to_dict() for j in sim.completed_jobs]
    }
    
    with open("integrated_schedule.json", "w") as f:
        json.dump(output_data, f, indent=4)
    print("\nSchedule saved to 'integrated_schedule.json'")