#!/usr/bin/env python3
import zmq
import cv2
import numpy as np
import time
import json
import threading
import sys

class VisionViewer:
    def __init__(self, host="localhost", video_port=5559, perception_port=5557, command_port=5561):
        self.host = host
        self.video_port = video_port
        self.perception_port = perception_port
        self.command_port = command_port
        
        self.context = zmq.Context()
        self.running = True
        self.window_name = "Pepper Vision (Host)"
        
        # State
        self.latest_detections = []
        self.current_thresh = 0.5
        
        # Sockets
        self.video_sub = None
        self.perception_req = None
        self.cmd_socket = None
        
    def connect(self):
        """Initialize ZMQ connections."""
        print(f"Connecting to PepperWizard at {self.host}...")
        
        # 1. Video Stream (SUB)
        self.video_sub = self.context.socket(zmq.SUB)
        self.video_sub.connect(f"tcp://{self.host}:{self.video_port}")
        self.video_sub.setsockopt_string(zmq.SUBSCRIBE, "video")
        self.video_sub.setsockopt(zmq.CONFLATE, 1) # Reduce latency: Only keep latest frame
        print(f" - Video: {self.video_port}")

        # 2. Perception Service (REQ)
        self.perception_req = self.context.socket(zmq.REQ)
        self.perception_req.connect(f"tcp://{self.host}:{self.perception_port}")
        self.perception_req.setsockopt(zmq.RCVTIMEO, 2000)
        self.perception_req.setsockopt(zmq.SNDTIMEO, 2000)
        print(f" - Perception: {self.perception_port}")
        
        # 3. Command Channel (REQ)
        self.cmd_socket = self.context.socket(zmq.REQ)
        self.cmd_socket.connect(f"tcp://{self.host}:{self.command_port}")
        self.cmd_socket.setsockopt(zmq.RCVTIMEO, 1000)
        self.cmd_socket.setsockopt(zmq.SNDTIMEO, 1000)
        print(f" - Commands: {self.command_port}")

    def setup_gui(self):
        cv2.namedWindow(self.window_name)
        cv2.createTrackbar("Confidence %", self.window_name, 50, 100, lambda x: None)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

    def _mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.handle_click(x, y)

    def handle_click(self, x, y):
        print(f"[Click] {x}, {y}")
        min_dist = float('inf')
        best_det = None
        
        # Find closest detection
        for det in self.latest_detections:
            bbox = det.get("bbox", [0,0,0,0])
            x1, y1, x2, y2 = map(int, bbox)
            cx, cy = (x1+x2)//2, (y1+y2)//2
            dist = ((x-cx)**2 + (y-cy)**2)**0.5
            
            if dist < min_dist:
                min_dist = dist
                best_det = det
        
        if best_det and min_dist < 100:
            target = best_det.get("class", "unknown")
            self.send_command("track", target)
        else:
            self.send_command("stop_track")

    def send_command(self, cmd_type, target=None):
        payload = {"command": cmd_type}
        if target:
            payload["target"] = target
            print(f">> TRACK: {target}")
        else:
            print(">> STOP TRACKING")
            
        try:
            self.cmd_socket.send_json(payload)
            rep = self.cmd_socket.recv_json()
            print(f"<< Wizard: {rep}")
        except zmq.ZMQError as e:
            print(f"Command Error: {e}")
            # Recreate socket on error
            self.cmd_socket.close()
            self.cmd_socket = self.context.socket(zmq.REQ)
            self.cmd_socket.connect(f"tcp://{self.host}:{self.command_port}")
            self.cmd_socket.setsockopt(zmq.RCVTIMEO, 1000)

    def decode_frame(self, msg):
        """Decodes various ZMQ buffer formats into BGR image."""
        if len(msg) == 76800: # 320x240 Grey
            h, w = 240, 320
            frame = np.frombuffer(msg, dtype=np.uint8).reshape((h, w))
            return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif len(msg) == 153600: # 320x240 YUV422
            h, w = 240, 320
            frame = np.frombuffer(msg, dtype=np.uint8).reshape((h, w, 2))
            return cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_YUYV)
        elif len(msg) == 230400: # 320x240 RGB
            h, w = 240, 320
            frame = np.frombuffer(msg, dtype=np.uint8).reshape((h, w, 3))
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        elif len(msg) == 921600: # 640x480 RGB
            h, w = 480, 640
            frame = np.frombuffer(msg, dtype=np.uint8).reshape((h, w, 3))
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        elif len(msg) == 38400: # 160x120 YUV422
            frame = np.frombuffer(msg, dtype=np.uint8).reshape((120, 160, 2))
            return cv2.cvtColor(cv2.resize(frame, (320, 240)), cv2.COLOR_YUV2BGR_YUYV)
        return None

    def get_perception(self, img_bgr):
        """Sends frame to perception service and gets results."""
        _, jpg = cv2.imencode('.jpg', img_bgr)
        try:
            self.perception_req.send_multipart([b'{}', jpg.tobytes()])
            return self.perception_req.recv_json()
        except zmq.ZMQError:
            # Reconnect lazy pirate
            self.perception_req.close()
            self.perception_req = self.context.socket(zmq.REQ)
            self.perception_req.connect(f"tcp://{self.host}:{self.perception_port}")
            self.perception_req.setsockopt(zmq.RCVTIMEO, 2000)
            return {}

    def draw_overlays(self, frame, data):
        """Draws detections and skeletons."""
        detections = []
        if isinstance(data, list):
            detections = data
        else:
            detections = data.get("detections", [])
            
        self.latest_detections = []
        self.current_thresh = cv2.getTrackbarPos("Confidence %", self.window_name) / 100.0
        
        # YOLO
        for det in detections:
            conf = det.get("confidence", 0.0)
            if conf < self.current_thresh: continue
            
            self.latest_detections.append(det)
            bbox = det.get("bbox", [0,0,0,0])
            x1, y1, x2, y2 = map(int, bbox)
            label = f"{det.get('class','?')} {conf:.2f}"
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 100, 0), 2)
            cv2.putText(frame, label, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,100,0), 1)

        # Skeleton
        pose = data.get("pose_landmarks") if isinstance(data, dict) else None
        if pose:
            self._draw_skeleton(frame, pose)

        # UI Info
        cv2.putText(frame, f"Detections: {len(self.latest_detections)}", (10, 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    def _draw_skeleton(self, frame, pose):
        h, w = frame.shape[:2]
        connections = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24), (0, 11), (0, 12)]
        
        for i, j in connections:
            if i < len(pose) and j < len(pose):
                 p1, p2 = pose[i], pose[j]
                 if p1["visibility"] > self.current_thresh and p2["visibility"] > self.current_thresh:
                     pt1 = (int(p1["x"] * w), int(p1["y"] * h))
                     pt2 = (int(p2["x"] * w), int(p2["y"] * h))
                     cv2.line(frame, pt1, pt2, (0, 255, 255), 2)

    def run(self):
        self.connect()
        self.setup_gui()
        print("VisionViewer Running. Press 'q' to exit.")
        
        # Start Perception Thread
        self.lock = threading.Lock()
        self.current_frame = None
        self.latest_data = {}
        
        perc_thread = threading.Thread(target=self._perception_loop, daemon=True)
        perc_thread.start()
        
        while self.running:
            try:
                # 1. Get Video (Blocking with short timeout or Polling)
                # Since we use CONFLATE, this should always give us the most recent frame instantly if available.
                if self.video_sub.poll(100):
                    parts = self.video_sub.recv_multipart()
                    if len(parts) < 2: continue
                    msg = parts[-1] 
                    
                    frame = self.decode_frame(msg)
                    if frame is not None:
                         # Share frame with perception thread
                         with self.lock:
                             self.current_frame = frame.copy() # Copy to avoid race if drawing writes to it? (drawing usually writes)
                             
                         # Get latest perception result
                         with self.lock:
                             data = self.latest_data
                         
                         # Draw
                         self.draw_overlays(frame, data)
                         cv2.imshow(self.window_name, frame)
                    
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        self.running = False
                        break
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                print(f"Main Loop Error: {e}")
                
        cv2.destroyAllWindows()
        self.context.term()

    def _perception_loop(self):
        """Runs perception inference in parallel."""
        while self.running:
            frame_to_process = None
            with self.lock:
                if self.current_frame is not None:
                     frame_to_process = self.current_frame.copy()
            
            if frame_to_process is not None:
                # This blocks but doesn't stop UI
                res = self.get_perception(frame_to_process)
                if res:
                    with self.lock:
                        self.latest_data = res.get("data", {})
            else:
                time.sleep(0.01)

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    viewer = VisionViewer(host=host)
    viewer.run()
