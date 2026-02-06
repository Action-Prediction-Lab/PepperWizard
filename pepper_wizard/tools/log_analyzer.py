#!/usr/bin/env python3
import json
import sys
import argparse
import statistics
from datetime import datetime, timedelta
from collections import defaultdict
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

def parse_args():
    parser = argparse.ArgumentParser(description="Analyze PepperWizard logs for health and performance.")
    parser.add_argument("logfile", help="Path to the JSONL log file")
    parser.add_argument("--gap-threshold", type=float, default=0.2, help="Threshold in seconds to consider a message gap significant (default 0.2s)")
    parser.add_argument("--plot", action="store_true", help="Generate a visualization of the session (requires matplotlib)")
    parser.add_argument("--compare", help="Path to another log file to compare against")
    return parser.parse_args()

def analyze_log(filepath, gap_threshold=0.2):
    print(f"--- PepperWizard Log Analysis: {filepath} ---")
    
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error opening file: {e}")
        return

    if not lines:
        print("Log file is empty.")
        return

    # Data Structures
    events = []
    move_commands = []
    battery_levels = []
    temp_warnings = []
    errors = []
    reconnections = []
    
    start_time = None
    last_time = None
    
    # Metrics
    gaps = []
    move_intervals = []

    for line in lines:
        try:
            entry = json.loads(line)
            timestamp = datetime.fromisoformat(entry['timestamp'])
            
            if start_time is None:
                start_time = timestamp
                
            # 1. Gap Detection (Connectivity Health)
            if last_time:
                delta = (timestamp - last_time).total_seconds()
                if delta > gap_threshold:
                    gaps.append((last_time, delta))
            
            last_time = timestamp
            
            # 2. Event Classification
            component = entry.get('component', 'Unknown')
            event_type = entry.get('event', 'Unknown')
            level = entry.get('level', 'INFO')
            data = entry.get('data', {})

            if level in ['ERROR', 'WARNING', 'CRITICAL']:
                errors.append(entry)

            if event_type == 'MoveCommand':
                move_commands.append(timestamp)
                
            elif event_type == 'BatteryStatus':
                charge = data.get('charge')
                if charge is not None:
                    battery_levels.append((timestamp, charge))
                    
            elif event_type == 'TemperatureWarning': # Assuming this event name based on main.py logic logic
                 temp_warnings.append((timestamp, data))
                 
            elif event_type == 'RobotConnectionFailed': # Inferred form main.py
                reconnections.append(timestamp)

        except json.JSONDecodeError:
            continue
        except Exception:
            continue

    if not start_time or not last_time:
        print("No valid timestamps found.")
        return

    duration = (last_time - start_time).total_seconds()
    
    # --- Analysis & Reporting ---
    
    # 1. Connectivity Health
    print(f"\n[Connectivity Health]")
    print(f"  Session Duration: {duration:.2f}s")
    
    gap_count = len(gaps)
    # Estimate expected packets (approx 50Hz for joints + others)
    # This is a rough heuristic.
    
    print(f"  Significant Gaps (> {gap_threshold}s): {gap_count}")
    if gap_count > 0:
        avg_gap = sum(g for _, g in gaps) / gap_count
        max_gap = max(g for _, g in gaps)
        print(f"    Avg Gap: {avg_gap:.3f}s")
        print(f"    Max Gap: {max_gap:.3f}s")
    
    if reconnections:
         print(f"  Reconnection Events: {len(reconnections)}")
    else:
         print(f"  Reconnection Events: 0 (Stable)")

    # 2. Responsiveness Health (Jitter)
    print(f"\n[Responsiveness Health]")
    jitter = 0.0 # Default if not enough data
    if len(move_commands) > 1:
        # Calculate inter-arrival times for move commands
        for i in range(1, len(move_commands)):
            interval = (move_commands[i] - move_commands[i-1]).total_seconds()
            # Filter out large pauses (user likely stopped moving joystick)
            if interval < 1.0: 
                move_intervals.append(interval)
        
        if move_intervals:
            avg_interval = statistics.mean(move_intervals)
            jitter = statistics.stdev(move_intervals) if len(move_intervals) > 1 else 0.0
            hz = 1.0 / avg_interval if avg_interval > 0 else 0
            
            print(f"  Move Command Freq: {hz:.2f} Hz (Target: ~50Hz)")
            print(f"  Jitter (StdDev):   {jitter*1000:.2f} ms")
            
            # Grade Jitter
            if jitter < 0.005: status = "Excellent"
            elif jitter < 0.010: status = "Good"
            else: status = "Poor (Network Latency Risk)"
            print(f"  Stability Status:  {status}")
        else:
             print("  No continuous move sequences found.")
    else:
        print("  Insufficient MoveCommands for analysis.")

    # 3. Robot Health (Battery & Temp)
    print(f"\n[Robot Health]")
    if battery_levels:
        start_charge = battery_levels[0][1]
        end_charge = battery_levels[-1][1]
        charge_delta = start_charge - end_charge
        
        # Extrapolate to hourly rate
        hours = duration / 3600.0
        drain_rate = (charge_delta / hours) if hours > 0.05 else 0
        
        print(f"  Battery: {start_charge}% -> {end_charge}%")
        print(f"  Drain:   {charge_delta}% ({drain_rate:.1f}%/hr)")
    else:
        print("  No Battery data found.")

    if temp_warnings:
        print(f"  Temperature Warnings: {len(temp_warnings)}")
        # Print first/last unique ones
        seen_warnings = set()
        for t, data in temp_warnings:
            msg = data.get('warning', 'Unknown') # Adjust key based on actual log structure
            if msg not in seen_warnings:
                 print(f"    {t.strftime('%H:%M:%S')} - {msg}")
                 seen_warnings.add(msg)
    else:
        print("  Temperature: Normal")

    # 4. Systems Health (Errors)
    print(f"\n[System Health]")
    if errors:
        print(f"  Errors/Warnings: {len(errors)}")
        # Summarize by component
        comp_counts = defaultdict(int)
        for e in errors:
            comp_counts[f"{e.get('component')}:{e.get('event')}"] += 1
        
        for k, v in comp_counts.items():
            print(f"    {k}: {v}")
    else:
        print(f"  Errors/Warnings: 0 (Clean)")

    # 5. Overall Score
    print(f"\n[Summary Score]")
    score = 100
    deductions = []
    
    # Penalize Gaps
    if gap_count > 0:
        pen = min(30, gap_count * 2)
        score -= pen
        deductions.append(f"-{pen} for connectivity gaps")
        
    # Penalize Jitter
    if move_intervals and jitter > 0.010:
        score -= 20
        deductions.append("-20 for high jitter")
        
    # Penalize Errors
    if errors:
        pen = min(20, len(errors))
        score -= pen
        deductions.append(f"-{pen} for system errors")
        
    # Penalize Reconnections
    if reconnections:
        score -= 20
        deductions.append("-20 for reconnections")

    score = max(0, score)
    print(f"  Health Score: {score}/100")
    if deductions:
        print(f"  Result: {', '.join(deductions)}")

    metrics = {
        "duration": duration,
        "gap_count": gap_count,
        "avg_gap": sum(g for _, g in gaps) / gap_count if gap_count else 0,
        "jitter": jitter,
        "battery_drain": charge_delta if battery_levels else 0,
        "errors": len(errors),
        "score": score,
        "move_intervals": move_intervals,
        "move_timestamps": move_commands,
        "start_time": start_time # Needed for plotting relative time
    }
    
    # 6. Periodicity Check (New)
    check_periodicity(move_intervals, move_commands)
    
    return metrics, events, gaps, battery_levels

def check_periodicity(intervals, timestamps):
    if not intervals or len(intervals) < 10: return
    
    # 1. Identify Spikes (>50ms)
    SPIKE_THRESHOLD = 0.050 
    spike_times = []
    for i, val in enumerate(intervals):
        if val > SPIKE_THRESHOLD:
            spike_times.append(timestamps[i])

    if len(spike_times) < 3:
        print("\n[Pattern Analysis]")
        print("  Not enough spikes to detect a pattern.")
        return

    # 2. Cluster Spikes into Bursts
    # If two spikes are closer than 1.0s, they belong to the same burst
    BURST_GAP = 1.0
    burst_starts = [spike_times[0]]
    current_burst_end = spike_times[0]
    
    burst_counts = [] # Spikes per burst
    current_count = 1
    
    for t in spike_times[1:]:
        delta = (t - current_burst_end).total_seconds()
        if delta < BURST_GAP:
            # Continue burst
            current_burst_end = t
            current_count += 1
        else:
            # New burst
            burst_starts.append(t)
            burst_counts.append(current_count)
            current_burst_end = t
            current_count = 1
    burst_counts.append(current_count) # Last one

    # 3. Analyze Burst Periodicity
    print(f"\n[Pattern Analysis]")
    print(f"  Total Spikes: {len(spike_times)}")
    print(f"  Detected Bursts: {len(burst_starts)}")
    
    if len(burst_starts) < 3:
        print("  >> Random/Continuous Spiking (No distinct bursts).")
        return

    inter_burst_times = []
    for i in range(1, len(burst_starts)):
        delta = (burst_starts[i] - burst_starts[i-1]).total_seconds()
        inter_burst_times.append(delta)

    avg_period = statistics.mean(inter_burst_times)
    std_period = statistics.stdev(inter_burst_times) if len(inter_burst_times) > 1 else 0
    avg_spikes_per_burst = statistics.mean(burst_counts)

    print(f"  Avg Burst Interval: {avg_period:.4f}s")
    print(f"  Interval Stability (Std): {std_period:.4f}s")
    print(f"  Avg Spikes/Burst: {avg_spikes_per_burst:.1f}")

    if std_period < 1.0: # Fairly strict stability
        print(f"  >> PERIODIC BURST PATTERN DETECTED: Every ~{avg_period:.1f}s")
    else:
        print(f"  >> Bursts appear irregular.")

def compare_sessions(current_metrics, ref_metrics, ref_file):
    print(f"\n--- SESSION COMPARISON ---")
    print(f"Current: [This File] | Reference: [{ref_file}]")
    print("-" * 75)
    print(f"{'Metric':<20} | {'Current':<15} | {'Reference':<15} | {'Diff':<10}")
    print("-" * 75)
    
    # helper
    def print_row(name, key, fmt="{:.2f}"):
        v1 = current_metrics.get(key, 0)
        v2 = ref_metrics.get(key, 0)
        diff = v1 - v2
        
        s1 = fmt.format(v1)
        s2 = fmt.format(v2)
        sdiff = fmt.format(diff)
        if diff > 0: sdiff = "+" + sdiff
        
        print(f"{name:<20} | {s1:<15} | {s2:<15} | {sdiff:<10}")

    print_row("Duration (s)", "duration")
    print_row("Health Score", "score", "{:.0f}")
    print_row("Jitter (ms)", "jitter", "{:.4f}")
    print_row("Gap Count", "gap_count", "{:.0f}")
    print_row("Battery Drain (%)", "battery_drain", "{:.1f}")
    print_row("Errors", "errors", "{:.0f}")
    print("-" * 75)

def plot_session(metrics, events, gaps, battery_levels):
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib not installed. Cannot generate plot.")
        return

    print("Generating session_visualization.png...")
    
    # Prepare Data
    move_times = metrics['move_timestamps'] 
    if len(move_times) < 2:
        print("Not enough data to plot.")
        return
        
    start_t = move_times[0]
    
    # Recalculate intervals locally to ensure X (Time) and Y (Latency) are aligned
    # (The metrics['move_intervals'] may have had gaps filtered out, causing mismatch)
    t_axis = []
    latency_axis = []
    
    for i in range(1, len(move_times)):
        dt = (move_times[i] - move_times[i-1]).total_seconds()
        # Optional: Filter drastic outliers if they mess up the graph, 
        # but seeing the spikes is the point. Let's filter > 2s to avoid compressing the Y axis too much
        if dt < 2.0: 
            rel_t = (move_times[i] - start_t).total_seconds()
            t_axis.append(rel_t)
            latency_axis.append(dt * 1000)

    if not t_axis:
        print("No valid intervals to plot.")
        return

    fig, ax1 = plt.figure(figsize=(12, 6)), plt.gca()
    
    # 1. Latency (Left Axis)
    ax1.set_xlabel('Session Time (s)')
    ax1.set_ylabel('Command Interval (ms)', color='tab:blue')
    ax1.plot(t_axis, latency_axis, color='tab:blue', alpha=0.6, linewidth=1, label='Command Interval')
    ax1.tick_params(axis='y', labelcolor='tab:blue')
    
    # Threshold line 20ms
    ax1.axhline(y=20, color='green', linestyle='--', alpha=0.5, label='Target (20ms)')
    
    # 2. Battery (Right Axis)
    if battery_levels:
        ax2 = ax1.twinx()
        ax2.set_ylabel('Battery (%)', color='tab:orange')
        bat_t = [(t - start_t).total_seconds() for t, _ in battery_levels]
        bat_v = [v for _, v in battery_levels]
        ax2.plot(bat_t, bat_v, color='tab:orange', linestyle='-', linewidth=2, label='Battery')
        ax2.tick_params(axis='y', labelcolor='tab:orange')
        # Force 0-100 scale? Maybe just generic
        ax2.set_ylim(0, 100)

    # 3. Gaps
    for gap_t, duration in gaps:
        relative_t = (gap_t - start_t).total_seconds()
        plt.axvline(x=relative_t, color='red', alpha=0.3, ymax=0.1)

    plt.title(f"Session Health: Jitter {metrics['jitter']*1000:.1f}ms | Score {metrics['score']}")
    fig.tight_layout()
    plt.savefig('session_visualization.png')
    print("Saved to session_visualization.png")

if __name__ == "__main__":
    args = parse_args()
    
    # 1. Analyze Main File
    print(f"\n>>> PROCESSING: {args.logfile}")
    res = analyze_log(args.logfile, args.gap_threshold)
    if not res:
        sys.exit(1)
        
    metrics, events, gaps, battery_levels = res
    
    # 2. Comparison
    if args.compare:
        print(f"\n>>> PROCESSING REFERENCE: {args.compare}")
        res_ref = analyze_log(args.compare, args.gap_threshold)
        if res_ref:
            ref_metrics, _, _, _ = res_ref
            compare_sessions(metrics, ref_metrics, args.compare)
    
    # 3. Plotting
    if args.plot and metrics:
        plot_session(metrics, events, gaps, battery_levels)
