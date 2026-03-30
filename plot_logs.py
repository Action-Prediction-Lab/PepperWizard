import matplotlib.pyplot as plt
import csv
import sys
import os

def plot_logs(filename="pid_log.csv"):
    if not os.path.exists(filename):
        print(f"Error: {filename} not found.")
        return

    timestamps = []
    raw_xs = []
    pred_xs = []
    error_xs = []
    outputs = []

    # Read CSV
    # Format: timestamp, raw_x, pred_x, error_x, output_yaw
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            try:
                if len(row) < 5: continue
                timestamps.append(float(row[0]))
                raw_xs.append(float(row[1]))
                pred_xs.append(float(row[2]))
                error_xs.append(float(row[3]))
                outputs.append(float(row[4]))
            except ValueError:
                continue

    if not timestamps:
        print("No valid data found.")
        return

    # Normalize time
    start_time = timestamps[0]
    times = [t - start_time for t in timestamps]

    # Plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # Subplot 1: Position Tracking
    ax1.set_title("Tracking Performance: Target vs Estimate")
    ax1.plot(times, raw_xs, 'ro', markersize=2, label="Raw Detection (Vision 8Hz)", alpha=0.5)
    ax1.plot(times, pred_xs, 'b-', label="Kalman Estimate (Servo 50Hz)", linewidth=1.5)
    ax1.set_ylabel("Pixel X Coordinate")
    ax1.legend()
    ax1.grid(True)

    # Subplot 2: PID Error & Output
    ax2.set_title("Control Loop: Error vs Output")
    ax2.plot(times, error_xs, 'r-', label="Normalized Error", alpha=0.7)
    ax2.plot(times, outputs, 'g-', label="PID Output (Yaw)", alpha=0.7)
    ax2.set_ylabel("Value (-1.0 to 1.0)")
    ax2.set_xlabel("Time (s)")
    ax2.axhline(0, color='black', linewidth=1)
    ax2.legend()
    ax2.grid(True)

    plt.tight_layout()
    output_filename = "tracking_analysis.png"
    plt.savefig(output_filename)
    print(f"Plot saved to {output_filename}")

if __name__ == "__main__":
    plot_logs()
