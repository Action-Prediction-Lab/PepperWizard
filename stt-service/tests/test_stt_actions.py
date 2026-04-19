import unittest
from unittest import mock

from main import STTService


class TestSTTActions(unittest.TestCase):
    """Unit-tests the action-dispatch table directly; no sockets, no threads."""

    @classmethod
    def setUpClass(cls):
        # Share the STTService (and its Whisper load) across the class.
        cls.svc = STTService(model_size="tiny.en", zmq_port=15562, sample_rate=16000)

    @classmethod
    def tearDownClass(cls):
        # Close the REP socket + context cleanly; no thread was ever started, so no races.
        try:
            cls.svc.socket.close(linger=0)
            cls.svc.context.term()
        except Exception:
            pass

    def test_ping(self):
        self.assertEqual(self.svc._handle_action({"action": "ping"}), {"status": "ok"})

    def test_unknown_action(self):
        reply = self.svc._handle_action({"action": "not_a_thing"})
        self.assertIn("error", reply)

    def test_mute_and_unmute(self):
        self.assertEqual(self.svc._handle_action({"action": "mute"}),   {"status": "muted"})
        self.assertTrue(self.svc._muted)
        self.assertEqual(self.svc._handle_action({"action": "unmute"}), {"status": "unmuted"})
        self.assertFalse(self.svc._muted)

    @mock.patch("main.StreamingWorker")
    def test_enable_and_disable_streaming(self, FakeWorker):
        fake_instance = FakeWorker.return_value
        self.assertEqual(self.svc._handle_action({"action": "enable_streaming"}), {"status": "streaming"})
        FakeWorker.assert_called_once()  # worker constructed
        fake_instance.start.assert_called_once()
        # Idempotent enable: second call doesn't create another worker
        self.assertEqual(self.svc._handle_action({"action": "enable_streaming"}), {"status": "streaming"})
        self.assertEqual(FakeWorker.call_count, 1)

        self.assertEqual(self.svc._handle_action({"action": "disable_streaming"}), {"status": "idle"})
        fake_instance.stop.assert_called_once()
        fake_instance.join.assert_called_once()
        # Idempotent disable
        self.assertEqual(self.svc._handle_action({"action": "disable_streaming"}), {"status": "idle"})
        fake_instance.stop.assert_called_once()  # still once, not twice
