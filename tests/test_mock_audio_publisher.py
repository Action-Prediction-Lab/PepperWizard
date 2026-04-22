import time
import threading
import unittest
import zmq
import numpy as np
import tempfile
import wave
import os
import json
import subprocess
import sys

from tools.mock_audio_publisher import stream_pcm_chunks, load_wav

CHUNK_BYTES = 5440  # 2720 int16 samples at 16 kHz front-mic


class TestMockPublisherWireContract(unittest.TestCase):
    def setUp(self):
        self.ctx = zmq.Context()
        self.sub = self.ctx.socket(zmq.SUB)

    def tearDown(self):
        self.sub.close(linger=0)
        self.ctx.term()

    def test_emits_one_chunk_every_170ms(self):
        self.sub.connect("tcp://localhost:15563")
        self.sub.setsockopt(zmq.SUBSCRIBE, b"")

        samples = b"\x00\x00" * (2720 * 3)
        t = threading.Thread(
            target=stream_pcm_chunks,
            kwargs={"pcm_bytes": samples, "bind": "tcp://*:15563"},
            daemon=True,
        )
        t.start()
        time.sleep(0.1)

        received = []
        t0 = time.time()
        while len(received) < 3 and time.time() - t0 < 2.0:
            try:
                msg = self.sub.recv(zmq.NOBLOCK)
                received.append((time.time() - t0, msg))
            except zmq.Again:
                time.sleep(0.01)
        t.join(timeout=2.0)

        self.assertGreaterEqual(len(received), 2)
        for _, msg in received:
            self.assertEqual(len(msg), CHUNK_BYTES)
        if len(received) >= 3:
            gap = received[2][0] - received[1][0]
        else:
            gap = received[1][0] - received[0][0]
        self.assertGreater(gap, 0.140)
        self.assertLess(gap, 0.250)


class TestMockPublisherWavLoader(unittest.TestCase):
    def _write_wav(self, path, samples_int16, sample_rate, channels):
        with wave.open(path, "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(samples_int16.tobytes())

    def test_loads_16k_mono_passthrough(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            samples = (np.sin(2 * np.pi * 440 * np.arange(16000) / 16000) * 10000).astype(np.int16)
            self._write_wav(path, samples, 16000, 1)
            pcm = load_wav(path)
            self.assertEqual(len(pcm), len(samples) * 2)
        finally:
            os.unlink(path)

    def test_resamples_44k_stereo_to_16k_mono(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            stereo = np.zeros((44100, 2), dtype=np.int16)
            stereo[:, 0] = (np.sin(2 * np.pi * 440 * np.arange(44100) / 44100) * 10000).astype(np.int16)
            stereo[:, 1] = stereo[:, 0]
            self._write_wav(path, stereo, 44100, 2)
            pcm = load_wav(path)
            # 1 second of source → ~16000 samples → 32000 bytes, allow ±1 %
            self.assertGreater(len(pcm), 31680)
            self.assertLess(len(pcm), 32320)
        finally:
            os.unlink(path)


class TestMockPublisherCLI(unittest.TestCase):
    def _make_wav(self, path, duration_s=0.5, sample_rate=16000):
        samples = (np.sin(2 * np.pi * 440 * np.arange(int(sample_rate * duration_s)) / sample_rate) * 10000).astype(np.int16)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(samples.tobytes())

    def test_list_fixtures_returns_sorted(self):
        from tools.mock_audio_publisher import _list_fixtures
        with tempfile.TemporaryDirectory() as d:
            for name in ["b.wav", "a.wav", "c.wav"]:
                self._make_wav(os.path.join(d, name))
            found = _list_fixtures(d)
            self.assertEqual([os.path.basename(p) for p in found], ["a.wav", "b.wav", "c.wav"])

    def test_list_fixtures_raises_on_empty(self):
        from tools.mock_audio_publisher import _list_fixtures
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                _list_fixtures(d)

    def test_cli_streams_fixtures_and_writes_log(self):
        """Drives the CLI end-to-end via a subprocess; asserts the JSONL log."""
        with tempfile.TemporaryDirectory() as d:
            fixture_a = os.path.join(d, "a.wav")
            fixture_b = os.path.join(d, "b.wav")
            self._make_wav(fixture_a, duration_s=0.2)
            self._make_wav(fixture_b, duration_s=0.2)
            log_path = os.path.join(d, "events.jsonl")

            proc = subprocess.run(
                [sys.executable, "-m", "tools.mock_audio_publisher",
                 d, "--port", "15564", "--gap-ms", "100", "--log", log_path],
                capture_output=True, timeout=15,
            )
            self.assertEqual(proc.returncode, 0,
                             msg=f"stderr: {proc.stderr.decode()}")

            with open(log_path) as f:
                events = [json.loads(line) for line in f]

            kinds = [e["event"] for e in events]
            self.assertEqual(kinds, [
                "utterance_start", "utterance_end", "gap_start",
                "utterance_start", "utterance_end", "gap_start",
            ])
            self.assertEqual(events[0]["file"], "a.wav")
            self.assertEqual(events[3]["file"], "b.wav")


if __name__ == "__main__":
    unittest.main()
