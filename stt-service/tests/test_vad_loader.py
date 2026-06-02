"""Unit tests for _load_vad_config in config_loader.py."""
import unittest

from config_loader import DEFAULT_VAD, _load_vad_config
from vad_segmenter import VadConfig


class TestLoadVadConfig(unittest.TestCase):
    """Tests for _load_vad_config, which builds a VadConfig from a parsed config dict."""

    def test_empty_config_returns_defaults(self):
        """An empty config dict yields VadConfig with all defaults."""
        cfg = _load_vad_config({})
        self.assertIsInstance(cfg, VadConfig)
        self.assertAlmostEqual(cfg.threshold, DEFAULT_VAD["threshold"])
        self.assertEqual(cfg.min_silence_ms, DEFAULT_VAD["min_silence_ms"])
        self.assertEqual(cfg.min_utterance_ms, DEFAULT_VAD["min_utterance_ms"])
        self.assertEqual(cfg.max_utterance_ms, DEFAULT_VAD["max_utterance_ms"])
        self.assertEqual(cfg.preroll_ms, DEFAULT_VAD["preroll_ms"])

    def test_custom_values_override_defaults(self):
        """Values in the vad block override the defaults; unset keys retain defaults."""
        cfg = _load_vad_config(
            {
                "vad": {
                    "threshold": 0.7,
                    "min_silence_ms": 500,
                    "preroll_ms": 100,
                }
            }
        )
        self.assertAlmostEqual(cfg.threshold, 0.7)
        self.assertEqual(cfg.min_silence_ms, 500)
        self.assertEqual(cfg.preroll_ms, 100)
        # Unset keys retain defaults.
        self.assertEqual(cfg.min_utterance_ms, DEFAULT_VAD["min_utterance_ms"])
        self.assertEqual(cfg.max_utterance_ms, DEFAULT_VAD["max_utterance_ms"])

    def test_empty_vad_block_returns_defaults(self):
        """A config with an empty vad block returns full defaults."""
        cfg = _load_vad_config({"vad": {}})
        self.assertAlmostEqual(cfg.threshold, DEFAULT_VAD["threshold"])
        self.assertEqual(cfg.min_silence_ms, DEFAULT_VAD["min_silence_ms"])

    def test_config_without_vad_key_returns_defaults(self):
        """A config dict missing the `vad` key falls back to defaults."""
        cfg = _load_vad_config({"other_key": "ignored"})
        self.assertIsInstance(cfg, VadConfig)
        self.assertAlmostEqual(cfg.threshold, DEFAULT_VAD["threshold"])
