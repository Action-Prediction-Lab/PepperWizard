"""Unit tests for VideoSink — ZMQ subscriber that timestamps and queues frames."""
import queue
import struct
import threading
import time
import unittest

import numpy as np
import zmq

from pepper_wizard.recording.video_sink import VideoSink


class _FakeVideoPublisher(threading.Thread):
    """Publishes greyscale 320x240 frames at a controlled cadence on a PUB socket."""

    def __init__(self, port, frame_count, interval_s=0.05):
        super().__init__(daemon=True)
        self.port = port
        self.frame_count = frame_count
        self.interval_s = interval_s
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        self._sock.bind(f"tcp://*:{port}")
        self._stop_evt = threading.Event()

    def run(self):
        time.sleep(0.1)
        for i in range(self.frame_count):
            if self._stop_evt.is_set():
                return
            img = (np.ones((240, 320), dtype=np.uint8) * (i % 256)).tobytes()
            header = struct.pack("d", time.time())
            self._sock.send_multipart([b"video", header, img])
            time.sleep(self.interval_s)

    def stop(self):
        self._stop_evt.set()
        self._sock.close(linger=0)


class TestVideoSink(unittest.TestCase):
    def test_captures_frames_with_timestamps(self):
        port = 25559
        out_queue = queue.Queue()
        pub = _FakeVideoPublisher(port, frame_count=5, interval_s=0.02)
        sink = VideoSink(f"tcp://localhost:{port}", out_queue)
        sink.start()
        pub.start()
        pub.join(timeout=5.0)
        time.sleep(0.3)
        sink.stop()

        frames = []
        while not out_queue.empty():
            frames.append(out_queue.get_nowait())

        self.assertGreaterEqual(len(frames), 3, "expected at least 3 frames received")
        for f in frames:
            self.assertIn("ingest_utc_ns", f)
            self.assertIn("robot_ts_s", f)
            self.assertIn("img_bytes", f)
            self.assertEqual(len(f["img_bytes"]), 320 * 240)
        ts = [f["ingest_utc_ns"] for f in frames]
        self.assertEqual(ts, sorted(ts))
        pub.stop()


if __name__ == "__main__":
    unittest.main()
