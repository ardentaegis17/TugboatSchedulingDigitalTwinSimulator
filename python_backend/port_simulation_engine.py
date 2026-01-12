import simpy
import random
import json
import pandas as pd

# --- CONFIGURATION ---
SIMULATION_DAYS = 3
SIM_DURATION_MINS = SIMULATION_DAYS * 24 * 60
AVG_INTER_ARRIVAL = 120  # Average ship every 2 hours (Poisson lambda)
RANDOM_SEED = 42

# Set seed for reproducibility
random.seed(RANDOM_SEED)

# --- CLASSES ---

class Vessel:
    """Represents the raw physical ship arriving at the port."""
    def __init__(self, id, arrival_time):
        self.id = id
        self.arrival_time = arrival_time
        
        # Stochastic Generation of Vessel Properties
        # Probabilities: 20% ULCV, 30% Panamax, 50% Feeder
        self.type = random.choices(
            ["Ultra Large", "Panamax", "Feeder"], 
            weights=[0.2, 0.3, 0.5]
        )[0]
        
        # Assign physical dimensions based on type (with some noise)
        if self.type == "Feeder":
            self.length = random.randint(100, 150)
            self.gross_tonnage = random.randint(5000, 15000)
        elif self.type == "Panamax":
            self.length = random.randint(200, 290)
            self.gross_tonnage = random.randint(40000, 60000)
        else: # Ultra Large
            self.length = random.randint(350, 400)
            self.gross_tonnage = random.randint(150000, 200000)

    def to_dict(self):
        return {
            "vessel_id": self.id,
            "type": self.type,
            "length_m": self.length,
            "arrival_tick": self.arrival_time
        }

class TowingJob:
    """Represents the derived demand passed to the Tug Scheduler."""
    def __init__(self, job_id, vessel_id, arrival_tick,required_tugs, duration, start_loc, end_loc):
        self.job_id = job_id
        self.vessel_id = vessel_id
        self.arrival_tick = arrival_tick
        self.required_tugs = required_tugs
        self.duration_mins = duration
        self.start_loc = start_loc
        self.end_loc = end_loc

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "vessel_ref": self.vessel_id,
            "arrival_tick": self.arrival_tick,
            "required_tugs": self.required_tugs,
            "est_duration": self.duration_mins,
            "start_node": self.start_loc,
            "end_node": self.end_loc
        }

# --- LOGIC ENGINE (Synthesis Layer) ---

def synthesize_tug_demand(vessel):
    """
    The Rule Engine: Converts a Vessel object into a Towing Job.
    Mimics port regulations based on vessel size.
    """
    
    # 1. Determine Tug Count (Power Requirement)
    if vessel.length < 160:
        n_tugs = 1
        base_time = 45
    elif vessel.length < 300:
        n_tugs = 2
        base_time = 75
    else:
        n_tugs = 4
        base_time = 120 # ULCVs are slow to maneuver

    # 2. Determine Mission Profile (Spatial Logic)
    # Randomize direction for simulation variety
    direction = random.choice(["Inbound", "Outbound"])
    
    if direction == "Inbound":
        s_loc = "Anchorage_North"
        e_loc = f"Berth_{random.randint(1, 8)}" # Assign random berth 1-8
    else:
        s_loc = f"Berth_{random.randint(1, 8)}"
        e_loc = "Open_Sea"

    # 3. Add Uncertainty (Stochasticity)
    # The paper mentions 'uncertain operation time'. We add noise.
    # Normal distribution: Mean=base_time, StdDev=15 mins
    actual_duration = int(random.normalvariate(base_time, 15))
    actual_duration = max(30, actual_duration) # Clip minimum time

    job_id = f"JOB_{vessel.id}_{direction[0]}" # e.g., JOB_101_I

    return TowingJob(job_id, vessel.id, vessel.arrival_time, n_tugs, actual_duration, s_loc, e_loc)

# --- SIMULATION LOOP (Traffic Layer) ---

class PortSimulation:
    def __init__(self):
        self.env = simpy.Environment()
        self.vessel_counter = 0
        self.generated_jobs = [] # This is the "Dataset" we send to Unity
        
    def vessel_generator(self):
        """Generates ships using a Poisson Process."""
        while True:
            # 1. Time to next arrival (Exponential Distribution)
            # lambda = 1 / AVG_INTER_ARRIVAL
            inter_arrival = random.expovariate(1.0 / AVG_INTER_ARRIVAL)
            
            # Wait for that time
            yield self.env.timeout(inter_arrival)

            # 2. Ship Arrives
            self.vessel_counter += 1
            current_time = int(self.env.now)
            
            new_vessel = Vessel(self.vessel_counter, current_time)
            
            # 3. SYNTHESIS: Convert Ship -> Job immediately
            new_job = synthesize_tug_demand(new_vessel)
            
            # 4. Log it
            self.generated_jobs.append({
                "vessel": new_vessel.to_dict(),
                "job": new_job.to_dict()
            })
            
            print(f"[{current_time:04d} min] Arrived: {new_vessel.type} (Len: {new_vessel.length}m) -> Needs {new_job.required_tugs} Tugs for {new_job.duration_mins}m")

    def run(self):
        print(f"--- Starting Simulation for {SIMULATION_DAYS} Days ---")
        self.env.process(self.vessel_generator())
        self.env.run(until=SIM_DURATION_MINS)
        print("--- Simulation Complete ---")

# --- EXECUTION & EXPORT ---

if __name__ == "__main__":
    # 1. Run the Integrated Simulation
    sim = PortSimulation()
    sim.run()
    
    # 2. Export Data for Unity
    # We flatten the structure to make it easy for C# to read
    unity_data = {
        "simulation_meta": {
            "duration_mins": SIM_DURATION_MINS,
            "total_jobs": len(sim.generated_jobs)
        },
        "mission_log": [entry['job'] for entry in sim.generated_jobs] # Only send the JOBS to Unity
    }
    
    filename = "unity_tug_missions.json"
    with open(filename, 'w') as f:
        json.dump(unity_data, f, indent=4)
        
    print(f"\nSuccess! Generated {len(sim.generated_jobs)} missions.")
    print(f"Data saved to: {filename} (Import this into Unity)")
    
    # Optional: Preview in Pandas for the User
    df = pd.DataFrame([j['job'] for j in sim.generated_jobs])
    print("\nData Preview:")
    print(df.head())