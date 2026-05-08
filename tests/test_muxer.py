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

    def test_mkv_duration_matches_pts_span(self):
        """Regression: dropping rate=30 from add_stream restored correct duration.

        Previously the stream was created with rate=30 which fixed time_base to
        1/30s and silently overrode our 1/1000 setting; PTS in ms were treated
        as 1/30s units and the recording played back at 1/33 speed.
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
        # 50 frames spanning exactly 5000 ms (last frame pts == 5000).
        for i in range(50):
            frame_bytes = (np.ones((240, 320), dtype=np.uint8) * 50).tobytes()
            muxer.write_video_frame(frame_bytes, pts_ms=i * 100)
        # Matching audio: chunks every 170 ms across 5 s.
        for i in range(30):
            samples = np.full(2720, 50, dtype=np.int16)
            muxer.write_audio_chunk(samples.tobytes(), pts_ms=i * 170)
        muxer.close()

        with av.open(self.path) as container:
            # Stream duration in seconds should be ~5 s (the PTS span), not 5*33 s.
            for s in container.streams:
                if s.duration is None or s.time_base is None:
                    continue
                dur_s = float(s.duration * s.time_base)
                self.assertLess(dur_s, 10.0,
                                f"{s.type} stream duration {dur_s:.1f}s implies PTS were "
                                "interpreted in the wrong time_base.")
                self.assertGreater(dur_s, 4.0,
                                   f"{s.type} stream duration {dur_s:.1f}s is too short.")

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
