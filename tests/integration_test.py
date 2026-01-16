import sys
import os
import time
import json
import logging

# Ensure parent dir is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pepper_wizard.logger import setup_logging, get_logger
from pepper_wizard.robot_client import RobotClient

def verify_full_stack_logging():
    log_file = "logs/integration_test_log.jsonl"
    
    # 1. Setup Logging
    print(f"--- Setting up logging to {log_file} ---")
    setup_logging(log_file, verbose=True)
    logger = get_logger("IntegrationTest")
    
    # 2. Connect to Robot
    host = "localhost" 
    port = 5000
    
    print(f"--- Connecting to Robot at {host}:{port} ---")
    try:
        client = RobotClient(host=host, port=port, verbose=True)
    except Exception as e:
        print(f"FATAL: Could not connect to robot: {e}")
        sys.exit(1)
        
    # 3. Perform Actions
    print("--- Performing Actions ---")
    
    # Action: Wake Up 
    print("Action: Wake Up")
    client.wake_up()

    # Action A: Social State Toggle
    print("Action: Toggle Social State")
    client.toggle_social_state(False)
    
    # Action B: Speech
    print("Action: Speech")
    client.talk("Testing integration logging.")
    
    # Action C: Animation
    print("Action: Animation")
    # Using a common animation that should exist
    client.play_animation_blocking("animations/Stand/Gestures/Hey_1")
    
    # Action D: Movement (with throttle check)
    print("Action: Movement (Throttled)")
    # Move 1
    client.move_toward(0.5, 0.0, 0.0)
    # Move 2 (Should be throttled)
    client.move_toward(0.5, 0.0, 0.0)
    
    time.sleep(2.0) # Wait for throttle and for movement to happen visibly
    
    # Move 3 (Should log)
    client.move_toward(0.0, 0.5, 0.0)
    
    # Stop
    client.stop_move()
    
    # Action: Rest
    print("Action: Rest")
    client.rest()
    
    # 4. Verify Log Content
    print(f"--- Verifying Log File: {log_file} ---")
    
    if not os.path.exists(log_file):
        print("FAILURE: Log file was not created.")
        sys.exit(1)
        
    with open(log_file, 'r') as f:
        lines = f.readlines()
        
    logs = [json.loads(line) for line in lines]
    print(f"Found {len(logs)} log entries.")
    
    # Check for specific events
    events = [l['event'] for l in logs]
    print(f"Events found: {events}")
    
    required_events = [
        "WakeUp",
        "Speech",
        "AnimationStarted",
        "MoveCommand", # Should appear at least twice
        "Rest"
    ]
    
    missing = []
    for req in required_events:
        if req not in events:
            missing.append(req)
            
    # Check Social State (Success or Error)
    if "SocialStateToggled" not in events and "SocialStateError" not in events:
        missing.append("SocialStateToggled/Error")
            
    # Check throttling
    move_count = events.count("MoveCommand")
    
    if missing:
        print(f"FAILURE: Missing expected events: {missing}")
        sys.exit(1)
        
    if move_count < 2:
        print(f"FAILURE: Expected at least 2 MoveCommand events, found {move_count}")
        sys.exit(1)
        
    print("--- SUCCESS: All checks passed! ---")
    # Clean up
    # os.remove(log_file)

if __name__ == "__main__":
    verify_full_stack_logging()
