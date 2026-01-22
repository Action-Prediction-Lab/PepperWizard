import zmq
import cv2
import numpy as np
import threading
import time
import json

class VisionClient(threading.Thread):
    def __init__(self, robot_client, perception_uri="tcp://localhost:5557", streamer_uri="tcp://localhost:5559"):
        super().__init__()
        self.robot_client = robot_client
        self.perception_uri = perception_uri
        self.streamer_uri = streamer_uri
        self.running = False
        self.target_class = None
        self.lock = threading.Lock()
        
        # PID Constants
        self.k_p = 0.1 # Proportional gain
        self.width = 320 # Default, will update
        self.height = 240
        self.deadzone_x = 0.05 # Reduced deadzone since we have smoothing
        
        # Smoothing State
        self.smoothed_err_x = 0.0
        self.smoothed_err_y = 0.0
        
        # PD Control State
        self.k_d = 0.02 # Derivative gain (damping/prediction)
        self.prev_err_x = 0.0
        self.prev_err_y = 0.0
        self.last_time = None
        
    def set_target(self, target_class):
        with self.lock:
            self.target_class = target_class
            
    def stop(self):
        self.running = False
        self.join()

    def run(self):
        self.running = True
        print(f"VisionClient: Connecting to Streamer at {self.streamer_uri}...")
        print(f"VisionClient: Connecting to Perception at {self.perception_uri}...")
        
        context = zmq.Context()
        
        # Subscriber for Video (From Robot)
        video_sub = context.socket(zmq.SUB)
        video_sub.connect(self.streamer_uri)
        video_sub.setsockopt_string(zmq.SUBSCRIBE, "video")
        
        # Performance Tuning: Conflate (Keep only last message) if supported
        try:
            video_sub.setsockopt(zmq.CONFLATE, 1)
        except AttributeError:
            # If pyzmq is old, set HWM to 1 to drop old messages
            video_sub.setsockopt(zmq.RCVHWM, 1)
        
        # Request for Perception (To Docker)
        perception_req = context.socket(zmq.REQ)
        perception_req.connect(self.perception_uri)
        
        print("VisionClient: Started.")
        
        # Check Robot Head Stiffness
        # TUNING: Reduced stiffness to 0.7 for mechanical smoothing (compliance)
        self.robot_client.set_stiffnesses("Head", 0.7)
        
        while self.running:
            try:
                # 1. Receive Image (Queue Jumping)
                # Ensure we have the LATEST image, drain the queue
                msg = None
                while video_sub.poll(0):
                    msg = video_sub.recv_multipart()
                
                # If nothing in immediate drain, wait a bit
                if msg is None:
                    if video_sub.poll(50): # 50ms timeout
                         msg = video_sub.recv_multipart()
                    else:
                        continue
                
                topic, img_data = msg
                                        
                if len(img_data) == 230400:
                    w, h = 320, 240
                elif len(img_data) == 921600:
                    w, h = 640, 480
                else:
                    print(f"Warning: Unknown image size {len(img_data)}")
                    continue
                    
                self.width, self.height = w, h
                    
                # 2. Encode for Perception Service (it expects JPG)
                # Convert raw bytes to numpy
                img_np = np.frombuffer(img_data, dtype=np.uint8).reshape((h, w, 3))
                
                # Check Target
                local_target = None
                with self.lock:
                    local_target = self.target_class
                    
                if not local_target:
                    time.sleep(0.1)
                    continue
                    
                # Encode (Convert RGB to BGR for OpenCV encoding)
                img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                _, img_jpg = cv2.imencode('.jpg', img_bgr)
                
                # 3. Request Inference
                perception_req.send_multipart([b'{}', img_jpg.tobytes()])
                result = perception_req.recv_json()
                
                # 4. Process Results
                # Service returns {"data": [...]}
                detections = result.get("data", [])
                
                best_det = None
                max_conf = 0.0
                
                for det in detections:
                    if det["class"] == local_target and det["confidence"] > 0.4:
                        if det["confidence"] > max_conf:
                            max_conf = det["confidence"]
                            best_det = det
                            
                if best_det:
                    # 5. Servo Logic
                    bbox = best_det["bbox"]
                    cx = (bbox[0] + bbox[2]) / 2
                    cy = (bbox[1] + bbox[3]) / 2
                    
                    # Normalized Error (-1 to +1)
                    # Center of image is target
                    target_err_x = -(cx - (w / 2)) / (w / 2) 
                    target_err_y = (cy - (h / 2)) / (h / 2)
                    
                    # Apply Exponential Smoothing (Low Pass Filter)
                    alpha = 0.2
                    self.smoothed_err_x = (alpha * target_err_x) + ((1 - alpha) * self.smoothed_err_x)
                    self.smoothed_err_y = (alpha * target_err_y) + ((1 - alpha) * self.smoothed_err_y)
                    
                    # Use smoothed error for control
                    err_x = self.smoothed_err_x
                    err_y = self.smoothed_err_y
                    
                    # Calculate Derivative (Rate of Change)
                    current_time = time.time()
                    if self.last_time is None:
                        dt = 0.1
                    else:
                        dt = current_time - self.last_time
                    
                    # Prevent divide by zero or huge jumps
                    if dt <= 0.001: dt = 0.001
                    
                    d_err_x = (err_x - self.prev_err_x) / dt
                    d_err_y = (err_y - self.prev_err_y) / dt
                    
                    self.last_time = current_time
                    self.prev_err_x = err_x
                    self.prev_err_y = err_y
                    
                    # Apply Deadzone
                    if abs(err_x) < self.deadzone_x: err_x = 0
                    if abs(err_y) < self.deadzone_x: err_y = 0
                    
                    if err_x != 0 or err_y != 0:
                        # Send Move Command (Change Angles)
                        # TUNING v5: Reverted to Low-FPS Robust Tuning (Source is ~4 FPS)
                        # High Kd needed to prevent overshoot between slow frames
                        
                        kp_yaw = 0.08
                        kd_yaw = 0.04
                        kp_pitch = 0.06
                        kd_pitch = 0.03
                        
                        p_term_x = err_x * kp_yaw
                        d_term_x = d_err_x * kd_yaw
                        yaw_change = p_term_x + d_term_x
                        
                        p_term_y = err_y * kp_pitch
                        d_term_y = d_err_y * kd_pitch
                        pitch_change = p_term_y + d_term_y
                        
                        max_step = 0.1 # rad
                        yaw_change = np.clip(yaw_change, -max_step, max_step)
                        pitch_change = np.clip(pitch_change, -max_step, max_step)
                        
                        # Debug Logging
                        # print(f"dt={dt:.3f} | ErrX={err_x:.2f} dX={d_err_x:.2f} | OutX={yaw_change:.3f} (P={p_term_x:.3f} D={d_term_x:.3f})")
                        
                        try:
                            # Increased speed to 35% to reduce execution lag
                            self.robot_client.client.ALMotion.changeAngles(["HeadYaw", "HeadPitch"], [yaw_change, pitch_change], 0.35)
                        except Exception as e:
                            print(f"Servo Error: {e}")
                            
                else:
                    # No detection: Decay smoothing to zero
                    self.smoothed_err_x *= 0.9
                    self.smoothed_err_y *= 0.9
                                
            except Exception as e:
                print(f"VisionClient Error: {e}")
                time.sleep(1)
        
        video_sub.close()
        perception_req.close()
        context.term()
        print("VisionClient: Stopped.")
