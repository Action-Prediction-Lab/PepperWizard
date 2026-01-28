#!/usr/bin/env python3
import zmq
import cv2
import numpy as np
import time
import json
import threading

def main():
    # Context
    context = zmq.Context()
    
    # 1. Connect to Video Stream (PUB) from PepperBox
    video_sub = context.socket(zmq.SUB)
    video_sub.connect("tcp://localhost:5559")
    video_sub.setsockopt_string(zmq.SUBSCRIBE, "video")
    print("Connected to Video Stream (5559)")

    # 2. Connect to Perception Service (REP) from PepperPerception
    def connect_perception():
        req = context.socket(zmq.REQ)
        req.connect("tcp://localhost:5557")
        req.setsockopt(zmq.RCVTIMEO, 5000) # 5s timeout
        req.setsockopt(zmq.SNDTIMEO, 5000)
        return req

    perception_req = connect_perception()
    print("Connected to Perception Service (5557)")
    
    # GUI Setup
    window_name = "Pepper Vision"
    cv2.namedWindow(window_name)
    
    # Trackbar for Confidence
    def nothing(x): pass
    cv2.createTrackbar("Confidence %", window_name, 50, 100, nothing)

    print("Starting visual debugger...")
    
    while True:
        try:
            # A. Receive Frame
            if video_sub.poll(100):
                try:
                    parts = video_sub.recv_multipart(flags=zmq.NOBLOCK)
                    timestamp = 0.0
                    if len(parts) == 3:
                        topic, header, msg = parts 
                        # timestamp = struct.unpack('d', header)[0]
                    elif len(parts) == 2:
                        topic, msg = parts
                    else:
                        continue
                except zmq.Again:
                    continue

                # Check Resolution
                if len(msg) == 76800:
                    # Greyscale Y-Channel (320x240, 1 byte/px)
                    h, w = 240, 320
                    frame_grey = np.frombuffer(msg, dtype=np.uint8).reshape((h, w))
                    # Convert to BGR for display
                    display_frame = cv2.cvtColor(frame_grey, cv2.COLOR_GRAY2BGR)
                elif len(msg) == 153600:
                    # YUV422 Input (320x240, 2 bytes/px)
                    h, w = 240, 320
                    frame_yuv = np.frombuffer(msg, dtype=np.uint8).reshape((h, w, 2))
                    display_frame = cv2.cvtColor(frame_yuv, cv2.COLOR_YUV2BGR_YUYV)
                elif len(msg) == 230400:
                    h, w = 240, 320
                    frame = np.frombuffer(msg, dtype=np.uint8).reshape((h, w, 3))
                    display_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                elif len(msg) == 921600:
                    h, w = 480, 640
                    frame = np.frombuffer(msg, dtype=np.uint8).reshape((h, w, 3))
                    display_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                elif len(msg) == 38400:
                    # QQVGA YUYV (160x120 * 2) -> Extract Y -> Resize
                    y_channel = msg[0::2]
                    h, w = 120, 160
                    frame_grey = np.frombuffer(y_channel, dtype=np.uint8).reshape((h, w))
                    display_frame = cv2.cvtColor(cv2.resize(frame_grey, (320, 240)), cv2.COLOR_GRAY2BGR)
                else:
                    print(f"Unknown frame size: {len(msg)}")
                    continue
                    
                # Format is already BGR for display/encode
                
                
                # B. Send to Perception (Needs JPG bytes)
                # CV2.imencode expects BGR input.
                _, jpg_encoded = cv2.imencode('.jpg', display_frame)
                
                # REQ/REP is blocking.
                try:
                    perception_req.send_multipart([b'{}', jpg_encoded.tobytes()])
                    # Wait for reply
                    result_json = perception_req.recv_json()
                except (zmq.Again, zmq.ZMQError) as e:
                    print(f"Warning: Perception timed out or error ({e}). Reconnecting...")
                    # Lazy Pirate: Close and Reopen
                    perception_req.close()
                    perception_req = connect_perception()
                    result_json = {}
                except Exception as e:
                    print(f"Perception Error: {e}")
                    result_json = {}
                
                # C. Overlay Results
                response_data = result_json.get("data", {})
                
                # Get threshold from slider
                current_thresh = cv2.getTrackbarPos("Confidence %", window_name) / 100.0
                
                filtered_detections = []
                
                # 1. Draw YOLO Bounding Boxes (if present)
                if isinstance(response_data, list):
                    detections = response_data
                else:
                    detections = response_data.get("detections", [])
                
                for det in detections:
                    class_name = det.get("class", "unknown")
                    conf = det.get("confidence", 0.0)
                    bbox = det.get("bbox", [0,0,0,0]) # [x1, y1, x2, y2]
                    
                    if conf < current_thresh:
                        continue
                        
                    filtered_detections.append(det)
                    x1, y1, x2, y2 = map(int, bbox)
                    
                    # Blue-ish for YOLO
                    color = (255, 100, 0) 
                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                    label = f"{class_name} {conf:.2f}"
                    cv2.putText(display_frame, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

                # 2. Draw Mediapipe Landmarks (if present)
                pose = None
                if not isinstance(response_data, list):
                    pose = response_data.get("pose_landmarks")
                if pose:
                    # Define simple skeleton topology (indices based on Mediapipe Pose)
                    # 0: Nose, 11: Yes, 12: Right Shoulder, 13: Left Elbow, 14: Right Elbow, ...
                    connections = [
                        (11, 12), (11, 13), (13, 15), # Left Arm
                        (12, 14), (14, 16),           # Right Arm
                        (11, 23), (12, 24), (23, 24), # Torso
                        (0, 11), (0, 12)              # Neck/Head estimate
                    ]
                    
                    # Draw Lines
                    for i, j in connections:
                         if i < len(pose) and j < len(pose):
                             p1 = pose[i]
                             p2 = pose[j]
                             if p1["visibility"] > current_thresh and p2["visibility"] > current_thresh:
                                 pt1 = (int(p1["x"] * w), int(p1["y"] * h))
                                 pt2 = (int(p2["x"] * w), int(p2["y"] * h))
                                 cv2.line(display_frame, pt1, pt2, (0, 255, 255), 2) # Yellow Skeleton
                    
                    # Draw Points
                    for i, lm in enumerate(pose):
                        if lm["visibility"] > current_thresh:
                            x, y = int(lm["x"] * w), int(lm["y"] * h)
                            # Nose = Green, Others = Red
                            color = (0, 255, 0) if i == 0 else (0, 0, 255)
                            radius = 4 if i == 0 else 2
                            cv2.circle(display_frame, (x, y), radius, color, -1)
                            
                            if i == 0:
                                cv2.putText(display_frame, "Target", (x+10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

                # Draw Detection Count
                info_text = f"YOLO: {len(filtered_detections)} | Pose: {'Yes' if pose else 'No'}"
                cv2.putText(display_frame, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # D. Show
                cv2.imshow(window_name, display_frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                pass

        except KeyboardInterrupt:
            print("Stopping...")
            break
        except Exception as e:
            print(f"Error: {e}")
            break
            
    cv2.destroyAllWindows()
    context.term()

if __name__ == "__main__":
    main()
