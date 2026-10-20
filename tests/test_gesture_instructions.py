"""Tests for asking the experiment for the GestureSwitch instructions in a reply before Pepper speaks it."""
import tempfile
import threading
import time
import unittest

import zmq

from pepper_wizard.gesture_instructions import GestureInstructionsUnavailable, request_instructions


class Experiment:
    """A REP socket that answers one request with a fixed reply, or with no reply never answers."""

    def __init__(self, reply=None):
        self._dir = tempfile.TemporaryDirectory()
        self.endpoint = f"ipc://{self._dir.name}/control"
        self._sock = zmq.Context.instance().socket(zmq.REP)
        self._sock.setsockopt(zmq.LINGER, 0)
        self._sock.bind(self.endpoint)
        self.received = []
        self._thread = threading.Thread(target=self._answer, args=(reply,))
        self._thread.start()

    def _answer(self, reply):
        if self._sock.poll(2000):
            self.received.append(self._sock.recv_json())
            if isinstance(reply, bytes):
                self._sock.send(reply)
            elif reply is not None:
                self._sock.send_json(reply)

    def close(self):
        self._thread.join()
        self._sock.close()
        self._dir.cleanup()


class RequestTests(unittest.TestCase):
    def ask(self, reply, timeout_s=1.0):
        experiment = Experiment(reply)
        try:
            return request_instructions({"endpoint": experiment.endpoint, "timeout_s": timeout_s}, "hello there"), experiment.received
        finally:
            experiment.close()

    def test_the_reply_comes_back_with_its_instructions(self):
        answer = {"status": "ok", "text": "hello ^pCall(GestureSwitch.off()) there", "off_now": False, "turn": 2, "duty": 0.3}
        before = time.time()
        result, received = self.ask(answer)
        self.assertEqual(result, answer)
        self.assertEqual([(r["action"], r["text"]) for r in received], [("gesture_instructions", "hello there")])
        self.assertTrue(before + 1.0 <= received[0]["deadline"] <= time.time() + 1.0)

    def test_no_answer_within_the_timeout_is_unavailable(self):
        silent = Experiment()
        outcome = {}

        def ask():
            t0 = time.monotonic()
            try:
                request_instructions({"endpoint": silent.endpoint, "timeout_s": 0.2}, "hello there")
            except GestureInstructionsUnavailable:
                outcome["waited"] = time.monotonic() - t0
        asker = threading.Thread(target=ask, daemon=True)
        asker.start()
        asker.join(timeout=2.0)
        silent.close()
        self.assertFalse(asker.is_alive())
        self.assertGreaterEqual(outcome["waited"], 0.19)
        self.assertLess(outcome["waited"], 0.6)

    def test_an_answer_that_is_not_json_is_unavailable(self):
        with self.assertRaises(GestureInstructionsUnavailable):
            self.ask(b"not json")

    def test_a_config_without_endpoint_or_timeout_is_unavailable(self):
        for config in ({"endpoint": "tcp://localhost:5582"}, {"timeout_s": 1.0}, None,
                       {"endpoint": "tcp://localhost:5582", "timeout_s": float("inf")}, {"endpoint": "tcp://localhost:5582", "timeout_s": float("nan")},
                       {"endpoint": "tcp://localhost:5582", "timeout_s": -1.0}, {"endpoint": "tcp://localhost:5582", "timeout_s": 1e7}):
            with self.assertRaises(GestureInstructionsUnavailable):
                request_instructions(config, "hello there")

    def test_an_error_answer_is_unavailable(self):
        with self.assertRaises(GestureInstructionsUnavailable) as cm:
            self.ask({"status": "error", "error": "gesture_instructions needs the within design"})
        self.assertIn("within design", str(cm.exception))

    def test_an_answer_without_text_or_off_now_is_unavailable(self):
        for answer in ({"status": "ok", "off_now": False}, {"status": "ok", "text": "hi", "off_now": "no"}):
            with self.assertRaises(GestureInstructionsUnavailable):
                self.ask(answer)

    def test_nothing_listening_is_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(GestureInstructionsUnavailable):
                request_instructions({"endpoint": f"ipc://{d}/nobody", "timeout_s": 0.2}, "hello")


if __name__ == "__main__":
    unittest.main()
