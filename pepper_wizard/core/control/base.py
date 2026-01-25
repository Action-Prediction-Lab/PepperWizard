import time
from typing import Optional
import numpy as np

class ExponentialSmoother:
    """Simple Alpha Filter for position smoothing."""
    def __init__(self, smoothing: float = 0.5):
        self.smoothing = smoothing
        self.value = None

    def reset(self):
        self.value = None

    def update(self, raw_value: float, dt: float = 0.01) -> float:
        if self.value is None:
            self.value = raw_value
        else:
            alpha = max(0.0, min(1.0, 1.0 - self.smoothing))
            self.value = (alpha * raw_value) + ((1.0 - alpha) * self.value)
        return self.value

class AlphaBetaEstimator:
    """Estimates velocity from position changes using wall-clock timing."""
    def __init__(self, beta: float = 0.1, max_velocity: float = 2.0):
        self.beta = beta
        self.max_v = max_velocity
        self.velocity = 0.0
        self.last_pos = None
        self.last_time = None

    def reset(self):
        self.velocity = 0.0
        self.last_pos = None
        self.last_time = None

    def update(self, pos: float, timestamp: Optional[float] = None) -> float:
        """Update velocity estimate with a new measurement."""
        now = timestamp if timestamp is not None else time.time()
        if self.last_pos is not None and self.last_time is not None:
            dt_v = now - self.last_time
            if dt_v > 0.001:
                inst_v = (pos - self.last_pos) / dt_v
                # Safety Clamp
                inst_v = max(-self.max_v, min(self.max_v, inst_v))
                # Smooth
                self.velocity = (self.beta * inst_v) + ((1.0 - self.beta) * self.velocity)
        
        self.last_pos = pos
        self.last_time = now
        return self.velocity

    def propagate(self, dt: float, decay: float = 0.95) -> float:
        """Decay velocity when no measurement is available. Does NOT move last_pos."""
        self.velocity *= decay
        return self.velocity

class TrapezoidalScheduler:
    """Integrates velocity to position with acceleration limits."""
    def __init__(self, max_v: float, max_a: float, kp: float = 8.0):
        self.max_v = max_v
        self.max_a = max_a
        self.kp = kp
        self.curr_v = 0.0
        self.last_cmd = None

    def reset(self):
        self.curr_v = 0.0
        self.last_cmd = None

    def update(self, target_pos: float, current_pos: float, dt: float, feed_forward_v: float = 0.0) -> float:
        if self.last_cmd is None:
            self.last_cmd = current_pos
            self.curr_v = 0.0
            return current_pos

        # 1. Proportional Control
        dist = target_pos - self.last_cmd
        des_vel = (dist * self.kp) + feed_forward_v
        
        # 2. Clamp Velocity
        des_vel = max(-self.max_v, min(self.max_v, des_vel))
        
        # 3. Limit Acceleration
        max_dv = self.max_a * dt
        dv = des_vel - self.curr_v
        dv = max(-max_dv, min(max_dv, dv))
        
        # 4. Integrate
        self.curr_v += dv
        self.last_cmd += self.curr_v * dt
        
        return self.last_cmd
