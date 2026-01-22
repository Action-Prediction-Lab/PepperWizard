import time

# Manages and dispatches operator commands
from . import cli
from .teleop import TeleopThread, ZMQTeleopController, teleop_running
from .keyboard_teleop import KeyboardTeleopController
from .exp_behaviors.behaviors import gaze_at_marker # Import the behavior function

class CommandHandler:
    """Handles user commands and dispatches them to the correct functions."""
    def __init__(self, robot_client, config, verbose=False):
        self.robot_client = robot_client
        self.config = config
        self.verbose = verbose
        self.teleop_thread = None
        self.tracking_modes = ["Head", "WholeBody", "Move"]
        self.current_mode_index = 0
        self.social_state_enabled = False # This state should ideally be managed by a dedicated social state module or the robot_client
        
        from .vision_client import VisionClient
        self.vision_client = VisionClient(robot_client)
        self.vision_client.start()
        
        from .logger import get_logger
        self.logger = get_logger("CommandHandler")

    def handle_command(self, command, teleop_state=None):
        """Handles a single user command."""
        self.logger.info("CommandReceived", {"command": command})
        command = command.lower()
        if command == 'j':
            # Toggle Teleop
            if self.teleop_thread is not None and self.teleop_thread.is_alive():
                 self.stop_teleop()
            else:
                 self.start_teleop(teleop_state)
        elif command == 'w':
            self.robot_client.wake_up()
        elif command == 'r':
            self.robot_client.rest()
        elif command == 's':
            # self.current_mode_index = self.robot_client.toggle_tracking_mode(self.current_mode_index, self.tracking_modes)
            current_mode_name = self.tracking_modes[self.current_mode_index]
            new_mode = cli.select_tracking_mode(current_mode_name)
            if new_mode:
                self.robot_client.set_tracking_mode(new_mode)
                if new_mode in self.tracking_modes:
                    self.current_mode_index = self.tracking_modes.index(new_mode)
        elif command == 'a':
            self.social_state_enabled = self.robot_client.toggle_social_state(self.social_state_enabled)
        elif command == 't':
            cli.pepper_talk_session(self.robot_client, self.config, self.verbose)
        elif command == 'bat':
            self.show_battery_status()
        elif command == 'gm': # Call the gaze_at_marker function from the new behaviors module
            gaze_at_marker(self.robot_client, marker_id=119, marker_size=0.22, search_timeout=10)
        elif command == 'q':
            self.stop_teleop()
        elif command == 'help':
            cli.print_help()
        elif command == 'tr':
            # Interactive Tracking Setup
            target = cli.get_tracking_target()
            if target:
                print(f"Tracking: {target}")
                self.vision_client.set_target(target)
            else:
                print("Stopping tracking.")
                self.vision_client.set_target(None)
        elif command.startswith('track '):
            # Keep legacy slash support just in case
            target = command.split(' ', 1)[1]
            print(f"Tracking: {target}")
            self.vision_client.set_target(target)
        elif command == 'stoptrack':
            print("Stopping tracking.")
            self.vision_client.set_target(None)
        else:
            print("Command not recognised.")

    def start_teleop(self, teleop_state=None):
        """Starts the teleoperation thread."""
        if self.teleop_thread is not None and self.teleop_thread.is_alive():
            print("Teleoperation is already running.")
            return

        mode = teleop_state.get('mode', 'Joystick') if teleop_state else 'Joystick'
        print(f"Launching {mode} Teleoperation...")
        
        teleop_running.clear()
        
        if mode == 'Keyboard':
            # Keyboard teleop must run in the main thread (blocking) to capture input
            controller = KeyboardTeleopController(self.robot_client, config=self.config, verbose=self.verbose)
            controller.run()
            # After it returns, it's done
            self.teleop_thread = None
        else:
            self.teleop_thread = ZMQTeleopController(self.robot_client, config=self.config, verbose=self.verbose)
            self.teleop_thread.start()

    def stop_teleop(self):
        """Stops the teleoperation thread."""
        if self.teleop_thread is not None and self.teleop_thread.is_alive():
            print("Stopping teleoperation...")
            teleop_running.set()
            self.teleop_thread.join() # Wait for the thread to finish
            self.teleop_thread = None
        else:
            print("Teleoperation is not running.")

    def show_battery_status(self):
        """Prints the robot's battery charge."""
        battery_charge = self.robot_client.get_battery_charge()
        if battery_charge is not None:
            print(f"Battery Charge: {battery_charge}%")

    def cleanup(self):
        """Cleans up resources, like stopping the teleop thread."""
        self.stop_teleop()
        if self.vision_client:
            self.vision_client.stop()