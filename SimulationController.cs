using UnityEngine;
using System.Collections.Generic;
using System.IO;

[System.Serializable]
public class JobData
{
    // Fields must match JSON keys EXACTLY
    public string job_id;
    public int vessel_ref;
    public int arrival_tick; 
    public int required_tugs;
    public int est_duration;
    public string start_node;
    public string end_node;
}

[System.Serializable]
public class SimulationData
{
    public List<JobData> mission_log;
}

public class SimulationController : MonoBehaviour
{
    public string jsonFileName = "unity_tug_missions.json";
    public float timeScale = 1.0f; // 1 real sec = 1 sim minute
    
    [Header("Runtime Info")]
    public float currentSimTime = 0f;
    
    private Queue<JobData> jobQueue;

    void Start()
    {
        LoadSimulationData();
    }

    void Update()
    {
        // Advance time
        currentSimTime += Time.deltaTime * timeScale;

        // Check if any jobs need to spawn
        CheckForArrivals();
    }

    void LoadSimulationData()
    {
        // 1. Read File
        string filePath = Path.Combine(Application.streamingAssetsPath, jsonFileName);
        
        if (File.Exists(filePath))
        {
            string jsonContent = File.ReadAllText(filePath);
            
            // 2. Parse JSON
            SimulationData data = JsonUtility.FromJson<SimulationData>(jsonContent);
            
            // 3. Sort by Arrival Time (Critical for the Queue to work)
            data.mission_log.Sort((a, b) => a.arrival_tick.CompareTo(b.arrival_tick));
            
            // 4. Enqueue
            jobQueue = new Queue<JobData>(data.mission_log);
            
            Debug.Log($"Loaded {jobQueue.Count} missions.");
        }
        else
        {
            Debug.LogError("JSON file not found! Put it in the StreamingAssets folder.");
        }
    }

    void CheckForArrivals()
    {
        if (jobQueue == null || jobQueue.Count == 0) return;

        // Peek at the next job
        JobData nextJob = jobQueue.Peek();

        // If current simulation time >= job arrival time
        if (currentSimTime >= nextJob.arrival_tick)
        {
            SpawnShip(nextJob);
            jobQueue.Dequeue(); // Remove from queue
            
            // Check again immediately in case multiple ships arrive at same tick
            CheckForArrivals(); 
        }
    }

    void SpawnShip(JobData job)
    {
        Debug.Log($"<color=green>[{currentSimTime:F0}] Spawning Ship for {job.job_id}</color> at {job.start_node}");
        
        // --- YOUR LOGIC HERE ---
        // 1. Find the spawn point Transform based on 'job.start_node' string
        // 2. Instantiate the Ship Prefab
        // 3. Assign the 'job' data to the Ship script so it knows where to go
    }
}