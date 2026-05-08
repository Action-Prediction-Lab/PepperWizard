"""Unit tests for the PyAV-based MKV muxer.

Feeds the muxer a deterministic stream of greyscale frames (320x240) and
int16 audio chunks, then re-opens the resulting MKV with PyAV and asserts
that both streams are present and the file is well-formed.
"""
import os
import tempfile
import unittest

import av
import numpy as np

from pepper_wizard.recording.muxer import MkvMuxer


class TestMkvMuxer(unittest.TestCase):
    def setUp(self):
        self.fd, self.path = tempfile.mkstemp(suffix=".mkv")
        os.close(self.fd)

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def _write_minimal_session(self, video_codec="ffv1", audio_codec="pcm_s16le"):
        muxer = MkvMuxer(
            path=self.path,
            video_codec=video_codec,
            video_pix_fmt="yuv420p",
            audio_codec=audio_codec,
            video_size=(320, 240),
            audio_sample_rate=16000,
            audio_channels=1,
        )
        N_FRAMES = 10
        FPS = 5
        for i in range(N_FRAMES):
            frame_bytes = (np.ones((240, 320), dtype=np.uint8) * (i * 25)).tobytes()
            pts = int(i * (1.0 / FPS) * 1000)
            muxer.write_video_frame(frame_bytes, pts_ms=pts)
        for i in range(12):
            samples = np.full(2720, 100 + i, dtype=np.int16)
            pts = int(i * 170)
            muxer.write_audio_chunk(samples.tobytes(), pts_ms=pts)
        muxer.close()

    def test_mkv_has_video_and_audio_streams(self):
        self._write_minimal_session()
        self.assertTrue(os.path.exists(self.path))
        self.assertGreater(os.path.getsize(self.path), 0)

        with av.open(self.path) as container:
            streams = list(container.streams)
            self.assertEqual(len(streams), 2)
            stream_types = {s.type for s in streams}
            self.assertSetEqual(stream_types, {"video", "audio"})

    def test_video_pts_match_input_and_audio_paced_sequentially(self):
        """Two regressions in one:

        1. Video PTS used to be silently rescaled by the codec's default rate
           (1/24s or 1/30s), making 5s recordings play back as 200s. We assert
           the LAST video packet's seconds-equivalent matches the last input ms.

        2. Audio is a continuous PCM stream — the publisher delivers chunks
           with variable wall-clock cadence (often bursts) but each chunk is a
           fixed duration of real audio. Using ingest-time PTS leaves silent
           gaps between every chunk in the MKV (clicks on playback). We feed
           the muxer an audio BURST (chunks with dt=5ms) and assert the OUTPUT
           pts are paced by sample count, not by input ms.
        """
        muxer = MkvMuxer(
            path=self.path,
            video_codec="ffv1",
            video_pix_fmt="yuv420p",
            audio_codec="pcm_s16le",
            video_size=(320, 240),
            audio_sample_rate=16000,
            audio_channels=1,
        )
        # Video at 100ms intervals.
        N_FRAMES = 50
        FRAME_DT_MS = 100
        last_video_pts_ms = (N_FRAMES - 1) * FRAME_DT_MS  # 4900 ms
        for i in range(N_FRAMES):
            frame_bytes = (np.ones((240, 320), dtype=np.uint8) * 50).tobytes()
            muxer.write_video_frame(frame_bytes, pts_ms=i * FRAME_DT_MS)
        # Audio BURST: 30 chunks at 5ms wall-clock dt, but each chunk is 2720
        # samples (170ms of real PCM @ 16kHz). Total real audio = 29 * 170 = 4930ms.
        N_CHUNKS = 30
        SAMPLES_PER_CHUNK = 2720
        for i in range(N_CHUNKS):
            samples = np.full(SAMPLES_PER_CHUNK, 50, dtype=np.int16)
            muxer.write_audio_chunk(samples.tobytes(), pts_ms=i * 5)  # burst
        expected_audio_last_ms = (N_CHUNKS - 1) * (SAMPLES_PER_CHUNK * 1000) // 16000  # 4930
        muxer.close()

        with av.open(self.path) as container:
            last_pts = {"video": None, "audio": None}
            time_base = {"video": None, "audio": None}
            for s in container.streams:
                time_base[s.type] = s.time_base
            for packet in container.demux():
                if packet.pts is not None and packet.stream.type in last_pts:
                    last_pts[packet.stream.type] = packet.pts

        v_seconds = float(last_pts["video"] * time_base["video"])
        a_seconds = float(last_pts["audio"] * time_base["audio"])
        self.assertAlmostEqual(v_seconds, last_video_pts_ms / 1000.0, delta=0.2,
                               msg=f"video last pts {v_seconds:.3f}s does not match "
                                   f"input {last_video_pts_ms/1000.0:.3f}s — "
                                   "PTS were silently rescaled.")
        self.assertAlmostEqual(a_seconds, expected_audio_last_ms / 1000.0, delta=0.2,
                               msg=f"audio last pts {a_seconds:.3f}s should be paced by "
                                   f"sample count to {expected_audio_last_ms/1000.0:.3f}s, "
                                   "not by ingest cadence.")

    def test_close_is_idempotent(self):
        muxer = MkvMuxer(
            path=self.path,
            video_codec="ffv1",
            video_pix_fmt="yuv420p",
            audio_codec="pcm_s16le",
            video_size=(320, 240),
            audio_sample_rate=16000,
            audio_channels=1,
        )
        muxer.close()
        muxer.close()


if __name__ == "__main__":
    unittest.main()
