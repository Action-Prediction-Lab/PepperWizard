import time

class PIDController:
    """
    Standard PID Controller implementation.
    """
    def __init__(self, kp=0.1, kd=0.0, ki=0.0, deadzone=0.0, max_output=None, max_acceleration=None, output_smoothing=0.0):
        self.kp = kp
        self.kd = kd
        self.ki = ki
        self.deadzone = deadzone
        self.max_output = max_output
        self.max_acceleration = max_acceleration
        self.output_smoothing = output_smoothing
        
        # State
        self.prev_error = 0.0
        self.integral = 0.0
        self.last_output = 0.0
        
    def reset(self):
        self.prev_error = 0.0
        self.integral = 0.0
        self.last_output = 0.0
        
    def update(self, error, dt):
        """
        Calculate control output.
        error: Target - Measured
        dt: Time delta in seconds
        """
        if dt <= 0.0001:
            return self.last_output

        # Deadzone Check
        if abs(error) < self.deadzone:
            # Inside deadzone
            error = 0.0
            # Common practice: Zero integral if error is zero to prevent windup
            self.integral = 0.0
            
        # P Term
        p_term = self.kp * error
        
        # D Term
        d_error = (error - self.prev_error) / dt
        d_term = self.kd * d_error
        
        # I Term
        self.integral += error * dt
        # Simple anti-windup clamp
        if self.integral > 0.5: self.integral = 0.5
        if self.integral < -0.5: self.integral = -0.5
        i_term = self.ki * self.integral
        
        # Total Output
        output = p_term + d_term + i_term
        
        # Clamp Output (Speed Limit)
        if self.max_output is not None:
            output = max(min(output, self.max_output), -self.max_output)
            
        # Acceleration Limit (Slew Rate Limiting)
        if self.max_acceleration is not None:
            max_change = self.max_acceleration * dt
            change = output - self.last_output
            change = max(min(change, max_change), -max_change)
            output = self.last_output + change
            
        # Output Smoothing (Low Pass Filter)
        if self.output_smoothing > 0.0:
            alpha = 1.0 - self.output_smoothing
            output = (alpha * output) + (self.output_smoothing * self.last_output)
            
        # Update State
        self.prev_error = error
        self.last_output = output
        
        return output
