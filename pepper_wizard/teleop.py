# Teleoperation (joystick) logic
import threading
import time
import zmq
from naoqi_proxy import NaoqiProxyError

# Global flag to signal the teleoperation thread to stop
teleop_running = threading.Event()

class TeleopThread(threading.Thread):
    """Thread for handling robot teleoperation."""
    def __init__(self, robot_client, verbose=False):
        super(TeleopThread, self).__init__()
        from .logger import get_logger
        self.logger = get_logger("TeleopThread")
        
        self.robot_client = robot_client
        self.verbose = verbose
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

    def run(self):
        """Main loop for the teleoperation thread."""
        if self.verbose:
            print("[TeleopThread.run()] Starting thread execution.")
        print(" --- Teleoperation Thread Started ---")
        self.logger.info("TeleopStarted")
        print(" --- Press 'q' in the main terminal and Enter to stop ---")
        
        # Set stiffness for movement
        self.robot_client.set_stiffnesses("Body", 1.0)
        self.logger.info("StiffnessSet", {"body_part": "Body", "value": 1.0})

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
                self.logger.error("ZMQError", {"error": str(e)})
                break
            except NaoqiProxyError as e:
                print(f"NAOqi Proxy Error in TeleopThread: {e}")
                self.logger.error("ProxyError", {"error": str(e)})
                break
        
        print("Stopping robot movement...")
        self.robot_client.stop_move()
        self.logger.info("TeleopStopped")
        print(" --- Teleoperation Thread Finished ---")

    def handle_controller_input(self, message):
        """Map controller input to robot motion."""
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

        self.motion_mapping(left_x, left_y, right_y, right_x)

    def motion_mapping(self, lx, ly, ry, rx):
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
            self.robot_client.move_toward(command_x, command_y, command_theta)
        except NaoqiProxyError as e:
            print(f"Failed to send move command: {e}")
            teleop_running.set() # Stop the thread on error

    def stop(self):
        """Signal the thread to stop."""
        teleop_running.set()
        self.subscriber.close()
        self.context.term()