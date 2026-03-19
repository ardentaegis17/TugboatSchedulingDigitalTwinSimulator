import pandas as pd
import glob
import os
import re

# ================= CONFIGURATION =================
INPUT_FOLDER = "trajectories/two_tug_trajectories"
OUTPUT_FOLDER = "trajectories/standardised_trajectories"
# =================================================

def standardise_headers():
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        
    files = glob.glob(os.path.join(INPUT_FOLDER, "*.csv"))
    print(f"Processing {len(files)} trajectories...")

    for f in files:
        try:
            df = pd.read_csv(f)
            
            # 1. Identify Unique Tug IDs in this file
            # Look for columns starting with 'lat_tug_'
            tug_cols = [c for c in df.columns if c.startswith('lat_tug_')]
            
            # Extract the IMO suffixes (e.g., '123456' from 'lat_tug_123456')
            tug_imos = sorted(list(set([c.replace('lat_tug_', '') for c in tug_cols])))
            
            # 2. Build Rename Map (IMO -> Index)
            # IMO 999999 -> 1
            # IMO 888888 -> 2
            rename_map = {}
            
            for i, imo in enumerate(tug_imos):
                new_id = str(i + 1) # Tug 1, Tug 2...
                
                # Rename all 4 property columns for this tug
                rename_map[f'lat_tug_{imo}'] = f'lat_tug_{new_id}'
                rename_map[f'lon_tug_{imo}'] = f'lon_tug_{new_id}'
                rename_map[f'sog_tug_{imo}'] = f'sog_tug_{new_id}'
                rename_map[f'heading_tug_{imo}'] = f'heading_tug_{new_id}'
            
            # 3. Rename & Save
            df_clean = df.rename(columns=rename_map)
            
            # Optional: Drop original IMOs if they are kept elsewhere to reduce file size
            
            base_name = os.path.basename(f)
            out_path = os.path.join(OUTPUT_FOLDER, base_name)
            
            df_clean.to_csv(out_path, index=False)
            print(f"  Converted {base_name}: {len(tug_imos)} Tugs -> {['tug_'+str(i+1) for i in range(len(tug_imos))]}")
            
        except Exception as e:
            print(f"Error processing {f}: {e}")

    print("\nDone. Files saved to:", OUTPUT_FOLDER)

if __name__ == "__main__":
    standardise_headers()