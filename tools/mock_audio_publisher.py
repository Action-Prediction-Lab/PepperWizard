"""Mock audio publisher: wire-compatible stand-in for PepperBox's ALAudioDevice PUB.

Emits 5440-byte int16-LE PCM chunks at 170 ms cadence on ZMQ PUB, matching the
NAOqi processRemote default. Downstream (stt-service) cannot tell whether the
source is the real bridge or this mock.
"""
import argparse
import glob as _glob
import json
import os
import sys
import time
import zmq
import wave
import numpy as np
from scipy.signal import resample_poly

CHUNK_BYTES = 5440  # 2720 int16 samples per chunk, 16 kHz mono
CHUNK_PERIOD_S = 0.170
DEFAULT_BIND = "tcp://*:5563"
TARGET_RATE = 16000


def load_wav(path: str) -> bytes:
    """Load a WAV file and return 16 kHz mono int16 LE PCM bytes.

    Auto-downmixes multichannel to mono and auto-resamples to 16 kHz.
    """
    with wave.open(path, "rb") as w:
        n_channels = w.getnchannels()
        sample_width = w.getsampwidth()
        sample_rate = w.getframerate()
        n_frames = w.getnframes()
        raw = w.readframes(n_frames)

    if sample_width != 2:
        raise ValueError(f"{path}: only 16-bit PCM WAV is supported (got {sample_width*8}-bit)")

    samples = np.frombuffer(raw, dtype=np.int16)
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1).astype(np.int16)

    if sample_rate != TARGET_RATE:
        # resample_poly with int16 needs float intermediate
        as_float = samples.astype(np.float32)
        resampled = resample_poly(as_float, TARGET_RATE, sample_rate)
        samples = np.clip(resampled, -32768, 32767).astype(np.int16)

    return samples.tobytes()


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


def _list_fixtures(path_or_glob: str) -> list:
    if os.path.isdir(path_or_glob):
        matches = sorted(_glob.glob(os.path.join(path_or_glob, "*.wav")))
    else:
        matches = sorted(_glob.glob(path_or_glob))
    if not matches:
        raise SystemExit(f"No WAV files found at: {path_or_glob}")
    return matches


def _emit(log_fp, event: dict) -> None:
    event["t"] = time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime()) + f"{int((time.time()%1)*1000):03d}Z"
    if log_fp is not None:
        log_fp.write(json.dumps(event) + "\n")
        log_fp.flush()


def _stream_bytes_via(sock, pcm_bytes: bytes) -> None:
    """Like stream_pcm_chunks but reusing an already-bound socket."""
    offset = 0
    next_deadline = time.time()
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


def main() -> int:
    p = argparse.ArgumentParser(
        description="Mock PepperBox audio publisher (wire-compatible)."
    )
    p.add_argument("source", help="Directory or glob of WAV fixtures.")
    p.add_argument("--port", type=int, default=5563)
    p.add_argument("--gap-ms", type=int, default=1000,
                   help="Silence padding between fixtures (default 1000; must be >= vad.min_silence_ms).")
    p.add_argument("--loop", action="store_true",
                   help="Repeat the fixture list indefinitely.")
    p.add_argument("--log", type=str, default=None,
                   help="Write JSONL event log to this path.")
    args = p.parse_args()

    fixtures = _list_fixtures(args.source)
    pcm_cache = [(os.path.basename(path), load_wav(path)) for path in fixtures]

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.PUB)
    sock.bind(f"tcp://*:{args.port}")
    # Brief warmup for subscribers to connect before the first chunk.
    time.sleep(0.2)

    log_fp = open(args.log, "w") if args.log else None
    gap_bytes = b"\x00\x00" * (TARGET_RATE * args.gap_ms // 1000)

    try:
        while True:
            for name, pcm in pcm_cache:
                _emit(log_fp, {"event": "utterance_start", "file": name,
                               "duration_s": round(len(pcm) / 2 / TARGET_RATE, 3)})
                _stream_bytes_via(sock, pcm)
                _emit(log_fp, {"event": "utterance_end", "file": name})

                _emit(log_fp, {"event": "gap_start", "duration_ms": args.gap_ms})
                _stream_bytes_via(sock, gap_bytes)

            if not args.loop:
                break
    finally:
        sock.close()
        if log_fp:
            log_fp.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
