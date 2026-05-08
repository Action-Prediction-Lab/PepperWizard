"""ZMQ audio subscriber that timestamps int16 PCM chunks and enqueues them.

Subscribes to the PepperBox audio PUB stream (default tcp://localhost:5563).
Wire format: single frame of raw bytes, int16 little-endian, mono, 16 kHz.
Default chunk size is 2720 samples (5440 bytes = 170 ms) but the sink does
not enforce a fixed size — it forwards whatever chunk size the publisher sends.

Output queue payload:
  {
    "ingest_utc_ns": int,
    "pcm_bytes": bytes,
    "samples": int,
    "chunk_index": int,
  }
"""
import threading
import time

import zmq


class AudioSink(threading.Thread):
    SAMPLE_BYTES = 2

    def __init__(self, zmq_address, out_queue):
        super().__init__(daemon=True)
        self.zmq_address = zmq_address
        self.out_queue = out_queue
        self._stop_evt = threading.Event()
        self._chunk_index = 0

    def stop(self):
        # _stop is an internal slot on threading.Thread; keep our Event as _stop_evt.
        self._stop_evt.set()

    def run(self):
        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.SUB)
        sock.connect(self.zmq_address)
        sock.setsockopt(zmq.SUBSCRIBE, b"")
        sock.setsockopt(zmq.RCVTIMEO, 200)

        try:
            while not self._stop_evt.is_set():
                try:
                    chunk = sock.recv()
                except zmq.Again:
                    continue
                ingest_ns = time.time_ns()
                if len(chunk) % self.SAMPLE_BYTES != 0:
                    continue
                self.out_queue.put({
                    "ingest_utc_ns": ingest_ns,
                    "pcm_bytes": chunk,
                    "samples": len(chunk) // self.SAMPLE_BYTES,
                    "chunk_index": self._chunk_index,
                })
                self._chunk_index += 1
        finally:
            sock.close(linger=0)
