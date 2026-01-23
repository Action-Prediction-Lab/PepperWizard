import threading
import time
import numpy as np
from .controllers import PIDController
from .state_estimator import KalmanFilter

class ServoManager(threading.Thread):
    def __init__(self, robot_client, width=320, height=240):
        super().__init__()
        self.robot_client = robot_client
        self.running = False
        self.lock = threading.Lock()
        
        # Dimensions for normalization
        self.width = width
        self.height = height
        
        # Shared State (Written by Vision, Read by Servo)
        self.latest_measurement = None # (x, y, timestamp)
        self.last_measurement_time = 0.0
        
        # Estimator & Controllers
        # TUNING: Increased measurement noise to 100.0 to heavily smooth out detection jitter
        self.kf = KalmanFilter(process_noise=0.1, measurement_noise=100.0)
        
        # TUNING: Drastically reduced gains for 50Hz loop.
        # Since we update 6x faster (50Hz vs 8Hz), we need smaller corrections per step.
        self.pid_yaw = PIDController(kp=0.04, kd=0.005, max_output=0.1)
        self.pid_pitch = PIDController(kp=0.03, kd=0.002, max_output=0.1)
        
        self.active_target = False
        
    def update_measurement(self, bbox):
        """Called by VisionReceiver when a new face is found."""
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        
        with self.lock:
            self.latest_measurement = (cx, cy, time.time())
            self.active_target = True

    def stop(self):
        self.running = False
        self.join()

    def run(self):
        self.running = True
        print("ServoManager: Started 50Hz Control Loop.")
        
        # Initial stiffness
        self.robot_client.set_stiffnesses("Head", 0.7)
        
        last_loop_time = time.time()
        
        while self.running:
            start_time = time.time()
            dt = start_time - last_loop_time
            if dt <= 0.001: dt = 0.001
            last_loop_time = start_time
            
            # 1. Update Estimator
            # Check for new measurement
            measurement = None
            with self.lock:
                if self.latest_measurement and self.latest_measurement[2] > self.last_measurement_time:
                    measurement = self.latest_measurement
                    self.last_measurement_time = measurement[2]
            
            # Predict
            pred_x, pred_y = self.kf.predict(dt)
            
            # Correct (if new data)
            if measurement:
                cx, cy, _ = measurement
                pred_x, pred_y = self.kf.update([cx, cy])
                
            # If no data for > 1 second, stop tracking
            if time.time() - self.last_measurement_time > 1.0:
                self.active_target = False
                
            # 2. Calculate Control
            if self.active_target:
                # Normalize Error
                # Center is (w/2, h/2) represents 0 error
                err_x = -(pred_x - (self.width / 2)) / (self.width / 2)
                err_y = (pred_y - (self.height / 2)) / (self.height / 2)
                
                # PID
                yaw_change = self.pid_yaw.update(err_x, dt)
                pitch_change = self.pid_pitch.update(err_y, dt)
                
                # 3. Actuate
                try:
                    # Move smoothly (Speed reduced to 0.2 for safety)
                    self.robot_client.client.ALMotion.changeAngles(["HeadYaw", "HeadPitch"], [yaw_change, pitch_change], 0.2)
                except Exception as e:
                    print(f"Servo Error: {e}")
            
            # Sleep to maintain 100Hz (10ms)
            elapsed = time.time() - start_time
            sleep_time = 0.01 - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
        print("ServoManager: Stopped.")
