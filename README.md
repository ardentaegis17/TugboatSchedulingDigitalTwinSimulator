
## 🚀 Installation & Setup

This project uses a Git Submodule to link the Python optimization engine with the Unity 3D Digital Twin. To ensure you download all the necessary files, **you must use the `--recurse-submodules` flag** when cloning this repository.

### Step 1: Clone the Repository
Open your terminal and run the following command:

```bash
git clone --recurse-submodules https://github.com/sg-t1aidan/TugboatSchedulingDigitalTwinSimulator.git

## Step 2: Set Up the Python Environment
Navigate into the root directory of the project and install the required routing and optimisation packages:

cd TugboatSchedulingDigitalTwinSimulator
```bash
pip install -r requirements.txt

## Step 3: Running the Project
1. Optimisation: Run python optimisation/batch_optimise.py to generate the dispatch schedules. The output will be saved in the generated_schedules/ folder.
2. Simulation: Open the simulation folder (which contains the TugSP-Unity project) using Unity Hub (Version 2022.3+ recommended). Press "Play" in the editor to load the schedules and watch the digital twin execute the routes.
