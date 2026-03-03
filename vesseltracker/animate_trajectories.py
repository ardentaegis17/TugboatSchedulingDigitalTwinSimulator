import folium
from folium.plugins import TimestampedGeoJson
import pandas as pd
import glob
import os
import random

# ================= CONFIGURATION =================
INPUT_FOLDER = "./extracted_trajectories"
OUTPUT_FILE = "realtime_trajectory_map.html"

# Map Center (Singapore)
CENTER_LAT = 1.26
CENTER_LON = 103.78

def get_random_color():
    """Generates a random hex color."""
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))

def generate_realtime_features(files):
    features = []
    
    print(f"Scanning {len(files)} files...")

    for file_path in sorted(files):
        filename = os.path.basename(file_path)
        color = get_random_color()
        
        try:
            df = pd.read_csv(file_path)
            
            # 1. PARSE REAL TIME
            # Ensure the Timestamp column is a proper datetime object
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            
            # Sort by time just in case the CSV is out of order
            df = df.sort_values('Timestamp')

            # Optional: Downsample (Take every 5th point) to keep file size small
            # df = df.iloc[::5, :]
            
            for i, row in df.iterrows():
                
                # 2. USE REAL ISO TIME
                # Folium needs the time in ISO string format (YYYY-MM-DDTHH:MM:SS)
                real_time_str = row['Timestamp'].isoformat()
                
                feature = {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [row['LongitudeDegrees'], row['LatitudeDegrees']]
                    },
                    'properties': {
                        'time': real_time_str, # <--- THIS IS THE KEY CHANGE
                        'style': {'color': color},
                        'icon': 'circle',
                        'iconstyle': {
                            'fillColor': color,
                            'fillOpacity': 0.8,
                            'stroke': 'false',
                            'radius': 3 # Small radius for a clean trace
                        },
                        'popup': f"<b>{filename}</b><br>{real_time_str}"
                    }
                }
                features.append(feature)

        except Exception as e:
            print(f"Error reading {filename}: {e}")
            
    return features

def main():
    # 1. Find Files
    files = glob.glob(os.path.join(INPUT_FOLDER, "*.csv"))
    if not files:
        print("No CSV files found!")
        return

    # 2. Initialize Map
    m = folium.Map(
        location=[CENTER_LAT, CENTER_LON], 
        zoom_start=12, 
        tiles='CartoDB dark_matter' # Dark map makes colored traces pop
    )

    # 3. Generate Data
    print("Processing trajectories...")
    features = generate_realtime_features(files)
    
    if not features:
        print("No valid data points found.")
        return

    # 4. Add Real-Time Animation
    print("Building animation layer...")
    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': features},
        
        # ANIMATION SETTINGS
        period='PT1M',       # Step size: Update map every 1 Minute of data
        duration='P1D',      # Point lifespan: Keep points visible for 1 Day (creates the long trace)
        
        # PLAYBACK SETTINGS
        add_last_point=True, # Leaves the dot on the map (tracing effect)
        auto_play=False,
        loop=False,
        max_speed=20,        # Allow fast forwarding
        loop_button=True,
        
        # TIME DISPLAY SETTINGS
        date_options='YYYY-MM-DD HH:mm:ss', # <--- Displays full Real Time on the slider
        time_slider_drag_update=True
    ).add_to(m)

    # 5. Save
    m.save(OUTPUT_FILE)
    print(f"Done! Map saved to: {OUTPUT_FILE}")
    print("Open the file in your browser. The slider at the bottom shows the REAL time.")

if __name__ == "__main__":
    main()