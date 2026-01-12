import simpy
import random

# Configuration
SIMULATION_TIME = 72 * 60  # 72 hours in minutes
AVG_INTER_ARRIVAL = 120    # Average ship arrives every 2 hours
SEED = 42

class Vessel:
    def __init__(self, id, type, arrival_time):
        self.id = id
        self.type = type
        self.arrival_time = arrival_time
        if type == "Feeder":
            self.containers = random.randint(200, 500)
            self.length = 150 # meters
        elif type == "Panamax":
            self.containers = random.randint(1000, 2500)
            self.length = 290
        else: # Ultra Large
            self.containers = random.randint(5000, 8000)
            self.length = 400

def vessel_generator(env, arrival_list):
    """
    Generates ships according to a Poisson Process.
    """
    vessel_id = 0
    while True:
        # 1. Wait for the next ship (Exponential Distribution)
        # 1.0 / AVG_INTER_ARRIVAL is lambda
        inter_arrival = random.expovariate(1.0 / AVG_INTER_ARRIVAL)
        yield env.timeout(inter_arrival)

        # 2. Determine Ship Characteristics
        vessel_id += 1
        current_time = env.now
        
        # 20% Ultra Large, 30% Panamax, 50% Feeder
        rand_type = random.choices(
            ["Ultra Large", "Panamax", "Feeder"], 
            weights=[0.2, 0.3, 0.5]
        )[0]

        # 3. Create Vessel
        new_vessel = Vessel(vessel_id, rand_type, current_time)
        arrival_list.append(new_vessel)
        
        print(f"[{env.now:.1f}] Arrived: Ship {vessel_id} ({rand_type}) - Load: {new_vessel.containers} TEU")

# --- Running the Simulation ---
env = simpy.Environment()
traffic_log = []
env.process(vessel_generator(env, traffic_log))
env.run(until=SIMULATION_TIME)

# Output: traffic_log contains your schedule for the next 3 days.

