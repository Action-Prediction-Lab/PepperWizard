import time
from ..control.pid import PIDController
from ..control.filters import KalmanFilter
from ..control.native import NativeController
from ..models import Detection

class HeadTracker:
    """
    Domain Logic for Head Tracking.
    Inputs: Target BBox, Current Angles.
    Outputs: Velocity/Position Commands.
    """
    def __init__(self, width=320, height=240, config=None):
        self.width = width
        self.height = height
        self.config = config or {}
        
        # Initialize Components
        self._init_components()
        
        # State
        self.last_update_time = time.time()
        self.is_tracking = False
        
    def _init_components(self):
        # Kalman Filter
        kf_cfg = self.config["kalman"]
        self.kf = KalmanFilter(
            process_noise=kf_cfg["process_noise"],
            measurement_noise=kf_cfg["measurement_noise"]
        )
        self.latency_comp = kf_cfg["latency_comp"]
        
        # Strategy Switching
        self.control_mode = self.config.get("control_mode", "pid")
        
        if self.control_mode == "native":
            self.native_ctrl = NativeController(self.config)
        else:
            # PID Controllers
            pid_cfg = self.config["pid"]
            
            # Resolve initial KP
            init_kp = pid_cfg["base_kp"] # Assume base_kp exists as per current tuning.json
                
            self.pid_yaw = PIDController(
                kp=init_kp,
                kd=pid_cfg["kd"],
                ki=pid_cfg["ki"],
                max_output=pid_cfg["max_output"],
                max_acceleration=None, # Not present in JSON
                deadzone=0.0 # Not present in JSON
            )
            self.pid_pitch = PIDController(
                kp=init_kp, 
                kd=pid_cfg["kd"],
                ki=pid_cfg["ki"],
                max_output=pid_cfg["max_output"],
                max_acceleration=None,
                deadzone=0.0
            )

    def reset(self):
        """Reset all internal state to start fresh."""
        self.last_update_time = time.time()
        self.is_tracking = False
        
        # Reset Kalman
        self.kf.reset()
        
        # Reset Controllers
        if self.control_mode == "native" and hasattr(self, 'native_ctrl'):
            self.native_ctrl.reset()
        else:
            self.pid_yaw.reset()
            self.pid_pitch.reset()

    def update(self, detection, current_state):
        """
        Calculate next head movement.
        
        Args:
            detection: Detection object or None if no detection.
            current_state: (yaw, pitch) angles of robot head.
            
        Returns:
            dict: Structured control command.
        """
        now = time.time()
        dt = now - self.last_update_time
        # SAFETY CLAMP
        safety_cfg = self.config["safety"]
        if dt > safety_cfg["max_dt"]: dt = safety_cfg["min_dt"] 
        if dt < safety_cfg["min_dt"]: dt = safety_cfg["min_dt"]
        self.last_update_time = now
        
        # 1. State Estimation (Predict)
        pred_x, pred_y = self.kf.predict(dt + self.latency_comp)
        target_x, target_y = pred_x, pred_y
        
        # 2. Update Filter (Correct)
        meas_yaw = None
        meas_pitch = None
        
        if detection:
            # Update KF with bbox center
            center = detection.bbox.center
            target_x, target_y = self.kf.update([center.x, center.y])
            
            # Extract synced angles if available
            if detection.source_angles:
                meas_yaw, meas_pitch = detection.source_angles
                
        # 3. Calculate Errors (Normalized -1 to 1)
        err_x = -(target_x - (self.width / 2)) / (self.width / 2)
        err_y = (target_y - (self.height / 2)) / (self.height / 2)
        
        # 4. Control Strategy
        if self.control_mode == "native":
            curr_yaw, curr_pitch = current_state if current_state else (None, None)
            
            # Use Synced Angles if available
            # REQUIRED FOR RAW MODE: Error is relative to the Capture Frame (meas_yaw).
            # Use meas_yaw to reconstruct the correct component of the Global Target.
            if meas_yaw is not None and meas_pitch is not None:
                 curr_yaw = meas_yaw
                 curr_pitch = meas_pitch

            # HYBRID - RAW MODE:
            # - When detection exists: Use RAW BBox Error. Bypass KF (it overshoots on egomotion).
            # - When detection missing: Pass None (Ghost Mode).
            
            calc_err_x = None
            calc_err_y = None
            det_ts = None
            
            if detection:
                center = detection.bbox.center
                calc_err_x = -(center.x - (self.width / 2)) / (self.width / 2)
                calc_err_y = (center.y - (self.height / 2)) / (self.height / 2)
                det_ts = detection.timestamp

            target_yaw, target_pitch, speed = self.native_ctrl.update(calc_err_x, calc_err_y, curr_yaw, curr_pitch, dt, det_ts, current_time=time.time())
            
            if target_yaw is not None:
                return {
                    "type": "position",
                    "yaw": target_yaw,
                    "pitch": target_pitch,
                    "speed": speed,
                    "debug": {"mode": "native"}
                }
            return None

        else:
            # PID VELOCITY CONTROL
            pid_cfg = self.config["pid"]
            if "base_kp" in pid_cfg:
                 base_kp = pid_cfg["base_kp"]
                 boost_kp = pid_cfg["boost_kp"]
                 total_error = max(abs(err_x), abs(err_y))
                 adaptive_kp = base_kp + (boost_kp * total_error)
                 self.pid_yaw.kp = adaptive_kp
                 self.pid_pitch.kp = adaptive_kp
            
            yaw_vel = self.pid_yaw.update(err_x, dt)
            pitch_vel = self.pid_pitch.update(err_y, dt)
            
            return {
                "type": "velocity",
                "yaw": yaw_vel,
                "pitch": pitch_vel,
                "speed": pid_cfg["default_speed"],
                "debug": {"mode": "pid"}
            }
