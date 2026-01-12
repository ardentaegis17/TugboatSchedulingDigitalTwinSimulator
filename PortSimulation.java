import java.util.*;

// --- 1. DATA CLASSES ---

class Vessel {
    int id;
    int arrivalTick;
    String type;
    int length;
    int reqTugs;
    int serviceDuration;

    public Vessel(int id, int arrivalTick) {
        this.id = id;
        this.arrivalTick = arrivalTick;
        
        // Randomly assign type
        double rand = Math.random();
        if (rand < 0.2) {
            this.type = "ULCV";
            this.length = 400;
            this.reqTugs = 3;
            this.serviceDuration = 120;
        } else if (rand < 0.5) {
            this.type = "Panamax";
            this.length = 250;
            this.reqTugs = 2;
            this.serviceDuration = 75;
        } else {
            this.type = "Feeder";
            this.length = 120;
            this.reqTugs = 1;
            this.serviceDuration = 45;
        }
    }
}

class Job {
    String id;
    Vessel vessel;
    String status = "PENDING";
    String startLoc;
    String endLoc;
    
    // Scheduled details
    List<Integer> assignedTugs = new ArrayList<>();
    int scheduledStartTime = -1;

    public Job(String id, Vessel vessel, String startLoc, String endLoc) {
        this.id = id;
        this.vessel = vessel;
        this.startLoc = startLoc;
        this.endLoc = endLoc;
    }

    public String toJson() {
        // Simple manual JSON string builder to avoid external dependencies
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"job_id\": \"").append(id).append("\", ");
        sb.append("\"vessel_id\": ").append(vessel.id).append(", ");
        sb.append("\"arrival_tick\": ").append(vessel.arrivalTick).append(", ");
        sb.append("\"required_tugs\": ").append(vessel.reqTugs).append(", ");
        sb.append("\"assigned_tugs\": ").append(assignedTugs.toString()).append(", ");
        sb.append("\"scheduled_start_time\": ").append(scheduledStartTime).append(", ");
        sb.append("\"duration\": ").append(vessel.serviceDuration).append(", ");
        sb.append("\"start_node\": \"").append(startLoc).append("\", ");
        sb.append("\"end_node\": \"").append(endLoc).append("\"");
        sb.append("}");
        return sb.toString();
    }
}

class Tug {
    int id;
    int nextFreeTime = 0;
    String loc = "Base";

    public Tug(int id) {
        this.id = id;
    }
}

// --- 2. OPTIMIZER (TABU SEARCH) ---

class TabuScheduler {
    private int tabuTenure;
    private int maxIterations;

    public TabuScheduler(int tabuTenure, int maxIterations) {
        this.tabuTenure = tabuTenure;
        this.maxIterations = maxIterations;
    }

    // --- Helper: Calculate Cost (Total Latency) ---
    private int calculateCost(Map<String, List<Integer>> scheduleMap, List<Job> jobs, List<Tug> tugs, int currentTime) {
        int totalLatency = 0;
        
        // Clone tug availability state
        Map<Integer, Integer> tugFreeTimes = new HashMap<>();
        for (Tug t : tugs) tugFreeTimes.put(t.id, t.nextFreeTime);

        // Sort jobs by arrival time to simulate timeline
        List<Job> sortedJobs = new ArrayList<>(jobs);
        sortedJobs.sort(Comparator.comparingInt(j -> j.vessel.arrivalTick));

        for (Job job : sortedJobs) {
            List<Integer> assignedIds = scheduleMap.get(job.id);
            if (assignedIds == null || assignedIds.isEmpty()) return Integer.MAX_VALUE;

            // When do these tugs become free?
            int maxTugReadyTime = 0;
            for (int tid : assignedIds) {
                maxTugReadyTime = Math.max(maxTugReadyTime, tugFreeTimes.get(tid));
            }

            // Actual start time
            int actualStart = Math.max(currentTime, Math.max(job.vessel.arrivalTick, maxTugReadyTime));

            // Cost calculation
            totalLatency += (actualStart - job.vessel.arrivalTick);

            // Update virtual tug state
            int finishTime = actualStart + job.vessel.serviceDuration;
            for (int tid : assignedIds) {
                tugFreeTimes.put(tid, finishTime);
            }
        }
        return totalLatency;
    }

    // --- Helper: Initial Solution (Greedy) ---
    private Map<String, List<Integer>> getInitialSolution(List<Job> jobs, List<Tug> tugs) {
        Map<String, List<Integer>> schedule = new HashMap<>();
        List<Integer> allTugIds = new ArrayList<>();
        for (Tug t : tugs) allTugIds.add(t.id);

        for (int i = 0; i < jobs.size(); i++) {
            Job job = jobs.get(i);
            int req = job.vessel.reqTugs;
            List<Integer> assigned = new ArrayList<>();
            
            // Simple Round Robin assignment to guarantee validity
            for (int k = 0; k < req; k++) {
                assigned.add(allTugIds.get((i + k) % allTugIds.size()));
            }
            schedule.put(job.id, assigned);
        }
        return schedule;
    }

    // --- Main Solve Method ---
    public Map<String, List<Integer>> solve(List<Job> jobs, List<Tug> tugs, int currentTime) {
        // 1. Initial Solution
        Map<String, List<Integer>> currentSchedule = getInitialSolution(jobs, tugs);
        int currentCost = calculateCost(currentSchedule, jobs, tugs, currentTime);
        
        Map<String, List<Integer>> bestSchedule = deepCopy(currentSchedule);
        int bestCost = currentCost;

        // Tabu List: Key="JobID_TugID", Value=ExpiryIteration
        Map<String, Integer> tabuList = new HashMap<>();
        
        System.out.println("   [Tabu] Initial Cost: " + currentCost + " mins");

        // 2. Optimization Loop
        for (int iter = 0; iter < maxIterations; iter++) {
            Map<String, List<Integer>> bestNeighbor = null;
            int bestNeighborCost = Integer.MAX_VALUE;
            String moveSignature = "";

            // --- Generate Neighborhood (Swap Tugs) ---
            List<Integer> allTugIds = new ArrayList<>();
            for(Tug t : tugs) allTugIds.add(t.id);

            for (Job job : jobs) {
                List<Integer> currentAssigned = currentSchedule.get(job.id);
                
                // Identify tugs NOT currently working on this job
                List<Integer> availableSwaps = new ArrayList<>(allTugIds);
                availableSwaps.removeAll(currentAssigned);

                for (int tugOut : currentAssigned) {
                    for (int tugIn : availableSwaps) {
                        
                        // Create Candidate (Swap)
                        Map<String, List<Integer>> candidate = deepCopy(currentSchedule);
                        List<Integer> candidateList = candidate.get(job.id);
                        candidateList.remove(Integer.valueOf(tugOut));
                        candidateList.add(tugIn);

                        int cost = calculateCost(candidate, jobs, tugs, currentTime);

                        // Tabu Check
                        String signature = job.id + "_" + tugIn;
                        boolean isTabu = tabuList.containsKey(signature) && tabuList.get(signature) > iter;

                        // Aspiration Criteria
                        if (isTabu && cost >= bestCost) continue;

                        if (cost < bestNeighborCost) {
                            bestNeighbor = candidate;
                            bestNeighborCost = cost;
                            moveSignature = job.id + "_" + tugOut; // Mark the OUT tug as tabu to prevent cycling
                        }
                    }
                }
            }

            // Update Current State
            if (bestNeighbor != null) {
                currentSchedule = bestNeighbor;
                // Update Global Best
                if (bestNeighborCost < bestCost) {
                    bestSchedule = deepCopy(bestNeighbor);
                    bestCost = bestNeighborCost;
                }
                tabuList.put(moveSignature, iter + tabuTenure);
            }
        }

        System.out.println("   [Tabu] Final Cost: " + bestCost + " mins (Improved by " + (currentCost - bestCost) + ")");
        return bestSchedule;
    }

    // Helper to deep copy the schedule map
    private Map<String, List<Integer>> deepCopy(Map<String, List<Integer>> original) {
        Map<String, List<Integer>> copy = new HashMap<>();
        for (Map.Entry<String, List<Integer>> entry : original.entrySet()) {
            copy.put(entry.getKey(), new ArrayList<>(entry.getValue()));
        }
        return copy;
    }
}

// --- 3. SIMULATION ENGINE (Discrete Event) ---

class PortSimulation {
    // Priority Queue acts as the "Time Engine" (SimPy replacement)
    PriorityQueue<SimulationEvent> eventQueue = new PriorityQueue<>(Comparator.comparingInt(e -> e.time));
    
    List<Tug> tugs = new ArrayList<>();
    List<Job> pendingQueue = new ArrayList<>();
    List<Job> completedJobs = new ArrayList<>(); // To export
    
    TabuScheduler scheduler;
    int currentTime = 0;
    int vesselCounter = 0;
    
    // Configuration
    int N_TUGS = 4;
    int AVG_INTER_ARRIVAL = 100;
    int SIM_DURATION = 2880; // 2 days

    public PortSimulation() {
        for (int i = 1; i <= N_TUGS; i++) tugs.add(new Tug(i));
        scheduler = new TabuScheduler(5, 50);
    }

    public void run() {
        // Schedule first arrival
        scheduleNextArrival(0);

        // Main Simulation Loop
        while (!eventQueue.isEmpty() && currentTime < SIM_DURATION) {
            SimulationEvent event = eventQueue.poll();
            currentTime = event.time;
            
            if (event.type == EventType.ARRIVAL) {
                handleArrival();
            }
        }
    }

    private void scheduleNextArrival(int timeBase) {
        // Exponential distribution for inter-arrival time
        double lambda = 1.0 / AVG_INTER_ARRIVAL;
        int nextTime = timeBase + (int)(-Math.log(1 - Math.random()) / lambda);
        if (nextTime < SIM_DURATION) {
            eventQueue.add(new SimulationEvent(nextTime, EventType.ARRIVAL));
        }
    }

    private void handleArrival() {
        vesselCounter++;
        Vessel v = new Vessel(vesselCounter, currentTime);
        
        String jobId = "JOB_" + vesselCounter + (Math.random() > 0.5 ? "_IN" : "_OUT");
        String start = "Anchorage";
        String end = "Berth_" + (int)(Math.random() * 5 + 1);
        
        Job job = new Job(jobId, v, start, end);
        pendingQueue.add(job);
        
        System.out.println("[" + currentTime + "] New Job: " + job.id + " (Needs " + v.reqTugs + " tugs)");
        
        runScheduler();
        scheduleNextArrival(currentTime);
    }

    private void runScheduler() {
        if (pendingQueue.isEmpty()) return;

        // 1. Call Tabu Search
        Map<String, List<Integer>> assignments = scheduler.solve(pendingQueue, tugs, currentTime);

        // 2. Apply Assignments
        // Map back to Job objects
        List<Job> scheduledJobs = new ArrayList<>();
        
        for (Job job : pendingQueue) {
            if (assignments.containsKey(job.id)) {
                List<Integer> tugIds = assignments.get(job.id);
                
                // Find actual Tug objects
                List<Tug> assignedTugs = new ArrayList<>();
                int maxReadyTime = 0;
                for (Tug t : tugs) {
                    if (tugIds.contains(t.id)) {
                        assignedTugs.add(t);
                        maxReadyTime = Math.max(maxReadyTime, t.nextFreeTime);
                    }
                }

                // Calculate Timings
                int start = Math.max(currentTime, Math.max(job.vessel.arrivalTick, maxReadyTime));
                int finish = start + job.vessel.serviceDuration;

                // Update Job
                job.status = "ASSIGNED";
                job.assignedTugs = tugIds;
                job.scheduledStartTime = start;
                
                // Update Tugs
                for (Tug t : assignedTugs) {
                    t.nextFreeTime = finish;
                }

                completedJobs.add(job);
                scheduledJobs.add(job);

                System.out.println("   -> Scheduled " + job.id + ": Start " + start + " | Tugs " + tugIds);
            }
        }
        
        // Remove scheduled jobs from pending
        pendingQueue.removeAll(scheduledJobs);
    }

    // --- INNER EVENT CLASSES ---
    enum EventType { ARRIVAL }
    
    class SimulationEvent {
        int time;
        EventType type;
        public SimulationEvent(int time, EventType type) {
            this.time = time;
            this.type = type;
        }
    }
}

