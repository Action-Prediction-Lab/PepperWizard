import time
import threading
import unittest
import zmq

from tools.mock_audio_publisher import stream_pcm_chunks

CHUNK_BYTES = 5440  # 2720 int16 samples at 16 kHz front-mic


class TestMockPublisherWireContract(unittest.TestCase):
    def test_emits_one_chunk_every_170ms(self):
        ctx = zmq.Context.instance()
        sub = ctx.socket(zmq.SUB)
        sub.connect("tcp://localhost:15563")
        sub.setsockopt(zmq.SUBSCRIBE, b"")

        samples = b"\x00\x00" * (2720 * 3)  # 3 chunks of silence
        t = threading.Thread(
            target=stream_pcm_chunks,
            kwargs={"pcm_bytes": samples, "bind": "tcp://*:15563"},
            daemon=True,
        )
        t.start()
        time.sleep(0.1)  # give the PUB a moment to bind

        received = []
        t0 = time.time()
        while len(received) < 3 and time.time() - t0 < 2.0:
            try:
                msg = sub.recv(zmq.NOBLOCK)
                received.append((time.time() - t0, msg))
            except zmq.Again:
                time.sleep(0.01)

        self.assertEqual(len(received), 3)
        for _, msg in received:
            self.assertEqual(len(msg), CHUNK_BYTES)
        # Cadence: chunks 2 and 3 should be ~170 ms apart
        gap = received[2][0] - received[1][0]
        self.assertGreater(gap, 0.140)
        self.assertLess(gap, 0.250)

        sub.close()


if __name__ == "__main__":
    unittest.main()
