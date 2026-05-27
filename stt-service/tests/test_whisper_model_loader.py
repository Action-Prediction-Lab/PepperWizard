"""Unit tests for _load_config + _resolve_whisper_model in config_loader.py."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr

from config_loader import (
    DEFAULT_WHISPER_MODEL,
    _load_config,
    _resolve_whisper_model,
)


def _write_tmp_json(payload):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        if isinstance(payload, str):
            f.write(payload)
        else:
            json.dump(payload, f)
        return f.name


class TestLoadConfig(unittest.TestCase):
    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(_load_config("/nonexistent/path/stt.json"), {})

    def test_malformed_json_returns_empty_dict(self):
        path = _write_tmp_json("not valid json {{")
        try:
            self.assertEqual(_load_config(path), {})
        finally:
            os.unlink(path)


class TestResolveWhisperModel(unittest.TestCase):
    def test_prefers_whisper_model_over_model_size(self):
        config = {"whisper_model": "small.en", "model_size": "tiny.en"}
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(_resolve_whisper_model(config), "small.en")
        self.assertNotIn("DEPRECATED", err.getvalue())

    def test_falls_back_to_model_size_with_stderr_warning(self):
        config = {"model_size": "medium.en"}
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(_resolve_whisper_model(config), "medium.en")
        self.assertIn("DEPRECATED", err.getvalue())
        self.assertIn("model_size", err.getvalue())
        self.assertIn("whisper_model", err.getvalue())

    def test_defaults_when_both_keys_absent(self):
        self.assertEqual(_resolve_whisper_model({}), DEFAULT_WHISPER_MODEL)
        self.assertEqual(DEFAULT_WHISPER_MODEL, "base.en")


class TestEndToEnd(unittest.TestCase):
    """Ports the four cases from the deleted test_model_size_loader.py."""

    def test_missing_file_resolves_to_default(self):
        self.assertEqual(
            _resolve_whisper_model(_load_config("/nonexistent/path/stt.json")),
            DEFAULT_WHISPER_MODEL,
        )

    def test_custom_whisper_model_value(self):
        path = _write_tmp_json({"whisper_model": "medium.en"})
        try:
            self.assertEqual(
                _resolve_whisper_model(_load_config(path)),
                "medium.en",
            )
        finally:
            os.unlink(path)

    def test_missing_key_resolves_to_default(self):
        path = _write_tmp_json({"other_key": "ignored"})
        try:
            self.assertEqual(
                _resolve_whisper_model(_load_config(path)),
                DEFAULT_WHISPER_MODEL,
            )
        finally:
            os.unlink(path)

    def test_malformed_json_resolves_to_default(self):
        path = _write_tmp_json("not valid json {{")
        try:
            self.assertEqual(
                _resolve_whisper_model(_load_config(path)),
                DEFAULT_WHISPER_MODEL,
            )
        finally:
            os.unlink(path)
