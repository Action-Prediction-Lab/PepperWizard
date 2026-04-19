"""Tests for StreamingWorker.

Uses the fixture_speech_16k.wav speech fixture (Option A) rather than
Gaussian noise, because Silero v6.2.1 does not classify Gaussian noise
as speech (max observed probability: ~0.027 at threshold=0.5).
"""
import json
import os
import threading
import time
import unittest
import wave

import numpy as np
import zmq

from main import StreamingWorker
from vad_segmenter import VadConfig

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixture_speech_16k.wav")


def _load_fixture_bytes() -> bytes:
    """Return the speech fixture as raw int16 PCM bytes at 16 kHz."""
    with wave.open(_FIXTURE, "rb") as wf:
        assert wf.getnchannels() == 1, "fixture must be mono"
        assert wf.getframerate() == 16000, "fixture must be 16 kHz"
        return wf.readframes(wf.getnframes())


class FakeWhisper:
    def transcribe(self, audio, beam_size=3, language="en", vad_filter=False):
        class Seg:
            text = "hello pepper"
        return [Seg()], None


class TestStreamingWorker(unittest.TestCase):
    def test_publishes_transcription_after_utterance(self):
        ctx = zmq.Context.instance()
        pub = ctx.socket(zmq.PUB)
        pub.bind("tcp://*:16563")  # feeder
        out_sub = ctx.socket(zmq.SUB)
        out_sub.connect("tcp://localhost:16564")
        out_sub.setsockopt(zmq.SUBSCRIBE, b"")

        cfg = VadConfig(threshold=0.5, min_silence_ms=200, min_utterance_ms=100,
                        max_utterance_ms=5000, preroll_ms=50)
        w = StreamingWorker(
            audio_addr="tcp://localhost:16563",
            pub_addr="tcp://*:16564",
            vad_config=cfg,
            whisper=FakeWhisper(),
            is_muted=lambda: False,
        )
        w.start()
        time.sleep(0.3)  # let the worker subscribe

        # Use the real speech fixture so Silero reliably detects speech.
        speech = _load_fixture_bytes()
        silence = b"\x00\x00" * 16000  # 1s silence to force end-of-utterance
        buf = speech + silence
        for i in range(0, len(buf), 5440):
            pub.send(buf[i:i + 5440])
            time.sleep(0.01)

        deadline = time.time() + 5.0
        received = None
        while time.time() < deadline:
            try:
                msg = out_sub.recv(zmq.NOBLOCK)
                received = json.loads(msg.decode())
                break
            except zmq.Again:
                time.sleep(0.02)

        w.stop()
        w.join(timeout=2.0)
        pub.close()
        out_sub.close()

        self.assertIsNotNone(received, "No transcription event received within deadline")
        self.assertEqual(received["text"], "hello pepper")
        self.assertEqual(received["source"], "robot_mic")
