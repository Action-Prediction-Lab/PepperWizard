import json
import os
import tempfile
import unittest
from pathlib import Path

from pepper_wizard.llm.client import LLMUnavailable
from pepper_wizard.llm.config_watcher import LLMConfigWatcher


def _bump_mtime(path: Path):
    """Force a visible mtime change even on filesystems with coarse timestamps."""
    stat = path.stat()
    new_time = stat.st_mtime + 1
    os.utime(path, (new_time, new_time))


class LLMConfigWatcherTests(unittest.TestCase):
    def setUp(self):
        fd, name = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.path = Path(name)
        self.path.write_text(json.dumps({"model": "claude-haiku-4-5", "temperature": 0.7}))

    def tearDown(self):
        if self.path.exists():
            self.path.unlink()

    def test_initial_load_returns_parsed_dict(self):
        watcher = LLMConfigWatcher(self.path)
        cfg = watcher.current()
        self.assertEqual(cfg["model"], "claude-haiku-4-5")
        self.assertEqual(cfg["temperature"], 0.7)

    def test_repeated_current_returns_same_object_when_unchanged(self):
        watcher = LLMConfigWatcher(self.path)
        first = watcher.current()
        second = watcher.current()
        self.assertIs(first, second)

    def test_mtime_bump_triggers_reload(self):
        watcher = LLMConfigWatcher(self.path)
        _ = watcher.current()
        self.path.write_text(json.dumps({"model": "claude-sonnet-4-6", "temperature": 0.2}))
        _bump_mtime(self.path)
        cfg = watcher.current()
        self.assertEqual(cfg["model"], "claude-sonnet-4-6")
        self.assertEqual(cfg["temperature"], 0.2)

    def test_on_change_callback_fires_with_old_and_new(self):
        events = []
        watcher = LLMConfigWatcher(
            self.path,
            on_change=lambda old, new: events.append((old, new)),
        )
        _ = watcher.current()
        self.path.write_text(json.dumps({"model": "claude-sonnet-4-6"}))
        _bump_mtime(self.path)
        _ = watcher.current()
        self.assertEqual(len(events), 1)
        old, new = events[0]
        self.assertEqual(old["model"], "claude-haiku-4-5")
        self.assertEqual(new["model"], "claude-sonnet-4-6")

    def test_malformed_json_keeps_cached_value_and_logs(self):
        watcher = LLMConfigWatcher(self.path)
        good = watcher.current()
        self.path.write_text("{ this is not json")
        _bump_mtime(self.path)
        with self.assertLogs("pepper_wizard.llm.config_watcher", level="WARNING"):
            cfg = watcher.current()
        self.assertIs(cfg, good)

    def test_recovers_after_malformed_then_valid(self):
        events = []
        watcher = LLMConfigWatcher(
            self.path,
            on_change=lambda old, new: events.append((old, new)),
        )
        _ = watcher.current()
        self.path.write_text("{ broken")
        _bump_mtime(self.path)
        with self.assertLogs("pepper_wizard.llm.config_watcher", level="WARNING"):
            _ = watcher.current()
        self.assertEqual(events, [])
        self.path.write_text(json.dumps({"model": "claude-opus-4-7"}))
        _bump_mtime(self.path)
        cfg = watcher.current()
        self.assertEqual(cfg["model"], "claude-opus-4-7")
        self.assertEqual(len(events), 1)

    def test_missing_file_keeps_cached_value(self):
        watcher = LLMConfigWatcher(self.path)
        good = watcher.current()
        self.path.unlink()
        with self.assertLogs("pepper_wizard.llm.config_watcher", level="WARNING"):
            cfg = watcher.current()
        self.assertIs(cfg, good)

    def test_initial_load_failure_raises_llm_unavailable(self):
        bogus = self.path.with_suffix(".does-not-exist")
        with self.assertRaises(LLMUnavailable):
            LLMConfigWatcher(bogus)

    def test_callback_exception_does_not_propagate(self):
        def boom(old, new):
            raise RuntimeError("callback should not crash watcher")

        watcher = LLMConfigWatcher(self.path, on_change=boom)
        _ = watcher.current()
        self.path.write_text(json.dumps({"model": "claude-sonnet-4-6"}))
        _bump_mtime(self.path)
        with self.assertLogs("pepper_wizard.llm.config_watcher", level="WARNING"):
            cfg = watcher.current()
        self.assertEqual(cfg["model"], "claude-sonnet-4-6")


if __name__ == "__main__":
    unittest.main()
