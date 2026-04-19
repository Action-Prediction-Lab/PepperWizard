"""Ad-hoc dev sniffer for the robot-mic audio ZMQ PUB.

Subscribes to :5563 and reports per-chunk size + non-zero byte count for the
first N chunks it receives. Useful for confirming audio actually reaches
stt-service when debugging the VAD pipeline.

Usage (from inside the pepper-wizard container, which has pyzmq):

    docker compose run --rm pepper-wizard python3 tools/audio_sniffer.py
"""
import argparse
import sys

import zmq


def main() -> int:
    p = argparse.ArgumentParser(description="Sniff the robot-mic audio PUB.")
    p.add_argument("--address", default="tcp://localhost:5563")
    p.add_argument("--count", type=int, default=5)
    args = p.parse_args()

    ctx = zmq.Context()
    sock = ctx.socket(zmq.SUB)
    sock.connect(args.address)
    sock.setsockopt(zmq.SUBSCRIBE, b"")

    print(f"Sniffing {args.address} for {args.count} chunks...", file=sys.stderr)
    for i in range(args.count):
        chunk = sock.recv()
        nonzero = sum(1 for b in chunk if b != 0)
        print(f"chunk {i}: {len(chunk)} bytes, {nonzero} non-zero")

    sock.close()
    ctx.term()
    return 0


if __name__ == "__main__":
    sys.exit(main())
