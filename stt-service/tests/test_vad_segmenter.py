import os
import unittest
import wave
import numpy as np

from vad_segmenter import VadSegmenter, VadConfig

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixture_speech_16k.wav")


def _load_fixture():
    """Return the speech fixture as an int16 numpy array at 16 kHz."""
    with wave.open(_FIXTURE, "rb") as wf:
        assert wf.getnchannels() == 1, "fixture must be mono"
        assert wf.getframerate() == 16000, "fixture must be 16 kHz"
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)


class TestVadSegmenter(unittest.TestCase):
    def test_silence_produces_no_utterances(self):
        cfg = VadConfig(threshold=0.5, min_silence_ms=400, min_utterance_ms=200,
                        max_utterance_ms=10000, preroll_ms=100)
        seg = VadSegmenter(cfg, sample_rate=16000)
        silence = np.zeros(16000 * 2, dtype=np.int16)  # 2s of zeros
        utterances = []
        seg.feed(silence, on_utterance=lambda pcm: utterances.append(pcm))
        seg.flush(on_utterance=lambda pcm: utterances.append(pcm))
        self.assertEqual(utterances, [])

    def test_speech_followed_by_silence_produces_one_utterance(self):
        # NOTE: The plan assumed Gaussian noise (amplitude 10000) would trigger
        # Silero v6.2.1 as speech. Observed max prob: 0.027, far below threshold
        # at any amplitude tested (10000, 15000, even 0.9*32768). Silero v6.2.1
        # is too well-trained to mistake Gaussian noise for speech.
        #
        # Replacement: use an espeak-ng speech fixture (fixture_speech_16k.wav,
        # ~3.44s, 55054 samples). Silero v6.2.1 gives 94/107 windows >= 0.5
        # and max prob ~1.0 on this fixture. Utterance bounds updated accordingly.
        cfg = VadConfig(threshold=0.5, min_silence_ms=400, min_utterance_ms=200,
                        max_utterance_ms=10000, preroll_ms=100)
        seg = VadSegmenter(cfg, sample_rate=16000)
        speech = _load_fixture()         # ~55054 samples at 16 kHz
        silence = np.zeros(16000, dtype=np.int16)  # 1s silence to flush the gate
        buf = np.concatenate([speech, silence])
        utterances = []
        seg.feed(buf, on_utterance=lambda pcm: utterances.append(pcm))
        seg.flush(on_utterance=lambda pcm: utterances.append(pcm))
        self.assertEqual(len(utterances), 1)
        # Utterance bytes / 2 = int16 sample count.
        # Speech fixture: 55054 samples; with preroll (~1600) and silence tail
        # (~6400) included before the gate fires. Observed: ~56320 samples.
        utt_samples = len(utterances[0]) // 2
        self.assertGreater(utt_samples, 50000)
        self.assertLess(utt_samples, 65000)


if __name__ == "__main__":
    unittest.main()
