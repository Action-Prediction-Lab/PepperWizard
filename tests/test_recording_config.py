"""Unit tests for recording config loader."""
import json
import os
import tempfile
import unittest

from pepper_wizard.config import load_recording_config


class TestLoadRecordingConfig(unittest.TestCase):
    def test_loads_user_values(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "record_by_default": False,
                "output_dir": "custom/path",
                "video_codec": "h264",
                "container": "mp4",
            }, f)
            path = f.name
        try:
            cfg = load_recording_config(path)
            self.assertFalse(cfg["record_by_default"])
            self.assertEqual(cfg["output_dir"], "custom/path")
            self.assertEqual(cfg["video_codec"], "h264")
            self.assertEqual(cfg["container"], "mp4")
        finally:
            os.unlink(path)

    def test_defaults_when_missing_fields(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            path = f.name
        try:
            cfg = load_recording_config(path)
            self.assertTrue(cfg["record_by_default"])
            self.assertEqual(cfg["output_dir"], "recordings")
            self.assertEqual(cfg["video_codec"], "ffv1")
            self.assertEqual(cfg["video_pix_fmt"], "yuv420p")
            self.assertEqual(cfg["audio_codec"], "pcm_s16le")
            self.assertEqual(cfg["container"], "mkv")
        finally:
            os.unlink(path)

    def test_defaults_when_file_missing(self):
        cfg = load_recording_config("/nonexistent/path/recording.json")
        self.assertTrue(cfg["record_by_default"])
        self.assertEqual(cfg["video_codec"], "ffv1")


if __name__ == "__main__":
    unittest.main()
