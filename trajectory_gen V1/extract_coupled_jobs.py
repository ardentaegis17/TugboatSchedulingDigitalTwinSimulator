import pandas as pd
import numpy as np
import glob
import os
import zipfile

# ================= CONFIGURATION =================
CS_JOB_FOLDER = "containership_trajectories_jun2023" # Result of obtain_containership_trajectories
TRAINING_ROOT = r"C:\Users\sg-t1aidan\Desktop\Vessel Data\202306"   #Raw Data Zips
OUTPUT_FOLDER = "coupled_jobs"

PROXIMITY_THRESHOLD_M = 200
MIN_COUPLING_PCT = 0.6
SKIP = 0
UNBERTH_ONLY = True
# =================================================

def get_sorted_zip_files(root_folder):
    pattern = os.path.join(root_folder, "**", "*.zip")
    return sorted(glob.glob(pattern, recursive=True))

def extract_coupled_jobs_mass():
    # 1. LOAD CS JOBS METADATA
    # We index all jobs by time so we know what to look for
    count = 0
    print("Indexing Containership Jobs...")
    cs_files = glob.glob(os.path.join(CS_JOB_FOLDER, "*.csv"))
    active_jobs = []

    for f in cs_files:
        try:
            # We only read the first/last row to be fast
            # (Requires pandas 1.1+) or just read specific cols
            df = pd.read_csv(f)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            active_jobs.append({
                'id': os.path.basename(f),
                'df': df, # Keep small extracted DF in memory
                'start': df['timestamp'].min(),
                'end': df['timestamp'].max()
            })
        except:
            continue
            
    print(f"Loaded {len(active_jobs)} target jobs.")
    
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    # 2. STREAM RAW DATA (Scan for Tugs)
    zip_files = get_sorted_zip_files(TRAINING_ROOT)
    
    for zip_path in zip_files:

        if count < SKIP:
            print(f"Skipping {os.path.basename(zip_path)}...")
            count += 1
            continue

        print(f"Scanning Tugs in: {os.path.basename(zip_path)}...")
        
        try:

            # Read CSV from Zip
            with zipfile.ZipFile(zip_path, 'r') as z:
                with z.open(z.namelist()[0]) as f:
                    # OPTIMIZATION: Read chunks or filter while reading if possible
                    # For now, read all, then drop non-tugs immediately
                    raw_df = pd.read_csv(f)
            
            # Standardize
            raw_df.columns = raw_df.columns.str.strip().str.lower()
            raw_df['timestamp'] = pd.to_datetime(raw_df['timestamp'])
            
            # 3. FILTER FOR TUGS ONLY (Critical for Memory)

            if 'type' in raw_df.columns:
                tugs_df = raw_df[raw_df['type'].isin(["TU","SV"])].copy()
            else:
                # Fallback: keep everything (slower)
                tugs_df = raw_df
            
            if tugs_df.empty: continue
            
            # Sort for merge_asof
            tugs_df = tugs_df.sort_values('timestamp')

            # Time range of this raw file
            file_start = raw_df['timestamp'].min()
            file_end = raw_df['timestamp'].max()

            # 4. CHECK JOBS AGAINST THIS DAY
            for job in active_jobs:
                # Does this job overlap with this day?
                # Logic: Job ends AFTER file starts AND Job starts BEFORE file ends

                if job['id'][:2] == "Be" and UNBERTH_ONLY == True:
                    continue

                if (job['end'] > file_start) and (job['start'] < file_end):
                    
                    # Extract Tugs relevant to this specific job
                    # (Add 1 min buffer)
                    mask = (tugs_df['timestamp'] >= job['start'] - pd.Timedelta('1min')) & \
                           (tugs_df['timestamp'] <= job['end'] + pd.Timedelta('1min'))
                    relevant_tugs = tugs_df[mask]
                    
                    if relevant_tugs.empty: continue
                    
                    # 5. PERFORM COUPLING (Per Tug)
                    for tug_imo, tug_track in relevant_tugs.groupby('imonumber'):
                        # Align data
                        merged = pd.merge_asof(
                            job['df'].sort_values('timestamp'),
                            tug_track.sort_values('timestamp'),
                            on='timestamp',
                            direction='nearest',
                            tolerance=pd.Timedelta('30s'),
                            suffixes=('_cs', '_tug')
                        )
                        
                        merged = merged.dropna(subset=['latitudedegrees_tug'])
                        if merged.empty: continue
                        
                        # Distance Calc
                        # Haversine approx
                        d_lat = np.radians(merged['latitudedegrees_tug'] - merged['latitudedegrees_cs'])
                        d_lon = np.radians(merged['longitudedegrees_tug'] - merged['longitudedegrees_cs'])
                        lat1 = np.radians(merged['latitudedegrees_cs'])
                        lat2 = np.radians(merged['latitudedegrees_tug'])
                        
                        a = np.sin(d_lat/2)**2 + np.cos(lat1)*np.cos(lat2) * np.sin(d_lon/2)**2
                        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
                        merged['dist_m'] = 6371000 * c
                        
                        # Check Ratio
                        close_points = merged[merged['dist_m'] < PROXIMITY_THRESHOLD_M]
                        match_ratio = len(close_points) / len(job['df'])

                        is_valid_coupling = False
                        
                        if match_ratio >= MIN_COUPLING_PCT:
                            is_valid_coupling = True

                        elif "Unberthing" in job['id']:
                            start_t = close_points['timestamp'].min()
                            end_t = close_points['timestamp'].max()
                            duration_mins = (end_t - start_t).total_seconds() / 60.0
                            if duration_mins >= 12:
                                is_valid_coupling = True
                        
                        if is_valid_coupling:
                            # SAVE MATCH
                            # Naming: JobID_TugIMO.csv
                            base_name = job['id'].replace('.csv', '')
                            out_name = f"{OUTPUT_FOLDER}/{base_name}_TUG-{tug_imo}.csv"
                            
                            # Avoid overwriting or duplicates
                            if not os.path.exists(out_name):
                                close_points.to_csv(out_name, index=False)
                                # print(f"  Match found: {base_name} <-> Tug {tug_imo}")

        except Exception as e:
            print(f"Error reading {zip_path}: {e}")

if __name__ == "__main__":
    extract_coupled_jobs_mass()