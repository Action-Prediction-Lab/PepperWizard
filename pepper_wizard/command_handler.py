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
        
        # Synchronize with robot social state
        self.social_state_enabled = self.robot_client.get_social_state()
        self.suppressed_social_state = False # Flag to remember if we auto-disabled social state
        
        from .orchestrators.tracking_orchestrator import TrackingOrchestrator
        self.tracker = TrackingOrchestrator(robot_client)
        self.tracker.start()
        
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
            current_mode_name = self.tracking_modes[self.current_mode_index]
            new_mode = cli.select_tracking_mode(current_mode_name)
            if new_mode:
                self.robot_client.set_tracking_mode(new_mode)
                if new_mode in self.tracking_modes:
                    self.current_mode_index = self.tracking_modes.index(new_mode)
        elif command == 'a':
            # Manual Toggle: Social State Overrides Tracking
            self.social_state_enabled = self.robot_client.toggle_social_state(self.social_state_enabled)
            if self.social_state_enabled:
                 # If operator turns social state ON, it OVERRIDES tracking
                 if self.tracker.active_target_label:
                      print("!!! Social State Enabled: Deactivating Tracking Override...")
                      self.tracker.set_target(None)
                      self.suppressed_social_state = False
        elif command == 't':
            cli.pepper_talk_session(self.robot_client, self.config, self.verbose)
        elif command == 'bat':
            self.show_battery_status()
        elif command == 'gm': 
            self.tracker.yield_control()
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
                self._suppress_social()
                self.tracker.set_target(target)
            else:
                print("Stopping tracking.")
                self.tracker.set_target(None)
                self._restore_social()
        elif command.startswith('track '):
            target = command.split(' ', 1)[1]
            print(f"Tracking: {target}")
            self._suppress_social()
            self.tracker.set_target(target)
        elif command == 'stoptrack':
            print("Stopping tracking.")
            self.tracker.set_target(None)
            self._restore_social()
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
            controller = KeyboardTeleopController(self.robot_client, config=self.config, verbose=self.verbose)
            controller.run()
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

    def _suppress_social(self):
        """Auto-disables social state when tracking starts."""
        # Query robot for truth
        real_social_state = self.robot_client.get_social_state()
        if real_social_state:
            print(">>> Tracking Started: Auto-suppressing Social State...")
            self.robot_client.set_social_state(False)
            self.social_state_enabled = False
            self.suppressed_social_state = True

    def _restore_social(self):
        """Restores social state if it was auto-disabled."""
        if self.suppressed_social_state:
            print("<<< Tracking Ended: Restoring Social State...")
            self.robot_client.set_social_state(True)
            self.social_state_enabled = True
            self.suppressed_social_state = False

    def cleanup(self):
        """Cleans up resources, like stopping the teleop thread."""
        self.stop_teleop()
        self._restore_social()
        if self.tracker:
            self.tracker.stop()