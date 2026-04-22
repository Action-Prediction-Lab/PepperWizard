"""Unit tests for _load_model_size in main.py."""
import json
import os
import tempfile
import unittest

from main import _load_model_size, DEFAULT_MODEL_SIZE


class TestLoadModelSize(unittest.TestCase):
    def test_missing_file_returns_default(self):
        self.assertEqual(
            _load_model_size(path="/nonexistent/path/stt.json"),
            DEFAULT_MODEL_SIZE,
        )

    def test_custom_value_overrides_default(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"model_size": "medium.en"}, f)
            tmp_path = f.name
        try:
            self.assertEqual(_load_model_size(path=tmp_path), "medium.en")
        finally:
            os.unlink(tmp_path)

    def test_missing_key_returns_default(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"other_key": "ignored"}, f)
            tmp_path = f.name
        try:
            self.assertEqual(_load_model_size(path=tmp_path), DEFAULT_MODEL_SIZE)
        finally:
            os.unlink(tmp_path)

    def test_malformed_json_falls_back_to_default(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{")
            tmp_path = f.name
        try:
            self.assertEqual(_load_model_size(path=tmp_path), DEFAULT_MODEL_SIZE)
        finally:
            os.unlink(tmp_path)
