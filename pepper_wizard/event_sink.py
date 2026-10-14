"""Subscriber to the PepperBox event stream that writes every NAOqi signal and event to the session log."""
import json
import threading
import time

import zmq

EVENT_STREAM = "tcp://localhost:5565"
HEARTBEAT_GAP_S = 2.0


class EventSink(threading.Thread):
    """Logs each stream message as NAOqiEvent, and EventStreamLost or EventStreamRestored when the heartbeat stops or returns."""

    def __init__(self, logger, zmq_addr=EVENT_STREAM, gap_s=HEARTBEAT_GAP_S):
        super().__init__(daemon=True)
        self.logger = logger
        self.zmq_addr = zmq_addr
        self.gap_s = gap_s
        self.running = False
        self.last_beat = None
        self.received = None
        self.started = None

    def stop(self):
        self.running = False
        self.join()

    def run(self):
        self.running = True
        context = zmq.Context.instance()
        socket = context.socket(zmq.SUB)
        socket.connect(self.zmq_addr)
        socket.setsockopt(zmq.SUBSCRIBE, b"")
        while self.running:
            try:
                if socket.poll(100):
                    topic, body = socket.recv_multipart()
                    self.handle(topic.decode(), json.loads(body), time.time())
                self.check(time.time())
            except Exception as e:
                print(f"EventSink Error: {e}")
                time.sleep(0.1)
        socket.close()

    def handle(self, topic, payload, now):
        """Log one stream message; a heartbeat after silence or from a restarted publisher logs where coverage resumes."""
        if topic != "heartbeat":
            self.logger.info("NAOqiEvent", {"topic": topic, "t": payload["t"], "value": payload["value"]})
            return
        if self.last_beat is not None and payload["started"] != self.started:
            self.lost()
        if self.last_beat is None:
            self.logger.info("EventStreamRestored", {"t": payload["t"], "started": payload["started"]})
        self.last_beat, self.received, self.started = payload["t"], now, payload["started"]

    def check(self, now):
        """Log EventStreamLost once when no heartbeat has arrived for longer than the gap."""
        if self.last_beat is not None and now - self.received > self.gap_s:
            self.lost()

    def lost(self):
        """Log the end of coverage at the last heartbeat."""
        self.logger.info("EventStreamLost", {"t": self.last_beat, "started": self.started})
        self.last_beat = None
