import pandas as pd
import matplotlib.pyplot as plt
import geopandas as gpd
import glob
import os

# ================= CONFIGURATION =================
# Folder containing your FINAL coupled files
INPUT_FOLDER = "finalised_trajectories" 

# Background Map Files
TERMINAL_GEOJSON = "Pasir Panjang Terminal/PPT_portboundary.json"
BERTHS_GEOJSON = "Pasir Panjang Terminal/PPT_berths.geojson"

# Plot Settings
SHIP_COLOR_IN = 'blue'   # Color for Berthing
SHIP_COLOR_OUT = 'green' # Color for Unberthing
LINE_ALPHA = 0.5        # Transparency (Lower = better density visualization)
# =================================================

def plot_background(ax):
    """Helper to render the port layout on a specific plot axis"""
    try:
        # Plot Terminal Boundary (Dashed Black)
        if os.path.exists(TERMINAL_GEOJSON):
            gpd.read_file(TERMINAL_GEOJSON).plot(
                ax=ax, facecolor='none', edgecolor='black', 
                linestyle='--', linewidth=0.8, alpha=0.5, zorder=0
            )
        
        # Plot Berths (Filled Grey)
        if os.path.exists(BERTHS_GEOJSON):
            gpd.read_file(BERTHS_GEOJSON).plot(
                ax=ax, facecolor='lightgrey', edgecolor='grey', 
                alpha=0.5, zorder=1
            )
    except Exception as e:
        print(f"Map Load Error: {e}")

def visualise_operations():
    # 1. Gather Files
    all_files = glob.glob(os.path.join(INPUT_FOLDER, "*.csv"))
    
    if not all_files:
        print(f"No CSV files found in {INPUT_FOLDER}!")
        return

    # 2. Split into Berthing vs Unberthing based on filename
    # Filename structure: "Berthing_P1..." or "Unberthing_P2..."
    berthing_files = [f for f in all_files if "Berthing" in os.path.basename(f)]
    unberthing_files = [f for f in all_files if "Unberthing" in os.path.basename(f)]

    print(f"Found {len(berthing_files)} Berthing and {len(unberthing_files)} Unberthing jobs.")

    # 3. Setup Canvas (2 Subplots side-by-side)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))
    
    # --- PLOT 1: BERTHING (INBOUND) ---
    print("Plotting Berthing Trajectories...")
    plot_background(ax1)
    
    for f in berthing_files:
        try:
            df = pd.read_csv(f)
            # Plot only the Containership path (Cleanest view)
            # If you want Tugs too, add a second plot command
            ax1.plot(df['longitudedegrees_cs'], df['latitudedegrees_cs'], 
                     color=SHIP_COLOR_IN, linewidth=0.8, alpha=LINE_ALPHA)
        except:
            continue

    ax1.set_title(f"Inbound Operations (n={len(berthing_files)})", fontsize=14)
    ax1.set_xlabel("Longitude")
    ax1.set_ylabel("Latitude")
    ax1.set_aspect('equal')
    ax1.grid(True, linestyle=':', alpha=0.3)

    # --- PLOT 2: UNBERTHING (OUTBOUND) ---
    print("Plotting Unberthing Trajectories...")
    plot_background(ax2)
    
    for f in unberthing_files:
        try:
            df = pd.read_csv(f)
            ax2.plot(df['longitudedegrees_cs'], df['latitudedegrees_cs'], 
                     color=SHIP_COLOR_OUT, linewidth=0.8, alpha=LINE_ALPHA)
        except:
            continue

    ax2.set_title(f"Outbound Operations (n={len(unberthing_files)})", fontsize=14)
    ax2.set_xlabel("Longitude")
    # ax2.set_ylabel("Latitude") # Shared Y-axis typically implies removing label 2
    ax2.set_aspect('equal')
    ax2.grid(True, linestyle=':', alpha=0.3)

    # 4. Final Layout Adjustments
    # Auto-zoom to data bounds (handling outliers by clipping to 99th percentile if needed)
    # For now, let matplotlib auto-scale, but ensure both maps have roughly same view if possible
    
    plt.tight_layout()
    
    # Save High-Res for Thesis
    save_path = "Figure_Operational_Coverage.png"
    plt.savefig(save_path, dpi=300)
    print(f"Saved visualization to {save_path}")
    plt.show()

if __name__ == "__main__":
    visualise_operations()