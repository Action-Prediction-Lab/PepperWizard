
import argparse
import sys
import threading
import time
import zmq
import numpy as np
from naoqi_proxy import NaoqiClient, NaoqiProxyError

# Global flag to signal the teleoperation thread to stop
teleop_running = threading.Event()

class TeleopThread(threading.Thread):
    """Thread for handling robot teleoperation."""
    def __init__(self, naoqi_client, verbose=False):
        super(TeleopThread, self).__init__()
        self.client = naoqi_client
        self.verbose = verbose # Assign verbose here
        if self.verbose:
            print(f"[TeleopThread.__init__] Verbose mode is: {self.verbose}")
        self.context = zmq.Context()
        self.subscriber = self.context.socket(zmq.SUB)
        # We connect to the dualshock_publisher service by its hostname in the Docker network
        self.subscriber.connect("tcp://172.18.0.1:5556")
        time.sleep(1) # Give time for the connection to establish
        if self.verbose:
            print("[TeleopThread.__init__] Connected to tcp://172.18.0.1:5556")
        self.subscriber.setsockopt_string(zmq.SUBSCRIBE, "")
        if self.verbose:
            print("[TeleopThread.__init__] Subscribed to all ZMQ messages")
        self.motion_service = self.client.ALMotion # Initialize motion service here
        self.alife_service = self.client.ALAutonomousLife
        self.tracker_service = self.client.ALTracker
        self.awareness_service = self.client.ALBasicAwareness
        self.face_service = self.client.ALFaceDetection
        self.social_perception_service = self.client.ALPeoplePerception

    def wake_up(self):
        print("Waking up robot...")
        self.motion_service.wakeUp()
        print("Robot is awake.")

    def rest(self):
        print("Putting robot to rest...")
        self.motion_service.rest()
        print("Robot is at rest.")

    def run(self):
        """Main loop for the teleoperation thread."""
        if self.verbose:
            print("[TeleopThread.run()] Starting thread execution.")
        print(" --- Teleoperation Thread Started ---")
        print(" --- Press 'q' in the main terminal and Enter to stop ---")
        
        motion_service = self.client.ALMotion
        
        # Set stiffness for movement
        motion_service.setStiffnesses("Body", 1.0)

        while not teleop_running.is_set():
            if self.verbose:
                print("[TeleopThread.run()] Loop iteration...")
            
            # Set a timeout to avoid blocking indefinitely
            poll_result = self.subscriber.poll(100) # 100ms timeout
            if poll_result == 0:
                if self.verbose:
                    print("[TeleopThread.run()] ZMQ poll timed out (no message).")
                continue # No message, continue loop
            elif self.verbose:
                print(f"[TeleopThread.run()] ZMQ poll returned: {poll_result} (message available).")

            try:
                message = self.subscriber.recv_json()
                if self.verbose:
                    print(f"[TeleopThread] Received ZMQ message: {message}") # Debug print
                self.handle_controller_input(message)
            except zmq.ZMQError as e:
                print(f"ZMQ Error in TeleopThread: {e}")
                break
            except NaoqiProxyError as e:
                print(f"NAOqi Proxy Error in TeleopThread: {e}")
                break
        
        print("Stopping robot movement...")
        motion_service.stopMove()
        print(" --- Teleoperation Thread Finished ---")

    def handle_controller_input(self, message):
        """Map controller input to robot motion."""
        # These axis names depend on the mappings in the dualshock_publisher.
        # We assume a standard mapping here.
        left_y = message.get("axes", {}).get("left_stick_y", 0.0)
        left_x = message.get("axes", {}).get("left_stick_x", 0.0)
        right_y = message.get("axes", {}).get("right_stick_y", 0.0)
        right_x = message.get("axes", {}).get("right_stick_x", 0.0)

        # Dead zone to prevent drift
        if abs(left_y) < 0.1: left_y = 0
        if abs(left_x) < 0.1: left_x = 0
        if abs(right_y) < 0.1: right_y = 0
        if abs(right_x) < 0.1: right_x = 0

        if self.verbose:
            print(f"[TeleopThread] Axes - LX:{left_x:.2f}, LY:{left_y:.2f}, RY:{right_y:.2f}, RX:{right_x:.2f}")

        self.motion_mapping(self.client.ALMotion, left_x, left_y, right_y, right_x)

    def motion_mapping(self, motion_service, lx, ly, ry, rx):
        """Adapted from the original script's MotionMapping function."""
        v_x = 0.2  # Forward/backward speed
        v_y = 0.2  # Strafe speed
        v_theta = 0.5  # Rotational speed

        command_x = -ly * v_x
        command_y = -lx * v_y
        command_theta = -rx * v_theta

        if self.verbose:
            print(f"[TeleopThread] Sending moveToward: x={command_x:.2f}, y={command_y:.2f}, theta={command_theta:.2f}")
        
        try:
            motion_service.moveToward(command_x, command_y, command_theta)
        except NaoqiProxyError as e:
            print(f"Failed to send move command: {e}")
            teleop_running.set() # Stop the thread on error

    def stop(self):
        """Signal the thread to stop."""
        teleop_running.set()
        self.subscriber.close()
        self.context.term()

def user_input(prompt):
    """Get input from the user."""
    return input(prompt)

def pepper_talk(client):
    """Handle Text-to-Speech functionality."""
    print(" --- Entering PepperTalk --- (type 'q' to exit)")
    tts_service = client.ALTextToSpeech
    
    while True:
        line = user_input("Pepper: ")
        if line.lower() == 'q':
            break
        try:
            tts_service.say(line)
        except NaoqiProxyError as e:
            print(f"TTS Error: {e}")
            break

def battery_status(client):
    """Print the robot's battery charge."""
    try:
        battery_charge = client.ALBattery.getBatteryCharge()
        print(f"Battery Charge: {battery_charge}%")
    except NaoqiProxyError as e:
        print(f"Could not get battery status: {e}")

def SocialState(alife, tracker_service, awareness_service, face_service, interaction_switch):
    alife.setAutonomousAbilityEnabled("BackgroundMovement", interaction_switch)
    alife.setAutonomousAbilityEnabled("BasicAwareness", interaction_switch)
    alife.setAutonomousAbilityEnabled("ListeningMovement", True)
    alife.setAutonomousAbilityEnabled("SpeakingMovement", True)
    alife.setAutonomousAbilityEnabled("AutonomousBlinking", True)
    face_service.setTrackingEnabled(interaction_switch)
    awareness_service.setEnabled(interaction_switch)
    
    basic_AwarenessState = awareness_service.isEnabled()

    print("SocialState Status: " + str(basic_AwarenessState))

    return

def LaunchSocialState(alife, tracker_service, awareness_service, face_service, wizard_command, social_perception):
    tracker_service.unregisterAllTargets()
    tracker_service.setTimeOut(2000)
    awareness_service.setEngagementMode("FullyEngaged")

    social_perception.setMaximumDetectionRange(2.0)
    social_perception.setTimeBeforePersonDisappears(2)
    social_perception.setFastModeEnabled(True)
    social_perception.setMovementDetectionEnabled(True)

    SocialState(alife, tracker_service, awareness_service, face_service, True)
    if wizard_command == 'S':
        tracking_mode = "Head"
    
    tracker_service.setMode(tracking_mode)
    print("Tracking Mode: ", str(tracker_service.getMode()))




def launcher(command, client, teleop_thread, args):
    """Launch actions based on user command."""
    if command.lower() == 'j':
        if teleop_thread is not None and teleop_thread.is_alive():
            print("Teleoperation is already running.")
            return teleop_thread

        print("Launching Joystick Teleoperation...")
        teleop_running.clear()
        thread = TeleopThread(client, verbose=args.verbose)
        thread.start()
        return thread
    
    elif command.lower() == 'w':
        if teleop_thread is None:
            teleop_thread = TeleopThread(client, verbose=args.verbose)
        teleop_thread.wake_up()

    elif command.lower() == 'r':
        if teleop_thread is None:
            teleop_thread = TeleopThread(client, verbose=args.verbose)
        teleop_thread.rest()

    elif command.lower() == 's':
        if teleop_thread is None:
            teleop_thread = TeleopThread(client, verbose=args.verbose)
        LaunchSocialState(teleop_thread.alife_service, teleop_thread.tracker_service, teleop_thread.awareness_service, teleop_thread.face_service, command.upper(), teleop_thread.social_perception_service)

    elif command.lower() == 't':
        pepper_talk(client)

    elif command.lower() == 'bat':
        battery_status(client)

    elif command.lower() == 'q':
        print("Stopping teleoperation if running...")
        if teleop_thread is not None and teleop_thread.is_alive():
            teleop_running.set()
            teleop_thread.join() # Wait for the thread to finish
        return None
        
    else:
        print("Command not recognised. Available commands: J (Joystick), T (Talk), Bat (Battery), q (Quit Joystick)")
    
    return teleop_thread

def print_title():
    print("__________                                   __      __.__                         .__")
    print("\______   \ ____ ______ ______   ___________/  \    /  \__|____________ _______  __| /")
    print(" |     ___// __  \____  \____ \_/ __ \_  __ \   \/\   /  \___   /\__  \_  __ \/ __  | ")
    print(" |    |   \  ___/|  |_> >  |_> >  ___/|  | \/        /|  |/    /  / __ \|  | \/ /_/ | ")
    print(" |____|    \___  >   __/|   __/ \___  >__|    \_/\  / |__/_____ \(____  /__|  \____ | ")
    print("               |__|   |__|                       \/           \/     \/           \/ ")
    print("---------------------------------------------------------------------------------------")
    print(" - jwgcurrie (Refactored for modular architecture)")

def main():
    """Main function to run the PepperWizard application."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-ip", type=str, default="pepper-robot-env",
                        help="IP address of the PepperBox shim server.")
    parser.add_argument("--proxy-port", type=int, default=5000,

                        help="Port number of the PepperBox shim server.")

    parser.add_argument("--verbose", action="store_true",

                        help="Enable verbose debug output.")

    args = parser.parse_args()

    print_title()

    client = None # Initialize client outside try for finally block access

    try:

        client = NaoqiClient(host=args.proxy_ip, port=args.proxy_port)

        # Ping a service to ensure connection

        client.ALTextToSpeech.getAvailableLanguages()

        print(" --- PepperBox Proxy Connected ---")

        print(" --- PepperWizard Ready ---")

        print("Welcome to PepperWizard. Enter 'help' for available commands.")

    except NaoqiProxyError as e:

        print(f"Failed to connect to PepperBox proxy at {args.proxy_ip}:{args.proxy_port}")

        print(f"Error: {e}")

        print("Please ensure the PepperBox container is running and accessible.")

        sys.exit(1)
    
    teleop_thread = None
    try:
        while True:
            command = user_input("Enter Command (type 'help' for options): ")
            
            if command.lower() == 'q' or command.lower() == 'exit':
                print("Shutting down PepperWizard...")
                break
            elif command.lower() == 'help':
                print("Available commands:")
                print("  J    - Start Joystick Teleoperation")
                print("  W    - Wake Up Robot")
                print("  R    - Put Robot to Rest")
                print("  T    - Enter Text-to-Speech mode")
                print("  Bat  - Check Robot Battery Status")
                print("  q    - Exit PepperWizard application")
                print("  exit - Exit PepperWizard application")
            else:
                                # The launcher function now only initiates actions, it doesn't handle 'q' or 'exit'
                
                                teleop_thread = launcher(command, client, teleop_thread, args)
            
    except KeyboardInterrupt:
        print("\nCaught KeyboardInterrupt. Shutting down...")
    finally:
        if teleop_thread is not None and teleop_thread.is_alive():
            teleop_running.set()
            teleop_thread.join()
    
    print(" --- Exiting Pepper Wizard --- ")

if __name__ == "__main__":
    main()
