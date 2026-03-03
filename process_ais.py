import os
import pandas as pd
import geopandas as gpd
import zipfile
from shapely.geometry import Point, shape
from tqdm import tqdm
from datetime import timedelta

# ================= CONFIGURATION =================
ROOT_DIR = r"C:\Users\sg-t1aidan\Desktop\Vessel Data\202303"
GEOJSON_PATH = "Pasir Panjang Terminal/PPT_portboundary.json"
OUTPUT_FILE = "pasir_panjang_arrivals.csv"

# Target Vessel Types
TARGET_TYPES = ['TA', 'CS', 'BC'] 

# Time threshold to consider a "New Arrival"
# If a ship leaves and returns within 4 hours, is it a new arrival? 
# Usually, for port Ops, we say yes. But to avoid signal jitter noise, we set a small buffer.
RE_ENTRY_THRESHOLD = timedelta(hours=2) 
# =================================================

def load_geofence(path):
    """
    Loads the GeoJSON and calculates the Bounding Box for fast filtering.
    """
    print(f"Loading GeoFence from {path}...")
    gdf = gpd.read_file(path)
    
    # Union all shapes if there are multiple polygons (e.g. multiple berths)
    polygon = gdf.union_all()
    
    # Get Bounding Box (minx, miny, maxx, maxy) for fast pre-filtering
    bbox = polygon.bounds 
    return polygon, bbox

def process_ais_data():
    polygon, bbox = load_geofence(GEOJSON_PATH)
    minx, miny, maxx, maxy = bbox
    
    # Dictionary to track vessel state: {imo: last_seen_timestamp}
    # This helps us distinguish a "new arrival" from a ship just sitting there.
    vessels_inside_state = {}
    
    all_arrivals = []

    # Walk through the directory structure
    files_to_process = []
    for root, dirs, files in os.walk(ROOT_DIR):
        for file in files:
            if file.endswith(".zip") and "vsl_position" in file:
                files_to_process.append(os.path.join(root, file))

    files_to_process.sort() # Ensure we process chronologically!
    
    print(f"Found {len(files_to_process)} daily files. Starting processing...")

    for file_path in tqdm(files_to_process, desc="Processing Files"):
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                # Assuming one CSV per zip, find it
                csv_name = [f for f in z.namelist() if f.endswith('.csv')][0]
                
                with z.open(csv_name) as f:
                    # Read CSV with specific columns to save memory
                    # Note: We read timeStamp as string first to parse safely later
                    df = pd.read_csv(f,usecols=['imoNumber','type','length','latitudeDegrees','longitudeDegrees','timeStamp','grossTonnage'])
            
            # --- FILTER 1: Vessel Type ---
            df = df[df['type'].isin(TARGET_TYPES)]
            
            if df.empty: continue

            # --- FILTER 2: Bounding Box (Vectorized - Fast) ---
            # Discard points clearly outside the rectangular range of the port
            df = df[
                (df['longitudeDegrees'] >= minx) & (df['longitudeDegrees'] <= maxx) &
                (df['latitudeDegrees'] >= miny) & (df['latitudeDegrees'] <= maxy)
            ]
            
            if df.empty: continue

            # --- PREP: Convert Timestamps ---
            # Parse dates. Specifying format is faster if known, otherwise infer.
            df['timeStamp'] = pd.to_datetime(df['timeStamp'])
            df = df.sort_values('timeStamp') # Ensure time order

            # --- FILTER 3: Precise Polygon Check (Slow) ---
            # Create geometry points only for the candidates remaining
            points = gpd.points_from_xy(df['longitudeDegrees'], df['latitudeDegrees'])
            
            # Check which points are actually inside the complex polygon
            # .contains is expensive, so we did Step 2 first
            is_inside = points.within(polygon)
            inside_df = df[is_inside].copy()
            
            if inside_df.empty: continue

            # --- LOGIC: Detect Arrivals ---
            # We iterate through the valid points to see if they are "new" entries
            for _, row in inside_df.iterrows():
                imo = row['imoNumber']
                curr_time = row['timeStamp']
                v_type = row['type']
                v_length = row['length']
                gross_ton = row['grossTonnage']

                is_new_arrival = False
                
                if imo not in vessels_inside_state:
                    # Never seen before (or at least not recently) -> Arrival
                    is_new_arrival = True
                else:
                    last_seen = vessels_inside_state[imo]
                    # If we haven't seen them inside for a while, count as re-entry
                    if (curr_time - last_seen) > RE_ENTRY_THRESHOLD:
                        is_new_arrival = True
                
                if is_new_arrival:
                    all_arrivals.append({
                        'timestamp': curr_time,
                        'imo': imo,
                        'type': v_type,
                        'length': v_length,
                        'grossTonnage': gross_ton

                    })
                
                # Update state
                vessels_inside_state[imo] = curr_time

            # --- MEMORY CLEANUP ---
            # Optional: Clear ships from state if haven't seen in 2 days to keep RAM low
            # (omitted for simplicity, but good for very long datasets)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    # --- OUTPUT ---
    print(f"Processing complete. Detected {len(all_arrivals)} arrivals.")
    results_df = pd.DataFrame(all_arrivals)
    results_df.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    process_ais_data()