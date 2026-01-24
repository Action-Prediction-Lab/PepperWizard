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
        # TUNING: Heavy Damping (Fixing Overshoot)
        # Process Noise (0.1): Back to assuming smooth/slow movement.
        self.kf = KalmanFilter(process_noise=0.1, measurement_noise=150.0)
        
        # TUNING: Gentle & Damped
        # Kp (0.03): Reduced from 0.04 to minimize "snap".
        # Ki (0.01): Halved from 0.02 to reduce windup overshoot.
        # Kd (0.025): Increased significantly (0.015 -> 0.025) to act as a "Brake".
        self.pid_yaw = PIDController(kp=0.03, kd=0.025, ki=0.01, max_output=0.12)
        self.pid_pitch = PIDController(kp=0.025, kd=0.02, ki=0.01, max_output=0.12)
        
        self.active_target = False
        
    def update_measurement(self, bbox, robot_state=None):
        """Called by VisionReceiver when a new face is found."""
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        
        with self.lock:
            # Store [cx, cy, timestamp, robot_yaw, robot_pitch]
            # If robot_state is None, we use current time and will fetching angles later (fallback)
            if robot_state:
                self.latest_measurement = (cx, cy, time.time(), robot_state[0], robot_state[1])
            else:
                self.latest_measurement = (cx, cy, time.time(), None, None)
            
            self.active_target = True

    def stop(self):
        self.running = False
        self.join()

    def run(self):
        self.running = True
        print("ServoManager: Started 50Hz Control Loop.")
        
        # Initial stiffness
        self.load_tuning()
        # Fix: Extract 'min' (or specific start value) instead of passing the whole dict
        init_stiffness = self.tuning.get("stiffness", {}).get("min", 0.6)
        if isinstance(self.tuning.get("stiffness"), (int, float)):
             init_stiffness = self.tuning["stiffness"] # Handle legacy simple config
             
        try:
            self.robot_client.set_stiffnesses("Head", init_stiffness)
        except Exception as e:
            print(f"Warning: Could not set initial stiffness: {e}")
        
        last_loop_time = time.time()
        loop_count = 0
        
        while self.running:
            start_time = time.time()
            dt = start_time - last_loop_time
            if dt <= 0.001: dt = 0.001
            last_loop_time = start_time
            
            # Hot-Reload Tuning (Every 1s / 50 frames)
            loop_count += 1
            if loop_count % 50 == 0:
                self.load_tuning()
                # Apply Stiffness if changed
                # (Ideally check diff, but setting it repeatedly is low cost on NaoQi proxy?)
                # Actually it generates bus traffic. Let's assume user changes it rarely.
                # For now, we only set it on startup or if we detect a change? 
                # Implementing a simple cache would be better.
                # But for tuning session, just applying it is fine.
                try:
                     self.robot_client.set_stiffnesses("Head", self.tuning["stiffness"])
                except:
                     pass

            # 1. Update Estimator
            # Check for new measurement
            measurement = None
            with self.lock:
                if self.latest_measurement and self.latest_measurement[2] > self.last_measurement_time:
                    measurement = self.latest_measurement
                    self.last_measurement_time = measurement[2]
            
            # Predict
            # TUNING: Latency Compensation
            # Predict ahead by dt + fixed_latency to aim where the target WILL be.
            latency_comp = self.tuning.get("kalman", {}).get("latency_comp", 0.0)
            pred_x, pred_y = self.kf.predict(dt + latency_comp)
            
            # Correct (if new data)
            if measurement:
                cx, cy, _, _, _ = measurement
                pred_x, pred_y = self.kf.update([cx, cy])
                
            # If no data for > 1 second, stop tracking
            if time.time() - self.last_measurement_time > 1.0:
                self.active_target = False
                
            # 2. Calculate Control
            ctrl_mode = self.tuning.get("control_mode", "pid")
            yaw_change = 0.0
            pitch_change = 0.0
            
            if self.active_target:
                if ctrl_mode == "native":
                    # NATIVE POSITION CONTROL (Smoother)
                    try:
                        # 1. Get Base Angles (Synced or Current)
                        curr_yaw = 0.0
                        curr_pitch = 0.0
                        
                        if measurement and measurement[3] is not None:
                            # Use the angles from the exact moment of capture!
                            curr_yaw, curr_pitch = measurement[3], measurement[4]
                        else:
                            # Fallback to current angles (laggy)
                            current_angles = self.robot_client.get_angles(["HeadYaw", "HeadPitch"], True)
                            if current_angles:
                                curr_yaw, curr_pitch = current_angles

                        # 2. Calculate Error (Raw BBox, bypassing KF)
                        # KF in pixel space confuses ego-motion with target motion
                        if measurement:
                            raw_cx = measurement[0]
                            raw_cy = measurement[1]
                            err_x = -(raw_cx - (self.width / 2)) / (self.width / 2)
                            err_y = (raw_cy - (self.height / 2)) / (self.height / 2)
                        else:
                            err_x = 0.0
                            err_y = 0.0
                            
                        # 3. Calculate Offset based on FOV
                        native_cfg = self.tuning.get("native", {})
                        fov_x = native_cfg.get("fov_x", 1.0)
                        fov_y = native_cfg.get("fov_y", 0.8)
                        speed = native_cfg.get("fraction_max_speed", 0.2)
                        deadzone_x = native_cfg.get("deadzone_x", 0.0)
                        deadzone_y = native_cfg.get("deadzone_y", deadzone_x) # Default to deadzone_x
                        
                        # Separate smoothing for axes
                        base_smoothing = native_cfg.get("smoothing", 0.0)
                        smoothing_x = native_cfg.get("smoothing_x", base_smoothing)
                        smoothing_y = native_cfg.get("smoothing_y", base_smoothing)
                        
                        # Error is -1 to 1. 
                        # DEADZONE CHECK
                        if abs(err_x) < deadzone_x:
                            err_x = 0.0
                        if abs(err_y) < deadzone_y:
                            err_y = 0.0
                            
                        # Calculate offsets based on error and FOV
                        yaw_offset = err_x * (fov_x * 0.5) 
                        pitch_offset = err_y * (fov_y * 0.5)
                        
                        # 4. Calculate Absolute Target
                        raw_target_yaw = curr_yaw + yaw_offset
                        raw_target_pitch = curr_pitch + pitch_offset
                        
                        # SMOOTHING (Exponential Moving Average)
                        # Initialize if missing
                        if not hasattr(self, 'smoothed_yaw'):
                            self.smoothed_yaw = raw_target_yaw
                            self.smoothed_pitch = raw_target_pitch
                            
                        # Alpha: 1.0 = No Smoothing, 0.1 = Heavy Smoothing
                        # Higher smoothing config = Lower Alpha (More history)
                        # We use clamp to ensure it is 0-1
                        alpha_x = max(0.0, min(1.0, 1.0 - smoothing_x))
                        alpha_y = max(0.0, min(1.0, 1.0 - smoothing_y))
                        
                        self.smoothed_yaw = (alpha_x * raw_target_yaw) + ((1.0 - alpha_x) * self.smoothed_yaw)
                        self.smoothed_pitch = (alpha_y * raw_target_pitch) + ((1.0 - alpha_y) * self.smoothed_pitch)
                        
                        target_yaw = self.smoothed_yaw
                        target_pitch = self.smoothed_pitch
                        
                        # 5. Command Native Smoothing
                        if abs(yaw_offset) > 0.001 or abs(pitch_offset) > 0.001:
                             self.robot_client.set_angles(["HeadYaw", "HeadPitch"], 
                                                        [target_yaw, target_pitch], 
                                                        speed)
                                                       
                        # LOGGING
                        with open("pid_log.csv", "a") as f:
                            f.write(f"{time.time()},{measurement[0] if measurement else -1},{pred_x},{err_x},{target_yaw},NATIVE\n")

                    except Exception as e:
                        print(f"Native Control Error: {e}")
                        
                else:
                    # LEGACY PID CONTROL
                    # ADAPTIVE CONTROL: Gain Scheduling
                    # Increase Kp linearly with error magnitude
                    total_error = max(abs(err_x), abs(err_y))
                    
                    # Fetch base tuning
                    base_kp = self.tuning.get("pid", {}).get("base_kp", 0.03)
                    boost_kp = self.tuning.get("pid", {}).get("boost_kp", 0.05)
                    
                    # Apply dynamic Kp
                    adaptive_kp = base_kp + (boost_kp * total_error)
                    self.pid_yaw.kp = adaptive_kp
                    self.pid_pitch.kp = adaptive_kp
                    
                    # PID Update
                    yaw_change = self.pid_yaw.update(err_x, dt)
                    pitch_change = self.pid_pitch.update(err_y, dt)
                    
                    # PID Actuation is handled below shared block...
                    pass 
                
                # 3. Actuate Head (PID Only) - Duplicate block removed in later cleanup, but for now just updating checks
                if ctrl_mode == "pid":
                    try:
                         # Log
                        with open("pid_log.csv", "a") as f:
                            f.write(f"{time.time()},{raw_x},{pred_x},{err_x},{yaw_change},{v_theta}\n")

                        # Move smoothly (Speed limited by PID max_output)
                        self.robot_client.client.ALMotion.changeAngles(["HeadYaw", "HeadPitch"], [yaw_change, pitch_change], 0.3)
                    except Exception as e:
                        print(f"Servo Error: {e}")
                
                # 4. Body Tracking (Interlinked)
                # MOVED BEFORE HEAD ACTUATION for correct Feed-Forward
                body_cfg = self.tuning.get("body", {})
                v_theta = 0.0
                
                # LOGGING: Tuning Data
                # timestamp, raw_x, pred_x, error_x, output_yaw, base_vel
                raw_x = measurement[0] if measurement else -1
                
                if body_cfg.get("enabled", False):
                    try:
                        # Get current HeadYaw
                        head_angles = self.robot_client.get_angles(["HeadYaw"], True)
                        if head_angles:
                            head_yaw = head_angles[0]
                            
                            deadzone = body_cfg.get("deadzone_yaw", 0.35)
                            kp_base = body_cfg.get("kp_base", 0.2)
                            max_speed = body_cfg.get("max_speed", 0.2)
                            
                            # Base Control Law
                            if abs(head_yaw) > deadzone:
                                # Turn Base to unwind Head
                                v_theta = head_yaw * kp_base
                                
                                # Clamp Base Speed
                                if v_theta > max_speed: v_theta = max_speed
                                if v_theta < -max_speed: v_theta = -max_speed
                            else:
                                v_theta = 0.0
                            
                            # Send Base Command    
                            if v_theta != 0.0:
                                self.robot_client.move_toward(0.0, 0.0, v_theta)
                            else:
                                self.robot_client.move_toward(0.0, 0.0, 0.0)
                            
                            # FEED FORWARD (The "Interlink")
                            # If Body turns Left (+), Camera moves Left.
                            # We must turn Head Right (-) to compensate.
                            if body_cfg.get("feed_forward", True):
                                yaw_change -= (v_theta * dt)
                                
                    except Exception as e:
                        print(f"Body Track Error: {e}")
                        
                # LOGGING: Tuning Data
                # timestamp, raw_x, pred_x, error_x, output_yaw, base_vel
                raw_x = measurement[0] if measurement else -1
                
                if body_cfg.get("enabled", False):
                    try:
                        # ... (Body Tracking Logic) ...
                        # Keep checking control_mode for Feed Forward application?
                        # Feed Forward modifies 'yaw_change'. 
                        # If Native, 'yaw_change' is undefined/unused!
                        pass
                    except:
                        pass
                        
                # 3. Actuate Head (PID Only) - Duplicate block removed in later cleanup, but for now just updating checks
                if self.active_target and ctrl_mode == "pid":
                    try:
                         # Log
                        with open("pid_log.csv", "a") as f:
                            f.write(f"{time.time()},{raw_x},{pred_x},{err_x},{yaw_change},{v_theta}\n")

                        # Move smoothly (Speed limited by PID max_output)
                        self.robot_client.client.ALMotion.changeAngles(["HeadYaw", "HeadPitch"], [yaw_change, pitch_change], 0.3)
                    except Exception as e:
                        print(f"Servo Error: {e}")
                    
                # 4. Body Tracking (The Exorcist Maneuver Prevention)
                # If the head turns too far, rotate the base to align the body with the head.
                # This keeps the head centered and allows 360 tracking.
                body_cfg = self.tuning.get("body", {})
                if body_cfg.get("enabled", False):
                    try:
                        # Get current HeadYaw
                        head_angles = self.robot_client.get_angles(["HeadYaw"], True)
                        if head_angles:
                            head_yaw = head_angles[0]
                            
                            deadzone = body_cfg.get("deadzone_yaw", 0.35)
                            kp_base = body_cfg.get("kp_base", 0.2)
                            max_speed = body_cfg.get("max_speed", 0.2)
                            
                            # Base Control Law
                            if abs(head_yaw) > deadzone:
                                # Turn Base to unwind Head
                                v_theta = head_yaw * kp_base
                                
                                # Clamp Base Speed
                                if v_theta > max_speed: v_theta = max_speed
                                if v_theta < -max_speed: v_theta = -max_speed
                            else:
                                v_theta = 0.0
                            
                            # Send Base Command    
                            if v_theta != 0.0:
                                self.robot_client.move_toward(0.0, 0.0, v_theta)
                            else:
                                self.robot_client.move_toward(0.0, 0.0, 0.0)
                            
                            # FEED FORWARD (The "Interlink")
                            # Only apply to PID mode (Native handles absolute angles automatically)
                            if control_mode == "pid" and body_cfg.get("feed_forward", True):
                                yaw_change -= (v_theta * dt)
                                
                    except Exception as e:
                        print(f"Body Track Error: {e}")
            
            # Sleep to maintain 100Hz (10ms)
            elapsed = time.time() - start_time
            sleep_time = 0.01 - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
        print("ServoManager: Stopped.")
        
    def load_tuning(self):
        try:
            import json
            import os
            if os.path.exists("tuning.json"):
                with open("tuning.json", "r") as f:
                    config = json.load(f)
                    
                self.tuning = config
                
                # Apply to Kalman
                if hasattr(self, 'kf'):
                    self.kf.R = np.eye(2) * config['kalman']['measurement_noise']
                    self.kf.Q = np.eye(4) * config['kalman']['process_noise']
                    
                # Apply to PID
                if hasattr(self, 'pid_yaw'):
                    p = config['pid']
                    # Support both simple and adaptive configs
                    if 'base_kp' in p:
                        self.pid_yaw.kp = p['base_kp'] # Start with base
                        self.pid_pitch.kp = p['base_kp']
                    else:
                        self.pid_yaw.kp = p['kp']
                        self.pid_pitch.kp = p['kp']
                        
                    self.pid_yaw.kd = p['kd']
                    self.pid_yaw.ki = p['ki']
                    self.pid_yaw.max_output = p.get('max_output', 0.15)
                    self.pid_yaw.max_acceleration = p.get('max_acceleration', None)
                    # TUNING: Disabled Output Smoothing to fix "stepping"
                    self.pid_yaw.output_smoothing = 0.0 # p.get('output_smoothing', 0.0)
                    
                    self.pid_pitch.kd = p['kd']
                    self.pid_pitch.ki = p['ki']
                    self.pid_pitch.max_output = p.get('max_output', 0.15)
                    self.pid_pitch.max_acceleration = p.get('max_acceleration', None)
                    self.pid_pitch.output_smoothing = p.get('output_smoothing', 0.0)
            else:
                # Default fallback
                self.tuning = {"stiffness": 0.7}
        except Exception as e:
            print(f"Error loading tuning.json: {e}")
