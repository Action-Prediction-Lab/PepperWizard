import zmq
import cv2
import numpy as np
import threading
import time
import json
import struct
from .servo_manager import ServoManager
from .state_buffer import StateBuffer

class VisionReceiver(threading.Thread):
    def __init__(self, robot_client, perception_uri="tcp://localhost:5557", streamer_uri="tcp://localhost:5559"):
        super().__init__()
        self.robot_client = robot_client # Just for passing to ServoManager
        self.perception_uri = perception_uri
        self.streamer_uri = streamer_uri
        self.running = False
        self.target_class = None
        self.lock = threading.Lock()
        
        
        # Instantiate Servo Manager (The "Brain")
        self.servo_manager = ServoManager(robot_client)
        
        # Instantiate State Buffer (The "Memory")
        self.state_buffer = StateBuffer()
        
    def set_target(self, target_class):
        with self.lock:
            self.target_class = target_class
            
    def stop(self):
        self.running = False
        self.servo_manager.stop()
        self.join()

    def run(self):
        self.running = True
        
        
        # Start the Reflexes
        self.state_buffer.start()
        self.servo_manager.start()
        
        print(f"VisionReceiver: Connecting to Streamer at {self.streamer_uri}...")
        print(f"VisionReceiver: Connecting to Perception at {self.perception_uri}...")
        
        context = zmq.Context()
        
        # Subscriber for Video
        video_sub = context.socket(zmq.SUB)
        video_sub.connect(self.streamer_uri)
        video_sub.setsockopt_string(zmq.SUBSCRIBE, "video")
        
        try:
            video_sub.setsockopt(zmq.CONFLATE, 1)
        except AttributeError:
            video_sub.setsockopt(zmq.RCVHWM, 1)
        
        # Request for Perception
        perception_req = context.socket(zmq.REQ)
        perception_req.connect(self.perception_uri)
        
        print(f"VisionReceiver: Started (v3 - Predictive Tracking). Source: {__file__}")
        
        while self.running:
            try:
                # 1. Receive Image
                msg = None
                while video_sub.poll(0):
                    msg = video_sub.recv_multipart()
                
                if msg is None:
                    if video_sub.poll(50):
                         msg = video_sub.recv_multipart()
                    else:
                        continue
                
                topic, msg_data = msg
                
                # Extract Timestamp (first 8 bytes, double)
                # VideoStreamer sends: [Header(8B)][ImageBytes]
                # Actually, ZMQ multipart is: [Topic, Header, ImageBytes] 
                # OR [Topic, PackedData] depending on my implementation in video_streamer
                # Let's check video_streamer implementation:
                # socket.send_multipart(["video", header, y_channel])
                # So we expect 3 parts: Topic, Header, Data
                
                if len(msg) == 3:
                    topic, header, img_data = msg
                    timestamp = struct.unpack('d', header)[0]
                elif len(msg) == 2:
                    # Legacy fallback (just in case)
                    topic, img_data = msg
                    timestamp = time.time() # Best guess (bad for sync)
                else:
                    continue
                                        
                # 2. Decode (Greyscale or YUV)
                w, h = 320, 240
                if len(img_data) == 76800:
                    img_np = np.frombuffer(img_data, dtype=np.uint8).reshape((h, w))
                    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
                elif len(img_data) == 153600:
                    img_np = np.frombuffer(img_data, dtype=np.uint8).reshape((h, w, 2))
                    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_YUV2BGR_YUYV)
                elif len(img_data) == 230400:
                    img_np = np.frombuffer(img_data, dtype=np.uint8).reshape((h, w, 3))
                    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                elif len(img_data) == 921600:
                    w, h = 640, 480
                    img_np = np.frombuffer(img_data, dtype=np.uint8).reshape((h, w, 3))
                    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                elif len(img_data) == 38400:
                    # QQVGA YUYV (160x120 * 2 bytes)
                    # Extract Y-channel (Every other byte)
                    y_channel = img_data[0::2] # Length 19200
                    h, w = 120, 160
                    img_np = np.frombuffer(y_channel, dtype=np.uint8).reshape((h, w))
                    # Resize back to 320x240
                    img_resized = cv2.resize(img_np, (320, 240))
                    img_bgr = cv2.cvtColor(img_resized, cv2.COLOR_GRAY2BGR)
                else:
                    print(f"Warning: Unknown image size {len(img_data)}")
                    continue
                
                # Check Target
                local_target = None
                with self.lock:
                    local_target = self.target_class
                    
                if not local_target:
                    time.sleep(0.1)
                    continue

                _, img_jpg = cv2.imencode('.jpg', img_bgr)
                
                # 3. Request Inference
                perception_req.send_multipart([b'{}', img_jpg.tobytes()])
                result = perception_req.recv_json()
                
                # 4. Process Results
                # 4. Process Results
                data = result.get("data", {})
                target_bbox = None
                
                # Check for "Person" intent
                is_person_target = local_target.lower() in ["person", "human", "face", "man", "woman"]

                # Case A: Try Mediapipe (Only if Person is requested)
                if is_person_target and isinstance(data, dict) and "pose_landmarks" in data:
                     pose = data.get("pose_landmarks")
                     if pose and len(pose) > 0:
                        nose = pose[0]
                        # Mediapipe is 0-1 normalized, convert to pixels
                        nx = nose["x"] * w
                        ny = nose["y"] * h
                        # Create a point-bbox [x, y, x, y]
                        target_bbox = [nx, ny, nx, ny]
                
                # Case B: YOLO Fallback (or Primary for non-person objects)
                # If Mediapipe failed OR we are looking for a bottle/cup/etc
                if not target_bbox:
                    # Parse detections
                    detections = []
                    if isinstance(data, list):
                        detections = data
                    elif isinstance(data, dict) and "detections" in data:
                        detections = data["detections"]
                        
                    best_det = None
                    max_conf = 0.0
                    
                    for det in detections:
                        if det["class"] == local_target and det["confidence"] > 0.4:
                            if det["confidence"] > max_conf:
                                max_conf = det["confidence"]
                                best_det = det
                    
                    if best_det:
                        target_bbox = best_det["bbox"]
                            
                # 5. Update State
                if target_bbox:
                    # Get Robot Head State at the time of image capture
                    robot_state = self.state_buffer.get_state_at(timestamp)
                    if robot_state:
                        # Pass both BBox and the ground-truth angles
                        self.servo_manager.update_measurement(target_bbox, robot_state)
                    else:
                        # Fallback (ServoManager will use current angles, less accurate)
                        self.servo_manager.update_measurement(target_bbox, None)
                                
            except Exception as e:
                print(f"VisionReceiver Error: {e}")
                time.sleep(1)
        
        video_sub.close()
        perception_req.close()
        context.term()
        print("VisionReceiver: Stopped.")

