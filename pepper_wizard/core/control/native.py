import numpy as np
from .base import ExponentialSmoother, AlphaBetaEstimator, TrapezoidalScheduler, SCurveScheduler

class NativeController:
    """
    Implements the native NAOQI control strategy from ServoManager.
    """
    def __init__(self, config):
        self.config = config
        self._init_components()
        
    def _init_components(self):
        native_cfg = self.config["native"]
        scale = np.pi / 180.0
        
        # Max Limits
        max_v = native_cfg["max_vel_deg_s"] * scale
        max_a = native_cfg["max_accel_deg_s2"] * scale
        
        kp = native_cfg["gain_p"]
        kv = native_cfg["gain_v"]
        
        # Smoothing
        base_smooth = native_cfg.get("smoothing", 0.0) # Optional legacy support if needed, or remove
        
        self.smoother_yaw = ExponentialSmoother(native_cfg["smoothing_x"])
        self.smoother_pitch = ExponentialSmoother(native_cfg["smoothing_y"])
        
        self.estimator_yaw = AlphaBetaEstimator(kv, max_v * native_cfg["estimator_limit_multiplier"])
        self.estimator_pitch = AlphaBetaEstimator(kv, max_v * native_cfg["estimator_limit_multiplier"])
        
        # Use Trapezoidal scheduler.
        self.scheduler_yaw = TrapezoidalScheduler(max_v, max_a, kp)
        self.scheduler_pitch = TrapezoidalScheduler(max_v, max_a, kp)

    def reset(self):
        self.smoother_yaw.reset()
        self.smoother_pitch.reset()
        self.estimator_yaw.reset()
        self.estimator_pitch.reset()
        self.scheduler_yaw.reset()
        self.scheduler_pitch.reset()

    def update(self, error_x, error_y, current_yaw, current_pitch, dt=0.01, timestamp=None, current_time=None):
        native_cfg = self.config["native"]
        safety_cfg = self.config["safety"]
        
        fov_x = native_cfg["fov_x"]
        fov_y = native_cfg["fov_y"]
        deadzone_x = native_cfg["deadzone_x"]
        deadzone_y = native_cfg["deadzone_y"]
        kd_v = native_cfg["vel_decay"]
        speed = native_cfg["fraction_max_speed"]
        
        # Calculate Latency
        latency = 0.0
        if current_time and timestamp:
            latency = current_time - timestamp
        
        # 1. Target Processing
        if error_x is not None and error_y is not None and current_yaw is not None and current_pitch is not None:
            # Deadzone
            if abs(error_x) < deadzone_x: error_x = 0.0
            if abs(error_y) < deadzone_y: error_y = 0.0
            
            # Map vision error to joint offsets (Radians)
            # fov_x is total FOV, so offset is error * (fov/2)
            raw_target_yaw = current_yaw + (error_x * fov_x * 0.5)
            raw_target_pitch = current_pitch + (error_y * fov_y * 0.5)
            
            # Smoothing
            s_yaw = self.smoother_yaw.update(raw_target_yaw)
            s_pitch = self.smoother_pitch.update(raw_target_pitch)
            
            # Velocity Estimation
            # System arrival time is monotonic and smoother.
            est_time = current_time if current_time else time.time()
            self.estimator_yaw.update(raw_target_yaw, est_time)
        else:
            # Ghost Pursuit / Propagation
            if self.scheduler_yaw.curr_v is not None:
                # Use a safe dt for propagation
                p_dt = min(dt, safety_cfg["safe_dt_propagation"])
                # Decay the smooth velocity
                v_yaw = self.scheduler_yaw.curr_v * kd_v
                
                # Update smoother target (Ghost Target)
                if self.smoother_yaw.value is not None:
                     self.smoother_yaw.value += v_yaw * p_dt

        # 2. Motion Scheduling
        target_pos_yaw = self.smoother_yaw.value
        target_pos_pitch = self.smoother_pitch.value
        
        if target_pos_yaw is not None and current_yaw is not None:
            # Safety clamp for internal motion logic
            inner_dt = max(safety_cfg["min_dt"], min(dt, safety_cfg["max_dt"]))
            
            # Keep estimator running for Ghost Mode (Propagation) but don't feed it to Scheduler.
            feed_yaw = 0.0 
            feed_pitch = 0.0 
            
            final_yaw = self.scheduler_yaw.update(target_pos_yaw, current_yaw, inner_dt, feed_yaw)
            final_pitch = self.scheduler_pitch.update(target_pos_pitch, current_pitch, inner_dt, feed_pitch)
            
            # LOGGING
            if hasattr(self, 'logger'):
                self.logger.log(
                    target_yaw=target_pos_yaw,
                    curr_yaw=current_yaw,
                    error_raw=error_x if error_x else 0.0,
                    est_vel=feed_yaw,
                    final_yaw=final_yaw,
                    latency=latency
                )
            
            return final_yaw, final_pitch, speed
            
        return None, None, speed
