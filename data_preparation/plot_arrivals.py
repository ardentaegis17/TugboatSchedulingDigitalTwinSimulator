import pandas as pd
import matplotlib.pyplot as plt

# 1. Load the processed data
df = pd.read_csv("data_preparation/pasir_panjang_arrivals.csv")
df['timestamp'] = pd.to_datetime(df['timestamp'],format="%d/%m/%Y %H:%M")

# 2. Extract Time Features
df['hour'] = df['timestamp'].dt.hour
df['date'] = df['timestamp'].dt.date
total_days = df['date'].nunique()

# 3. Aggregate Data
# We want to count arrivals for each (Hour, Type) pair
# unstack() pivots the table so columns are Types and rows are Hours
hourly_counts = df.groupby(['hour', 'type']).size().unstack(fill_value=0)

# 4. Calculate Lambda (Average Arrivals per Hour)
# Divide total counts by the number of days observed (e.g., 90 days)
lambda_t = hourly_counts / total_days
lambda_t.to_csv("data_preparation/lambda_parameters.csv")
# 5. Plotting
plt.figure(figsize=(12, 6))

# Define colors/styles for clarity
styles = {
    'TA': {'color': 'red', 'label': 'Tankers (TA)', 'marker': 'o'},
    'CS': {'color': 'blue', 'label': 'Container/Cargo (CS)', 'marker': 's'},
    'BC': {'color': 'green', 'label': 'Bulk Carriers (BC)', 'marker': '^'}
}

# Loop through the types present in your data and plot them
for v_type in lambda_t.columns:
    if v_type in styles:
        plt.plot(lambda_t.index, lambda_t[v_type], 
                 label=styles[v_type]['label'],
                 color=styles[v_type]['color'],
                 marker=styles[v_type]['marker'],
                 linewidth=2, alpha=0.8)

plt.title(f"Average Hourly Vessel Arrivals $\lambda(t)$ by Type (Pasir Panjang)", fontsize=14)
plt.xlabel("Hour of Day (00:00 - 23:00)", fontsize=12)
plt.ylabel("Avg Arrivals per Hour", fontsize=12)
plt.xticks(range(0, 24))
plt.grid(True, linestyle='--', alpha=0.5)
plt.legend(title="Vessel Type")
plt.tight_layout()

# Save the plot
plt.savefig("docs/vessel_arrivals_by_type.png")
plt.show()


# --- Simple Average ---
# Count total arrivals per hour bin across all 3 months
hourly_counts = df.groupby('hour').size()
total_days = df['date'].nunique()

# Lambda = Average arrivals per hour
lambda_t = hourly_counts / total_days

print("Estimated Hourly Arrival Rates (Lambda):")
print(lambda_t)

# --- VISUALIZATION ---
plt.figure(figsize=(10, 6))
plt.bar(lambda_t.index, lambda_t.values, color='skyblue', edgecolor='black')
plt.title("Estimated Vessel Arrival Intensity $\lambda(t)$ (Pasir Panjang)")
plt.xlabel("Hour of Day")
plt.ylabel("Avg Arrivals per Hour")
plt.xticks(range(0, 24))
plt.grid(axis='y', alpha=0.5)
plt.show()

