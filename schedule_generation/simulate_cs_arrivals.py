import pandas as pd
import numpy as np
import glob
import json
import random
import os
import re

# ================= CONFIGURATION =================
# Input Files
ARRIVAL_DATA_FILE = 'data_preparation/pasir_panjang_arrivals.csv'
LAMBDA_PARAMS_FILE = 'data_preparation/lambda_parameters.csv'
TRAJECTORY_FOLDER = 'trajectories/standardised_trajectories'

# Batch Output Settings
OUTPUT_DIR = 'generated_schedules'
NUM_SCENARIOS = 5

# Simulation Settings
SIMULATION_HOURS = 24
BASE_SEED = 42  # Used as a starting point for the runs

# CS Length Linear Regression Model Parameters
SLOPE = 334.97
INTERCEPT = 229.11

# =================================================

def get_tugs_required(length):
    if length >= 280:
        return 4
    return 2 

def get_trajectory_map(folder):
    """
    Creates a nested dictionary: map[tug_count][berth_id] = {'inbound': [...], 'outbound': [...]}
    Ensures that we only use berths that have BOTH an inbound and an outbound trajectory.
    """
    trajectory_groups = {}
    files = glob.glob(os.path.join(folder, "*.csv"))
    
    # Regex to extract info from filenames
    berth_pattern = re.compile(r"(?i)Berthing_PPT Berth[_ -]?([a-zA-Z0-9]+)")
    outbound_pattern = re.compile(r"(?i)Unberthing") 
    
    for f in files:
        filename = os.path.basename(f)
        berth_match = berth_pattern.search(filename)
        
        if berth_match:
            berth_id = berth_match.group(1).upper()
            is_outbound = bool(outbound_pattern.search(filename))
            
            if berth_id not in trajectory_groups:
                trajectory_groups[berth_id] = {'inbound': [], 'outbound': []}
            
            if is_outbound:
                trajectory_groups[berth_id]['outbound'].append(filename)
            else:
                trajectory_groups[berth_id]['inbound'].append(filename)
                
    valid_berths = {
        b_id: paths 
        for b_id, paths in trajectory_groups.items() 
        if paths['inbound'] and paths['outbound']
    }
            
    return valid_berths

def generate_schedule(run_index, current_seed, trajectory_map, cs_pool, lambda_df):
    np.random.seed(current_seed)
    random.seed(current_seed)
    
    schedule = []
    job_counter = 1
    
    for hour in range(SIMULATION_HOURS):
        hour_index = hour % 24
        rate = lambda_df.iloc[hour_index]['CS'] 
        num_arrivals = np.random.poisson(rate)
        
        for _ in range(num_arrivals):
            offset_seconds = np.random.uniform(3600 * 4, 3600 * 12)
            arrival_time_abs = (hour * 3600) + offset_seconds
            
            vessel = cs_pool.sample(1).iloc[0] 
            v_len = float(vessel['length'])
            tugs_needed = get_tugs_required(v_len)
            
            berth_id = random.choice(list(trajectory_map.keys()))

                
            selected_file_in = random.choice(trajectory_map[berth_id]['inbound'])
            selected_file_out = random.choice(trajectory_map[berth_id]['outbound'])

            vessel_id_str = f"VESSEL_{job_counter:03d}"

            # --- INBOUND JOB ---
            job_in = {
                "jobId": f"{vessel_id_str}_IN",
                "isOutbound": False,
                "vesselImo": str(vessel['imo']),
                "vesselType": "CS",
                "length": v_len,
                "grossTonnage": int(vessel['grossTonnage']),
                "eta": round(arrival_time_abs, 2),
                "tugsRequired": tugs_needed,
                "TrajectoryFile": selected_file_in
            }
            
            # --- OUTBOUND JOB ---
            berth_duration = random.uniform(12 * 3600, 24 * 3600)
            outbound_eta = arrival_time_abs + berth_duration
            
            job_out = {
                "jobId": f"{vessel_id_str}_OUT",
                "isOutbound": True,
                "vesselImo": str(vessel['imo']),
                "vesselType": "CS",
                "length": v_len,
                "grossTonnage": int(vessel['grossTonnage']),
                "eta": round(outbound_eta, 2),
                "tugsRequired": tugs_needed,
                "TrajectoryFile": selected_file_out
            }
            
            schedule.append(job_in)
            schedule.append(job_out)
            job_counter += 1

    schedule.sort(key=lambda x: x['eta'])
    output_file = os.path.join(OUTPUT_DIR, f"scenario_{run_index}.json")
    with open(output_file, 'w') as f:
        json.dump(schedule, f, indent=2)

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    arrivals_df = pd.read_csv(ARRIVAL_DATA_FILE)
    lambda_df = pd.read_csv(LAMBDA_PARAMS_FILE)
    trajectory_map = get_trajectory_map(TRAJECTORY_FOLDER)
    
    cs_pool = arrivals_df[arrivals_df['type'] == 'CS'].copy()
    if 'length' not in cs_pool.columns or cs_pool['length'].isnull().any():
        cs_pool['length'] = cs_pool.apply(
            lambda row: row['length'] if pd.notnull(row.get('length')) 
            else ((SLOPE * row['grossTonnage'] + INTERCEPT) ** (1/3)), axis=1
        )

    for i in range(1, NUM_SCENARIOS + 1):
        generate_schedule(i, BASE_SEED + i, trajectory_map, cs_pool, lambda_df)

if __name__ == "__main__":
    main()