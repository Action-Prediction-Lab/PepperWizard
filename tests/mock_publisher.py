import zmq
import time
import json
import math

def mock_publisher():
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind("tcp://*:5556")
    
    print("Mock Publisher started on tcp://*:5556")
    print("Simulating DualShock controller inputs...")

    try:
        t = 0
        while True:
            # Simulate a circle motion on left stick (move) and right stick (turn)
            t += 0.1
            
            # Message structure matches teleop.py expectation
            message = {
                "axes": {
                    "left_stick_x": 0.5 * math.sin(t),
                    "left_stick_y": 0.5 * math.cos(t),
                    "right_stick_x": 0.2 * math.sin(t * 0.5), # Slower rotation
                    "right_stick_y": 0.0
                },
                "buttons": {
                    # Add dummy buttons if needed
                    "cross": 0
                }
            }
            
            socket.send_json(message)
            print(f"Sent: {json.dumps(message)}")
            time.sleep(0.1) # 10Hz
            
    except KeyboardInterrupt:
        print("Stopping Mock Publisher")
    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    mock_publisher()
