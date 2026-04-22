"""Silero-backed VAD segmenter. Pure; no Whisper or ZMQ.

Feed int16 PCM frames in any size; call `on_utterance(pcm_bytes)` for each
detected utterance. Uses Silero VAD at 16 kHz with 512-sample (32 ms) windows.
"""
from dataclasses import dataclass
import numpy as np
import torch
from silero_vad import load_silero_vad

SILERO_WINDOW_SAMPLES = 512  # 32 ms at 16 kHz


@dataclass
class VadConfig:
    threshold: float
    min_silence_ms: int
    min_utterance_ms: int
    max_utterance_ms: int
    preroll_ms: int


class VadSegmenter:
    def __init__(self, cfg: VadConfig, sample_rate: int = 16000):
        if sample_rate != 16000:
            raise ValueError("VadSegmenter requires 16 kHz input.")
        self.cfg = cfg
        self.sr = sample_rate
        self.model = load_silero_vad()

        self._rolling = np.zeros(0, dtype=np.int16)
        self._preroll_samples = int(cfg.preroll_ms * sample_rate / 1000)
        self._min_silence_windows = int(cfg.min_silence_ms * sample_rate / 1000 / SILERO_WINDOW_SAMPLES)
        self._min_utt_samples = int(cfg.min_utterance_ms * sample_rate / 1000)
        self._max_utt_samples = int(cfg.max_utterance_ms * sample_rate / 1000)

        self._in_utterance = False
        self._utt_buf = []  # list of int16 np arrays accumulating the current utterance
        self._silence_count = 0
        self._preroll_buf = np.zeros(0, dtype=np.int16)  # last preroll_samples of non-speech, carried forward

    def feed(self, pcm: np.ndarray, on_utterance) -> None:
        """Feed int16 samples. May call `on_utterance(bytes)` zero or more times."""
        if pcm.dtype != np.int16:
            raise ValueError("feed expects int16 samples")
        self._rolling = np.concatenate([self._rolling, pcm])

        while len(self._rolling) >= SILERO_WINDOW_SAMPLES:
            window = self._rolling[:SILERO_WINDOW_SAMPLES]
            self._rolling = self._rolling[SILERO_WINDOW_SAMPLES:]
            self._process_window(window, on_utterance)

    def flush(self, on_utterance) -> None:
        """Force-flush any in-progress utterance."""
        if self._in_utterance and len(self._utt_buf) > 0:
            self._emit(on_utterance)

    def _process_window(self, window: np.ndarray, on_utterance) -> None:
        prob = self._prob(window)
        is_speech = prob >= self.cfg.threshold

        if self._in_utterance:
            self._utt_buf.append(window)
            if is_speech:
                self._silence_count = 0
            else:
                self._silence_count += 1
                if self._silence_count >= self._min_silence_windows:
                    self._emit(on_utterance)
                    return
            if sum(len(w) for w in self._utt_buf) >= self._max_utt_samples:
                self._emit(on_utterance)
                return
        else:
            if is_speech:
                self._in_utterance = True
                self._silence_count = 0
                if len(self._preroll_buf) > 0:
                    self._utt_buf.append(self._preroll_buf)
                self._utt_buf.append(window)
            else:
                self._preroll_buf = np.concatenate([self._preroll_buf, window])
                if len(self._preroll_buf) > self._preroll_samples:
                    self._preroll_buf = self._preroll_buf[-self._preroll_samples:]

    def _prob(self, window: np.ndarray) -> float:
        t = torch.from_numpy(window.astype(np.float32) / 32768.0)
        with torch.no_grad():
            return float(self.model(t, self.sr).item())

    def _emit(self, on_utterance) -> None:
        utt = np.concatenate(self._utt_buf)
        self._utt_buf = []
        self._in_utterance = False
        self._silence_count = 0
        self._preroll_buf = np.zeros(0, dtype=np.int16)
        if len(utt) >= self._min_utt_samples:
            on_utterance(utt.tobytes())
