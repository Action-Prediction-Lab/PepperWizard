import os
from collections import deque


class LLMUnavailable(Exception):
    pass


class LLMClient:
    """Anthropic-backed dialogue client with rolling history.

    Lazy-imports `anthropic` so that the rest of PepperWizard keeps importing
    even when the SDK isn't installed (matches the perception/tracking
    convention).
    """

    def __init__(self, config):
        self.model = config.get("model", "claude-haiku-4-5")
        self.system_prompt = config.get(
            "system_prompt",
            "You are Pepper, a humanoid robot. Keep replies brief and conversational.",
        )
        self.max_tokens = config.get("max_tokens", 256)
        self.temperature = config.get("temperature", 0.7)

        history_turns = config.get("history_turns", 10)
        self._history = deque(maxlen=history_turns * 2)

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

    def reply(self, user_text):
        """Send `user_text` with the rolling history and return the reply."""
        self._history.append({"role": "user", "content": user_text})

        response = self._client.messages.create(
            model=self.model,
            system=self.system_prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=list(self._history),
        )

        reply_text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        self._history.append({"role": "assistant", "content": reply_text})
        return reply_text

    def reset(self):
        self._history.clear()
