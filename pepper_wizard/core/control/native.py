import numpy as np
from .base import ExponentialSmoother, AlphaBetaEstimator, TrapezoidalScheduler, SCurveScheduler

class NativeController:
    """
    Implements the 'Native' control strategy from ServoManager.
    This version uses decomposed components for better modularity.
    """
    def __init__(self, config):
        self.config = config
        self._init_components()
        
    def _init_components(self):
        native_cfg = self.config.get("native", {})
        scale = np.pi / 180.0
        
        # Max Limits
        max_v = native_cfg.get("max_vel_deg_s", 120.0) * scale
        max_a = native_cfg.get("max_accel_deg_s2", 600.0) * scale
        max_j = native_cfg.get("max_jerk_deg_s3", 3000.0) * scale # New Config
        
        kp = native_cfg.get("gain_p", 8.0)
        kv = native_cfg.get("gain_v", 0.1)
        
        # Smoothing
        base_smooth = native_cfg.get("smoothing", 0.0)
        
        self.smoother_yaw = ExponentialSmoother(native_cfg.get("smoothing_x", base_smooth))
        self.smoother_pitch = ExponentialSmoother(native_cfg.get("smoothing_y", base_smooth))
        
        self.estimator_yaw = AlphaBetaEstimator(kv, max_v * 1.5)
        self.estimator_pitch = AlphaBetaEstimator(kv, max_v * 1.5)
        
        # REVERT: S-Curve proved unstable ("Seizure"). Back to Robust Trapezoidal.
        # self.scheduler_yaw = SCurveScheduler(max_v, max_a, kp, max_j)
        # self.scheduler_pitch = SCurveScheduler(max_v, max_a, kp, max_j)
        
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
        native_cfg = self.config.get("native", {})
        fov_x = native_cfg.get("fov_x", 1.0)
        fov_y = native_cfg.get("fov_y", 0.8)
        deadzone_x = native_cfg.get("deadzone_x", 0.0)
        deadzone_y = native_cfg.get("deadzone_y", deadzone_x)
        kd_v = native_cfg.get("vel_decay", 0.95)
        speed = native_cfg.get("fraction_max_speed", 0.2)
        
        # Latency Calc
        latency = 0.0
        if current_time and timestamp:
            latency = current_time - timestamp
        
        # 1. Target Processing
        if error_x is not None and error_y is not None and current_yaw is not None and current_pitch is not None:
            # Deadzone
            if abs(error_x) < deadzone_x: error_x = 0.0
            if abs(error_y) < deadzone_y: error_y = 0.0
            
            # Map vision error to joint offsets (Radians)
            raw_target_yaw = current_yaw + (error_x * fov_x * 0.5)
            raw_target_pitch = current_pitch + (error_y * fov_y * 0.5)
            
            # Smoothing
            s_yaw = self.smoother_yaw.update(raw_target_yaw)
            s_pitch = self.smoother_pitch.update(raw_target_pitch)
            
            # Velocity Estimation
            # CRITICAL FIX: Use current_time (Arrival Time) instead of timestamp (Capture Time)
            # Capture timestamps are jittery (buffering) causing massive velocity spikes.
            # System arrival time is monotonic and smoother.
            est_time = current_time if current_time else time.time()
            self.estimator_yaw.update(raw_target_yaw, est_time)
            # self.estimator_pitch.update(raw_target_pitch, est_time) 
        else:
            # Ghost Pursuit / Propagation
            # FIXED: Use Scheduler's smooth velocity instead of noisy estimator velocity
            if self.scheduler_yaw.curr_v is not None:
                # Use a safe dt for propagation
                p_dt = min(dt, 0.05)
                # Decay the smooth velocity
                v_yaw = self.scheduler_yaw.curr_v * kd_v
                # v_pitch = self.scheduler_pitch.curr_v * kd_v
                
                # Update smoother target (Ghost Target)
                if self.smoother_yaw.value is not None:
                     self.smoother_yaw.value += v_yaw * p_dt
                # self.smoother_pitch.value += v_pitch * p_dt
        
        # 2. Motion Scheduling
        target_pos_yaw = self.smoother_yaw.value
        target_pos_pitch = self.smoother_pitch.value
        
        if target_pos_yaw is not None and current_yaw is not None:
            # Safety clamp for internal motion logic
            inner_dt = max(0.001, min(dt, 0.05))
            
            # feed_yaw = self.estimator_yaw.velocity
            # FEED-FORWARD DISABLED: Input (Sensor) Stability is too low.
            # Injecting derivative noise causes spikes.
            # We keep estimator running for Ghost Mode (Propagation) but don't feed it to Scheduler.
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
