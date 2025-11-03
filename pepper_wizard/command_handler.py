# Manages and dispatches user commands
from . import cli
from .teleop import TeleopThread, teleop_running

class CommandHandler:
    """Handles user commands and dispatches them to the correct functions."""
    def __init__(self, robot_client, config, verbose=False):
        self.robot_client = robot_client
        self.config = config
        self.verbose = verbose
        self.teleop_thread = None
        self.tracking_modes = ["Head", "WholeBody", "Move"]
        self.current_mode_index = 0
        self.social_state_enabled = False

    def handle_command(self, command):
        """Handles a single user command."""
        command = command.lower()
        if command == 'j':
            self.start_teleop()
        elif command == 'w':
            self.robot_client.wake_up()
        elif command == 'r':
            self.robot_client.rest()
        elif command == 's':
            self.current_mode_index = self.robot_client.toggle_tracking_mode(self.current_mode_index, self.tracking_modes)
        elif command == 'a':
            self.social_state_enabled = self.robot_client.toggle_social_state(self.social_state_enabled)
        elif command == 't':
            cli.pepper_talk_session(self.robot_client, self.config, self.verbose)
        elif command == 'bat':
            self.show_battery_status()
        elif command == 'q':
            self.stop_teleop()
        elif command == 'help':
            cli.print_help()
        else:
            print("Command not recognised.")

    def start_teleop(self):
        """Starts the teleoperation thread."""
        if self.teleop_thread is not None and self.teleop_thread.is_alive():
            print("Teleoperation is already running.")
            return

        print("Launching Joystick Teleoperation...")
        teleop_running.clear()
        self.teleop_thread = TeleopThread(self.robot_client, verbose=self.verbose)
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