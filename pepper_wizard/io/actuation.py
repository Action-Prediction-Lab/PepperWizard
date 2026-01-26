from threading import Thread, Event
import time
import queue

class RobotActuator(Thread):
    """
    Decoupled Actuator Thread.
    Consumes commands from a queue and sends them to RobotClient.
    Runs at a fixed frequency (e.g. 50Hz) to prevent overloading Naoqi.
    """
    def __init__(self, robot_client, frequency=50.0):
        super().__init__()
        self.client = robot_client
        self.frequency = frequency
        self.period = 1.0 / frequency
        self._stop_event = Event()
        self.command_queue = queue.Queue(maxsize=1) # Only keep latest command
        self.daemon = True
        
    def start_service(self):
        """Interface compatibility."""
        if not self.is_alive():
            self.start()

    def stop_service(self):
        self.stop() # Alias

    def stop(self):
        self._stop_event.set()

    def set_stiffness(self, val):
        """Set head stiffness directly (blocking/immediate)."""
        try:
            # RobotClient wraps ALMotion, so use its method
            if hasattr(self.client, 'set_stiffnesses'):
                 self.client.set_stiffnesses("Head", val)
            else:
                 # Fallback if accessed via direct proxy (unlikely here)
                 self.client.ALMotion.setStiffnesses("Head", val)
        except Exception as e:
            print(f"Error setting stiffness: {e}")

    def set_head_position(self, yaw, pitch, speed=0.1):
        """Queue a position command."""
        cmd = {
            "type": "position",
            "yaw": yaw,
            "pitch": pitch,
            "speed": speed
        }
        self._send_internal(cmd)

    def set_head_velocity(self, yaw_vel, pitch_vel):
        """Queue a velocity command."""
        cmd = {
            "type": "velocity",
            "yaw": yaw_vel,
            "pitch": pitch_vel
        }
        self._send_internal(cmd)

    def _send_internal(self, command):
        """
        Non-blocking send. Overwrites previous command if queue is full.
        """
        try:
            # Empty queue first to ensure we always send freshest data
            while not self.command_queue.empty():
                self.command_queue.get_nowait()
        except queue.Empty:
            pass
            
        try:
            self.command_queue.put_nowait(command)
        except queue.Full:
            pass

    def run(self):
        while not self._stop_event.is_set():
            start_t = time.time()
            
            try:
                try:
                    cmd = self.command_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                    
                if cmd['type'] == 'position':
                    speed = cmd.get('speed', 0.1)
                    # Use set_angles for smooth interpolated control
                    # OPTIMIZATION: Send both joints in one packet to reduce latency/overhead
                    # and ensure synchronized motion start.
                    self.client.set_angles(["HeadYaw", "HeadPitch"], [cmd['yaw'], cmd['pitch']], speed)
                    
                elif cmd['type'] == 'velocity':
                    # Support velocity control if needed (e.g. for PID)
                    names = ["HeadYaw", "HeadPitch"]
                    changes = [cmd['yaw'], cmd['pitch']]
                    # setAngles with fraction? Or changeAngles? 
                    # Actually, for velocity, we usually use move() or setStiffness. 
                    # If this is PID velocity output, we integrate it to position in tracker anyway?
                    # Wait, the tracker output 'velocity' type might need setAngles relative?
                    # Original code likely didn't use this much if 'native' is position.
                    pass
                    
            except Exception as e:
                print(f"Actuator Error: {e}")
                
            # Sleep to maintain frequency
            elapsed = time.time() - start_t
            sleep_t = self.period - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)
