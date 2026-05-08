"""Unit tests for AudioSink."""
import queue
import threading
import time
import unittest

import numpy as np
import zmq

from pepper_wizard.recording.audio_sink import AudioSink


class _FakeAudioPublisher(threading.Thread):
    """Publishes int16 mono 16kHz chunks (170ms = 2720 samples) on a PUB socket."""

    def __init__(self, port, chunk_count, interval_s=0.05):
        super().__init__(daemon=True)
        self.port = port
        self.chunk_count = chunk_count
        self.interval_s = interval_s
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        self._sock.bind(f"tcp://*:{port}")
        self._stop_evt = threading.Event()

    def run(self):
        time.sleep(0.1)
        for i in range(self.chunk_count):
            if self._stop_evt.is_set():
                return
            samples = np.full(2720, i % 32767, dtype=np.int16)
            self._sock.send(samples.tobytes())
            time.sleep(self.interval_s)

    def stop(self):
        self._stop_evt.set()
        self._sock.close(linger=0)


class TestAudioSink(unittest.TestCase):
    def test_captures_chunks_with_timestamps(self):
        port = 25563
        out_queue = queue.Queue()
        pub = _FakeAudioPublisher(port, chunk_count=5, interval_s=0.02)
        sink = AudioSink(f"tcp://localhost:{port}", out_queue)
        sink.start()
        pub.start()
        pub.join(timeout=5.0)
        time.sleep(0.3)
        sink.stop()

        chunks = []
        while not out_queue.empty():
            chunks.append(out_queue.get_nowait())

        self.assertGreaterEqual(len(chunks), 3)
        for c in chunks:
            self.assertIn("ingest_utc_ns", c)
            self.assertIn("pcm_bytes", c)
            self.assertEqual(c["samples"], 2720)
            self.assertEqual(len(c["pcm_bytes"]), 2720 * 2)
        ts = [c["ingest_utc_ns"] for c in chunks]
        self.assertEqual(ts, sorted(ts))
        pub.stop()


if __name__ == "__main__":
    unittest.main()
