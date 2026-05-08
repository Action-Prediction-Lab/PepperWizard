"""Unit tests for the Recorder orchestrator."""
import json
import os
import struct
import tempfile
import threading
import time
import unittest

import av
import numpy as np
import zmq

from pepper_wizard.recording.recorder import Recorder


class _FakeStreams:
    """Spawns video + audio fake publishers on chosen ports."""

    def __init__(self, video_port=25559, audio_port=25563):
        self.video_port = video_port
        self.audio_port = audio_port
        self._stop_evt = threading.Event()
        self._ctx = zmq.Context.instance()
        self._vsock = self._ctx.socket(zmq.PUB)
        self._vsock.bind(f"tcp://*:{video_port}")
        self._asock = self._ctx.socket(zmq.PUB)
        self._asock.bind(f"tcp://*:{audio_port}")
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        time.sleep(0.2)
        i = 0
        while not self._stop_evt.is_set():
            img = (np.ones((240, 320), dtype=np.uint8) * (i % 256)).tobytes()
            self._vsock.send_multipart([b"video", struct.pack("d", time.time()), img])
            samples = np.full(2720, i % 1000, dtype=np.int16)
            self._asock.send(samples.tobytes())
            i += 1
            time.sleep(0.05)

    def start(self):
        self._t.start()

    def stop(self):
        self._stop_evt.set()
        self._t.join(timeout=2.0)
        self._vsock.close(linger=0)
        self._asock.close(linger=0)


class TestRecorder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.streams = _FakeStreams()
        self.streams.start()

    def tearDown(self):
        self.streams.stop()

    def _config(self):
        return {
            "record_by_default": False,
            "output_dir": self.tmp,
            "video_codec": "ffv1",
            "video_pix_fmt": "yuv420p",
            "audio_codec": "pcm_s16le",
            "container": "mkv",
        }

    def _new_recorder(self):
        return Recorder(
            config=self._config(),
            session_id="TEST",
            video_address=f"tcp://localhost:{self.streams.video_port}",
            audio_address=f"tcp://localhost:{self.streams.audio_port}",
            clock_sync_url=None,
        )

    def test_start_stop_produces_triple(self):
        rec = self._new_recorder()
        rec.start()
        time.sleep(1.5)
        result = rec.stop()
        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result["mkv"]))
        self.assertTrue(os.path.exists(result["jsonl"]))
        self.assertTrue(os.path.exists(result["clocksync"]))

    def test_mkv_is_readable_and_has_both_streams(self):
        rec = self._new_recorder()
        rec.start()
        time.sleep(1.5)
        result = rec.stop()
        with av.open(result["mkv"]) as c:
            stream_types = {s.type for s in c.streams}
            self.assertSetEqual(stream_types, {"video", "audio"})

    def test_sidecar_has_header_and_records(self):
        rec = self._new_recorder()
        rec.start()
        time.sleep(1.5)
        result = rec.stop()
        with open(result["jsonl"]) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(lines[0]["type"], "header")
        self.assertIn("recording_start_utc_ns", lines[0])
        self.assertEqual(lines[0]["session_id"], "TEST")
        types = {l.get("type") for l in lines[1:]}
        self.assertIn("video", types)
        self.assertIn("audio", types)
        for stream in ("video", "audio"):
            ts = [l["ingest_utc_ns"] for l in lines if l.get("type") == stream]
            self.assertEqual(ts, sorted(ts), f"{stream} timestamps not monotonic")

    def test_double_start_is_no_op(self):
        rec = self._new_recorder()
        rec.start()
        rec.start()
        time.sleep(0.5)
        rec.stop()


if __name__ == "__main__":
    unittest.main()
