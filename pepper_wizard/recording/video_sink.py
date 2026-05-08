"""ZMQ video subscriber that timestamps frames and enqueues them.

Subscribes to the PepperBox video PUB stream (default tcp://localhost:5559).
Wire format: multipart [topic, header, img_data]
  - topic: bytes (b"video")
  - header: 8 bytes, packed double, robot wall-clock seconds
  - img_data: raw bytes (76800 greyscale Y8 320x240, or 153600 YUYV422)

Captures time.time_ns() immediately on recv() return, before any decode.
Output queue payload:
  {
    "ingest_utc_ns": int,
    "robot_ts_s": float | None,
    "img_bytes": bytes,
    "frame_index": int,  # monotonic counter assigned by the sink
  }

NB: We do NOT use ZMQ CONFLATE here. Recording requires every frame.
"""
import struct
import threading
import time

import zmq


class VideoSink(threading.Thread):
    def __init__(self, zmq_address, out_queue):
        super().__init__(daemon=True)
        self.zmq_address = zmq_address
        self.out_queue = out_queue
        self._stop_evt = threading.Event()
        self._frame_index = 0

    def stop(self):
        # _stop is an internal slot on threading.Thread; keep our Event as _stop_evt.
        self._stop_evt.set()

    def run(self):
        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.SUB)
        sock.connect(self.zmq_address)
        sock.setsockopt(zmq.SUBSCRIBE, b"video")
        sock.setsockopt(zmq.RCVTIMEO, 200)

        try:
            while not self._stop_evt.is_set():
                try:
                    msg = sock.recv_multipart()
                except zmq.Again:
                    continue
                ingest_ns = time.time_ns()
                if len(msg) == 3:
                    _topic, header, img_data = msg
                    try:
                        robot_ts_s = struct.unpack("d", header)[0]
                    except struct.error:
                        robot_ts_s = None
                elif len(msg) == 2:
                    _topic, img_data = msg
                    robot_ts_s = None
                else:
                    continue

                self.out_queue.put({
                    "ingest_utc_ns": ingest_ns,
                    "robot_ts_s": robot_ts_s,
                    "img_bytes": img_data,
                    "frame_index": self._frame_index,
                })
                self._frame_index += 1
        finally:
            sock.close(linger=0)
