#!/usr/bin/env python3
import json
import sys
import argparse
import statistics
from datetime import datetime, timedelta
from collections import defaultdict

def parse_args():
    parser = argparse.ArgumentParser(description="Analyze PepperWizard logs for health and performance.")
    parser.add_argument("logfile", help="Path to the JSONL log file")
    parser.add_argument("--gap-threshold", type=float, default=0.2, help="Threshold in seconds to consider a message gap significant (default 0.2s)")
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

if __name__ == "__main__":
    args = parse_args()
    analyze_log(args.logfile, args.gap_threshold)
