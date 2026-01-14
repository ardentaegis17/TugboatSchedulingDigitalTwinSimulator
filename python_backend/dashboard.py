# streamlit_app.py
import streamlit as st
import pandas as pd
import geopandas as gpd
import movingpandas as mpd
from datetime import timedelta
import numpy as np
from streamlit_keplergl import keplergl_static
from keplergl import KeplerGl
import json

st.set_page_config(page_title="Vessel Movement Dashboard", layout="wide")

st.title("🚢 Pasir Panjang Vessel Movement Dashboard")

# --- File uploader ---
uploaded_file = st.file_uploader("Upload vessel movement CSV", type=["csv"])

# Load polygons (ensure they’re in EPSG:4326)
port_fence = gpd.read_file("Pasir Panjang Terminal/PPT_portboundary.json").to_crs(epsg=4326)
maneuvering_zone = gpd.read_file("Pasir Panjang Terminal/PPT_maneuveringzone.geojson").to_crs(epsg=4326)
anchorage_zones = gpd.read_file("Pasir Panjang Terminal/PPT_anchorage.geojson").to_crs(epsg=4326)
berths = gpd.read_file("Pasir Panjang Terminal/PPT_berths.geojson").to_crs(epsg=4326)


if uploaded_file:
    data = pd.read_csv(uploaded_file)

    # Filter subset (optional)
    seed = 200
    subset = data[data['mmsi'].isin(data['mmsi'].unique()[:seed])]
    subset = subset[['mmsi','vessel_name','lat','lon','timestamp','speed','vessel_type', 'nav_stat',
                     'anchorage','maneuvering_zone','berth']]

    # Create GeoDataFrame
    geodata = gpd.GeoDataFrame(
        subset,
        geometry=gpd.points_from_xy(subset['lon'], subset['lat']),
        crs='epsg:4326'
    )

    # Spatial joins with GeoJSON polygons
    geodata['in_maneuvering'] = geodata.sjoin(maneuvering_zone, predicate='within', how='left')['index_right'].notna()
    geodata['in_anchorage'] = geodata.sjoin(anchorage_zones, predicate='within', how='left')['index_right'].notna()
    geodata['in_berth'] = geodata.sjoin(berths, predicate='within', how='left')['index_right'].notna()
    geodata['in_port'] = geodata.sjoin(port_fence, predicate='within', how='left')['index_right'].notna()

    geodata['t'] = pd.to_datetime(geodata['timestamp'])
    geodata['timestamp_unix'] = geodata['t'].astype(np.int64) // 10**9

    MOVING_STATUSES = {0, 3, 4, 8, 11, 12}
    geodata['is_moving'] = (geodata['speed'] > 1) | (geodata['nav_stat'].isin(MOVING_STATUSES))

    def classify_activity(row):
        if row['in_berth'] and row['speed'] < 1:
            return "Alongside/Hotel"
        elif row['in_anchorage'] and row['speed'] < 1:
            return "Anchorage"
        elif row['in_maneuvering'] and row['is_moving']:
            return "Maneuvering"
        elif row['in_port'] and row['is_moving'] and not row['in_maneuvering']:
            return "Transit"
        elif not row['in_port']:
            return "Outside Port"
        else:
            return "Unknown"

    geodata['activity_label'] = geodata.apply(classify_activity, axis=1)

    # Build trajectories
    traj_collection = mpd.TrajectoryCollection(geodata, traj_id_col='mmsi', t='t', min_length=50)
    traj_collection = mpd.MinTimeDeltaGeneralizer(traj_collection).generalize(tolerance=timedelta(minutes=5))

    # get linestrings
    line_traj = traj_collection.to_line_gdf()
    # get a simple dataframe
    line_vis = line_traj[['vessel_type', 'geometry', 'vessel_name','t','timestamp_unix','activity_label']].dropna()
    line_vis.to_file('line_vis_kepler_200.geojson')

    # get points from trajectories
    point_traj =  traj_collection.to_point_gdf()

    # get index 
    point_traj_t = point_traj.reset_index(drop=False)
    
    # with open("line_vis_kepler_200.geojson") as f:
    #     geojson_data = json.load(f)

    # for feature in geojson_data["features"]:
    #     ts = feature["properties"]["timestamp_unix"]
    #     coords = feature["geometry"]["coordinates"]
    #     # Add altitude=0 and timestamp as the 4th value
    #     new_coords = [[lon, lat, 0, ts] for lon, lat in coords]
    #     feature["geometry"]["coordinates"] = new_coords

    # # Save updated GeoJSON
    # with open("line_vis_kepler_trip.geojson", "w") as f:
    #     json.dump(geojson_data, f)
    # --- KPIs ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Unique Vessels", geodata['mmsi'].nunique())
    col2.metric("Avg Speed (knots)", round(geodata['speed'].mean(), 2))
    col3.metric("Trajectories", len(traj_collection))
    col4.metric("Total Records", len(geodata))

    # --- Aggregations ---
    st.subheader("Activity Breakdown")
    activity_counts = geodata['activity_label'].value_counts().reset_index()
    st.write(activity_counts)
    st.bar_chart(activity_counts.set_index('activity_label'))

    # --- Map Visualization (pydeck) ---
    st.subheader("Vessel Trajectories Map")

    viz_data = gpd.read_file("line_vis_kepler_trip.geojson")

    map_ = KeplerGl(height=1000)
    map_.add_data(data=viz_data, name="Vessel Movements")

    keplergl_static(map_,center_map=True)

    # --- Trajectory summary table ---
    st.subheader("Trajectory Summary")
    st.dataframe(activity_counts)

else:
    st.info("Please upload your vessel movement dataset to begin.")
