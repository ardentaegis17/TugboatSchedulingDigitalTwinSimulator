import pandas as pd
import glob
import os
from datetime import timedelta
import zipfile
from tqdm import tqdm

# ================= CONFIGURATION =================
# Target Vessel
TARGET_IMO = 9874428 #ENG HUP ARGO
TARGET_MMSI = 563083290 # X Tron
TARGET_NAME = "HYDROMOVER"

# Paths (Adjust these to match your PC)
INPUT_FOLDER = r"C:\Users\sg-t1aidan\Desktop\Vessel Data\202312" 
OUTPUT_FOLDER = "./extracted_trajectories"

# settings
TIME_GAP_THRESHOLD = 30  # Minutes (Split into new file if gap > 30 mins)
MIN_DATAPOINTS = 50      # Ignore trajectories with fewer than 50 points


# ================= EXTRACTION LOGIC =================
def extract_trajectories():
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    print(f"--- Searching for {TARGET_NAME} ({TARGET_MMSI}) in {INPUT_FOLDER} ---")
    
    # 1. Gather all CSV files
    # Walk through the directory structure
    files_to_process = []
    for root, dirs, files in os.walk(INPUT_FOLDER):
        for file in files:
            if file.endswith(".zip") and "vsl_position" in file:
                files_to_process.append(os.path.join(root, file))

    # 2. Load and Filter Data
    vessel_data = []
    
    for file_path in tqdm(files_to_process, desc="Processing Files"):
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                # Assuming one CSV per zip, find it
                csv_name = [f for f in z.namelist() if f.endswith('.csv')][0]
 
                
                with z.open(csv_name) as f:
                    # Read CSV with specific columns to save memory
                    # Note: We read timeStamp as string first to parse safely later
                    df = pd.read_csv(f)
                    # print(df.head())

                    # Filter by IMO
                    filtered = df[df['imoNumber'] == TARGET_IMO].copy()

                    # Filter by MMSI
                    # filtered = df[df['mmsiNumber'] == TARGET_MMSI].copy()

                    # Filter by Name
                    # filtered = df[df['name'] == TARGET_NAME].copy()
                    
                    if not filtered.empty:
                        vessel_data.append(filtered)
                        print(f"Found {len(filtered)} points in {os.path.basename(csv_name)}")
            
            

        except Exception as e:
            print(f"Skipping {f}: {e}")

    if not vessel_data:
        print("No data found for this MMSI.")
        return

    # 3. Merge and Sort
    full_df = pd.concat(vessel_data, ignore_index=True)
    
    # Parse Timestamp
    full_df['timeStamp'] = pd.to_datetime(full_df['timeStamp'])
    full_df = full_df.sort_values(by='timeStamp')
    
    # 4. Detect Trajectories (Split by Time Gap)
    # Calculate time difference between rows
    full_df['dt'] = full_df['timeStamp'].diff().dt.total_seconds() / 60.0 # in minutes
    
    # Identify gaps > Threshold
    full_df['gap'] = full_df['dt'] > TIME_GAP_THRESHOLD
    
    # Assign Trajectory ID (increment every time a gap is found)
    full_df['traj_id'] = full_df['gap'].cumsum()
    
    # 5. Export Individual Trajectories
    unique_ids = full_df['traj_id'].unique()
    print(f"--- Processing {len(unique_ids)} potential segments ---")

    count = 0
    for tid in unique_ids:
        segment = full_df[full_df['traj_id'] == tid].copy()
        
        # Filter noise (short segments)
        if len(segment) < MIN_DATAPOINTS:
            continue
            
        # Clean up columns for export
        start_time = segment['timeStamp'].iloc[0].strftime("%Y%m%d_%H%M")
        filename = f"{TARGET_NAME}_{start_time}_ID{int(tid)}.csv"
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        
        # Standardize columns for Unity (LatitudeDegrees, LongitudeDegrees, etc.)
        export_df = pd.DataFrame({
            'Timestamp': segment['timeStamp'],
            'LatitudeDegrees': segment['latitudeDegrees'],
            'LongitudeDegrees': segment['longitudeDegrees'],
            'SpeedKnots': segment['speedOverGround'],
            'CourseDegrees': segment['courseOverGround'],
            'HeadingDegrees': segment['headingOverGround']
        })
        
        export_df.to_csv(output_path, index=False)
        print(f"Saved: {filename} ({len(segment)} points)")
        count += 1

    print(f"--- Extraction Complete. Saved {count} trajectories to {OUTPUT_FOLDER} ---")

if __name__ == "__main__":
    extract_trajectories()