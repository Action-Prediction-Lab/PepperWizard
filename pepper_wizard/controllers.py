import logging

class PIDController:
    """
    A simple PID Controller for the robot head servo.
    Separated from VisionClient to allow independent 50Hz updates.
    """
    def __init__(self, kp=0.1, kd=0.02, ki=0.0, deadzone=0.05, max_output=0.1):
        self.kp = kp
        self.kd = kd
        self.ki = ki
        self.deadzone = deadzone
        self.max_output = max_output
        
        # State
        self.prev_error = 0.0
        self.integral = 0.0
        
    def update(self, error, dt):
        """
        Calculate control output.
        error: Normalized error (-1.0 to 1.0)
        dt: Time delta in seconds
        """
        # Deadzone
        if abs(error) < self.deadzone:
            error = 0.0
            self.integral = 0.0 # Reset integral in deadzone to prevent drift
            
        if dt <= 0.001:
            dt = 0.001
            
        # Derivative
        d_error = (error - self.prev_error) / dt
        
        # Integral
        self.integral += error * dt
        # Anti-windup (simple clamp on integral)
        if self.integral > 0.5: self.integral = 0.5
        if self.integral < -0.5: self.integral = -0.5
        
        # PID Law
        output = (self.kp * error) + (self.kd * d_error) + (self.ki * self.integral)
        
        # Clamp
        if output > self.max_output: output = self.max_output
        if output < -self.max_output: output = -self.max_output
        
        # Update State
        self.prev_error = error
        
        return output
