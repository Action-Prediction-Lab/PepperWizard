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
        self.deadzone_x = 0.1 # 10% center deadzone
        
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
        
        # Request for Perception (To Docker)
        perception_req = context.socket(zmq.REQ)
        perception_req.connect(self.perception_uri)
        
        print("VisionClient: Started.")
        
        # Check Robot Head Stiffness
        self.robot_client.set_stiffnesses("Head", 1.0)
        
        while self.running:
            try:
                # 1. Receive Image (Non-blocking check?)
                if video_sub.poll(100):
                    topic, img_data = video_sub.recv_multipart()
                    
                    # Assume VGA/QVGA based on len?
                    # The Streamer sends raw bytes. 
                    # We need to know resolution. Streamer uses kqvga (320x240) -> 320*240*3 = 230400 bytes
                    # or kvga (640x480) -> 921600 bytes.
                    
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
                        
                    # Encode
                    _, img_jpg = cv2.imencode('.jpg', img_np)
                    
                    # 3. Request Inference
                    perception_req.send_multipart([b'{}', img_jpg.tobytes()])
                    result = perception_req.recv_json()
                    
                    # 4. Process Results
                    detections = result.get("detections", [])
                    
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
                        err_x = -(cx - (w / 2)) / (w / 2) # NaoQi HeadYaw: Positive is Left. If object is right (cx > w/2), err_x is negative. We want to turn Right (Negative Yaw). Correct.
                        err_y = (cy - (h / 2)) / (h / 2) # NaoQi HeadPitch: Positive is Down. If object is down (cy > h/2), err_y is positive. We want to pitch Down. Correct.
                        
                        # Apply Deadzone
                        if abs(err_x) < self.deadzone_x: err_x = 0
                        if abs(err_y) < self.deadzone_x: err_y = 0
                        
                        if err_x != 0 or err_y != 0:
                            # Send Move Command (Change Angles)
                            # Scaling factor
                            yaw_change = err_x * 0.2 # Max step 0.2 rad
                            pitch_change = err_y * 0.1 # Max step 0.1 rad
                            
                            try:
                                self.robot_client.client.ALMotion.changeAngles(["HeadYaw", "HeadPitch"], [yaw_change, pitch_change], 0.1)
                            except Exception as e:
                                print(f"Servo Error: {e}")
                                
            except Exception as e:
                print(f"VisionClient Error: {e}")
                time.sleep(1)
        
        video_sub.close()
        perception_req.close()
        context.term()
        print("VisionClient: Stopped.")
