# LLM integration

The LLM talk mode enables realtime dialogue between Pepper and a person through a speech ->[stt-service]-> text -> [llm] -> pepper's speech pipeline. An inference provider (configured by default as Anthropic's claude) is layered on top of the audio path documented in [`stt-service.md`](stt-service.md). The operator-facing description sits at [`../user/talk-modes.md`](../user/talk-modes.md#llm-dialogue-mode).

## Client and lazy import

Two symbols live in [`pepper_wizard/llm/client.py`](../../pepper_wizard/llm/client.py): the [`LLMUnavailable`](../../pepper_wizard/llm/client.py#L5) exception and the [`LLMClient`](../../pepper_wizard/llm/client.py#L9) wrapper. The subpackage's [`__init__.py`](../../pepper_wizard/llm/__init__.py) is an empty namespace marker.

The `anthropic` import is performed inside [`LLMClient.__init__`](../../pepper_wizard/llm/client.py#L17), not at module load. This is since `pepper-wizard` must keep importing on hosts where the SDK is missing or `ANTHROPIC_API_KEY` is unset. Placing the import to the top of the module would break the CLI's import graph whenever Anthropic was unreachable, and the rest of PepperWizard does not depend on the inference provider.

The constructor raises `LLMUnavailable` at two sites:

- [`client.py#L31`](../../pepper_wizard/llm/client.py#L31). `ANTHROPIC_API_KEY` is not present in the container's environment.
- [`client.py#L39`](../../pepper_wizard/llm/client.py#L39). The `anthropic` package is not installed in the running image.

Both messages name the corrective action (export the key in the host shell, or rebuild the image).

Conversation state is a `collections.deque` capped at `history_turns * 2`, since each turn contributes a user message and an assistant reply. [`LLMClient.reply`](../../pepper_wizard/llm/client.py#L46) appends the user turn, calls `messages.create` with the windowed history as the `messages` parameter and `system_prompt` as the separate `system` parameter, then appends the assistant reply. [`LLMClient.reset`](../../pepper_wizard/llm/client.py#L65) clears the deque without rebuilding the SDK client, which is what `/reset` calls in the session loop.

## Config schema

[`pepper_wizard/config/llm.json`](../../pepper_wizard/config/llm.json) carries five keys; defaults in `LLMClient.__init__` apply when a key is absent. Operator-facing detail is in [`../user/configuration.md#llmjson`](../user/configuration.md#llmjson).

- `model`. The Anthropic model identifier passed to `messages.create`. The default is `claude-haiku-4-5`. Any model the account has access to is valid.
- `system_prompt`. The system message sent on every turn. It is not part of the rolling history; it travels alongside the message list as a top-level parameter, so changing it takes effect on the next turn without a `/reset`.
- `max_tokens`. Upper bound on response length, in tokens. Defaults to `256`. Pepper's TTS sounds best with one or two short sentences; the prompt asks for that, and `max_tokens` sets the absolute maximum.
- `temperature`. Sampling temperature passed through unchanged. Defaults to `0.7`.
- `history_turns`. Number of full turns retained. The deque holds `history_turns * 2` messages so a turn boundary always coincides with a user message at the head.

## Session flow

[`llm_talk_session`](../../pepper_wizard/cli.py#L771) is the entry point invoked when the operator confirms `Talk Mode [LLM]` from the main menu. It instantiates `LLMClient`, opens an `STTClient` REQ socket on `:5562`, and calls [`enable_streaming`](../../pepper_wizard/cli.py#L796) to start the service's `StreamingWorker`. A SUB socket then binds to the transcription PUB on `:5564` (default `tcp://localhost:5564`).

A background thread, [`_sub_loop`](../../pepper_wizard/cli.py#L819), drains the SUB socket. The review gate flag lives in a one-element list, [`review_mode`](../../pepper_wizard/cli.py#L817), so the thread reads the current value on every iteration and `/review` toggles take effect without restarting the loop. When review is on, events are pushed onto a `queue.Queue` for the main thread; when review is off, the thread calls the llm api directly.

The main thread runs a `prompt_toolkit` session under `patch_stdout`. On every iteration it drains queued review events, then accepts a typed line. Slash commands are matched literally:

- `/q`. Exits the session; the `finally` block disables streaming and closes both sockets.
- `/reset`. Calls `LLMClient.reset` to clear the rolling history.
- `/review`. Toggles `review_mode[0]` and prints the new state.

Anything else is treated as a typed turn and forwarded to [`_dispatch_to_llm`](../../pepper_wizard/cli.py#L933) with `source="typed"`.

[`_handle_vad_event`](../../pepper_wizard/cli.py#L894) is the per-utterance entry point for both code paths. Empty transcriptions are dropped with a `VADUtterance` log entry. With review on, the event opens a nested `prompt_toolkit` prompt seeded with the transcribed text; the operator confirms, edits, or discards before dispatch. With review off, the text goes to `_dispatch_to_llm` immediately, with `source="robot_mic"`.

`_dispatch_to_llm` mutes the streaming worker through the STT REP `mute` action before calling `LLMClient.reply`, so frames captured while Pepper is speaking are dropped at the service rather than being transcribed and fed back as new turns. The reply is printed, spoken via [`robot_client.talk`](../../pepper_wizard/cli.py#L961), and the worker is unmuted in every exit path, including the LLM-error and empty-reply branches. The full action surface is documented in [`stt-service.md#5562-rep--commands`](stt-service.md#5562-rep--commands).

## Graceful degradation

`Talk Mode` always cycles Voice, Text, and LLM regardless of whether the SDK or the API key is present. The check sits at [`pepper_wizard/cli.py#L189`](../../pepper_wizard/cli.py#L189); the menu does not hide the LLM entry on a missing key.

Failures surface at entry-time. Selecting LLM without `ANTHROPIC_API_KEY` raises [`LLMUnavailable`](../../pepper_wizard/llm/client.py#L31); selecting LLM in an image where `anthropic` is not installed raises [`LLMUnavailable`](../../pepper_wizard/llm/client.py#L39). Both raises are caught at [`pepper_wizard/cli.py#L782`](../../pepper_wizard/cli.py#L782); the CLI prints the exception message in red and returns to the main menu. The rest of the application is unaffected, and the typed Talk and Voice modes continue to work.

`ANTHROPIC_API_KEY` is forwarded into the `pepper-wizard` container by `docker-compose.yml` from the host shell that ran `docker compose up`. The reminder sits at the bottom of [`robot.env.example`](../../robot.env.example).

