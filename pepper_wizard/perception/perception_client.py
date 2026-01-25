import zmq
import json
import cv2
import time

class PerceptionClient:
    def __init__(self, service_uri="tcp://localhost:5557"):
        self.service_uri = service_uri
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(service_uri)
        # Connected (Silenced for clean CLI)

    def detect(self, img_bgr, target_label=None):
        """
        Sends image to perception service.
        Returns list of detections or None on timeout/error.
        """
        try:
            # Encode to JPG
            _, img_jpg = cv2.imencode('.jpg', img_bgr)
            
            # Send Request
            # Protocol: [MetadataJSON, ImageBytes]
            meta = {}
            if target_label:
                meta["target"] = target_label
            
            self.socket.send_multipart([json.dumps(meta).encode(), img_jpg.tobytes()])
            
            # Wait for Reply (Blocking but fast)
            if self.socket.poll(1000): # 1s timeout
                result = self.socket.recv_json()
                return result.get("data", {})
            else:
                # Timeout (Silenced for clean CLI)
                # Reset socket on timeout
                self.socket.close()
                self.socket = self.context.socket(zmq.REQ)
                self.socket.connect(self.service_uri)
                return None
                
        except Exception as e:
            print(f"PerceptionClient Error: {e}")
            return None

    def close(self):
        self.socket.close()
        self.context.term()
