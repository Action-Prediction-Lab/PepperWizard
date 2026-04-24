"""
STT Service — Speech-to-Text microservice for PepperWizard.

Captures audio from the host microphone (via PortAudio/ALSA routed through PulseAudio) and transcribes it
using a configurable Whisper model. Communicates with pepper-wizard over
ZMQ REQ/REP.

Protocol:
    REQ: {"action": "start"}       → REP: {"status": "recording"}
    REQ: {"action": "stop"}        → REP: {"transcription": "...", "duration": float}
    REQ: {"action": "ping"}        → REP: {"status": "ok"}
"""

import argparse
import json
import os
import time
import threading
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import sounddevice as sd
import zmq
from faster_whisper import WhisperModel

from vad_segmenter import VadSegmenter, VadConfig
from events import UtteranceEvent, encode_event, encode_error


class StreamingWorker(threading.Thread):
    """Consumes robot-mic audio on a SUB, segments via VAD, transcribes with
    Whisper (sequentially), and publishes JSON utterance events on a PUB socket."""

    def __init__(self, audio_addr: str, pub_addr: str,
                 vad_config: VadConfig, whisper, is_muted):
        super().__init__(daemon=True)
        self._audio_addr = audio_addr
        self._pub_addr = pub_addr
        self._vad_config = vad_config
        self._whisper = whisper
        self._is_muted = is_muted
        self._stop_evt = threading.Event()

    def stop(self) -> None:
        self._stop_evt.set()

    def run(self) -> None:
        ctx = zmq.Context.instance()
        sub = ctx.socket(zmq.SUB)
        sub.connect(self._audio_addr)
        sub.setsockopt(zmq.SUBSCRIBE, b"")
        sub.setsockopt(zmq.RCVTIMEO, 200)

        pub = ctx.socket(zmq.PUB)
        pub.bind(self._pub_addr)

        seg = VadSegmenter(self._vad_config, sample_rate=16000)
        utt_start = [None]

        def on_utterance(pcm_bytes: bytes) -> None:
            t_end = datetime.now(timezone.utc)
            t_start = utt_start[0] or t_end
            audio_f32 = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            try:
                segments, _ = self._whisper.transcribe(
                    audio_f32, beam_size=3, language="en", vad_filter=False,
                )
                text = " ".join(s.text.strip() for s in segments).strip()
            except Exception as e:
                pub.send_string(encode_error("whisper_failed", str(e), t_start))
                utt_start[0] = None
                return
            duration_s = len(audio_f32) / 16000.0
            pub.send_string(encode_event(UtteranceEvent(
                text=text, duration_s=duration_s,
                t_start=t_start, t_end=t_end, source="robot_mic",
            )))
            utt_start[0] = None

        try:
            while not self._stop_evt.is_set():
                try:
                    chunk = sub.recv(zmq.NOBLOCK)
                except zmq.Again:
                    self._stop_evt.wait(0.02)
                    continue
                if self._is_muted():
                    continue
                pcm = np.frombuffer(chunk, dtype=np.int16)
                if utt_start[0] is None:
                    utt_start[0] = datetime.now(timezone.utc)
                seg.feed(pcm, on_utterance)
            seg.flush(on_utterance)
        finally:
            sub.close()
            pub.close()


class AudioRecorder:
    """Records audio from the default input device into a buffer."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.recording = False
        self._buffer = []
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        """sounddevice callback — called from the audio thread."""
        if status:
            print(f"[AudioRecorder] Status: {status}")
        if self.recording:
            with self._lock:
                self._buffer.append(indata.copy())

    def start(self):
        """Begin capturing audio."""
        with self._lock:
            self._buffer = []
        self.recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        print("[AudioRecorder] Recording started.")

    def stop(self) -> np.ndarray:
        """Stop capturing and return the recorded audio as a float32 numpy array."""
        self.recording = False
        self._stream.stop()
        self._stream.close()
        with self._lock:
            if not self._buffer:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._buffer, axis=0).flatten()
        duration = len(audio) / self.sample_rate
        print(f"[AudioRecorder] Recording stopped. Duration: {duration:.2f}s")
        return audio


# Import-time snapshots of STT_DEVICE / STT_COMPUTE_TYPE, kept for diagnostics and
# future consumers (e.g. a startup banner). _load_whisper below deliberately reads
# os.environ at call time rather than using these constants, so tests can patch
# the env without reimporting the module. See test_reads_env_when_args_omitted.
DEFAULT_DEVICE = os.environ.get("STT_DEVICE", "auto")
DEFAULT_COMPUTE_TYPE = os.environ.get("STT_COMPUTE_TYPE", "auto")


def _load_whisper(model_size: str,
                  device: Optional[str] = None,
                  compute_type: Optional[str] = None):
    """Load WhisperModel with runtime device selection.

    Resolution order for `device` and `compute_type`:
      1. explicit argument, if provided
      2. STT_DEVICE / STT_COMPUTE_TYPE environment variables (per-call read)
      3. "auto"

    Behaviour:
      - device="auto": try CUDA/float16 first; on RuntimeError/ValueError, fall back to CPU/int8.
      - device="cuda": try CUDA/float16; re-raise on failure (operator asked for GPU and should notice).
      - device="cpu":  use CPU/int8 directly.

    compute_type="auto" resolves to "float16" for CUDA paths and "int8" for CPU paths.
    Any explicit compute_type is honoured as-is.
    """
    if device is None:
        device = os.environ.get("STT_DEVICE", "auto")
    if compute_type is None:
        compute_type = os.environ.get("STT_COMPUTE_TYPE", "auto")

    requested_device = device

    if requested_device in ("auto", "cuda"):
        actual_device = "cuda"
        actual_compute = "float16" if compute_type == "auto" else compute_type
        try:
            print(f"[STTService] Trying GPU: device={actual_device}, compute_type={actual_compute}")
            model = WhisperModel(model_size, device=actual_device, compute_type=actual_compute)
            print(f"[STTService] Loaded whisper '{model_size}' on {actual_device}/{actual_compute}")
            return model
        except (RuntimeError, ValueError) as exc:
            if requested_device == "cuda":
                raise
            print(f"[STTService] GPU load failed ({exc}); falling back to CPU.")

    actual_device = "cpu"
    actual_compute = "int8" if compute_type == "auto" else compute_type
    model = WhisperModel(model_size, device=actual_device, compute_type=actual_compute)
    print(f"[STTService] Loaded whisper '{model_size}' on {actual_device}/{actual_compute}")
    return model


DEFAULT_VAD = {
    "threshold": 0.5,
    "min_silence_ms": 700,
    "min_utterance_ms": 300,
    "max_utterance_ms": 15000,
    "preroll_ms": 200,
}

DEFAULT_MODEL_SIZE = "small.en"


def _load_vad_config(path: str = "/app/pepper_config/stt.json") -> VadConfig:
    """Load VAD parameters from stt.json if present; fall back to DEFAULT_VAD."""
    params = dict(DEFAULT_VAD)
    try:
        with open(path) as f:
            data = json.load(f)
        params.update(data.get("vad", {}))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return VadConfig(**params)


def _load_model_size(path: str = "/app/pepper_config/stt.json") -> str:
    """Load Whisper model_size from stt.json if present; fall back to DEFAULT_MODEL_SIZE."""
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("model_size", DEFAULT_MODEL_SIZE)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return DEFAULT_MODEL_SIZE


class STTService:
    """ZMQ REQ/REP service that records and transcribes on demand."""

    def __init__(self, model_size: str, zmq_port: int, sample_rate: int):
        self.recorder = AudioRecorder(sample_rate=sample_rate)

        # Resolve device/compute_type at runtime via _load_whisper (see module-level helper).
        self.model = _load_whisper(model_size)
        print(f"[STTService] Model loaded.")

        # ZMQ setup
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        bind_addr = f"tcp://*:{zmq_port}"
        self.socket.bind(bind_addr)
        print(f"[STTService] Listening on {bind_addr}")

        self._muted = False
        self._worker = None
        self._vad_config = _load_vad_config()
        self._audio_addr = "tcp://localhost:5563"
        self._pub_addr = "tcp://*:5564"

    def transcribe(self, audio: np.ndarray) -> str:
        """Run whisper transcription on a float32 audio array."""
        if len(audio) == 0:
            return ""

        segments, _info = self.model.transcribe(
            audio,
            beam_size=3,
            language="en",
            vad_filter=True,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text

    def _handle_action(self, msg: dict) -> dict:
        """Dispatch a message dict to the appropriate action handler.

        Returns a reply dict. Does NOT touch self.socket.
        """
        action = msg.get("action", "")

        if action == "ping":
            return {"status": "ok"}

        elif action == "start":
            try:
                self.recorder.start()
                return {"status": "recording"}
            except Exception as e:
                print(f"[STTService] Failed to start recording: {e}")
                return {
                    "status": "error",
                    "error": f"Recording failed: {e}",
                }

        elif action == "stop":
            try:
                audio = self.recorder.stop()
            except Exception as e:
                print(f"[STTService] Failed to stop recording: {e}")
                return {
                    "transcription": "",
                    "duration": 0,
                    "error": f"Stop failed: {e}",
                }

            duration = len(audio) / self.recorder.sample_rate

            if duration < 0.3:
                # Too short to be meaningful speech
                return {
                    "transcription": "",
                    "duration": round(duration, 2),
                    "error": "Recording too short",
                }
            else:
                print(f"[STTService] Transcribing {duration:.2f}s of audio...")
                t0 = time.time()
                text = self.transcribe(audio)
                elapsed = time.time() - t0
                print(f"[STTService] Transcription: '{text}' ({elapsed:.2f}s)")

                return {
                    "transcription": text,
                    "duration": round(duration, 2),
                }

        elif action == "enable_streaming":
            if self._worker is None:
                self._worker = StreamingWorker(
                    audio_addr=self._audio_addr,
                    pub_addr=self._pub_addr,
                    vad_config=self._vad_config,
                    whisper=self.model,
                    is_muted=lambda: self._muted,
                )
                self._worker.start()
            return {"status": "streaming"}

        elif action == "disable_streaming":
            if self._worker is not None:
                self._worker.stop()
                self._worker.join(timeout=2.0)
                self._worker = None
            return {"status": "idle"}

        elif action == "mute":
            self._muted = True
            return {"status": "muted"}

        elif action == "unmute":
            self._muted = False
            return {"status": "unmuted"}

        else:
            return {"error": f"Unknown action: {action}"}

    def run(self):
        """Main service loop — handles REQ/REP messages."""
        print("[STTService] Ready. Waiting for commands...")
        while True:
            try:
                msg = self.socket.recv_json()
                reply = self._handle_action(msg)
                self.socket.send_json(reply)
            except zmq.ZMQError as e:
                print(f"[STTService] ZMQ Error: {e}")
                break
            except KeyboardInterrupt:
                print("\n[STTService] Shutting down...")
                break

        self.socket.close()
        self.context.term()


def main():
    parser = argparse.ArgumentParser(description="PepperWizard STT Service")
    parser.add_argument(
        "--model", type=str, default=None,
        help="Whisper model size (overrides stt.json model_size; default taken from stt.json)",
    )
    parser.add_argument(
        "--port", type=int, default=5562,
        help="ZMQ REP port (default: 5562)",
    )
    parser.add_argument(
        "--sample-rate", type=int, default=16000,
        help="Audio sample rate in Hz (default: 16000)",
    )
    args = parser.parse_args()

    model_size = args.model if args.model is not None else _load_model_size()

    service = STTService(
        model_size=model_size,
        zmq_port=args.port,
        sample_rate=args.sample_rate,
    )
    service.run()


if __name__ == "__main__":
    main()
