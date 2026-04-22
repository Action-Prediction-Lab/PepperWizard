"""
Unit tests for STTClient using a mock ZMQ REP server.
"""

import threading
import time
import unittest

import zmq

from pepper_wizard.stt_client import STTClient


# ───────────────────────────────── Helpers ──────────────────────────────────

class _FakeSTTServer(threading.Thread):
    """Mock ZMQ REP server for testing STTClient."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.received = []
        self._should_stop = threading.Event()

    def stop(self):
        self._should_stop.set()

    def run(self):
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REP)
        sock.bind(f"tcp://*:{self.port}")
        sock.setsockopt(zmq.RCVTIMEO, 100)
        while not self._should_stop.is_set():
            try:
                msg = sock.recv_json()
            except zmq.Again:
                continue
            self.received.append(msg)
            action = msg.get("action", "")
            if action == "ping":
                sock.send_json({"status": "ok"})
            elif action == "start":
                sock.send_json({"status": "recording"})
            elif action == "stop":
                sock.send_json({"transcription": "Hello world", "duration": 1.5})
            elif action == "enable_streaming":
                sock.send_json({"status": "streaming"})
            elif action == "disable_streaming":
                sock.send_json({"status": "idle"})
            elif action == "mute":
                sock.send_json({"status": "muted"})
            elif action == "unmute":
                sock.send_json({"status": "unmuted"})
            else:
                sock.send_json({"error": f"Unknown: {action}"})
        sock.close(linger=0)
        ctx.term()


# ──────────────────────────────── Tests ─────────────────────────────────────

class TestSTTClient(unittest.TestCase):
    def setUp(self):
        self.server = _FakeSTTServer(port=15562)
        self.server.start()
        time.sleep(0.1)
        self.client = STTClient("tcp://localhost:15562", timeout_ms=5000)

    def tearDown(self):
        self.client.close()
        self.server.stop()
        self.server.join(timeout=1.0)

    def test_ping(self):
        self.assertTrue(self.client.ping())
        self.assertTrue(self.client.is_connected)

    def test_start_recording(self):
        self.assertTrue(self.client.start_recording())

    def test_stop_and_transcribe(self):
        self.client.start_recording()
        result = self.client.stop_and_transcribe()
        self.assertEqual(result["transcription"], "Hello world")
        self.assertEqual(result["duration"], 1.5)
        self.assertNotIn("error", result)

    def test_full_flow(self):
        """Simulate a complete ping → start → stop → transcribe flow."""
        self.assertTrue(self.client.ping())
        self.assertTrue(self.client.start_recording())

        result = self.client.stop_and_transcribe()
        self.assertEqual(result["transcription"], "Hello world")
        self.assertIsInstance(result["duration"], float)

    def test_timeout_on_unreachable_server(self):
        """Client should handle a downed server gracefully."""
        self.client.close()
        self.server.stop()
        self.server.join(timeout=1.0)

        unreachable_client = STTClient("tcp://localhost:19999", timeout_ms=1000)
        self.assertFalse(unreachable_client.ping())
        self.assertFalse(unreachable_client.is_connected)
        unreachable_client.close()

    def test_enable_streaming(self):
        self.assertTrue(self.client.enable_streaming())

    def test_disable_streaming(self):
        self.assertTrue(self.client.disable_streaming())

    def test_mute(self):
        self.assertTrue(self.client.mute())

    def test_unmute(self):
        self.assertTrue(self.client.unmute())


if __name__ == "__main__":
    unittest.main()
