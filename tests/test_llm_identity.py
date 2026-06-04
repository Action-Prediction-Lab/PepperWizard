import unittest

from pepper_wizard.llm.identity import (
    resolve_config,
    config_fingerprint,
    build_config_snapshot,
)

_BEHAVIOURAL = {"model", "system_prompt", "max_tokens", "temperature", "history_turns"}


class ResolveConfigTests(unittest.TestCase):
    def test_applies_defaults_for_missing_fields(self):
        resolved = resolve_config({"system_prompt": "hi"})
        self.assertEqual(resolved["model"], "claude-haiku-4-5")
        self.assertEqual(resolved["max_tokens"], 256)
        self.assertEqual(resolved["temperature"], 0.7)
        self.assertEqual(resolved["history_turns"], 10)
        self.assertEqual(resolved["system_prompt"], "hi")

    def test_drops_non_behavioural_keys(self):
        resolved = resolve_config({"name": "persona-a", "model": "m", "extra": 1})
        self.assertNotIn("name", resolved)
        self.assertNotIn("extra", resolved)
        self.assertEqual(set(resolved), _BEHAVIOURAL)


class FingerprintTests(unittest.TestCase):
    def test_deterministic_and_order_independent(self):
        a = config_fingerprint(
            {"model": "m", "system_prompt": "p", "max_tokens": 1,
             "temperature": 0.1, "history_turns": 2}
        )
        b = config_fingerprint(
            {"history_turns": 2, "temperature": 0.1, "max_tokens": 1,
             "system_prompt": "p", "model": "m"}
        )
        self.assertEqual(a, b)

    def test_length_is_twelve_hex(self):
        h = config_fingerprint(resolve_config({}))
        self.assertEqual(len(h), 12)
        int(h, 16)  # raises if not hex

    def test_prompt_edit_changes_hash(self):
        base = resolve_config({"system_prompt": "old"})
        edited = resolve_config({"system_prompt": "new"})
        self.assertNotEqual(config_fingerprint(base), config_fingerprint(edited))

    def test_fingerprint_ignores_non_behavioural_keys(self):
        # A raw config (with name + extras) and its resolved form fingerprint
        # identically: config_fingerprint resolves internally, so there is no
        # raw-vs-resolved mis-attribution surface.
        raw = {"name": "persona-a", "model": "m", "system_prompt": "p", "extra": 1}
        self.assertEqual(config_fingerprint(raw), config_fingerprint(resolve_config(raw)))


class BuildSnapshotTests(unittest.TestCase):
    def test_session_start_shape(self):
        snap = build_config_snapshot(
            {"name": "a", "model": "m", "system_prompt": "p"}, "session_start"
        )
        self.assertEqual(snap["reason"], "session_start")
        self.assertEqual(snap["config_source"], "file")
        self.assertEqual(snap["config_name"], "a")
        self.assertEqual(len(snap["config_hash"]), 12)
        self.assertEqual(set(snap["config"]), _BEHAVIOURAL)
        self.assertNotIn("changed", snap)

    def test_config_name_none_when_absent(self):
        snap = build_config_snapshot({"model": "m"}, "session_start")
        self.assertIsNone(snap["config_name"])

    def test_name_excluded_from_hash(self):
        a = build_config_snapshot({"name": "a", "model": "m", "system_prompt": "p"}, "session_start")
        b = build_config_snapshot({"name": "b", "model": "m", "system_prompt": "p"}, "session_start")
        self.assertEqual(a["config_hash"], b["config_hash"])
        self.assertNotEqual(a["config_name"], b["config_name"])

    def test_reload_includes_changed(self):
        snap = build_config_snapshot(
            {"model": "m"}, "reload", changed=["temperature 0.7→0.9"]
        )
        self.assertEqual(snap["reason"], "reload")
        self.assertEqual(snap["changed"], ["temperature 0.7→0.9"])

    def test_hash_matches_fingerprint_of_resolved(self):
        raw = {"model": "m", "system_prompt": "p"}
        snap = build_config_snapshot(raw, "session_start")
        self.assertEqual(snap["config_hash"], config_fingerprint(resolve_config(raw)))


if __name__ == "__main__":
    unittest.main()
