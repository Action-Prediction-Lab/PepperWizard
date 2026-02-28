"""
Manual STT Service Integration Test.

As a prerequisite the stt-service must be started prior to running this test.
It is intended to simulate pepper-wizard's side of the protocol: connect, ping, record, transcribe.

Usage:
    python tests/manual_stt_test.py [--port 5562]
"""

import argparse
import sys
import time

import zmq


def main():
    parser = argparse.ArgumentParser(description="Manual STT integration test")
    parser.add_argument("--port", type=int, default=5562)
    args = parser.parse_args()

    addr = f"tcp://localhost:{args.port}"
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, 30000)
    sock.setsockopt(zmq.LINGER, 0)
    sock.connect(addr)

    # 1. Ping
    print(f"--- Pinging stt-service at {addr} ---")
    sock.send_json({"action": "ping"})
    reply = sock.recv_json()
    if reply.get("status") != "ok":
        print(f"FAILURE: Ping failed: {reply}")
        sys.exit(1)
    print("Action: Ping successful.")

    # 2. Start Recording
    input("--- Press Enter to START recording, then speak a sentence ---")
    sock.send_json({"action": "start"})
    reply = sock.recv_json()
    if reply.get("status") != "recording":
        print(f"FAILURE: Start failed: {reply}")
        sys.exit(1)
    print("Action: Recording started.")

    # 3. Stop and Transcribe
    input("--- Press Enter to STOP recording ---")
    sock.send_json({"action": "stop"})
    print("Action: Transcribing...")
    reply = sock.recv_json()

    transcription = reply.get("transcription", "")
    duration = reply.get("duration", 0)
    error = reply.get("error")

    # 4. Verify
    print(f"--- Verifying Transcription ---")

    if error:
        print(f"FAILURE: STT error: {error}")
        sys.exit(1)

    print(f"Duration: {duration:.2f}s")
    print(f"Transcription: \"{transcription}\"")

    if not transcription:
        print("FAILURE: No transcription returned (mic issue or too quiet?).")
        sys.exit(1)

    print("--- SUCCESS: STT pipeline works end-to-end. ---")

    sock.close()
    ctx.term()


if __name__ == "__main__":
    main()
