import pandas as pd
import numpy as np
import glob
import os
import zipfile

# ================= CONFIGURATION =================
# Input folders
CS_JOB_FOLDER = "containership_trajectories_may2023" # From previous step
TRAINING_ROOT = r"C:\Users\sg-t1aidan\Desktop\Vessel Data\202305" 
OUTPUT_FOLDER = "coupled_jobs_wide_may2023"

# Parameters
PROXIMITY_THRESHOLD_M = 200  # Distance to be considered "coupled"
DURATION_THRESHOLD_MIN = 15  # Minimum time required in proximity
# =================================================

def get_sorted_zip_files(root_folder):
    pattern = os.path.join(root_folder, "**", "*.zip")
    return sorted(glob.glob(pattern, recursive=True))

def extract_coupled_jobs_wide():
    # 1. LOAD CS JOBS METADATA
    print("Indexing Containership Jobs...")
    cs_files = glob.glob(os.path.join(CS_JOB_FOLDER, "*.csv"))
    
    active_jobs = []
    for f in cs_files:
        try:
            df = pd.read_csv(f)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            active_jobs.append({
                'id': os.path.basename(f).replace('.csv', ''),
                'df': df.sort_values('timestamp'),
                'start': df['timestamp'].min(),
                'end': df['timestamp'].max(),
                'tug_buffer': [] # List to store raw tug data chunks
            })
        except Exception as e:
            print(f"Skipping {f}: {e}")
            continue
            
    print(f"Loaded {len(active_jobs)} target jobs.")
    
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    # 2. STREAM RAW DATA (Accumulate Potential Tugs)
    zip_files = get_sorted_zip_files(TRAINING_ROOT)
    
    for zip_path in zip_files:
        print(f"Scanning Tugs in: {os.path.basename(zip_path)}...")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                with z.open(z.namelist()[0]) as f:
                    raw_df = pd.read_csv(f)
            
            raw_df.columns = raw_df.columns.str.strip().str.lower()
            raw_df['timestamp'] = pd.to_datetime(raw_df['timestamp'])
            
            # Filter for Tugs (TU) or Service Vessels (SV)
            if 'type' in raw_df.columns:
                tugs_df = raw_df[raw_df['type'].isin(["TU", "SV"])].copy()
            else:
                tugs_df = raw_df
            
            if tugs_df.empty: continue
            
            # Optimization: Only keep columns we need
            cols_to_keep = ['timestamp', 'imonumber', 'latitudedegrees', 'longitudedegrees', 'speedoverground', 'headingoverwater']
            # Ensure columns exist before selecting
            valid_cols = [c for c in cols_to_keep if c in tugs_df.columns]
            tugs_df = tugs_df[valid_cols]

            file_start = tugs_df['timestamp'].min()
            file_end = tugs_df['timestamp'].max()

            # Assign relevant tug data to jobs
            for job in active_jobs:
                # Buffer times to catch approach/departure
                search_start = job['start'] - pd.Timedelta(minutes=30)
                search_end = job['end'] + pd.Timedelta(minutes=30)

                # Check overlap
                if (search_end > file_start) and (search_start < file_end):
                    mask = (tugs_df['timestamp'] >= search_start) & (tugs_df['timestamp'] <= search_end)
                    relevant_slice = tugs_df[mask]
                    
                    if not relevant_slice.empty:
                        job['tug_buffer'].append(relevant_slice)

        except Exception as e:
            print(f"Error reading {zip_path}: {e}")

    # 3. PROCESS EACH JOB (Filter & Merge)
    print("\nProcessing coupled trajectories...")
    
    for job in active_jobs:
        if not job['tug_buffer']:
            continue
            
        # Combine all buffered tug chunks for this job
        all_tugs = pd.concat(job['tug_buffer'], ignore_index=True)
        all_tugs = all_tugs.drop_duplicates().sort_values('timestamp')
        
        # Base DataFrame is the Containership Trajectory
        final_df = job['df'].copy()
        final_df = final_df.sort_values('timestamp')
        
        tugs_found = 0
        
        # Iterate through each unique Tug found in the time window
        for tug_imo, tug_track in all_tugs.groupby('imonumber'):
            
            # A. Check Coupling Criteria
            # Merge tug track onto CS track to calc distance
            check_merge = pd.merge_asof(
                final_df[['timestamp', 'latitudedegrees', 'longitudedegrees']], # Use minimal CS data for check
                tug_track[['timestamp', 'latitudedegrees', 'longitudedegrees']],
                on='timestamp',
                direction='nearest',
                tolerance=pd.Timedelta('30s'),
                suffixes=('_cs', '_tug')
            )
            
            # Haversine Distance
            d_lat = np.radians(check_merge['latitudedegrees_tug'] - check_merge['latitudedegrees_cs'])
            d_lon = np.radians(check_merge['longitudedegrees_tug'] - check_merge['longitudedegrees_cs'])
            a = np.sin(d_lat/2)**2 + np.cos(np.radians(check_merge['latitudedegrees_cs'])) * \
                np.cos(np.radians(check_merge['latitudedegrees_tug'])) * np.sin(d_lon/2)**2
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
            check_merge['dist_m'] = 6371000 * c
            
            # Filter for proximity
            close_points = check_merge[check_merge['dist_m'] < PROXIMITY_THRESHOLD_M]
            
            if len(close_points) < 2:
                continue
                
            # Calculate Duration
            start_t = close_points['timestamp'].min()
            end_t = close_points['timestamp'].max()
            duration_mins = (end_t - start_t).total_seconds() / 60.0
            
            # B. If Valid, Merge into Final DataFrame
            if duration_mins >= DURATION_THRESHOLD_MIN:
                tugs_found += 1
                
                # Prepare tug columns with specific suffix
                tug_track_renamed = tug_track.copy()
                suffix = f"_{int(tug_imo)}"
                
                # Rename columns: e.g., latitudedegrees -> lat_tug_12345
                rename_map = {
                    'latitudedegrees': f'lat_tug{suffix}',
                    'longitudedegrees': f'lon_tug{suffix}',
                    'speedoverground': f'sog_tug{suffix}',
                    'headingoverwater': f'heading_tug{suffix}'
                }
                tug_track_renamed = tug_track_renamed.rename(columns=rename_map)
                
                # Merge onto the growing final_df
                # We use left join logic (merge_asof) to keep CS timeline intact
                final_df = pd.merge_asof(
                    final_df,
                    tug_track_renamed[['timestamp'] + list(rename_map.values())],
                    on='timestamp',
                    direction='nearest',
                    tolerance=pd.Timedelta('30s')
                )

        # 4. SAVE OUTPUT
        # Only save if we found tugs (or if you want to save CS regardless, remove the if)
        if tugs_found > 0:
            out_name = f"{OUTPUT_FOLDER}/{job['id']}_WITH_{tugs_found}_TUGS.csv"
            final_df.to_csv(out_name, index=False)
            # print(f"Saved {job['id']} with {tugs_found} tugs.")

if __name__ == "__main__":
    extract_coupled_jobs_wide()