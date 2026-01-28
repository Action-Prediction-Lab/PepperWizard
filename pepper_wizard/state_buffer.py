import zmq
import threading
import time
import struct
import collections
import bisect

class StateBuffer(threading.Thread):
    def __init__(self, zmq_addr="tcp://localhost:5560", maxlen=200):
        super().__init__()
        self.zmq_addr = zmq_addr
        self.running = False
        # Buffer stores (timestamp, yaw, pitch)
        self.buffer = collections.deque(maxlen=maxlen)
        self.lock = threading.Lock()
        
    def stop(self):
        self.running = False
        self.join()
        
    def run(self):
        self.running = True
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(self.zmq_addr)
        socket.setsockopt_string(zmq.SUBSCRIBE, "joints")
        
        # Subscribed to {self.zmq_addr} (Silenced for clean CLI)
        
        while self.running:
            try:
                if socket.poll(100):
                    topic, data = socket.recv_multipart()
                    # Unpack: timestamp (double), yaw (float), pitch (float)
                    # format 'dff' is 16 bytes
                    if len(data) == 16:
                        ts, yaw, pitch = struct.unpack('dff', data)
                        with self.lock:
                            self.buffer.append((ts, yaw, pitch))
            except Exception as e:
                print(f"StateBuffer Error: {e}")
                time.sleep(0.1)
                
        socket.close()
        context.term()
        
    def get_state_at(self, query_time):
        """
        Returns (yaw, pitch) interpolated at query_time.
        Returns None if query_time is too old or too new (out of buffer range).
        """
        with self.lock:
            if not self.buffer:
                return None
            
            # Times in buffer are increasing
            timestamps = [x[0] for x in self.buffer]
            
            # Check bounds (allowing 50ms slack)
            if query_time < timestamps[0] - 0.05:
                # Too old
                return None 
            if query_time > timestamps[-1] + 0.05:
                # Too new (future?)
                return self.buffer[-1][1:] # Return latest
                
            # Find insertion point
            idx = bisect.bisect_right(timestamps, query_time)
            
            if idx == 0:
                return self.buffer[0][1:]
            if idx == len(timestamps):
                return self.buffer[-1][1:]
                
            # Interpolate
            t0, y0, p0 = self.buffer[idx-1]
            t1, y1, p1 = self.buffer[idx]
            
            # Linear interpolation factor
            alpha = (query_time - t0) / (t1 - t0) if (t1 - t0) > 0 else 0
            
            yaw = y0 + alpha * (y1 - y0)
            pitch = p0 + alpha * (p1 - p0)
            
            return (yaw, pitch)
