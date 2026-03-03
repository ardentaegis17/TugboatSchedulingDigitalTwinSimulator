import folium
from folium.plugins import TimestampedGeoJson
import pandas as pd
import glob
import os
import random

# ================= CONFIGURATION =================
# Get the exact directory where this Python script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Build absolute paths based on the script's location
INPUT_FOLDER = os.path.join(SCRIPT_DIR, "extracted_trajectories")
OUTPUT_MAP = os.path.join(SCRIPT_DIR, "enghupargo_map_animated.html")

# Map Settings
CENTER_LAT = 1.26  # Approx Singapore Port Lat
CENTER_LON = 103.78 # Approx Singapore Port Lon
ZOOM_START = 12

def get_random_color():
    # Returns a hex color string for distinct lines
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))

def visualize():
    print(f"--- Scanning {INPUT_FOLDER} for trajectories ---")
    
    # 1. Initialize Map
    m = folium.Map(location=[CENTER_LAT, CENTER_LON], zoom_start=ZOOM_START, tiles='CartoDB positron')
    
    # 2. Find Files
    files = glob.glob(os.path.join(INPUT_FOLDER, "*.csv"))
    if not files:
        print("No CSV files found! Run the extraction script first.")
        return

    print(f"Found {len(files)} trajectory files. Formatting for Time Slider...")

    features = []
    count = 0

    for f in files:
        try:
            df = pd.read_csv(f)
            
            # Ensure we have data
            if len(df) < 2: continue

            # Convert timestamps to ISO 8601 format for the plugin
            # Coerce errors drops any corrupted datetime strings
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
            df = df.dropna(subset=['Timestamp'])
            
            if df.empty: continue

            times = df['Timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S').tolist()
            
            # IMPORTANT: GeoJSON format requires [Longitude, Latitude]
            coordinates = df[['LongitudeDegrees', 'LatitudeDegrees']].values.tolist()
            
            filename = os.path.basename(f)
            color = get_random_color()
            
            # 3. Build GeoJSON Feature for this trajectory
            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': coordinates
                },
                'properties': {
                    'times': times,
                    'style': {
                        'color': color,
                        'weight': 3,
                        'opacity': 0.8
                    },
                    'popup': f"<b>File:</b> {filename}"
                }
            }
            
            features.append(feature)
            count += 1
            
        except Exception as e:
            print(f"Error processing {f}: {e}")

    if count == 0:
        print("No valid data could be plotted.")
        return

    # 4. Wrap all features into a FeatureCollection
    geojson_data = {
        'type': 'FeatureCollection',
        'features': features
    }

    # 5. Add the TimestampedGeoJson Plugin
    TimestampedGeoJson(
        geojson_data,
        period='P1D',          # Slider steps forward by 1 Day ('PT1H' would be 1 Hour)
        duration='P1D',        # Trajectories stay visible for 1 Day before fading out
        add_last_point=True,   # Connects the dots into a line
        auto_play=False,       # Start paused
        loop=False,
        max_speed=1,
        loop_button=True,
        date_options='YYYY-MM-DD',
        time_slider_drag_update=True
    ).add_to(m)

    # 6. Save Map
    m.save(OUTPUT_MAP)
    print(f"--- Success! Animated map saved to {OUTPUT_MAP} ({count} trajectories) ---")
    print(f"Open {OUTPUT_MAP} in your web browser to view the time slider.")

if __name__ == "__main__":
    visualize()