"""Host-microphone publisher: reads int16-LE mono 16 kHz PCM from stdin and
publishes 5440-byte chunks on ZMQ PUB. Wire-compatible with the mock and real
PepperBox audio publishers, so stt-service cannot tell the source.

Intended usage:

    arecord -f S16_LE -r 16000 -c 1 -q | python3 tools/host_mic_publisher.py

stdin backpressures at arecord's real-time capture rate, so chunks naturally
pace to 170 ms (5440 bytes / 32000 B/s = 0.17 s). No explicit timing needed.
"""
import argparse
import sys

import zmq

# Must match tools/mock_audio_publisher.py — 2720 int16 samples = 170 ms at 16 kHz mono.
CHUNK_BYTES = 5440
DEFAULT_BIND = "tcp://*:5563"


def publish_pcm_stream(stream, bind: str = DEFAULT_BIND) -> int:
    """Read raw int16-LE PCM bytes from `stream` and publish them as 5440-byte
    chunks on a ZMQ PUB. Blocks until EOF (a short read). Returns the number of
    full chunks published.

    `stream` must be a binary readable: `sys.stdin.buffer` in production, any
    `io.BytesIO` / pipe in tests.
    """
    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.PUB)
    sock.setsockopt(zmq.LINGER, 500)
    sock.bind(bind)

    # Brief warmup for subscribers to connect before the first chunk.
    # (Real-robot and mock paths both pay a similar cost; keeps the wire
    # behavior uniform.)
    import time
    time.sleep(0.05)

    n_chunks = 0
    try:
        while True:
            chunk = stream.read(CHUNK_BYTES)
            if len(chunk) < CHUNK_BYTES:
                # EOF — the trailing partial chunk is dropped (matches what the
                # mock does for whole-utterance files).
                break
            sock.send(chunk)
            n_chunks += 1
    finally:
        sock.close()
    return n_chunks


def main() -> int:
    p = argparse.ArgumentParser(
        description="Publish raw int16-LE mono 16 kHz PCM from stdin onto ZMQ PUB."
    )
    p.add_argument("--bind", type=str, default=DEFAULT_BIND,
                   help=f"ZMQ PUB bind address (default {DEFAULT_BIND}).")
    args = p.parse_args()

    n = publish_pcm_stream(sys.stdin.buffer, bind=args.bind)
    print(f"[host_mic_publisher] published {n} chunks, exiting.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
