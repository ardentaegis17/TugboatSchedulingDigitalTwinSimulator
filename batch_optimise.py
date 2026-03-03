import os
import subprocess
import time
import sys

# ================= CONFIGURATION =================
NUM_SCENARIOS = 31
INPUT_DIR = "generated_schedules"    # Where your base scenarios live
OUTPUT_DIR = "generated_schedules"   # We'll save the optimized ones here too
# =================================================

def run_batch():
    print(f"--- Starting Optimization Batch for {NUM_SCENARIOS} Scenarios ---")
    start_time = time.time()

    for i in range(1, NUM_SCENARIOS + 1):
        print(f"\n================ Processing Scenario {i}/{NUM_SCENARIOS} ================")
        
        # 1. Define the file paths
        base_file = os.path.join(INPUT_DIR, f"scenario_{i}.json")
        ci_file = os.path.join(OUTPUT_DIR, f"ci_scenario_{i}.json")
        tabu_file = os.path.join(OUTPUT_DIR, f"tabu_scenario_{i}.json")

        # Skip if the base file doesn't exist
        if not os.path.exists(base_file):
            print(f"Error: Could not find {base_file}. Skipping.")
            continue

        # 2. Run Cheap Insertion
        # Equivalent to typing: python cheap_insertion.py <input> <output>
        print(f"-> Running Cheap Insertion for Scenario {i}...")
        subprocess.run(["python", "cheapest_insertion.py", base_file, ci_file])

        # 3. Run Tabu Search (Using the Cheap Insertion output as its Warm Start)
        if os.path.exists(ci_file):
            print(f"-> Running Tabu Search for Scenario {i}...")
            subprocess.run(["python", "cheapest_insertion_tabu.py", ci_file, tabu_file])
        else:
            print(f"Error: {ci_file} was not generated. Skipping Tabu Search.")

    # Finished
    elapsed = time.time() - start_time
    mins, secs = divmod(elapsed, 60)
    print(f"\n--- Batch Complete! ---")
    print(f"Total processing time: {int(mins)}m {int(secs)}s")
    print(f"All 93 schedules are ready in the '{OUTPUT_DIR}' folder.")

if __name__ == "__main__":
    run_batch()