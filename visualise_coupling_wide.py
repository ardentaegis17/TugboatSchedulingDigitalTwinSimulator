import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Button
import geopandas as gpd
import glob
import os
import shutil
import numpy as np

# ================= CONFIGURATION =================
INPUT_FOLDER = "coupled_jobs_wide_jun2023"
OUTPUT_FOLDER = "three_tug_trajectories"
TERMINAL_GEOJSON = "Pasir Panjang Terminal/PPT_portboundary.json"
BERTHS_GEOJSON = "Pasir Panjang Terminal/PPT_berths.json"

MIN_TUGS = 1
FRAME_INTERVAL_MS = 50 
UNBERTH_ONLY = True
# =================================================

def get_tug_imos(df):
    tug_cols = [c for c in df.columns if c.startswith('lat_tug_')]
    imos = [c.split('_')[-1] for c in tug_cols]
    return sorted(list(set(imos)))

def get_uv(heading_deg):
    if pd.isna(heading_deg): return 0, 0
    rad = np.radians(90 - heading_deg)
    return np.cos(rad), np.sin(rad)

def animate_and_verify(df, file_path, tug_imos):
    file_name = os.path.basename(file_path)
    print(f"Reviewing: {file_name} ({len(tug_imos)} Tugs)...")
    
    # 1. Setup Plot (Make figure wider to fit button)
    fig, ax = plt.subplots(figsize=(14, 10))
    plt.subplots_adjust(bottom=0.15) # Make room at bottom for button
    
    # Map Layers
    if os.path.exists(TERMINAL_GEOJSON):
        gpd.read_file(TERMINAL_GEOJSON).plot(ax=ax, facecolor='none', edgecolor='black', linestyle='--', alpha=0.3)
    if os.path.exists(BERTHS_GEOJSON):
        gpd.read_file(BERTHS_GEOJSON).plot(ax=ax, facecolor='lightgrey', edgecolor='grey', alpha=0.3)

    # Bounds
    pad = 0.004
    ax.set_xlim(df['longitudedegrees'].min()-pad, df['longitudedegrees'].max()+pad)
    ax.set_ylim(df['latitudedegrees'].min()-pad, df['latitudedegrees'].max()+pad)
    ax.set_aspect('equal')
    ax.set_title(f"REVIEW MODE: {file_name}")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    # Graphics
    ship_quiver = ax.quiver([], [], [], [], color='blue', scale=25, width=0.005, label='Ship', zorder=5)
    
    tug_quivers = {}
    tow_lines = {}
    colors = ['red', 'orange', 'green', 'purple', 'magenta']
    
    for i, imo in enumerate(tug_imos):
        c = colors[i % len(colors)]
        tq = ax.quiver([], [], [], [], color=c, scale=30, width=0.003, label=f'Tug {imo}', zorder=4)
        tug_quivers[imo] = tq
        tl, = ax.plot([], [], color=c, linestyle='-', linewidth=0.8, alpha=0.6, zorder=3)
        tow_lines[imo] = tl

    info_text = ax.text(0.02, 0.95, '', transform=ax.transAxes, 
                        bbox=dict(boxstyle="round", fc="white", alpha=0.9), verticalalignment='top')
    ax.legend(loc='lower right')

    # --- BUTTON LOGIC ---
    # Define Button Position [left, bottom, width, height]
    ax_btn = plt.axes([0.7, 0.02, 0.2, 0.075])
    btn = Button(ax_btn, 'APPROVE & MOVE', color='lightgreen', hovercolor='green')

    def on_click(event):
        # 1. Create Output Folder
        if not os.path.exists(OUTPUT_FOLDER):
            os.makedirs(OUTPUT_FOLDER)
        
        # 2. Move File
        dest_path = os.path.join(OUTPUT_FOLDER, file_name)
        try:
            # We use copy+remove or move. Shutil.move is safest.
            shutil.move(file_path, dest_path)
            print(f" >>> APPROVED! Moved to {OUTPUT_FOLDER}")
            
            # 3. Change Window Title to confirm
            ax.set_title(f"APPROVED: {file_name}", color='green', fontweight='bold')
            plt.draw()
            
            # 4. Close Window (Optional: Remove this line if you want to keep watching)
            plt.close(fig) 
            
        except Exception as e:
            print(f"Error moving file: {e}")

    # Attach callback
    btn.on_clicked(on_click)
    
    # Keep reference to prevent garbage collection
    fig.my_btn = btn 

    # --- ANIMATION UPDATE ---
    def update(frame):
        row = df.iloc[frame]
        
        u, v = get_uv(row['headingoverwater'])
        ship_quiver.set_offsets([row['longitudedegrees'], row['latitudedegrees']])
        ship_quiver.set_UVC(u, v)
        
        status_str = f"Time: {row['timestamp'].strftime('%H:%M:%S')}\n"
        status_str += f"Ship Speed: {row['speedoverground']:.1f} kts\n\n"
        
        for i, imo in enumerate(tug_imos):
            lat_col = f"lat_tug_{imo}"
            lon_col = f"lon_tug_{imo}"
            hdg_col = f"heading_tug_{imo}"
            
            if pd.isna(row[lat_col]):
                tug_quivers[imo].set_UVC(0, 0)
                tow_lines[imo].set_data([], [])
                continue
            
            tu, tv = get_uv(row[hdg_col])
            tug_quivers[imo].set_offsets([row[lon_col], row[lat_col]])
            tug_quivers[imo].set_UVC(tu, tv)
            tow_lines[imo].set_data([row['longitudedegrees'], row[lon_col]], [row['latitudedegrees'], row[lat_col]])
            
            dist = np.sqrt((row['latitudedegrees'] - row[lat_col])**2 + (row['longitudedegrees'] - row[lon_col])**2) * 111000
            status_str += f"Tug {imo}: {dist:.0f}m\n"

        info_text.set_text(status_str)
        return [ship_quiver, info_text] + list(tug_quivers.values()) + list(tow_lines.values())

    anim = FuncAnimation(fig, update, frames=len(df), interval=FRAME_INTERVAL_MS, blit=False)
    plt.show()

def main():
    files = glob.glob(os.path.join(INPUT_FOLDER, "*.csv"))
    if not files:
        print(f"No files found in {INPUT_FOLDER}")
        return

    print(f"Scanning {len(files)} files...")
    
    count = 0
    for f in files:
        if os.path.basename(f)[:2] == "Be" and UNBERTH_ONLY == True:
            continue

        try:
            df = pd.read_csv(f)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            tug_imos = get_tug_imos(df)
            
            if len(tug_imos) == MIN_TUGS:
                # IMPORTANT: Pass the full file path 'f' so we can move it
                animate_and_verify(df, f, tug_imos)
                count += 1
        except Exception as e:
            print(f"Error reading {f}: {e}")

    if count == 0:
        print("No matching jobs found.")

if __name__ == "__main__":
    main()