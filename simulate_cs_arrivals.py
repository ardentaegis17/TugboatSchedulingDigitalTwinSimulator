import pandas as pd
import numpy as np
import glob
import json
import random
import os
import re

# ================= CONFIGURATION =================
# Input Files
ARRIVAL_DATA_FILE = 'pasir_panjang_arrivals_lengthpred.csv'
LAMBDA_PARAMS_FILE = 'lambda_parameters.csv'
TRAJECTORY_FOLDER = 'standardised_trajectories'

# Batch Output Settings
OUTPUT_DIR = 'generated_schedules'
NUM_SCENARIOS = 31

# Simulation Settings
SIMULATION_HOURS = 24
BASE_SEED = 42  # Used as a starting point for the 31 runs

# CS Length Linear Regression Model Parameters
SLOPE = 334.97
INTERCEPT = 229.11

# =================================================

def get_tugs_required(length):
    if length >= 280:
        return 4
    elif length >= 61:
        return 2
    else:
        return 2 

def get_trajectory_map(folder):
    trajectory_groups = {}
    files = glob.glob(os.path.join(folder, "*.csv"))
    tug_count_pattern = re.compile(r"_WITH_(\d+)_TUGS")
    
    for f in files:
        filename = os.path.basename(f)
        match = tug_count_pattern.search(filename)
        
        if match:
            count = int(match.group(1))
            if count not in trajectory_groups:
                trajectory_groups[count] = []
            trajectory_groups[count].append(filename)
            
    return trajectory_groups

def generate_schedule(run_index, current_seed, trajectory_map, cs_pool, lambda_df):
    # Seed BOTH generators for perfect reproducibility
    np.random.seed(current_seed)
    random.seed(current_seed)
    
    schedule = []
    job_counter = 1
    
    for hour in range(SIMULATION_HOURS):
        hour_index = hour % 24
        rate = lambda_df.iloc[hour_index]['CS'] 
        
        num_arrivals = np.random.poisson(rate)
        
        for _ in range(num_arrivals):
            offset_seconds = np.random.uniform(0, 3600)
            arrival_time_abs = (hour * 3600) + offset_seconds
            
            vessel = cs_pool.sample(1).iloc[0] 
            v_len = float(vessel['length'])
            
            tugs_needed = get_tugs_required(v_len)
            
            if tugs_needed in trajectory_map and trajectory_map[tugs_needed]:
                selected_file = random.choice(trajectory_map[tugs_needed])
            else:
                fallback_count = random.choice(list(trajectory_map.keys()))
                selected_file = random.choice(trajectory_map[fallback_count])

            job = {
                "jobId": f"JOB_{job_counter:03d}",
                "vesselImo": str(vessel['imo']),
                "vesselType": "CS",
                "length": v_len,
                "grossTonnage": int(vessel['grossTonnage']),
                "eta": round(arrival_time_abs, 2),
                "tugsRequired": tugs_needed,
                "TrajectoryFile": selected_file
            }
            
            schedule.append(job)
            job_counter += 1

    schedule.sort(key=lambda x: x['eta'])
    
    # Export to the designated folder
    output_file = os.path.join(OUTPUT_DIR, f"scenario_{run_index}.json")
    with open(output_file, 'w') as f:
        json.dump(schedule, f, indent=2)
        
    print(f"Generated Scenario {run_index} ({len(schedule)} jobs) -> {output_file}")

def main():
    # 1. Setup Output Directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 2. Load Data ONCE to save processing time
    print("Loading base data for batch generation...")
    try:
        arrivals_df = pd.read_csv(ARRIVAL_DATA_FILE)
        lambda_df = pd.read_csv(LAMBDA_PARAMS_FILE)
        trajectory_map = get_trajectory_map(TRAJECTORY_FOLDER)
        
        if not trajectory_map:
            print("CRITICAL ERROR: No valid trajectory files found.")
            return
            
    except Exception as e:
        print(f"Error loading data: {e}")
        return

    # Filter and prepare the pool
    cs_pool = arrivals_df[arrivals_df['type'] == 'CS'].copy()
    if 'length' not in cs_pool.columns or cs_pool['length'].isnull().any():
        cs_pool['length'] = cs_pool.apply(
            lambda row: row['length'] if pd.notnull(row.get('length')) 
            else ((SLOPE * row['grossTonnage'] + INTERCEPT) ** (1/3)), axis=1
        )

    # 3. Generate all scenarios
    print(f"\n--- Starting Batch Generation ({NUM_SCENARIOS} scenarios) ---")
    for i in range(1, NUM_SCENARIOS + 1):
        # We shift the seed by 'i' so every scenario is unique but reproducible
        generate_schedule(
            run_index=i, 
            current_seed=BASE_SEED + i, 
            trajectory_map=trajectory_map, 
            cs_pool=cs_pool, 
            lambda_df=lambda_df
        )
        
    print("\n--- Batch Generation Complete! ---")

if __name__ == "__main__":
    main()