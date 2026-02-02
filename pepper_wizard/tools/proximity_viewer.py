#!/usr/bin/env python3
import zmq
import json
import time
import math
import math
import numpy as np
import cv2
import sys
import struct

class ProximityViewer:
    def __init__(self, host="localhost", port=5560):
        self.host = host
        self.port = port
        self.running = True
        self.window_name = "Pepper Proximity (Radar)"
        
        # ZMQ
        self.context = zmq.Context()
        self.sub = None
        
        # UI Settings
        self.size = 600
        self.center = (self.size // 2, self.size // 2)
        self.px_per_m = 150 # 1 meter = 150 pixels
        
        # Colors (BGR)
        self.COLOR_BG = (15, 15, 15)
        self.COLOR_ROBOT = (200, 200, 200)
        self.COLOR_SONAR = (255, 255, 0) # Cyan
        self.COLOR_LASER = (50, 50, 255) # Red
        self.COLOR_GRID = (40, 40, 40)
        self.COLOR_TEXT = (180, 180, 180)
        self.COLOR_GAZE = (0, 255, 255) # Yellow
        self.COLOR_BUMPER = (0, 0, 255) # Red
        
    def connect(self):
        print(f"Connecting to State Service at {self.host}:{self.port}...")
        self.sub = self.context.socket(zmq.SUB)
        self.sub.connect(f"tcp://{self.host}:{self.port}")
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "proximity")
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "joints")
        self.sub.setsockopt(zmq.CONFLATE, 1) 

    def draw_grid(self, frame):
        for d in [0.5, 1.0, 1.5, 2.0]:
            r = int(d * self.px_per_m)
            cv2.circle(frame, self.center, r, self.COLOR_GRID, 1)
            cv2.putText(frame, f"{d}m", (self.center[0] + 5, self.center[1] - r - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, self.COLOR_TEXT, 1, cv2.LINE_AA)
        cv2.line(frame, (self.center[0], 0), (self.center[0], self.size), self.COLOR_GRID, 1)
        cv2.line(frame, (0, self.center[1]), (self.size, self.center[1]), self.COLOR_GRID, 1)

    def draw_robot(self, frame):
        radius = int(0.25 * self.px_per_m)
        cv2.circle(frame, self.center, radius, self.COLOR_ROBOT, 2, cv2.LINE_AA)
        front_pt = (self.center[0], self.center[1] - radius)
        cv2.circle(frame, front_pt, 4, self.COLOR_ROBOT, -1)


    def draw_sonar(self, frame, sonar_data):
        if not sonar_data: return
        angles = {"front_left": -22.5, "front_right": 22.5, "back_left": -157.5, "back_right": 157.5}
        for side, dist in sonar_data.items():
            if dist is None or dist > 5.0: continue
            angle_center = angles[side] - 90
            r = int(dist * self.px_per_m)
            overlay = frame.copy()
            cv2.ellipse(overlay, self.center, (r, r), 0, angle_center - 15, angle_center + 15, self.COLOR_SONAR, -1)
            cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
            angle_rad = math.radians(angle_center)
            end_pt = (int(self.center[0] + r * math.cos(angle_rad)), int(self.center[1] + r * math.sin(angle_rad)))
            cv2.line(frame, self.center, end_pt, self.COLOR_SONAR, 1, cv2.LINE_AA)

    def draw_lasers(self, frame, laser_data):
        if not laser_data: return
        configs = {"front": {"center_deg": -90, "fov": 60}, "left": {"center_deg": -180, "fov": 60}, "right": {"center_deg": 0, "fov": 60}}
        
        for side, segments in laser_data.items():
            if not segments: continue
            cfg = configs[side]
            start_deg = cfg["center_deg"] - (cfg["fov"] / 2)
            step = cfg["fov"] / len(segments)
            
            # Calculate all points first
            points = []
            for i, dist in enumerate(segments):
                if dist is None or dist > 3.0: 
                    points.append(None)
                    continue
                angle_rad = math.radians(start_deg + i * step)
                r = int(dist * self.px_per_m)
                pt = (int(self.center[0] + r * math.cos(angle_rad)), int(self.center[1] + r * math.sin(angle_rad)))
                points.append((pt, dist))

            # Draw lines between valid adjacent points
            for i in range(len(points) - 1):
                p1 = points[i]
                p2 = points[i+1]
                
                if p1 and p2:
                    pt1, dist1 = p1
                    pt2, dist2 = p2
                    
                    # Check physical distance (if > 30cm, likely a gap/jump)
                    # Simple heuristic: abs diff in range
                    if abs(dist1 - dist2) < 0.3:
                        color = self.COLOR_LASER
                        if dist1 < 0.5: color = (0, 0, 255)
                        elif dist1 < 1.0: color = (0, 165, 255)
                        
                        cv2.line(frame, pt1, pt2, color, 2, cv2.LINE_AA)
                        cv2.circle(frame, pt1, 2, color, -1) # Keep small dots for vertices

    def draw_gaze(self, frame, head_yaw):
        if head_yaw is None: return
        # Start at robot center
        length = 100
        # Robot(x,y) -> Screen(x,y):
        # x_screen = center_x - (robot_y * scale)
        # y_screen = center_y - (robot_x * scale)
        
        # Vector:
        vec_x_robot = math.cos(head_yaw)
        vec_y_robot = math.sin(head_yaw)
        
        end_pt = (
            int(self.center[0] - (vec_y_robot * length)),
            int(self.center[1] - (vec_x_robot * length))
        )
        
        cv2.line(frame, self.center, end_pt, self.COLOR_GAZE, 2, cv2.LINE_AA)

    def draw_bumpers(self, frame, bumper_data):
        if not bumper_data: return
        hit = False
        if bumper_data.get("front_left"):
            cv2.putText(frame, "HIT: FRONT LEFT", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.COLOR_BUMPER, 2)
            hit = True
        if bumper_data.get("front_right"):
            cv2.putText(frame, "HIT: FRONT RIGHT", (self.size - 220, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.COLOR_BUMPER, 2)
            hit = True
        if bumper_data.get("back"):
            cv2.putText(frame, "HIT: BACK", (self.size // 2 - 60, self.size - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.COLOR_BUMPER, 2)
            hit = True
        if hit:
            cv2.rectangle(frame, (0,0), (self.size, self.size), self.COLOR_BUMPER, 10)

    def run(self):
        self.connect()
        cv2.namedWindow(self.window_name)
        print(f"Proximity Viewer Running. Press 'q' to quit.")
        last_time = time.time()
        
        # Data persistence
        current_data = {"sonar": {}, "lasers": {}, "bumpers": {}, "head_yaw": 0.0, "vision": {}}
        last_data_time = 0
        DATA_TIMEOUT = 2.0 
        
        # Persistence Map Layer (Black)
        self.map_layer = np.zeros((self.size, self.size, 3), dtype=np.uint8)

        while self.running:
            # 1. Decay Map (Fade out old readings)
            # Subtract constant to fade to black
            self.map_layer = cv2.subtract(self.map_layer, (5, 5, 5, 0))
            
            # 2. Receiver over ZMQ (Non-blocking update)
            try:
                # Poll Main socket
                if self.sub.poll(5): # Short poll
                    topic, msg = self.sub.recv_multipart()
                    topic = topic.decode('utf-8')
                    if topic == "proximity":
                        new_data = json.loads(msg)
                        if new_data.get("sonar"): current_data["sonar"] = new_data["sonar"]
                        if new_data.get("lasers"): current_data["lasers"] = new_data["lasers"]
                        if new_data.get("bumpers"): current_data["bumpers"] = new_data["bumpers"]
                        last_data_time = time.time()
                    elif topic == "joints":
                        try:
                            t, yaw, pitch = struct.unpack('dff', msg)
                            current_data["head_yaw"] = yaw
                        except: pass
                
            except zmq.ZMQError:
                pass
            
            is_connected = (time.time() - last_data_time) < DATA_TIMEOUT
            
            # 3. Draw Sensors onto Map Layer (Additive)
            if is_connected:
                # Draw new data onto map
                self.draw_sonar(self.map_layer, current_data.get("sonar"))
                self.draw_lasers(self.map_layer, current_data.get("lasers"))
            
            # 4. Compose Final Frame
            # Start with Map Layer
            frame = self.map_layer.copy()
            
            # Draw Overlays (Non-persistent)
            self.draw_grid(frame)
            self.draw_robot(frame)
            
            if is_connected:
                self.draw_gaze(frame, current_data.get("head_yaw"))
                self.draw_bumpers(frame, current_data.get("bumpers"))
                status_color, status_text = (0, 255, 0), "CONNECTED"
            else:
                status_color, status_text = (0, 0, 255), "NO SIGNAL"

            # 4. UI Info
            now = time.time()
            fps = 1.0 / (now - last_time) if now - last_time > 0 else 0
            last_time = now
            cv2.putText(frame, f"{status_text} | {fps:.1f} Hz", (10, self.size - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 1, cv2.LINE_AA)
            cv2.putText(frame, f"Source: {self.host}:{self.port}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.COLOR_TEXT, 1, cv2.LINE_AA)
            
            cv2.imshow(self.window_name, frame)
            if cv2.waitKey(10) & 0xFF == ord('q'):
                break
                
        cv2.destroyAllWindows()
        self.context.term()

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    viewer = ProximityViewer(host=host)
    viewer.run()
