import time
import threading

# Import SDKs 
from clients.vision_client import VisionClient
from clients.state_client import StateClient
from perception_service.client import PerceptionClient

# Import Core
from ..core.tracking.head_tracker import HeadTracker
from ..io.actuation import RobotActuator
from ..perception.interpreter import PerceptionInterpreter

class TrackingOrchestrator:
    """
    Manages the threaded, closed-loop visual tracking system.

    This class decouples high-latency perception (running on event-driven vision callbacks) 
    from high-frequency actuation (running on a dedicated 100Hz control thread).

    Key Responsibilities:
    1.  **Pipeline Integration**: Connects Vision, State, Perception, and Actuation clients.
    2.  **Concurrency**: safely bridges asynchronous detections to the synchronous control loop.
    3.  **Execution**: Drives the `HeadTracker` logic and hot-reloads tuning configurations.
    """
    def __init__(self, robot_client):
        # IO
        self.vision = VisionClient()
        self.state = StateClient()
        self.perception = PerceptionClient()
        self.actuator = RobotActuator(robot_client)
        
        # Config
        self.config = self._load_tuning_config()
        
        # Core
        self.tracker = HeadTracker(config=self.config)
        self.interpreter = PerceptionInterpreter()
        
        # State
        self.running = False
        self.active_target_label = None
        
        # Threading
        self.lock = threading.Lock()
        self.last_detection = None
        self.last_measurement_time = 0

    def _load_tuning_config(self):
        import json
        import os
        try:
            config_path = os.path.join(os.path.dirname(__file__), "..", "config", "tuning.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"TrackingOrchestrator: Error loading tuning.json: {e}")
        return {}

        
    def start(self):
        self.running = True
        self.state.start()
        # Start Actuator Thread
        self.actuator.start_service()
        # Bind Vision callback
        self.vision.start_receiving(self.on_frame_received)
        
        # Ensure Stiffness (Ported from ServoManager)
        stiff_cfg = self.config.get("stiffness", {})
        val = stiff_cfg.get("min", 0.65) if isinstance(stiff_cfg, dict) else 0.65
        # Ensure Stiffness (Ported from ServoManager)
        stiff_cfg = self.config.get("stiffness", {})
        val = stiff_cfg.get("min", 0.65) if isinstance(stiff_cfg, dict) else 0.65
        self.actuator.set_stiffness(val)
        
        # Verify Deadzone
        native_cfg = self.config.get("native", {})
        
        # Start Control Loop Thread
        self.control_thread = threading.Thread(target=self._control_loop)
        self.control_thread.daemon = True
        self.control_thread.start()
        
    def stop(self):
        self.running = False
        self.vision.stop()
        self.state.stop()
        self.perception.close()
        self.actuator.stop_service()
        self.actuator.stop()
        if hasattr(self, 'control_thread') and self.control_thread.is_alive():
             self.control_thread.join(timeout=1.0)
        pass
        
    def set_target(self, label):
        self.active_target_label = label
        self.tracker.reset()

    def yield_control(self):
        """Used by external behaviors to stop tracking and free resources."""
        self.active_target_label = None
        self.tracker.reset()
        # Ensure head stops moving at next loop
        self.actuator.set_head_velocity(0.0, 0.0)
        
    def _control_loop(self):
        """
        100Hz Control Loop.
        Decoupled from Vision FPS.
        """
        hz = 100
        dt_target = 1.0 / hz
        
        loop_counter = 0
        last_log_time = time.time()
        
        while self.running:
            start_time = time.time()
            loop_counter += 1
            
            # Monitoring (Removed to keep CLI clean)
            # if start_time - last_log_time >= 5.0:
            #     print(f"TrackingOrchestrator Status: Running at {hz}Hz target. Active Label: {self.active_target_label}")
            #     last_log_time = start_time
            
            # Check for active tracking
            
            if self.active_target_label is not None:
                # 1. Get State
                now = time.time()
                robot_state = self.state.get_state_at(now)
                
                # 2. Update Core Logic (Rate Decoupling)
                # Atomically consume the latest vision measurement to avoid double-counting.
                # - If detection exists: Tracker performs "Predict + Correct".
                # - If None: Tracker performs "Predict-Only" (smoothing/dead-reckoning).

                detection = None
                with self.lock:
                    if self.last_detection:
                        detection = self.last_detection
                        self.last_detection = None # Consume it
                        self.last_measurement_time = detection.timestamp

                # Target Loss Recovery Logic
                target_lost_timeout = self.config.get("native", {}).get("target_lost_timeout", 0.5)
                
                # Check for recovery
                if detection and getattr(self, 'target_lost_active', False):
                    self.target_lost_active = False

                # Timeout Check (0.5s default)
                if self.last_measurement_time > 0 and (now - self.last_measurement_time > target_lost_timeout):
                    if not getattr(self, 'target_lost_active', False):
                        self.tracker.reset()
                        self.actuator.set_head_position(0.0, 0.0, speed=0.1)
                        self.target_lost_active = True
                    continue # Skip update/integration while lost
                
                # Hot-Reload tuning config (Every 1s / 100 frames)
                if loop_counter % 100 == 0:
                    new_cfg = self._load_tuning_config()
                    if new_cfg:
                       # Update in-place to ensure references (HeadTracker -> NativeController) see it
                       self.config.update(new_cfg)
                       # Update local vars that depend on it (Stiffnes)
                       stiff_cfg = self.config.get("stiffness", {})
                       val = stiff_cfg.get("min", 0.65) if isinstance(stiff_cfg, dict) else 0.65
                       if not hasattr(self, '_last_stiff') or self._last_stiff != val:
                           self.actuator.set_stiffness(val)
                           self._last_stiff = val
                
                # Timeout Check (1.0s) to prevent infinite spinning
                if self.last_measurement_time > 0 and (now - self.last_measurement_time > 1.0):
                    # Target lost (Non-blocking stop)
                    self.actuator.set_head_velocity(0.0, 0.0)
                    continue

                cmd = self.tracker.update(detection, robot_state)
                
                # 3. Actuate
                if cmd:
                    if cmd.get("type") == "position":
                        self.actuator.set_head_position(cmd["yaw"], cmd["pitch"], cmd["speed"])
                    else:
                        # Default / PID (Velocity)
                        self.actuator.set_head_velocity(cmd["yaw"], cmd["pitch"])
            
            # Sleep to maintain rate
            elapsed = time.time() - start_time
            sleep_time = dt_target - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def on_frame_received(self, timestamp, img_bgr):
        """
        Main Vision Callback: 10-15Hz (Incoming from camera)
        """
        if not self.running or not self.active_target_label:
            return
            
        # 1. Perception Backend (Blocking)
        raw_data = self.perception.detect(img_bgr, target_label=self.active_target_label)
        
        # 2. Extract Valid Target
        detection = self.interpreter.interpret(
            raw_data, 
            self.active_target_label, 
            timestamp,
            source_angles=self.state.get_state_at(timestamp)
        )
        
        if detection:
            with self.lock:
                self.last_detection = detection
                self.last_measurement_time = timestamp
