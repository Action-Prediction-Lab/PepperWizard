import io
import threading
import time
import unittest

import zmq

from tools.host_mic_publisher import publish_pcm_stream

CHUNK_BYTES = 5440
TEST_BIND = "tcp://*:15565"
TEST_CONNECT = "tcp://localhost:15565"


class PacedBytesIO(io.BytesIO):
    """BytesIO that sleeps between chunk reads to simulate realistic pacing.

    The sleep duration must be long enough that messages stay in flight when the
    subscriber connects. Without this, all messages are sent and buffered before
    the subscriber can connect, causing them to be lost (PUB/SUB does not buffer).
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chunk_sleep = 0.05  # 50ms per chunk: enough to keep chunks in flight

    def read(self, n=-1):
        # For our use case, this is always called with n=CHUNK_BYTES.
        # Sleep to pace the reads like stdin would at real-time rate.
        if n == CHUNK_BYTES:
            time.sleep(self.chunk_sleep)
        return super().read(n)


class TestHostMicPublisher(unittest.TestCase):
    def setUp(self):
        self.ctx = zmq.Context()
        self.sub = self.ctx.socket(zmq.SUB)

    def tearDown(self):
        self.sub.close(linger=0)
        self.ctx.term()

    def test_publishes_full_chunks_from_stream(self):
        # 3 full chunks of known content + 1 partial (should be dropped).
        pcm = b"\x01\x00" * (2720 * 3) + b"\x02\x00" * 100
        stream = PacedBytesIO(pcm)

        n_chunks_holder = []
        t = threading.Thread(
            target=lambda: n_chunks_holder.append(
                publish_pcm_stream(stream, bind=TEST_BIND)
            ),
            daemon=True,
        )
        t.start()

        # Wait for publisher to bind and start sending, then connect subscriber.
        # PacedBytesIO sleeps 0.05s per chunk: warmup=0.05s, chunk1 starts at 0.05s.
        # Connect at 0.12s to catch chunks 2-3 in flight. Chunk 1 may be lost (slow-joiner).
        time.sleep(0.12)
        self.sub.connect(TEST_CONNECT)
        self.sub.setsockopt(zmq.SUBSCRIBE, b"")

        # Collect messages.
        received = []
        t0 = time.time()
        while len(received) < 3 and time.time() - t0 < 2.0:
            try:
                msg = self.sub.recv(zmq.NOBLOCK)
                received.append(msg)
            except zmq.Again:
                time.sleep(0.005)

        t.join(timeout=2.0)

        # Should receive at least 2 chunks (first is lost due to slow-joiner).
        self.assertGreaterEqual(len(received), 2)
        for msg in received:
            self.assertEqual(len(msg), CHUNK_BYTES)

        # publish_pcm_stream should report exactly 3 full chunks (partial dropped).
        self.assertEqual(n_chunks_holder, [3])

    def test_short_stream_publishes_nothing(self):
        stream = io.BytesIO(b"\x00" * 100)  # < one chunk

        n_chunks_holder = []
        t = threading.Thread(
            target=lambda: n_chunks_holder.append(
                publish_pcm_stream(stream, bind=TEST_BIND)
            ),
            daemon=True,
        )
        t.start()

        # Let the publisher finish (it will immediately fail to read CHUNK_BYTES).
        t.join(timeout=2.0)

        # Verify no chunks were published.
        self.assertEqual(n_chunks_holder, [0])


if __name__ == "__main__":
    unittest.main()
