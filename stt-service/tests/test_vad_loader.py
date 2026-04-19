"""Unit tests for _load_vad_config in main.py."""
import json
import os
import tempfile
import unittest

from main import _load_vad_config, DEFAULT_VAD
from vad_segmenter import VadConfig


class TestLoadVadConfig(unittest.TestCase):
    """Tests for _load_vad_config with explicit path injection (no real mount required)."""

    def test_missing_file_returns_defaults(self):
        """When the config file does not exist, defaults are used."""
        cfg = _load_vad_config(path="/nonexistent/path/stt.json")
        self.assertIsInstance(cfg, VadConfig)
        self.assertAlmostEqual(cfg.threshold, DEFAULT_VAD["threshold"])
        self.assertEqual(cfg.min_silence_ms, DEFAULT_VAD["min_silence_ms"])
        self.assertEqual(cfg.min_utterance_ms, DEFAULT_VAD["min_utterance_ms"])
        self.assertEqual(cfg.max_utterance_ms, DEFAULT_VAD["max_utterance_ms"])
        self.assertEqual(cfg.preroll_ms, DEFAULT_VAD["preroll_ms"])

    def test_custom_values_override_defaults(self):
        """Values in the vad block override the defaults."""
        custom = {
            "vad": {
                "threshold": 0.7,
                "min_silence_ms": 500,
                "preroll_ms": 100,
            }
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(custom, f)
            tmp_path = f.name

        try:
            cfg = _load_vad_config(path=tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertAlmostEqual(cfg.threshold, 0.7)
        self.assertEqual(cfg.min_silence_ms, 500)
        self.assertEqual(cfg.preroll_ms, 100)
        # Unset keys retain defaults.
        self.assertEqual(cfg.min_utterance_ms, DEFAULT_VAD["min_utterance_ms"])
        self.assertEqual(cfg.max_utterance_ms, DEFAULT_VAD["max_utterance_ms"])

    def test_empty_vad_block_returns_defaults(self):
        """A stt.json with an empty vad block returns full defaults."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"vad": {}}, f)
            tmp_path = f.name

        try:
            cfg = _load_vad_config(path=tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertAlmostEqual(cfg.threshold, DEFAULT_VAD["threshold"])
        self.assertEqual(cfg.min_silence_ms, DEFAULT_VAD["min_silence_ms"])

    def test_malformed_json_falls_back_to_defaults(self):
        """A corrupt JSON file silently falls back to defaults."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("not valid json {{")
            tmp_path = f.name

        try:
            cfg = _load_vad_config(path=tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertIsInstance(cfg, VadConfig)
        self.assertAlmostEqual(cfg.threshold, DEFAULT_VAD["threshold"])
