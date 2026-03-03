import pandas as pd
import json
import os

# 1. Load the Experiment Results from Unity
df = pd.read_csv('results/Final_Experiment_Results.csv')

# 2. Function to count vessels in JSON files
def get_vessel_count(scenario_id, strategy):
    prefix = ""
    if strategy == "CheapInsertion": prefix = "ci_"
    elif strategy == "TabuSearch": prefix = "tabu_"
    
    file_name = f"{prefix}scenario_{scenario_id}.json"
    file_path = os.path.join("generated_schedules", file_name)
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            # Support both list and dictionary formats
            jobs = data['jobs'] if isinstance(data, dict) else data
            return len(jobs)
    except FileNotFoundError:
        return 0

# 3. Apply vessel counting
df['VesselCount'] = df.apply(lambda r: get_vessel_count(r['ScenarioID'], r['Strategy']), axis=1)

# 4. Calculate Mean Wait Time Per Vessel (Hours)
# (Total Seconds / Vessel Count) / 3600
df['AvgWait_Hrs'] = (df['WaitTime'] / df['VesselCount']) / 3600

# 5. Generate Final Thesis Table
final_table = df.groupby('Strategy').agg({
    'VesselCount': 'mean',
    'AvgWait_Hrs': ['mean', 'std'],
    'SafetyScore': 'mean',
    'NearMisses': 'mean'
}).round(2)

print("--- THESIS RESULTS TABLE ---")
print(final_table)

# 6. Save for plotting
df.to_csv('Vessel_Normalized_Results.csv', index=False)