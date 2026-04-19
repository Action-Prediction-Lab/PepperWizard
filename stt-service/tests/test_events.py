import json
import unittest
from datetime import datetime, timezone

from events import UtteranceEvent, encode_event, encode_error


class TestEvents(unittest.TestCase):
    def test_utterance_event_round_trip(self):
        t0 = datetime(2026, 4, 19, 15, 44, 12, 1000, tzinfo=timezone.utc)
        t1 = datetime(2026, 4, 19, 15, 44, 14, 141000, tzinfo=timezone.utc)
        evt = UtteranceEvent(text="hello pepper", duration_s=2.14, t_start=t0, t_end=t1, source="robot_mic")
        payload = json.loads(encode_event(evt))
        self.assertEqual(payload["text"], "hello pepper")
        self.assertEqual(payload["duration_s"], 2.14)
        self.assertEqual(payload["t_start"], "2026-04-19T15:44:12.001Z")
        self.assertEqual(payload["t_end"],   "2026-04-19T15:44:14.141Z")
        self.assertEqual(payload["source"], "robot_mic")

    def test_error_event(self):
        t0 = datetime(2026, 4, 19, 15, 44, 12, tzinfo=timezone.utc)
        payload = json.loads(encode_error("whisper_failed", "cuda oom", t0))
        self.assertEqual(payload["error"], "whisper_failed")
        self.assertEqual(payload["detail"], "cuda oom")
        self.assertEqual(payload["t_start"], "2026-04-19T15:44:12.000Z")
