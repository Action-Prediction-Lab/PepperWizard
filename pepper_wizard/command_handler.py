import time
import threading
import zmq
import json

# Manages and dispatches operator commands
from . import cli
from .teleop import TeleopThread, ZMQTeleopController, teleop_running
from .keyboard_teleop import KeyboardTeleopController
from .exp_behaviors.behaviors import gaze_at_marker

class ZMQCommandListener(threading.Thread):
    """Listens for external JSON commands on TCP 5561."""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.running = threading.Event()
        self.running.set()
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        try:
            self.socket.bind("tcp://*:5561")
        except zmq.ZMQError as e:
            print(f"ERROR: Could not bind Command Listener to port 5561: {e}")
            print("External commands will NOT be available.")
            self.running.clear()
            self.socket.close()
            self.context.term()
            return
        
    def run(self):
        print("External Command Listener bound to tcp://*:5561")
        while self.running.is_set():
            try:
                # Poll to allow checking running flag
                if self.socket.poll(timeout=200):
                    msg = self.socket.recv_json()
                    response = {"status": "ok", "message": "Command received"}
                    
                    try:
                        if self.callback:
                            self.callback(msg)
                    except Exception as e:
                        print(f"Error processing external command: {e}")
                        response = {"status": "error", "message": str(e)}
                        
                    self.socket.send_json(response)
            except zmq.ZMQError as e:
                if self.running.is_set():
                    print(f"ZMQ Error in CommandListener: {e}")
            except Exception as e:
                print(f"Error in CommandListener loop: {e}")
                
        self.socket.close()
        self.context.term()

    def stop(self):
        self.running.clear()

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
        self.suppressed_social_state = False 
        
        from .orchestrators.tracking_orchestrator import TrackingOrchestrator
        self.tracker = TrackingOrchestrator(robot_client)
        self.tracker.start()
        
        from .logger import get_logger
        self.logger = get_logger("CommandHandler")

        # External Command Listener
        self.cmd_listener = ZMQCommandListener(self._handle_external_command)
        self.cmd_listener.start()

    def _handle_external_command(self, msg):
        """Callback for external ZMQ commands."""
        # Expected format: {"command": "track", "target": "bottle"}
        cmd_type = msg.get("command")
        
        if cmd_type == "track":
            target = msg.get("target")
            if target:
                # print(f"External CMD: Tracking {target}")
                self._suppress_social()
                self.tracker.set_target(target)
            else:
                # print("External CMD: Stop Tracking")
                self.tracker.set_target(None)
                self._restore_social()
        elif cmd_type == "stop_track":
             # print("External CMD: Stop Tracking")
             self.tracker.set_target(None)
             self._restore_social()
        else:
            print(f"Unknown external command: {cmd_type}")

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
            desired_state = teleop_state.get('robot_state', 'Rest')
            if desired_state == "Wake":
                 self.robot_client.wake_up()
            else:
                 self.robot_client.rest()
        elif command == 's':
            desired_mode = teleop_state.get('tracking_mode', 'Head')
            self.robot_client.set_tracking_mode(desired_mode)
        elif command == 'a':
            # Set Social State based on selection
            desired_mode = teleop_state.get('social_mode', 'Disabled')
            should_enable = (desired_mode == "Autonomous")
            
            self.social_state_enabled = self.robot_client.set_social_state(should_enable)
            if self.social_state_enabled:
                 # If operator turns social state ON, it OVERRIDES tracking
                 if self.tracker.active_target_label:
                      print("!!! Social State Enabled: Deactivating Tracking Override...")
                      self.tracker.set_target(None)
                      self.suppressed_social_state = False
        elif command == 't':
            cli.pepper_talk_session(self.robot_client, self.config, self.verbose)
        elif command == 'tm':
            from .cli import show_temperature_view
            show_temperature_view(self.robot_client, self.config)

        elif command == 'gm': 
            if self.is_teleop_running():
                print("Stopping active Teleop for Marker Behavior...")
                self.stop_teleop()
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
            # Force "Head" tracking mode to prevent "Move" conflict during Joystick control
            print("Safeguard: Forcing Tracking Mode to 'Head' and Disabling Social State for Joystick control.")
            
            # 1. Force Head Mode
            if hasattr(self.robot_client, 'set_tracking_mode'):
                 self.robot_client.set_tracking_mode("Head")

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

    def is_teleop_running(self):
        """Returns True if the teleoperation thread is active."""
        return self.teleop_thread is not None and self.teleop_thread.is_alive()

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
            # print(">>> Tracking Started: Auto-suppressing Social State...")
            self.robot_client.set_social_state(False)
            self.social_state_enabled = False
            self.suppressed_social_state = True

    def _restore_social(self):
        """Restores social state if it was auto-disabled."""
        if self.suppressed_social_state:
            # print("<<< Tracking Ended: Restoring Social State...")
            self.robot_client.set_social_state(True)
            self.social_state_enabled = True
            self.suppressed_social_state = False

    def cleanup(self):
        """Cleans up resources, like stopping the teleop thread."""
        if hasattr(self, 'cmd_listener') and self.cmd_listener:
             self.cmd_listener.stop()
             
        self.stop_teleop()
        self._restore_social()
        if self.tracker:
            self.tracker.stop()