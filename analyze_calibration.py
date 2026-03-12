import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

def analyze_and_plot(csv_file):
    print(f"\n--- Analyzing {csv_file} ---")
    
    try:
        df = pd.read_csv(csv_file)
    except Exception as e:
        print(f"Error reading {csv_file}: {e}")
        return

    # Check required columns
    required_cols = ['Answer', 'LLM_Answer', 'LLM_Confidence']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
         print(f"Missing columns: {missing_cols}. Skipping.")
         return

    # 1. Correctness Calculation
    # Compare LLM_Answer with True Answer (ignore case, strip whitespace)
    df['is_correct'] = (df['LLM_Answer'].str.strip().str.upper() == 
                        df['Answer'].str.strip().str.upper()).astype(int)

    # Convert confidence to float
    # It might contain "%" signs or be empty/invalid
    def parse_confidence(c):
        try:
            val = str(c).replace('%', '').strip()
            if not val or val == 'nan':
                 return np.nan
            return float(val)
        except Exception:
            return np.nan

    df['Confidence_Percent'] = df['LLM_Confidence'].apply(parse_confidence)
    
    # Drop rows without a valid confidence score
    df_clean = df.dropna(subset=['Confidence_Percent'])
    dropped = len(df) - len(df_clean)
    if dropped > 0:
        print(f"Dropped {dropped} rows with invalid confidence values.")

    accuracy = df_clean['is_correct'].mean()
    mean_conf = df_clean['Confidence_Percent'].mean() / 100.0
    print(f"Overall Accuracy: {accuracy*100:.1f}%")
    print(f"Overall Mean Confidence: {mean_conf*100:.1f}%")

    # 2. Calibration Analysis (Binning)
    # 5 bins: (0-20], (20-40], (40-60], (60-80], (80-100]
    bins = [0, 20, 40, 60, 80, 100]
    labels = ['0-20%', '21-40%', '41-60%', '61-80%', '81-100%']
    
    # Use pd.cut to assign bins
    df_clean['Conf_Bin'] = pd.cut(df_clean['Confidence_Percent'], bins=bins, labels=labels, include_lowest=True)

    # Aggregate by bin
    bin_stats = df_clean.groupby('Conf_Bin', observed=False).agg(
        Mean_Accuracy=('is_correct', 'mean'),
        Mean_Confidence=('Confidence_Percent', 'mean'),
        Count=('is_correct', 'count')
    ).reset_index()

    # Drop empty bins for plotting
    bin_stats = bin_stats[bin_stats['Count'] > 0].copy()

    # Convert Means to 0.0 - 1.0 range for plotting
    bin_stats['Mean_Confidence'] = bin_stats['Mean_Confidence'] / 100.0

    print("\nBin Statistics:")
    print(bin_stats)

    # 3. Visualization: Reliability Diagram
    plot_calibration_curve(bin_stats, csv_file, accuracy, mean_conf)

def plot_calibration_curve(bin_stats, csv_file, accuracy, mean_conf):
    plt.figure(figsize=(8, 8))
    
    # Plot the points (no connecting line)
    plt.plot(bin_stats['Mean_Confidence'], bin_stats['Mean_Accuracy'], marker='o', 
             linestyle='none', label='Model Calibration', color='blue', markersize=8)

    # Draw the Identity Line (perfect calibration) y = x
    plt.plot([0, 1], [0, 1], linestyle='--', color='gray', label='Perfect Calibration (y=x)')

    # Add count labels to points
    for i, row in bin_stats.iterrows():
        plt.annotate(f"n={int(row['Count'])}", 
                     (row['Mean_Confidence'], row['Mean_Accuracy']), 
                     textcoords="offset points", 
                     xytext=(0,10), 
                     ha='center')

    # Formatting the plot
    plt.xlim(0, 1.05)
    plt.ylim(0, 1.05)
    plt.xlabel('Mean Confidence', fontsize=12)
    plt.ylabel('Mean Accuracy (Correctness)', fontsize=12)
    
    # Make a clean title from the filename
    base_name = os.path.basename(csv_file).replace('.csv', '')
    title_text = f"Reliability Diagram: {base_name}\n"
    title_text += f"Accuracy: {accuracy*100:.1f}%, Mean Conf: {mean_conf*100:.1f}%"
    plt.title(title_text, fontsize=14)
    
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc='lower right')

    # Save the plot
    output_png = f"{base_name}_calibration_plot.png"
    plt.savefig(output_png, bbox_inches='tight', dpi=150)
    plt.close()
    print(f"Saved calibration plot to {output_png}")

if __name__ == "__main__":
    # List of CSV files to analyze
    target_files = [
        "mmlu_hard_subset_results_nebula_gpt5.1.csv",
        "mmlu_hard_subset_results_nebula_gpt5.1_rationalist.csv",
        "mmlu_hard_subset_results_nebula_gpt5.1_empiricist.csv",
        "mmlu_hard_subset_results_openai.csv",
        "mmlu_hard_subset_results_council.csv",
    ]
    
    for file in target_files:
        if os.path.exists(file):
             analyze_and_plot(file)
        else:
             print(f"\nWARNING: File not found - {file}")
