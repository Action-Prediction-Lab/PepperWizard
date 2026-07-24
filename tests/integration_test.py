import sys
import os
import time
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pepper_wizard.logger import setup_logging, get_logger
from pepper_wizard.robot_client import RobotClient

LOG_FILE = "logs/integration_test_log.jsonl"
TOL_RAD = 0.02
MIN_FORWARD_M = 0.05
MAX_LATERAL_M = 0.05

_failures = []

def check(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" ({detail})" if detail else ""))
    if not ok:
        _failures.append(label)

def run():
    # Fresh log per run so the record is a single clean run, not appended history.
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    setup_logging(log_file=LOG_FILE, verbose=True)
    get_logger("IntegrationTest")

    print("--- Connecting to sim at localhost:5000 ---")
    try:
        client = RobotClient(host="localhost", port=5000, verbose=True)
    except Exception as e:
        print(f"FATAL: could not connect to robot: {e}")
        sys.exit(1)
    raw = client.client  # raw NaoqiClient for getRobotPosition, not wrapped by RobotClient

    # Action walk drives the event-presence coverage.
    client.wake_up()
    client.toggle_social_state(False)
    client.talk("Testing integration logging.")
    client.play_animation_blocking("animations/Stand/Gestures/Hey_1")

    # Guard: a forward move produces a measurable base displacement.
    pos0 = raw.ALMotion.getRobotPosition(True)
    client.move_toward(0.5, 0.0, 0.0)
    time.sleep(2.0)
    client.stop_move()
    pos1 = raw.ALMotion.getRobotPosition(True)
    dx, dy = pos1[0] - pos0[0], pos1[1] - pos0[1]
    check("base moves forward on move_toward", dx > MIN_FORWARD_M, f"dx={dx:.3f}")
    check("base holds axis (no lateral drift)", abs(dy) < MAX_LATERAL_M, f"dy={dy:.3f}")
    client.move_toward(0.0, 0.5, 0.0)  # second logged MoveCommand for the >=2 count
    client.stop_move()

    # Guard: commanded joint angles are reflected in the read-back.
    joint_names = ["HeadYaw", "HeadPitch"]
    joint_goal = [0.4, -0.2]
    client.set_angles(joint_names, joint_goal, 0.2)
    time.sleep(1.5)
    joint_read = client.get_angles(joint_names)
    check("get_angles returned all joints", len(joint_read) == len(joint_names), f"{joint_read}")
    for name, goal, got in zip(joint_names, joint_goal, joint_read):
        check(f"joint {name} tracks command", abs(got - goal) <= TOL_RAD,
              f"cmd={goal:.3f} read={got:.3f}")

    # Smoke: diagnostics return sane sim constants.
    batt = client.get_battery_charge()
    check("battery charge sane", isinstance(batt, (int, float)) and 0 < batt <= 100, f"{batt}")
    mode = client.get_tracking_mode()
    check("tracking mode is a string", isinstance(mode, str) and bool(mode), repr(mode))
    diag = client.get_temperature_diagnosis()
    check("temp diagnosis shaped [int, list]",
          isinstance(diag, list) and len(diag) == 2
          and isinstance(diag[0], int) and isinstance(diag[1], list), f"{diag}")

    # is_awake(), social-state readback, and joint temperatures are sim-stubbed
    # (always True, always False, {}); asserting them would test the stub, not our code.

    client.rest()

    # Event-presence coverage on the fresh single-run log.
    with open(LOG_FILE) as f:
        events = [json.loads(line)["event"] for line in f]
    for req in ["WakeUp", "Speech", "AnimationStarted", "Rest"]:
        check(f"event {req} logged", req in events)
    check("social state logged", "SocialStateSet" in events)
    check("MoveCommand logged >=2", events.count("MoveCommand") >= 2, f"count={events.count('MoveCommand')}")

    if _failures:
        print(f"\n--- FAILURE: {len(_failures)} check(s) failed: {_failures} ---")
        sys.exit(1)
    print("\n--- SUCCESS: all checks passed ---")

if __name__ == "__main__":
    run()
