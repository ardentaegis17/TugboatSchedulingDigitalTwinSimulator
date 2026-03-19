import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

# 1. Load the results
df = pd.read_csv('results/Vessel_Normalized_Results.csv')

# 2. Descriptive Statistics Summary
summary = df.groupby('Strategy').agg({
    'AvgWait_Hrs': ['mean', 'std'],
    'SafetyScore': ['mean', 'std'],
    'NearMisses': ['mean', 'std'],
}).round(2)
print("Summary Statistics:\n", summary)

# 3. Visualisation: Wait Time and Safety
plt.style.use('seaborn-v0_8-whitegrid')
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 6))

# Plot A: Average Wait Time
sns.boxplot(x='Strategy', y='AvgWait_Hrs', data=df, ax=ax1, palette='viridis')
ax1.set_title('Average Vessel Wait Time by Strategy')
ax1.set_ylabel('Average Wait Time (hours)')

# Plot B: Safety Score
sns.boxplot(x='Strategy', y='SafetyScore', data=df, ax=ax2, palette='viridis')
ax2.set_title('Operational Safety Score by Strategy')
ax2.set_ylabel('Safety Score (%)')

# Plot C: Near Misses
sns.boxplot(x='Strategy', y='NearMisses', data=df, ax=ax3, palette='viridis')
ax3.set_title('Count of Near Misses by Strategy')
ax3.set_ylabel('Near Misses')


plt.tight_layout()
plt.savefig('docs/experiment_results_visualisation.png')


# Plot C: Average Wait Time Histograms
plt.style.use('seaborn-v0_8-whitegrid')
fig, axes = plt.subplots(2, 2, figsize=(15, 10), sharex=True)
axes = axes.flatten()

strategies = ['FCFS', 'Greedy', 'CheapInsertion', 'TabuSearch']
colors = ['#4c72b0', '#55a868', '#c44e52', '#8172b3']

for i, strategy in enumerate(strategies):
    data = df[df['Strategy'] == strategy]['AvgWait_Hrs']
    sns.histplot(data, bins=10, ax=axes[i], color=colors[i], kde=True)
    axes[i].set_title(f'Wait Time Distribution: {strategy}', fontsize=14, fontweight='bold')
    axes[i].set_xlabel('Average Wait Time (Hours/Vessel)', fontsize=12)
    axes[i].set_ylabel('Frequency', fontsize=12)

plt.tight_layout()
plt.savefig('docs/wait_time_histograms.png', dpi=300)
print("Histograms generated and saved.")

# 4. Hypothesis Testing

# Define the groups
fcfs = df[df['Strategy'] == 'FCFS']
greedy = df[df['Strategy'] == 'Greedy']
ci = df[df['Strategy'] == 'CheapInsertion']
ts = df[df['Strategy'] == 'TabuSearch']

# Pairs to compare
comparisons = [
    ('FCFS', 'CheapInsertion'),
    ('FCFS', 'TabuSearch'),
    ('Greedy', 'CheapInsertion'),
    ('Greedy', 'TabuSearch')
]

metrics = ['AvgWait_Hrs', 'SafetyScore', 'NearMisses']

results = []

for s1_name, s2_name in comparisons:
    s1_data = df[df['Strategy'] == s1_name]
    s2_data = df[df['Strategy'] == s2_name]
    
    for metric in metrics:
        t_stat, p_val = stats.ttest_ind(s1_data[metric], s2_data[metric])
        results.append({
            'Comparison': f"{s1_name} vs {s2_name}",
            'Metric': metric,
            't-statistic': round(t_stat, 4),
            'p-value': round(p_val, 10) # Using high precision for small p-values
        })

# Create a DataFrame for the results
results_df = pd.DataFrame(results)
print(results_df)