import time
import numpy as np

class KalmanFilter:
    """
    Constant Velocity Kalman Filter for 2D tracking.
    State: [x, y, dx, dy]
    Measurement: [x, y]
    """
    def __init__(self, process_noise=0.1, measurement_noise=1.0):
        # State Vector [x, y, dx, dy]
        self.x = np.zeros((4, 1))
        
        # Covariance Matrix
        self.P = np.eye(4) * 10.0
        
        # Measurement Matrix (We observe x, y)
        self.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ])
        
        # Process Noise Covariance (Q)
        # Assume noise in acceleration (jerk)
        self.Q = np.eye(4) * process_noise
        
        # Measurement Noise Covariance (R)
        self.R = np.eye(2) * measurement_noise
        
        self.last_update_time = time.time()
        
    def predict(self, dt):
        """
        Predict state forward by dt seconds.
        """
        # State Transition Matrix (F)
        # x = x + dx*dt
        F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        
        # Predict State
        self.x = F @ self.x
        
        # Predict Covariance
        self.P = F @ self.P @ F.T + self.Q
        
        return self.x[0,0], self.x[1,0]
        
    def update(self, measurement):
        """
        Update with new measurement [x, y].
        """
        z = np.array(measurement).reshape((2, 1))
        
        # Measurement Residual
        y = z - (self.H @ self.x)
        
        # Residual Covariance
        S = self.H @ self.P @ self.H.T + self.R
        
        # Optimal Kalman Gain
        K = self.P @ self.H.T @ np.linalg.inv(S)
        
        # Update State
        self.x = self.x + (K @ y)
        
        # Update Covariance
        I = np.eye(4)
        self.P = (I - (K @ self.H)) @ self.P
        
        self.last_update_time = time.time()
        
        return self.x[0,0], self.x[1,0]
