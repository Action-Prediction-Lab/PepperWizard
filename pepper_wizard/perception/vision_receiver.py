import zmq
import struct
import numpy as np
import cv2
import time
import threading

class VisionReceiver(threading.Thread):
    def __init__(self, streamer_uri="tcp://localhost:5559"):
        super().__init__()
        self.streamer_uri = streamer_uri
        self.running = False
        self.lock = threading.Lock()
        self.latest_frame = None # (timestamp, img_bgr)
        self.callback = None

    def start_receiving(self, callback):
        """Register a callback(timestamp, img_bgr) to be called on new frames."""
        self.callback = callback
        self.start()

    def stop(self):
        self.running = False
        self.join()

    def run(self):
        self.running = True
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(self.streamer_uri)
        socket.setsockopt_string(zmq.SUBSCRIBE, "video")
        
        # Conflate to always get latest frame
        try:
            socket.setsockopt(zmq.CONFLATE, 1)
        except AttributeError:
            socket.setsockopt(zmq.RCVHWM, 1)
            
        print(f"VisionReceiver: Listening on {self.streamer_uri}")
        
        while self.running:
            try:
                # DRAIN QUEUE: Read all available frames, keep only the last one
                last_msg = None
                while socket.poll(0):
                    last_msg = socket.recv_multipart()
                
                if last_msg is None:
                    # No new data, wait a bit to avoid spin lock (but poll(100) above handles waiting if empty)
                    if socket.poll(100):
                         last_msg = socket.recv_multipart()
                    else:
                         # print("No data...")
                         continue
                
                msg = last_msg
                # print(f"Got msg len: {len(msg)}") 
                    
                # Protocol: [Topic, Header(double timestamp), Data]
                if len(msg) == 3:
                    topic, header, img_data = msg
                    timestamp = struct.unpack('d', header)[0]
                elif len(msg) == 2:
                    timestamp = time.time()
                    topic, img_data = msg
                else:
                    print(f"VisionReceiver: Invalid msg len {len(msg)}")
                    continue
                        
                # Decode
                # Assume QVGA (320x240) YUV422 or Grey
                w, h = 320, 240
                img_bgr = None
                
                if len(img_data) == 76800: # Greyscale
                    img_np = np.frombuffer(img_data, dtype=np.uint8).reshape((h, w))
                    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
                elif len(img_data) == 153600: # YUYV 422
                    img_np = np.frombuffer(img_data, dtype=np.uint8).reshape((h, w, 2))
                    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_YUV2BGR_YUYV)
                else:
                    print(f"VisionReceiver: Unknown data len {len(img_data)}")
                
                if img_bgr is not None and self.callback:
                    # print(f"VisionReceiver: Processing frame TS={timestamp}")
                    self.callback(timestamp, img_bgr)
            except Exception as e:
                print(f"VisionReceiver Error: {e}")
                time.sleep(0.1)
                
        socket.close()
        context.term()
