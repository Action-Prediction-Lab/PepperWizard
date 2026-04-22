import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class FakeWatcher:
    """Stand-in for LLMConfigWatcher with mutable state for tests."""

    def __init__(self, config):
        self._config = dict(config)

    def current(self):
        return self._config

    def update(self, **changes):
        self._config = {**self._config, **changes}


def _make_anthropic_response(text):
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block])


class LLMClientTests(unittest.TestCase):
    def setUp(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        self._anthropic_patch = patch("anthropic.Anthropic")
        self._mock_anthropic = self._anthropic_patch.start()
        self._mock_messages = MagicMock()
        self._mock_messages.create.return_value = _make_anthropic_response("hello back")
        self._mock_anthropic.return_value.messages = self._mock_messages

    def tearDown(self):
        self._anthropic_patch.stop()

    def test_reply_calls_watcher_each_turn(self):
        from pepper_wizard.llm.client import LLMClient

        watcher = FakeWatcher({
            "model": "claude-haiku-4-5",
            "system_prompt": "be brief",
            "max_tokens": 100,
            "temperature": 0.5,
            "history_turns": 4,
        })
        watcher.current = MagicMock(wraps=watcher.current)
        client = LLMClient(watcher)
        client.reply("hi")
        client.reply("again")
        self.assertEqual(watcher.current.call_count, 2)

    def test_api_call_uses_current_config_values(self):
        from pepper_wizard.llm.client import LLMClient

        watcher = FakeWatcher({
            "model": "claude-haiku-4-5",
            "system_prompt": "be brief",
            "max_tokens": 50,
            "temperature": 0.3,
            "history_turns": 4,
        })
        client = LLMClient(watcher)
        client.reply("hi")
        kwargs = self._mock_messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-haiku-4-5")
        self.assertEqual(kwargs["system"], "be brief")
        self.assertEqual(kwargs["max_tokens"], 50)
        self.assertEqual(kwargs["temperature"], 0.3)

    def test_history_preserved_across_system_prompt_swap(self):
        from pepper_wizard.llm.client import LLMClient

        watcher = FakeWatcher({
            "system_prompt": "old prompt",
            "history_turns": 4,
        })
        client = LLMClient(watcher)
        client.reply("first")
        watcher.update(system_prompt="new prompt")
        client.reply("second")
        kwargs = self._mock_messages.create.call_args.kwargs
        self.assertEqual(kwargs["system"], "new prompt")
        # Two prior turns + the new user message = 3 messages in the second call
        self.assertEqual(len(kwargs["messages"]), 3)
        self.assertEqual(kwargs["messages"][0]["content"], "first")
        self.assertEqual(kwargs["messages"][-1]["content"], "second")

    def test_history_turns_shrink_truncates_oldest(self):
        from pepper_wizard.llm.client import LLMClient

        watcher = FakeWatcher({"history_turns": 5})
        client = LLMClient(watcher)
        for i in range(5):
            client.reply(f"turn-{i}")
        # 5 user + 5 assistant = 10 messages in the deque, maxlen 10
        self.assertEqual(client._history.maxlen, 10)
        self.assertEqual(len(client._history), 10)

        watcher.update(history_turns=2)
        client.reply("after-shrink")
        self.assertEqual(client._history.maxlen, 4)
        # Rebuild discards anything beyond the new maxlen (4): only the most
        # recent prior entry plus the new user/assistant pair survive.
        contents = [m["content"] for m in client._history]
        self.assertEqual(contents[-2], "after-shrink")
        self.assertNotIn("turn-0", contents)
        self.assertNotIn("turn-1", contents)
        self.assertNotIn("turn-2", contents)
        self.assertNotIn("turn-3", contents)

    def test_history_turns_grow_preserves_existing(self):
        from pepper_wizard.llm.client import LLMClient

        watcher = FakeWatcher({"history_turns": 2})
        client = LLMClient(watcher)
        client.reply("a")
        client.reply("b")
        self.assertEqual(client._history.maxlen, 4)
        watcher.update(history_turns=10)
        client.reply("c")
        self.assertEqual(client._history.maxlen, 20)
        contents = [m["content"] for m in client._history]
        self.assertEqual(contents[0], "a")
        self.assertEqual(contents[-2], "c")

    def test_reply_appends_user_and_assistant_turns(self):
        from pepper_wizard.llm.client import LLMClient

        watcher = FakeWatcher({"history_turns": 4})
        client = LLMClient(watcher)
        self._mock_messages.create.return_value = _make_anthropic_response("the reply")
        result = client.reply("the question")
        self.assertEqual(result, "the reply")
        self.assertEqual(list(client._history), [
            {"role": "user", "content": "the question"},
            {"role": "assistant", "content": "the reply"},
        ])

    def test_reset_clears_history_without_touching_watcher(self):
        from pepper_wizard.llm.client import LLMClient

        watcher = FakeWatcher({"history_turns": 4})
        watcher.current = MagicMock(wraps=watcher.current)
        client = LLMClient(watcher)
        client.reply("hi")
        self.assertEqual(len(client._history), 2)
        before = watcher.current.call_count
        client.reset()
        self.assertEqual(len(client._history), 0)
        self.assertEqual(watcher.current.call_count, before)

    def test_model_property_reflects_watcher(self):
        from pepper_wizard.llm.client import LLMClient

        watcher = FakeWatcher({"model": "claude-haiku-4-5"})
        client = LLMClient(watcher)
        self.assertEqual(client.model, "claude-haiku-4-5")
        watcher.update(model="claude-sonnet-4-6")
        self.assertEqual(client.model, "claude-sonnet-4-6")


if __name__ == "__main__":
    unittest.main()
