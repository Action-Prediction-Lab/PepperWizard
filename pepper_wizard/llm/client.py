import os
import threading
from collections import deque, namedtuple
from .identity import resolve_config, config_fingerprint
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config_watcher import LLMConfigWatcher


ReplyResult = namedtuple("ReplyResult", ["text", "config_hash", "config_name"])


class LLMUnavailable(Exception):
    pass


class LLMClient:
    """Anthropic-backed dialogue client backed by a hot-swappable config watcher.

    The watcher is the ground truth for `model`, `system_prompt`, `max_tokens`,
    `temperature`, and `history_turns`. Each `reply()` call reads the current
    config from the watcher, so edits to `llm.json` take effect on the next turn.
    """

    def __init__(self, watcher: "LLMConfigWatcher"):
        self._watcher = watcher
        self._lock = threading.Lock()
        self._history = deque(maxlen=10 * 2)

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMUnavailable(
                "ANTHROPIC_API_KEY is not set. Export it in the shell "
                "running `docker compose up`."
            )

        try:
            import anthropic
        except ImportError as exc:
            raise LLMUnavailable(
                "The `anthropic` package is not installed. Rebuild the "
                "pepper-wizard image."
            ) from exc

        self._client = anthropic.Anthropic(api_key=api_key)

    @property
    def model(self) -> str:
        return self._watcher.current().get("model", "claude-haiku-4-5")

    def reply(self, user_text: str) -> "ReplyResult":
        """Send user_text with the rolling history; return a ReplyResult with the
        reply text plus the identity (config_hash, config_name) of the config used
        for THIS turn. A per-client lock serializes concurrent callers (e.g. the
        auto-dispatch VAD thread and typed input) so attribution is captured atomically 
        instead of read back from shared state."""
        with self._lock:
            raw = self._watcher.current()
            resolved = resolve_config(raw)

            desired_maxlen = resolved["history_turns"] * 2
            if self._history.maxlen != desired_maxlen:
                self._history = deque(self._history, maxlen=desired_maxlen)

            self._history.append({"role": "user", "content": user_text})

            response = self._client.messages.create(
                model=resolved["model"],
                system=resolved["system_prompt"],
                max_tokens=resolved["max_tokens"],
                temperature=resolved["temperature"],
                messages=list(self._history),
            )

            reply_text = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

            self._history.append({"role": "assistant", "content": reply_text})
            return ReplyResult(reply_text, config_fingerprint(resolved), raw.get("name"))

    def reset(self):
        with self._lock:
            self._history.clear()
