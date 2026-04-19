"""Mock audio publisher: wire-compatible stand-in for PepperBox's ALAudioDevice PUB.

Emits 5440-byte int16-LE PCM chunks at 170 ms cadence on ZMQ PUB, matching the
NAOqi processRemote default. Downstream (stt-service) cannot tell whether the
source is the real bridge or this mock.
"""
import time
import zmq

CHUNK_BYTES = 5440  # 2720 int16 samples per chunk, 16 kHz mono
CHUNK_PERIOD_S = 0.170
DEFAULT_BIND = "tcp://*:5563"


def stream_pcm_chunks(pcm_bytes: bytes, bind: str = DEFAULT_BIND) -> None:
    """Stream `pcm_bytes` on a ZMQ PUB at 170 ms cadence. Blocks until done."""
    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.PUB)
    sock.bind(bind)
    sock.setsockopt(zmq.LINGER, 500)  # keep socket alive up to 500ms during close to flush pending sends

    time.sleep(0.05)  # Allow TCP connections to establish before first send
    next_deadline = time.time()
    offset = 0
    while offset < len(pcm_bytes):
        chunk = pcm_bytes[offset : offset + CHUNK_BYTES]
        if len(chunk) < CHUNK_BYTES:
            chunk = chunk + b"\x00" * (CHUNK_BYTES - len(chunk))
        sock.send(chunk)
        offset += CHUNK_BYTES

        next_deadline += CHUNK_PERIOD_S
        sleep_for = next_deadline - time.time()
        if sleep_for > 0:
            time.sleep(sleep_for)

    sock.close()
