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

    def test_mkv_packet_pts_match_input_pts(self):
        """Regression: previously frame.pts (intended in ms) was reinterpreted in
        the codec's default frame rate (1/24s or 1/30s) and rescaled to the
        stream's 1/1000s, multiplying every recorded pts by ~33-42×. VLC played
        the result at 1/33 speed, looking exactly like a starving feed.

        We assert that the LAST video and audio packet's pts (in stream time_base)
        is within tolerance of the LAST input pts_ms — i.e. no silent rescaling.
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
        N_FRAMES = 50
        FRAME_DT_MS = 100
        last_video_pts_ms = (N_FRAMES - 1) * FRAME_DT_MS  # 4900 ms
        for i in range(N_FRAMES):
            frame_bytes = (np.ones((240, 320), dtype=np.uint8) * 50).tobytes()
            muxer.write_video_frame(frame_bytes, pts_ms=i * FRAME_DT_MS)
        N_CHUNKS = 30
        CHUNK_DT_MS = 170
        last_audio_pts_ms = (N_CHUNKS - 1) * CHUNK_DT_MS  # 4930 ms
        for i in range(N_CHUNKS):
            samples = np.full(2720, 50, dtype=np.int16)
            muxer.write_audio_chunk(samples.tobytes(), pts_ms=i * CHUNK_DT_MS)
        muxer.close()

        with av.open(self.path) as container:
            last_pts = {"video": None, "audio": None}
            time_base = {"video": None, "audio": None}
            for s in container.streams:
                time_base[s.type] = s.time_base
            for packet in container.demux():
                if packet.pts is not None and packet.stream.type in last_pts:
                    last_pts[packet.stream.type] = packet.pts

        # Assert last packet's seconds-equivalent matches input within 200ms.
        v_seconds = float(last_pts["video"] * time_base["video"])
        a_seconds = float(last_pts["audio"] * time_base["audio"])
        self.assertAlmostEqual(v_seconds, last_video_pts_ms / 1000.0, delta=0.2,
                               msg=f"video last pts {v_seconds:.3f}s does not match "
                                   f"input {last_video_pts_ms/1000.0:.3f}s — "
                                   "PTS were silently rescaled.")
        self.assertAlmostEqual(a_seconds, last_audio_pts_ms / 1000.0, delta=0.2,
                               msg=f"audio last pts {a_seconds:.3f}s does not match "
                                   f"input {last_audio_pts_ms/1000.0:.3f}s.")

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
