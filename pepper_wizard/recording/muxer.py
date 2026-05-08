"""PyAV-based MKV muxer for synchronised A/V recording.

Owns a single OutputContainer with one video and one audio stream.
Callers feed it frames (write_video_frame) and audio chunks (write_audio_chunk),
each tagged with a presentation timestamp in milliseconds since recording start.

PyAV is thread-safe across separate streams within one container, but each
stream's encoder is not — callers must not interleave write_video_frame()
calls across multiple threads, nor write_audio_chunk(). The Recorder uses
two dedicated drain threads (one per stream) which satisfies this.
"""
import threading
from fractions import Fraction

import av
import numpy as np


class MkvMuxer:
    VIDEO_TIMEBASE_MS = 1000  # 1 unit = 1 ms

    def __init__(self, path, video_codec, video_pix_fmt, audio_codec,
                 video_size, audio_sample_rate, audio_channels):
        self._path = path
        self._lock = threading.Lock()
        self._closed = False

        self._container = av.open(path, mode="w", format="matroska")

        # Variable-rate video: do NOT pass `rate=` (which fixes time_base to 1/rate
        # and causes PyAV/matroska to ignore subsequent time_base overrides — that's
        # what made early recordings play back at 1/33 speed).  Set time_base
        # explicitly to 1ms so frame.pts in ms matches stream time_base.
        self._vstream = self._container.add_stream(video_codec)
        self._vstream.width, self._vstream.height = video_size
        self._vstream.pix_fmt = video_pix_fmt
        self._vstream.time_base = Fraction(1, self.VIDEO_TIMEBASE_MS)

        self._astream = self._container.add_stream(audio_codec, rate=audio_sample_rate)
        self._astream.layout = "mono" if audio_channels == 1 else "stereo"
        self._astream.format = "s16"
        self._astream.time_base = Fraction(1, audio_sample_rate)

        self._video_size = video_size
        self._audio_sample_rate = audio_sample_rate
        self._audio_channels = audio_channels

        # Audio is paced sequentially in the MKV (continuous PCM stream),
        # anchored to the first chunk's wall-clock pts_ms so it lines up with
        # the video track at the start. The publisher delivers chunks with
        # variable wall-clock gaps that don't reflect real audio time, so
        # ingest-time PTS would leave silent gaps between every chunk.
        self._audio_first_pts_ms = None
        self._audio_total_samples = 0

    def write_video_frame(self, gray_bytes, pts_ms):
        if self._closed:
            return
        w, h = self._video_size
        if len(gray_bytes) != w * h:
            return
        arr = np.frombuffer(gray_bytes, dtype=np.uint8).reshape((h, w))
        frame = av.VideoFrame.from_ndarray(arr, format="gray")
        frame = frame.reformat(format=self._vstream.pix_fmt)
        # CRITICAL: pin frame.time_base explicitly. Without this, PyAV treats
        # the frame's pts in the codec's default rate (24fps → 1/24s) then
        # rescales to the stream's 1/1000s, multiplying every pts by ~41.67×
        # (a 30s recording plays back as 1250s).
        frame.pts = int(pts_ms)
        frame.time_base = Fraction(1, self.VIDEO_TIMEBASE_MS)
        for packet in self._vstream.encode(frame):
            self._container.mux(packet)

    def write_audio_chunk(self, pcm_bytes, pts_ms):
        if self._closed:
            return
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        if samples.size == 0:
            return
        arr = samples.reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(arr, format="s16", layout=self._astream.layout)
        frame.sample_rate = self._audio_sample_rate

        # Anchor the audio track to the first chunk's wall-clock pts_ms, then
        # pace subsequent chunks by their actual sample count. This produces a
        # continuous PCM stream (no click-inducing gaps from variable publisher
        # cadence) while still syncing the start of the audio track with the
        # video track. Wall-clock truth lives in the sidecar; the MKV is the
        # convenience artifact.
        if self._audio_first_pts_ms is None:
            self._audio_first_pts_ms = int(pts_ms)
        chunk_pts_ms = self._audio_first_pts_ms + \
            (self._audio_total_samples * 1000) // self._audio_sample_rate
        self._audio_total_samples += samples.size

        frame.pts = chunk_pts_ms
        frame.time_base = Fraction(1, self.VIDEO_TIMEBASE_MS)
        for packet in self._astream.encode(frame):
            self._container.mux(packet)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            for packet in self._vstream.encode():
                self._container.mux(packet)
        except Exception:
            pass
        try:
            for packet in self._astream.encode():
                self._container.mux(packet)
        except Exception:
            pass
        try:
            self._container.close()
        except Exception:
            pass
