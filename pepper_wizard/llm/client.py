import os
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config_watcher import LLMConfigWatcher


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

        # Initialise with the default maxlen; reply() will resize on first call
        # if the watcher's history_turns differs. We do not call watcher.current()
        # here so that the watcher call-count seen by callers reflects only
        # active turns, not construction overhead.
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

    def reply(self, user_text: str) -> str:
        """Send `user_text` with the rolling history and return the reply."""
        config = self._watcher.current()

        desired_maxlen = config.get("history_turns", 10) * 2
        if self._history.maxlen != desired_maxlen:
            self._history = deque(self._history, maxlen=desired_maxlen)

        self._history.append({"role": "user", "content": user_text})

        response = self._client.messages.create(
            model=config.get("model", "claude-haiku-4-5"),
            system=config.get(
                "system_prompt",
                "You are Pepper, a humanoid robot. Keep replies brief and conversational.",
            ),
            max_tokens=config.get("max_tokens", 256),
            temperature=config.get("temperature", 0.7),
            messages=list(self._history),
        )

        reply_text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        self._history.append({"role": "assistant", "content": reply_text})
        return reply_text

    def reset(self):
        self._history.clear()
