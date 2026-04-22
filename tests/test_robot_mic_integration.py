"""End-to-end: mock publisher -> stt-service streaming -> :5564 event receipt.

Requires the compose stack to be up (stt-service reachable on 5562 and 5564).
Skips cleanly if no speech fixtures have been recorded in tests/fixtures/audio/.
"""
import glob
import json
import os
import subprocess
import sys
import time
import unittest

import zmq

from pepper_wizard.stt_client import STTClient

FIXTURE_GLOB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "fixtures", "audio", "*.wav",
)


def _has_fixtures() -> bool:
    return bool(glob.glob(FIXTURE_GLOB))


@unittest.skipUnless(_has_fixtures(),
                     f"No WAV fixtures at {FIXTURE_GLOB} — record some and rerun.")
class TestRobotMicIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stt = STTClient("tcp://localhost:5562")
        if not cls.stt.ping():
            raise unittest.SkipTest(
                "stt-service not reachable on :5562 — is the stack up? "
                "(docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d)"
            )
        if not cls.stt.enable_streaming():
            raise unittest.SkipTest("stt-service refused enable_streaming")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "stt"):
            try:
                cls.stt.disable_streaming()
            except Exception:
                pass
            cls.stt.close()

    def test_mock_publisher_drives_transcription(self):
        ctx = zmq.Context.instance()
        sub = ctx.socket(zmq.SUB)
        sub.connect("tcp://localhost:5564")
        sub.setsockopt(zmq.SUBSCRIBE, b"")
        sub.setsockopt(zmq.RCVTIMEO, 500)

        fixture_dir = os.path.dirname(FIXTURE_GLOB)
        proc = subprocess.Popen([
            sys.executable, "-m", "tools.mock_audio_publisher",
            fixture_dir, "--gap-ms", "1200",
        ])

        received = []
        deadline = time.time() + 60.0
        try:
            while time.time() < deadline:
                try:
                    msg = sub.recv()
                except zmq.Again:
                    continue
                evt = json.loads(msg.decode())
                received.append(evt)
                if "text" in evt and evt["text"]:
                    break
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            sub.close()

        self.assertGreater(len(received), 0,
                           "no events received on :5564 within 60s; is streaming enabled?")
        utt = next((e for e in received if "text" in e), None)
        self.assertIsNotNone(utt, f"no utterance event in {received!r}")
        self.assertEqual(utt["source"], "robot_mic")
        self.assertGreater(utt["duration_s"], 0.1)


if __name__ == "__main__":
    unittest.main()
