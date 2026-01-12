import java.io.FileWriter;
import java.io.IOException;

public class Main {
    public static void main(String[] args) {
        System.out.println("--- Starting Java Port Simulation ---");
        
        PortSimulation sim = new PortSimulation();
        sim.run();

        // Export JSON
        try (FileWriter file = new FileWriter("integrated_schedule.json")) {
            file.write("{\n");
            file.write("  \"meta\": { \"total_jobs\": " + sim.completedJobs.size() + " },\n");
            file.write("  \"schedule\": [\n");
            
            for (int i = 0; i < sim.completedJobs.size(); i++) {
                file.write("    " + sim.completedJobs.get(i).toJson());
                if (i < sim.completedJobs.size() - 1) file.write(",");
                file.write("\n");
            }
            
            file.write("  ]\n");
            file.write("}");
            System.out.println("\nSuccessfully exported 'integrated_schedule.json'");
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}