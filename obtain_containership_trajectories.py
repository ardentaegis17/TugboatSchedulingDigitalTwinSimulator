import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import os
import glob
import zipfile

# ================= CONFIGURATION =================
TRAINING_ROOT = r"C:\Users\sg-t1aidan\Desktop\Vessel Data\202305" 
BERTHS_GEOJSON = "Pasir Panjang Terminal/PPT_berths.geojson"
OUTPUT_DIR = "containership_trajectories"

WINDOW_MINUTES = 90
MAX_DIST_DEG = 0.15 
EVENT_COOLDOWN_MINUTES = 120 # Ignore duplicates within 2 hours of a saved event
# =================================================

def get_sorted_zip_files(root_folder):
    pattern = os.path.join(root_folder, "**", "*.zip")
    return sorted(glob.glob(pattern, recursive=True))

def extract_trajectories_mass():
    berths_gdf = gpd.read_file(BERTHS_GEOJSON)
    zip_files = get_sorted_zip_files(TRAINING_ROOT)
    
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    buffer_df = pd.DataFrame() 
    processed_count = 0
    
    # --- DEDUPLICATION TRACKER ---
    # Dictionary to store the last time we saved an event for a ship
    # Key: (IMO, EventType) -> Value: Timestamp of saved event
    last_saved = {} 

    print(f"Found {len(zip_files)} daily zip files. Processing...")

    for file_path in zip_files:
        print(f"Processing: {os.path.basename(file_path)}...")
        
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                with z.open(z.namelist()[0]) as f:
                    current_df = pd.read_csv(f)
            
            # Standardize
            current_df = current_df[current_df["type"] == "CS"]
            current_df.columns = current_df.columns.str.strip().str.lower()
            current_df['timestamp'] = pd.to_datetime(current_df['timestamp'])
            
            if 'imonumber' in current_df.columns:
                current_df = current_df.dropna(subset=['imonumber'])
                current_df = current_df[current_df['imonumber'] != 0]

            # Merge Buffer
            if not buffer_df.empty:
                full_day_df = pd.concat([buffer_df, current_df], ignore_index=True)
            else:
                full_day_df = current_df

            full_day_df = full_day_df.sort_values(['imonumber', 'timestamp'])
            full_day_df['is_stopped'] = full_day_df['speedoverground'] < 0.5

            # Group by Ship
            for imo, group in full_day_df.groupby('imonumber'):
                group = group.reset_index(drop=True)
                
                # --- DETECT EVENTS ---
                # Berthing: Moving -> Stopped
                berth_mask = (~group['is_stopped'].shift(1).fillna(False)) & (group['is_stopped'])
                # Unberthing: Stopped -> Moving
                unberth_mask = (group['is_stopped'].shift(1).fillna(False)) & (~group['is_stopped'])
                
                berth_indices = group.index[berth_mask]
                unberth_indices = group.index[unberth_mask]

                # --- PROCESS BERTHING ---
                for idx in berth_indices:
                    event_time = group.loc[idx, 'timestamp']
                    
                    # 1. SKIP OLD BUFFER EVENTS
                    if event_time < current_df['timestamp'].min(): continue

                    # 2. CHECK COOLDOWN
                    last_time = last_saved.get((imo, 'Berthing'))
                    if last_time and (event_time - last_time).total_seconds() < (EVENT_COOLDOWN_MINUTES * 60):
                        continue # Skip this duplicate/noise event

                    # 3. SPATIAL CHECK
                    pt = Point(group.loc[idx, 'longitudedegrees'], group.loc[idx, 'latitudedegrees'])
                    found_berth = None
                    for _, berth in berths_gdf.iterrows():
                        if berth.geometry.contains(pt):
                            found_berth = berth.get('POIName', berth.get('name', 'Unknown'))
                            break
                    
                    if found_berth:
                        # VALID NEW EVENT! SAVE IT.
                        last_saved[(imo, 'Berthing')] = event_time # Update tracker
                        
                        # Extract Window
                        t_end = event_time
                        t_start = t_end - pd.Timedelta(minutes=WINDOW_MINUTES)
                        traj = group[(group['timestamp'] >= t_start) & (group['timestamp'] <= t_end)]
                        
                        # Save
                        if len(traj) > 20:
                            fname = f"{OUTPUT_DIR}/Berthing_{found_berth}_{imo}_{event_time.strftime('%Y%m%d%H%M')}.csv"
                            traj.to_csv(fname, index=False)
                            processed_count += 1

                # --- PROCESS UNBERTHING ---
                for idx in unberth_indices:
                    if idx == 0: continue
                    event_time = group.loc[idx-1, 'timestamp'] # Time it was STILL stopped
                    
                    if event_time < current_df['timestamp'].min(): continue

                    # COOLDOWN CHECK
                    last_time = last_saved.get((imo, 'Unberthing'))
                    if last_time and (event_time - last_time).total_seconds() < (EVENT_COOLDOWN_MINUTES * 60):
                        continue 

                    # SPATIAL CHECK (Check previous 'stopped' row)
                    prev_row = group.loc[idx-1]
                    pt = Point(prev_row['longitudedegrees'], prev_row['latitudedegrees'])
                    found_berth = None
                    for _, berth in berths_gdf.iterrows():
                        if berth.geometry.contains(pt):
                            found_berth = berth.get('POIName', berth.get('name', 'Unknown'))
                            break
                    
                    if found_berth:
                        last_saved[(imo, 'Unberthing')] = event_time
                        
                        t_start = group.loc[idx, 'timestamp'] # Start moving time
                        t_end = t_start + pd.Timedelta(minutes=WINDOW_MINUTES)
                        traj = group[(group['timestamp'] >= t_start) & (group['timestamp'] <= t_end)]
                        
                        if len(traj) > 20:
                            fname = f"{OUTPUT_DIR}/Unberthing_{found_berth}_{imo}_{event_time.strftime('%Y%m%d%H%M')}.csv"
                            traj.to_csv(fname, index=False)
                            processed_count += 1

            # Update Buffer
            max_time = current_df['timestamp'].max()
            buffer_start = max_time - pd.Timedelta(minutes=WINDOW_MINUTES + 30)
            buffer_df = current_df[current_df['timestamp'] > buffer_start].copy()
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    print(f"Done. Extracted {processed_count} unique trajectories.")

if __name__ == "__main__":
    extract_trajectories_mass()