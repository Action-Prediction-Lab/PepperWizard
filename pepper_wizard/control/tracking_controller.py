import threading
import time
from ..perception.vision_receiver import VisionReceiver
from ..perception.perception_client import PerceptionClient
from ..state_buffer import StateBuffer
from ..servo_manager import ServoManager

class TrackingController:
    """
    Orchestrates a closed-loop visual tracking pipeline by coordinating vision, 
    inference, and actuation subsystems.

    This class serves as the central control node that:
    1.  **Ingests Visual Data**: Receives frames asynchronously via the `VisionReceiver`.
    2.  **Performs Inference**: Delegates object or pose detection to the `PerceptionClient`.
    3.  **Synchronizes State**: Correlates visual detection timestamps with historical 
        robot kinematics (via `StateBuffer`) to compensate for perception and transmission latency.
    4.  **Executes Control**: Dispatches measurement updates to the `ServoManager` to drive 
        the robot toward the target.

    Attributes:
        robot_client: The interface for robot communication.
        vision (VisionReceiver): Handles camera streams and callbacks.
        perception (PerceptionClient): Wrapper for inference models (e.g., YOLO, Mediapipe).
        state_buffer (StateBuffer): Stores a time-series of robot states for latency compensation.
        servo (ServoManager): Calculates and applies motor control updates.
    """
    def __init__(self, robot_client):
        self.robot_client = robot_client
        
        # Modules
        self.vision = VisionReceiver()
        self.perception = PerceptionClient()
        self.state_buffer = StateBuffer()
        self.servo = ServoManager(robot_client)
        
        # State
        self.active_target_label = None
        self.running = False
        
    def start(self):
        self.running = True
        self.state_buffer.start()
        self.servo.start()
        # Start vision loop, triggering process_frame on arrival
        self.vision.start_receiving(self.process_frame)
        print("TrackingController: Started.")

    def stop(self):
        self.running = False
        self.vision.stop() # Stops receiving callbacks
        self.servo.stop()
        self.state_buffer.stop()
        self.perception.close()
        print("TrackingController: Stopped.")

    def set_target(self, label):
        """Sets the object label to track (e.g. 'person', 'cup'). None to stop."""
        self.active_target_label = label
        print(f"TrackingController: Target set to '{label}'")

    def process_frame(self, timestamp, img_bgr):
        """Callback from VisionReceiver. Executes the control pipeline."""
        if not self.running or not self.active_target_label:
            return

        # 1. Perception Inference
        # Briefly block, since this is in the dedicated VisionThread (from VisionReceiver) this is not a concern. 
        results = self.perception.detect(img_bgr, self.active_target_label)
        
        if not results:
            return

        # 2. Logic: Select target (highest confidence for objects, first instance for humans)
        target_bbox = self._find_best_bbox(results, self.active_target_label, img_bgr.shape[1], img_bgr.shape[0])
        
        if target_bbox:
            # 3. Synchronization: Get Robot State at Capture Time
            robot_state = self.state_buffer.get_state_at(timestamp)
            
            now = time.time()
            latency = now - timestamp
            if robot_state:
                pass
            else:
                buf_min = self.state_buffer.buffer[0][0] if self.state_buffer.buffer else -1
                buf_max = self.state_buffer.buffer[-1][0] if self.state_buffer.buffer else -1
            
            # 4. Action: Update Servo Loop
            self.servo.update_measurement(target_bbox, robot_state)

    def _find_best_bbox(self, data, label, w, h):
        """Parses YOLO/Mediapipe results to find the target bbox."""
        # Case A: Mediapipe Pose (if 'person')
        if label in ["person", "human", "face"] and "pose_landmarks" in data:
            pose = data.get("pose_landmarks")
            if pose and len(pose) > 0:
                nose = pose[0]
                nx = nose["x"] * w
                ny = nose["y"] * h
                return [nx, ny, nx, ny] # Point bbox

        # Case B: YOLO Detections
        detections = []
        if isinstance(data, list):
            detections = data
        elif isinstance(data, dict) and "detections" in data:
            detections = data["detections"]
            
        best_det = None
        max_conf = 0.0
        
        for det in detections:
            # Simple filtered match
            if det["class"] == label and det["confidence"] > 0.4:
                if det["confidence"] > max_conf:
                    max_conf = det["confidence"]
                    best_det = det
        
        if best_det:
            return best_det["bbox"]
            
        return None
