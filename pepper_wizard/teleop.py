# Teleoperation logic
import threading
import time
import zmq
from abc import ABC, abstractmethod
from naoqi_proxy import NaoqiProxyError

# Global flag to signal the teleoperation thread to stop
teleop_running = threading.Event()

class BaseTeleopController(threading.Thread, ABC):
    """Base class for teleoperation controllers."""
    def __init__(self, robot_client, config, verbose=False):
        super(BaseTeleopController, self).__init__()
        from .logger import get_logger
        self.logger = get_logger(self.__class__.__name__)
        self.robot_client = robot_client
        self.config = config
        self.verbose = verbose

    @abstractmethod
    def run(self):
        """Main loop for the controller."""
        pass

    def motion_mapping(self, lx, ly, ry, rx):
        """
        Maps generic joystick axes to robot motion.
        lx, ly: Left stick (Strafe/Forward)
        ry, rx: Right stick (Turn)
        All inputs expected to be in range [-1.0, 1.0]
        """
        speeds = self.config.teleop_config.get("speeds", {})
        v_x = speeds.get("v_x", 0.2)
        v_y = speeds.get("v_y", 0.2)
        v_theta = speeds.get("v_theta", 0.5)

        command_x = -ly * v_x
        command_y = -lx * v_y
        command_theta = -rx * v_theta

        if self.verbose:
            print(f"[{self.__class__.__name__}] Sending moveToward: x={command_x:.2f}, y={command_y:.2f}, theta={command_theta:.2f}")
        
        try:
            self.robot_client.move_toward(command_x, command_y, command_theta)
        except NaoqiProxyError as e:
            print(f"Failed to send move command: {e}")
            self.stop_signal() 

    def stop_signal(self):
        """Sets the global stop event."""
        teleop_running.set()

    def stop_robot(self):
        """Stops the robot movement."""
        print("Stopping robot movement...")
        self.robot_client.stop_move()
        self.logger.info("TeleopStopped")


class ZMQTeleopController(BaseTeleopController):
    """Thread for handling robot teleoperation via ZMQ (DualShock)."""
    def __init__(self, robot_client, config, verbose=False):
        super(ZMQTeleopController, self).__init__(robot_client, config, verbose)
        self.context = zmq.Context()
        self.subscriber = self.context.socket(zmq.SUB)
        
        # Load connection details from config
        ds_config = self.config.dualshock_config
        self.zmq_address = ds_config.get("zmq_address", "tcp://172.18.0.1:5556")
        
        # We connect to the dualshock_publisher service
        try:
            self.subscriber.connect(self.zmq_address)
            time.sleep(1) # Give time for the connection to establish
            if self.verbose:
                print(f"[ZMQTeleopController.__init__] Connected to {self.zmq_address}")
            self.subscriber.setsockopt_string(zmq.SUBSCRIBE, "")
            if self.verbose:
                print("[ZMQTeleopController.__init__] Subscribed to all ZMQ messages")
        except zmq.ZMQError as e:
            print(f"[ZMQTeleopController] Failed to connect to {self.zmq_address}: {e}")

    def run(self):
        """Main loop for the teleoperation thread."""
        if self.verbose:
            print("[ZMQTeleopController.run()] Starting thread execution.")
        print(" --- Teleoperation Thread Started ---")
        self.logger.info("TeleopStarted")
        print(" --- Press 'q' in the main terminal and Enter to stop ---")

        # Wait for first joystick message before committing stiffness changes.
        # If the DualShock publisher isn't running (MVP / lab handoff stacks),
        # exit cleanly rather than leaving the robot stiffened and unresponsive.
        first_message_timeout = self.config.teleop_config.get("joystick_first_message_timeout", 3.0)
        first_message_received = False
        waited_since = time.time()
        stiffness_set = False

        while not teleop_running.is_set():
            poll_result = self.subscriber.poll(100) # 100ms timeout

            if poll_result == 0:
                if not first_message_received and (time.time() - waited_since) > first_message_timeout:
                    print(f" --- No joystick input on {self.zmq_address} within {first_message_timeout:.0f}s — aborting. Use Keyboard mode instead. ---")
                    self.logger.warning("JoystickUnavailable", {"address": self.zmq_address, "timeout": first_message_timeout})
                    break
                continue

            try:
                message = self.subscriber.recv_json()

                while True:
                    try:
                        latest = self.subscriber.recv_json(flags=zmq.NOBLOCK)
                        message = latest
                        if self.verbose:
                            print("[ZMQTeleopController] Skipped old message in queue")
                    except zmq.Again:
                        break

                if not first_message_received:
                    first_message_received = True
                    self.robot_client.set_stiffnesses("Body", 1.0)
                    self.robot_client.set_stiffnesses("Head", 0.6)
                    self.logger.info("StiffnessSet", {"body_part": "Body", "value": 1.0, "head_override": 0.6})
                    stiffness_set = True

                if self.verbose:
                    print(f"[ZMQTeleopController] Processing latest ZMQ message: {message}")
                self.handle_controller_input(message)

            except zmq.ZMQError as e:
                print(f"ZMQ Error in ZMQTeleopController: {e}")
                self.logger.error("ZMQError", {"error": str(e)})
                break
            except NaoqiProxyError as e:
                print(f"NAOqi Proxy Error: {e}")
                self.logger.error("ProxyError", {"error": str(e)})
                break

        if stiffness_set:
            self.stop_robot()
        print(" --- Teleoperation Thread Finished ---")
        self.cleanup()

    def handle_controller_input(self, message):
        """Map ZMQ message to motion."""
        ds_config = self.config.dualshock_config
        axes_map = ds_config.get("axes", {})
        deadzone = ds_config.get("deadzone", 0.1)

        # Get axis names from config, defaulting to original names if missing
        key_drive = axes_map.get("drive", "left_stick_y")
        key_strafe = axes_map.get("strafe", "left_stick_x")
        key_turn = axes_map.get("turn", "right_stick_x")

        # Extract values
        axes = message.get("axes", {})
        left_y = axes.get(key_drive, 0.0)
        left_x = axes.get(key_strafe, 0.0)
        right_x = axes.get(key_turn, 0.0)
        # We don't use right_y currently

        # Dead zone to prevent drift
        if abs(left_y) < deadzone: left_y = 0
        if abs(left_x) < deadzone: left_x = 0
        if abs(right_x) < deadzone: right_x = 0

        self.motion_mapping(left_x, left_y, 0.0, right_x)

    def cleanup(self):
        """Close ZMQ sockets."""
        self.subscriber.close()
        self.context.term()

# For backward compatibility (if needed temporarily, but we should update call sites)
TeleopThread = ZMQTeleopController