"""Recorder lifecycle orchestrator.

Owns:
  - A clock-sync probe (run once on each start, optional)
  - A MkvMuxer
  - A SidecarWriter
  - Two consumer threads draining frame/chunk queues into the muxer + sidecar.
  - Two source threads (VideoSink, AudioSink) owning ZMQ subscribers.

Each Recorder instance corresponds to one toggle-on session (one file triple).
For repeated start/stop in the same process, see RecordingController.
"""
import datetime
import json
import os
import queue
import threading
import time

from .audio_sink import AudioSink
from .clock_sync import probe_clock_sync
from .muxer import MkvMuxer
from .sidecar import SidecarWriter
from .video_sink import VideoSink


VIDEO_RES_W = 320
VIDEO_RES_H = 240
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1


class Recorder:
    def __init__(self, config, session_id, video_address, audio_address,
                 clock_sync_url=None):
        self._config = dict(config)
        self._session_id = session_id or "unset"
        self._video_address = video_address
        self._audio_address = audio_address
        self._clock_sync_url = clock_sync_url

        self._started = False
        self._stopped = False
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()

        self._paths = None
        self._muxer = None
        self._sidecar = None
        self._video_sink = None
        self._audio_sink = None
        self._video_q = None
        self._audio_q = None
        self._video_drain = None
        self._audio_drain = None
        self._t0_ns = None

    def _make_paths(self):
        out_dir = self._config["output_dir"]
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        stem = os.path.join(out_dir, f"session_{self._session_id}_{ts}")
        return {
            "mkv": stem + ".mkv",
            "jsonl": stem + ".jsonl",
            "clocksync": stem + ".clocksync.json",
        }

    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True

        self._paths = self._make_paths()
        self._t0_ns = time.time_ns()

        clock_sync = None
        if self._clock_sync_url:
            clock_sync = probe_clock_sync(self._clock_sync_url, samples=10, timeout_s=2.0)

        with open(self._paths["clocksync"], "w") as f:
            json.dump(clock_sync, f, indent=2)

        self._muxer = MkvMuxer(
            path=self._paths["mkv"],
            video_codec=self._config["video_codec"],
            video_pix_fmt=self._config["video_pix_fmt"],
            audio_codec=self._config["audio_codec"],
            video_size=(VIDEO_RES_W, VIDEO_RES_H),
            audio_sample_rate=AUDIO_SAMPLE_RATE,
            audio_channels=AUDIO_CHANNELS,
        )
        self._sidecar = SidecarWriter(self._paths["jsonl"])
        self._sidecar.write_header({
            "version": 1,
            "recording_start_utc_ns": self._t0_ns,
            "session_id": self._session_id,
            "clock_sync": clock_sync,
            "video": {"address": self._video_address, "resolution": [VIDEO_RES_W, VIDEO_RES_H], "format": "y8"},
            "audio": {"address": self._audio_address, "sample_rate": AUDIO_SAMPLE_RATE, "channels": AUDIO_CHANNELS, "dtype": "int16"},
        })

        self._video_q = queue.Queue()
        self._audio_q = queue.Queue()
        self._video_sink = VideoSink(self._video_address, self._video_q)
        self._audio_sink = AudioSink(self._audio_address, self._audio_q)
        self._video_sink.start()
        self._audio_sink.start()

        self._video_drain = threading.Thread(target=self._drain_video, daemon=True)
        self._audio_drain = threading.Thread(target=self._drain_audio, daemon=True)
        self._video_drain.start()
        self._audio_drain.start()

    def _drain_video(self):
        while not self._stop_evt.is_set() or not self._video_q.empty():
            try:
                frame = self._video_q.get(timeout=0.1)
            except queue.Empty:
                continue
            pts_ms = max(0, (frame["ingest_utc_ns"] - self._t0_ns) // 1_000_000)
            self._muxer.write_video_frame(frame["img_bytes"], pts_ms=pts_ms)
            self._sidecar.write({
                "type": "video",
                "ingest_utc_ns": frame["ingest_utc_ns"],
                "robot_ts_s": frame["robot_ts_s"],
                "frame_index": frame["frame_index"],
            })

    def _drain_audio(self):
        while not self._stop_evt.is_set() or not self._audio_q.empty():
            try:
                chunk = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            pts_ms = max(0, (chunk["ingest_utc_ns"] - self._t0_ns) // 1_000_000)
            self._muxer.write_audio_chunk(chunk["pcm_bytes"], pts_ms=pts_ms)
            self._sidecar.write({
                "type": "audio",
                "ingest_utc_ns": chunk["ingest_utc_ns"],
                "samples": chunk["samples"],
                "chunk_index": chunk["chunk_index"],
            })

    def stop(self):
        with self._lock:
            if self._stopped:
                return self._paths
            if not self._started:
                return None
            self._stopped = True

        if self._video_sink:
            self._video_sink.stop()
            self._video_sink.join(timeout=2.0)
        if self._audio_sink:
            self._audio_sink.stop()
            self._audio_sink.join(timeout=2.0)
        self._stop_evt.set()
        if self._video_drain:
            self._video_drain.join(timeout=2.0)
        if self._audio_drain:
            self._audio_drain.join(timeout=2.0)
        if self._muxer:
            self._muxer.close()
        if self._sidecar:
            self._sidecar.close()

        return self._paths


class RecordingController:
    """Wraps Recorder to support repeated start/stop cycles in one process.

    Each toggle-on instantiates a fresh Recorder. Toggle-off finalises it.
    """

    def __init__(self, config, session_id, video_address, audio_address, clock_sync_url=None):
        self._config = config
        self._session_id = session_id
        self._video_address = video_address
        self._audio_address = audio_address
        self._clock_sync_url = clock_sync_url
        self._current = None
        self._lock = threading.Lock()

    @property
    def is_recording(self):
        return self._current is not None

    def toggle(self):
        with self._lock:
            if self._current is None:
                self._current = Recorder(
                    config=self._config,
                    session_id=self._session_id,
                    video_address=self._video_address,
                    audio_address=self._audio_address,
                    clock_sync_url=self._clock_sync_url,
                )
                self._current.start()
                print("Recording started.")
            else:
                paths = self._current.stop()
                self._current = None
                print(f"Recording stopped: {paths['mkv']}")

    def stop_if_recording(self):
        with self._lock:
            if self._current is not None:
                paths = self._current.stop()
                self._current = None
                return paths
            return None
