# DSA4288 - Maritime Digital Twin Simulator for Ops Planning
This repository contains the scripts and assets used by the Tugboat Scheduling Maritime Digital Twin Simulator. 

Tugboat services play an important role in maritime shipping, helping large containerships to navigate through the narrow channels of a port terminal during berthing and unberthing operations. In Singapore, a vessel arrives and departs every 3 minutes, with many enroute to other countries within Asia. There is thus a need to ensure timely service delivery to prevent ships from waiting too long, which can cause cascading delays throughout the shipping network. However, trying to tow too many containerships at once increases the risk of collisions between vessels. A safety buffer of 3 cable lengths (555m) is often imposed between moving vessels to avoid such events, with any violation of the buffer considered a near-miss incident.

The primary goal of this project is to simulate the arrival and towing of containership vessels, followed by the construction and optimisation of tugboat schedules. By adopting different strategies in the allocation of tugboats, we can consider how proactive scheduling policies can improve the efficiency of tugboat services by minimising wait time while ensuring safe navigation through minimising near-miss incidents. This is achieved through batch simulation of port operations in a physics-based game engine like Unity3D, where interactions between tugs and containerships can be observed and performance metrics measured. This application of a Maritime Digital Twin can help improve port throughput while ensuring safety at sea, serving as a valuable decision support tool for marine service providers and port authorities.

This repository is organised into the following directories:

```bash
TugboatSchedulingDigitalTwinSimulator/
│
├── .gitmodules                         # Git configuration tracking the Unity submodule
│
├── data_preparation/                   # Scripts for cleaning and formatting raw input data
│
├── docs/                               # Project documentation, architecture images, and demo video
│
├── generated_schedules/                # Staging area for initial, CI, and CI-TS schedule outputs (JSON)
│
├── jobs/                               # Storage for coupled containership-tug trajectories to be approved.
│
├── optimisation/                       # Python Scheduling & Optimisation Engine
│   ├── batch_optimise.py               # Orchestration script for executing multiple schedule iterations
│   ├── cheapest_insertion_tabu.py      # Meta-heuristic optimisation script (Tabu Search)
│   ├── cheapest_insertion.py           # Core constructive heuristic script (Cheap Insertion)
│   └── routeplanner.py                 # Graph-based physical distance calculations
│
├── Pasir Panjang Terminal/             # Raw geographic/geojson data defining the port layout
│
├── results/                            # Raw CSV metrics from simulation runs and visualisation scripts
│
├── schedule_generation/                # simulate the arrival of containerships to be serviced and visualise optimised CI and CI-TS schedules
│
├── trajectories/                       # Processed AIS vessel trajectory datasets (containerships, tugs, approved coupled trajectories)
│
├── simulation/ @ TugSP-Unity           # [GIT SUBMODULE] Unity3D Digital Twin Build
│
├── README.md                           # Setup and cloning instructions
└── requirements.txt                    # Python environment dependencies
```

## 🚀 Installation & Setup

This project uses a Git Submodule to link the Python optimisation engine with the Unity 3D Digital Twin. To ensure you download all the necessary files, **you must use the `--recurse-submodules` flag** when cloning this repository.

### Step 1: Clone the Repository
Open your terminal and run the following command:

```bash
git clone --recurse-submodules https://github.com/sg-t1aidan/TugboatSchedulingDigitalTwinSimulator.git
```

## Step 2: Set Up the Python Environment
Navigate into the root directory of the project. Create and activate a virtual environment:

``` bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

install the required routing and optimisation packages:

```bash
cd TugboatSchedulingDigitalTwinSimulator
pip install -r requirements.txt
```

## Step 3: Running the Project
1. Optimisation: Run python optimisation/batch_optimise.py to generate the dispatch schedules. The output will be saved in the generated_schedules/ folder.
2. Simulation: Open the simulation folder (which contains the TugSP-Unity project) using Unity Hub (Version 2022.3+ recommended). Press "Play" in the editor to load the schedules and watch the digital twin execute the routes.
