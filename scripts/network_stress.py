import socket
import time
import sys
import threading

TARGET_IP = "192.168.123.50"
TARGET_PORT = 9559 # Stress the Naoqi port, or a random one
DURATION = 300 # Seconds (5 minutes)
PACKET_SIZE = 1024 # 1KB

def flood():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = b'X' * PACKET_SIZE
    
    print(f"Starting pulsing stress test: {BURST_DURATION}s Burst / {QUIET_DURATION}s Quiet...")
    
    while True:
        # 1. Burst Phase
        print(f"\n[STRESS START] Flooding for {BURST_DURATION}s...")
        burst_end = time.time() + BURST_DURATION
        count = 0
        while time.time() < burst_end:
            try:
                sock.sendto(payload, (TARGET_IP, TARGET_PORT))
                count += 1
                time.sleep(0.001) 
            except Exception as e:
                print(f"Error: {e}")
                break
        print(f"[STRESS END] Sent {count} packets. Resting...")
        
        # 2. Quiet Phase
        time.sleep(QUIET_DURATION)

if __name__ == "__main__":
    BURST_DURATION = 10
    QUIET_DURATION = 5 # Relentless! Only 5s to recover.
    THREAD_COUNT = 5   # Parallel flooding
    
    print(f"Starting RELENTLESS stress test: {THREAD_COUNT} threads, {BURST_DURATION}s Burst / {QUIET_DURATION}s Quiet...")

    # Run multiple threads to maximize throughput during burst
    threads = []
    for i in range(THREAD_COUNT):
        t = threading.Thread(target=flood)
        t.daemon = True # Allow easy kill
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()
