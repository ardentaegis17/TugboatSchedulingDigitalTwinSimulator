import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import geopandas as gpd
import glob
import os
import numpy as np

# ================= CONFIGURATION =================
JOB_FOLDER = "trajectory_gen V1/finalised_trajectories"
TERMINAL_GEOJSON = "Pasir Panjang Terminal/PPT_portboundary.json"
BERTHS_GEOJSON = "Pasir Panjang Terminal/PPT_berths.json"

# =================================================

def get_job_groups():
    files = glob.glob(os.path.join(JOB_FOLDER, "*.csv"))
    jobs = {}
    for f in files:
        filename = os.path.basename(f)
        parts = filename.split('_TUG-')
        if len(parts) != 2: continue
        job_id = parts[0]
        if job_id not in jobs: jobs[job_id] = []
        jobs[job_id].append(f)
    return jobs

def synchronize_data(file_list):
    dfs = []
    for f in file_list:
        df = pd.read_csv(f)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp').sort_index()
        # Remove duplicates
        df = df[~df.index.duplicated(keep='first')]
        dfs.append(df)
        
    t_min = min(df.index.min() for df in dfs)
    t_max = max(df.index.max() for df in dfs)
    master_time = pd.date_range(start=t_min, end=t_max, freq='5S')
    
    # Interpolate CS (Include Heading)
    # Note: Interpolating degrees (359 -> 1) is tricky. 
    # For simple visualization, linear interp is usually "okay" unless it crosses North.
    # A proper solution unwraps angles, but for typical port moves, it's fine.
    cs_cols = ['latitudedegrees_cs', 'longitudedegrees_cs', 'headingoverwater_cs']
    if 'headingoverwater_cs' not in dfs[0].columns:
        print("WARNING: 'headingoverwater_cs' not found. Defaulting to 0.")
        dfs[0]['headingoverwater_cs'] = 0
        
    cs_interp = dfs[0][cs_cols].reindex(master_time).interpolate(method='time')
    
    tugs_interp = []
    for df in dfs:
        if 'headingoverwater_tug' not in df.columns: df['headingoverwater_tug'] = 0
        cols = ['latitudedegrees_tug', 'longitudedegrees_tug', 'headingoverwater_tug', 'dist_m']
        tug_res = df[cols].reindex(master_time).interpolate(method='time')
        tugs_interp.append(tug_res)
        
    return master_time, cs_interp, tugs_interp

def animate_job(job_id, file_list):
    print(f"Animating Job: {job_id}...")
    timeline, cs_df, tugs_dfs = synchronize_data(file_list)
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Load Map
    if os.path.exists(TERMINAL_GEOJSON):
        gpd.read_file(TERMINAL_GEOJSON).plot(ax=ax, facecolor='none', edgecolor='black', linestyle='--', alpha=0.3)
    if os.path.exists(BERTHS_GEOJSON):
        gpd.read_file(BERTHS_GEOJSON).plot(ax=ax, facecolor='lightblue', edgecolor='blue', alpha=0.3)

    # Set Bounds
    pad = 0.002
    ax.set_xlim(cs_df['longitudedegrees_cs'].min()-pad, cs_df['longitudedegrees_cs'].max()+pad)
    ax.set_ylim(cs_df['latitudedegrees_cs'].min()-pad, cs_df['latitudedegrees_cs'].max()+pad)
    ax.set_aspect('equal')
    ax.set_title(f"Heading Visualization: {job_id}")

    # --- GRAPHIC ELEMENTS ---
    
    # 1. Containership Quiver (Arrow)
    # pivot='mid' means the lat/lon is the center of the arrow
    cs_quiver = ax.quiver([], [], [], [], color='blue', scale=20, width=0.005, pivot='mid', label='CS Heading')
    
    # 2. Tug Quivers
    tug_quivers = []
    tow_lines = []
    colors = ['red', 'orange', 'magenta', 'purple']
    
    for i in range(len(tugs_dfs)):
        c = colors[i % len(colors)]
        # Tug Arrow
        tq = ax.quiver([], [], [], [], color=c, scale=30, width=0.003, pivot='mid', label=f'Tug {i+1}')
        tug_quivers.append(tq)
        # Tow Line
        tl, = ax.plot([], [], '-', color=c, linewidth=1, alpha=0.6)
        tow_lines.append(tl)

    info_text = ax.text(0.02, 0.95, '', transform=ax.transAxes, bbox=dict(boxstyle="round", fc="white", alpha=0.9))
    ax.legend(loc='lower right')

    def get_uv(heading_deg):
        # Convert AIS Heading (0=N, 90=E) to Math Vectors
        # U (x) = sin(heading)
        # V (y) = cos(heading)
        rad = np.radians(heading_deg)
        return np.sin(rad), np.cos(rad)

    def update(frame):
        idx = timeline[frame]
        
        # --- UPDATE CS ---
        cs_pos = cs_df.loc[idx]
        if np.isnan(cs_pos['latitudedegrees_cs']): return cs_quiver,
        
        # Update Position (offsets) and Direction (U, V)
        u, v = get_uv(cs_pos['headingoverwater_cs'])
        cs_quiver.set_offsets([cs_pos['longitudedegrees_cs'], cs_pos['latitudedegrees_cs']])
        cs_quiver.set_UVC(u, v)
        
        # --- UPDATE TUGS ---
        status_str = f"Time: {idx.strftime('%H:%M:%S')}\n"
        
        for i, tug_df in enumerate(tugs_dfs):
            tug_pos = tug_df.loc[idx]
            
            if np.isnan(tug_pos['latitudedegrees_tug']):
                tug_quivers[i].set_UVC(0, 0) # Hide
                tow_lines[i].set_data([], [])
                continue
                
            # Update Arrow
            u_t, v_t = get_uv(tug_pos['headingoverwater_tug'])
            tug_quivers[i].set_offsets([tug_pos['longitudedegrees_tug'], tug_pos['latitudedegrees_tug']])
            tug_quivers[i].set_UVC(u_t, v_t)
            
            # Update Line
            tow_lines[i].set_data([cs_pos['longitudedegrees_cs'], tug_pos['longitudedegrees_tug']], 
                                  [cs_pos['latitudedegrees_cs'], tug_pos['latitudedegrees_tug']])
            
            status_str += f"Tug {i+1}: {tug_pos['headingoverwater_tug']:.0f}°\n"

        info_text.set_text(status_str)
        return [cs_quiver] + tug_quivers + tow_lines + [info_text]

    anim = FuncAnimation(fig, update, frames=len(timeline), interval=50, blit=False)
    plt.show()

def main():
    jobs = get_job_groups()
    print(jobs)
    for job_id, files in jobs.items():
        if len(files) >= 1:
            animate_job(job_id, files)

if __name__ == "__main__":
    main()