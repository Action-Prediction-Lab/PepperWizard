"""Tests for the event sink: the session log lines it writes from the PepperBox event stream."""
import json
import time
import unittest

import zmq

from pepper_wizard.event_sink import EventSink


class RecordingLogger:
    def __init__(self):
        self.lines = []

    def info(self, event, data):
        self.lines.append((event, data))

    def events(self):
        """The event names logged so far, in order."""
        return [event for event, _ in self.lines]


def heartbeat(t, started=1.0):
    return ("heartbeat", {"t": t, "started": started})


class SinkTests(unittest.TestCase):
    def setUp(self):
        self.logger = RecordingLogger()
        self.sink = EventSink(self.logger, gap_s=2.0)

    def test_each_message_is_logged_as_a_naoqi_event(self):
        """A behaviour or ALMemory message is logged with its topic, time and value."""
        self.sink.handle("ALTextToSpeech/TextStarted", {"t": 10.0, "value": 1}, now=10.1)
        self.assertEqual(self.logger.lines, [("NAOqiEvent", {"topic": "ALTextToSpeech/TextStarted", "t": 10.0, "value": 1})])

    def test_the_first_heartbeat_logs_where_coverage_begins(self):
        """The first heartbeat of the session logs EventStreamRestored, and later ones log nothing."""
        self.sink.handle(*heartbeat(10.0), now=10.0)
        self.sink.handle(*heartbeat(11.0), now=11.0)
        self.assertEqual(self.logger.lines, [("EventStreamRestored", {"t": 10.0, "started": 1.0})])

    def test_silence_past_the_gap_logs_lost_once_at_the_last_heartbeat(self):
        """EventStreamLost is logged once, carrying the last heartbeat's time, when no heartbeat arrives within the gap."""
        self.sink.handle(*heartbeat(10.0), now=10.0)
        self.sink.check(11.5)
        self.sink.check(12.5)
        self.sink.check(13.0)
        self.assertEqual(self.logger.lines[1:], [("EventStreamLost", {"t": 10.0, "started": 1.0})])

    def test_a_heartbeat_after_a_loss_logs_restored_again(self):
        """Coverage resumes at the next heartbeat after a loss."""
        self.sink.handle(*heartbeat(10.0), now=10.0)
        self.sink.check(12.5)
        self.sink.handle(*heartbeat(20.0), now=20.0)
        self.assertEqual(self.logger.events(), ["EventStreamRestored", "EventStreamLost", "EventStreamRestored"])
        self.assertEqual(self.logger.lines[-1][1]["t"], 20.0)

    def test_a_restarted_publisher_logs_a_loss_and_a_restore(self):
        """A heartbeat with a new start time inside the gap means events were missed during the restart."""
        self.sink.handle(*heartbeat(10.0, started=1.0), now=10.0)
        self.sink.handle(*heartbeat(11.0, started=5.0), now=11.0)
        self.assertEqual(self.logger.lines, [
            ("EventStreamRestored", {"t": 10.0, "started": 1.0}),
            ("EventStreamLost", {"t": 10.0, "started": 1.0}),
            ("EventStreamRestored", {"t": 11.0, "started": 5.0})])


class StreamTests(unittest.TestCase):
    def test_the_stream_reaches_the_log(self):
        """Messages published as topic and JSON frames are logged by the running sink."""
        pub = zmq.Context.instance().socket(zmq.PUB)
        pub.bind("tcp://127.0.0.1:15565")
        logger = RecordingLogger()
        sink = EventSink(logger, zmq_addr="tcp://127.0.0.1:15565")
        sink.start()
        try:
            time.sleep(0.3)
            now = time.time()
            for topic, payload in (heartbeat(now), ("ALBehaviorManager.behaviorStarted", {"t": now, "value": "animations/Stand/Gestures/Me_8"})):
                pub.send_multipart([topic.encode(), json.dumps(payload).encode()])
            time.sleep(0.3)
        finally:
            sink.stop()
            pub.close()
        self.assertEqual(logger.events(), ["EventStreamRestored", "NAOqiEvent"])
        self.assertEqual(logger.lines[1][1]["value"], "animations/Stand/Gestures/Me_8")


if __name__ == "__main__":
    unittest.main()
