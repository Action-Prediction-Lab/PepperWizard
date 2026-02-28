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
import time
import threading

import numpy as np
import sounddevice as sd
import zmq
from faster_whisper import WhisperModel


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


class STTService:
    """ZMQ REQ/REP service that records and transcribes on demand."""

    def __init__(self, model_size: str, zmq_port: int, sample_rate: int):
        self.recorder = AudioRecorder(sample_rate=sample_rate)

        # Load the Whisper model (CPU, int8 quantised)
        print(f"[STTService] Loading whisper model '{model_size}' (cpu, int8)...")
        self.model = WhisperModel(
            model_size, device="cpu", compute_type="int8"
        )
        print(f"[STTService] Model loaded.")

        # ZMQ setup
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        bind_addr = f"tcp://*:{zmq_port}"
        self.socket.bind(bind_addr)
        print(f"[STTService] Listening on {bind_addr}")

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

    def run(self):
        """Main service loop — handles REQ/REP messages."""
        print("[STTService] Ready. Waiting for commands...")
        while True:
            try:
                msg = self.socket.recv_json()
                action = msg.get("action", "")

                if action == "ping":
                    self.socket.send_json({"status": "ok"})

                elif action == "start":
                    try:
                        self.recorder.start()
                        self.socket.send_json({"status": "recording"})
                    except Exception as e:
                        print(f"[STTService] Failed to start recording: {e}")
                        self.socket.send_json({
                            "status": "error",
                            "error": f"Recording failed: {e}",
                        })

                elif action == "stop":
                    try:
                        audio = self.recorder.stop()
                    except Exception as e:
                        print(f"[STTService] Failed to stop recording: {e}")
                        self.socket.send_json({
                            "transcription": "",
                            "duration": 0,
                            "error": f"Stop failed: {e}",
                        })
                        continue

                    duration = len(audio) / self.recorder.sample_rate

                    if duration < 0.3:
                        # Too short to be meaningful speech
                        self.socket.send_json({
                            "transcription": "",
                            "duration": round(duration, 2),
                            "error": "Recording too short",
                        })
                    else:
                        print(f"[STTService] Transcribing {duration:.2f}s of audio...")
                        t0 = time.time()
                        text = self.transcribe(audio)
                        elapsed = time.time() - t0
                        print(f"[STTService] Transcription: '{text}' ({elapsed:.2f}s)")

                        self.socket.send_json({
                            "transcription": text,
                            "duration": round(duration, 2),
                        })

                else:
                    self.socket.send_json({
                        "error": f"Unknown action: {action}"
                    })

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
        "--model", type=str, default="base.en",
        help="Whisper model size (default: base.en)",
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

    service = STTService(
        model_size=args.model,
        zmq_port=args.port,
        sample_rate=args.sample_rate,
    )
    service.run()


if __name__ == "__main__":
    main()
