"""
This module contains specific, high-level robot behaviors for the VPT experiment (2025.11).

Unlike the main application logic, this module can contain less generic,
"one-off" behaviors that are triggered by the CommandHandler.
"""
import time

TO_RAD = 0.017453292519943295

def gaze_at_marker(robot_client, marker_id, marker_size, search_timeout):
    """
    Makes the robot find and gaze at a specific NAOqi marker.
    This function contains the direct implementation of the behavior.
    """
    print(f"Attempting to gaze at NAOqi marker ID: {marker_id}")
    t0 = time.time()
    
    # Access NAOqi services directly via the NaoqiClient wrapper
    alife = robot_client.client.ALAutonomousLife
    tracker_service = robot_client.client.ALTracker
    motion_service = robot_client.client.ALMotion
    landmark_service = robot_client.client.ALLandMarkDetection
    memory_service = robot_client.client.ALMemory
    awareness_service = robot_client.client.ALBasicAwareness
    face_service = robot_client.client.ALFaceDetection

    # --- Disable SocialState and Autonomous Behaviors ---
    print("Disabling autonomous behaviors for landmark search...")
    alife.setAutonomousAbilityEnabled("BackgroundMovement", False)
    alife.setAutonomousAbilityEnabled("BasicAwareness", False)
    alife.setAutonomousAbilityEnabled("ListeningMovement", False) 
    alife.setAutonomousAbilityEnabled("SpeakingMovement", False)
    alife.setAutonomousAbilityEnabled("AutonomousBlinking", False)

    face_service.setTrackingEnabled(False)
    awareness_service.setEnabled(False)

    # --- Tracker setup ---
    print("Setting up tracker...")
    landmark_service.subscribe("Test_LandMark", 500, 0.0)
    tracker_service.unregisterAllTargets()
    tracker_service.setEffector("None") 
    tracker_service.toggleSearch(False) 
    
    target_name = "LandMark"
    tracker_service.registerTarget(target_name, [marker_size, [marker_id]]) 
    tracker_service.setMode("Head")

    # Initial lookAt to position the robot where the landmark is expected to be
    initial_look_position = [2.27, 0.17, -0.27] 
    position_frame = 2 # FRAME_ROBOT
    fractional_speed = 0.05
    use_whole_body = True
    print(f"Executing initial lookAt to position: {initial_look_position}")
    tracker_service.lookAt(initial_look_position, position_frame, fractional_speed, use_whole_body)

    # --- Task Posture (Breath and LRArm_position) ---
    print("Setting task posture...")
    motion_service.setBreathConfig([["Bpm", 15.0], ["Amplitude", 0.99]])
    motion_service.setBreathEnabled("Legs", True)

    motion_service.setExternalCollisionProtectionEnabled("RArm", False)
    motion_service.setExternalCollisionProtectionEnabled("LArm", False)
    joint_names_lr = ("RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw",
                      "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw")
    
    arm_lr_angles_deg = [45, -0.5, 0, 36, 90, 45, -0.5, 0, -36, -90]
    arm_lr_angles_rad = [x * TO_RAD for x in arm_lr_angles_deg]
    motion_service.setAngles(joint_names_lr, arm_lr_angles_rad, 0.1)
    print("Robot has successfully entered task posture.")

    # --- Landmark Detection Loop ---
    landmark_found = False
    time_elapsed = 0
    print("Starting landmark detection loop...")
    while not landmark_found and (time_elapsed < search_timeout):
        t1 = time.time()
        time_elapsed = t1 - t0
        try:
            val = memory_service.getData("LandmarkDetected", 0)
            if val and len(val) > 1 and len(val[1]) > 0:
                mark_info_list = val[1]
                if len(mark_info_list) > 0:
                    first_mark_info = mark_info_list[0]
                    if len(first_mark_info) > 1:
                        extra_info = first_mark_info[1] # This is [markID]
                        if len(extra_info) > 0:
                            detected_id = extra_info[0]
                            # Now register and track the detected landmark
                            tracker_service.registerTarget(target_name, [marker_size, extra_info]) # Legacy fix: extra_info is already [id]
                            tracker_service.track(target_name)
                            landmark_found = True
                            print(f"Found Landmark ID {detected_id} - Centering gaze (3s)...")
                            # Wait for tracker to center the head
                            time.sleep(3.0)
                            tracker_service.stopTracker()
                            print(f"Gaze centered on Landmark {detected_id}.")
                            
                            # Reduce stiffness to prevent overheating while holding position
                            print("Reducing Head stiffness to 0.4 to prevent overheating...")
                            motion_service.setStiffnesses("Head", 0.4)
            
        except Exception:
            pass

        if not landmark_found:
            print(f"Searching for landmark... {round((search_timeout - time_elapsed), 1)}s remaining.")
            time.sleep(0.5)

    landmark_service.unsubscribe("Test_LandMark")
    
    if not landmark_found:
        print(f"Landmark search timed out after {search_timeout}s.")
        tracker_service.stopTracker()


    print("Gaze at marker behavior finished.")
    return landmark_found