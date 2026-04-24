# Talk modes

There are three channels from the operator to Pepper's voice and animations: spoken push-to-talk, typed text with autocomplete and emoticon triggers, and a Claude-driven dialogue that listens through Pepper's own microphone. All three live under the same Talk Mode menu entry.

## Switching between modes

The main menu shows a single `Talk Mode [<mode>]` row. `[Tab]` from the main menu cycles Voice, Text, and LLM, then wraps back to Voice (see [`pepper_wizard/cli.py#L189`](../../pepper_wizard/cli.py#L189)). Confirming the entry enters the selected mode. `/q` from within any mode returns to the main menu.

## Voice mode

Push-to-talk speech-to-text through Whisper. `[Space]` starts a recording and `[Enter]` stops it; the captured audio is sent to the `stt-service` container over ZMQ and returned as text.

Transcriptions flow through the review gate before they are spoken (see [Review gate](#review-gate)). When `review_mode` is `true`, each transcription is shown in an editable prompt that accepts `[Enter]` to confirm, typed edits to correct, and `[Esc]` to discard. When `review_mode` is `false`, Pepper speaks the transcription verbatim as soon as it arrives.

Typing text at the `Voice [<mode>]:` prompt speaks that text directly, bypassing the microphone path.

Backing service and capture pipeline are documented in [`../developer/stt-service.md`](../developer/stt-service.md).

## Text mode

Typed input with three features layered over one `prompt_toolkit` session.

- **Live spellcheck.** As the operator types, a correction is proposed for the last word and displayed inline. `[Tab]` toggles between the suggestion and the raw input; `[Enter]` accepts whichever is currently shown.
- **Slash autocomplete.** Typing `/` opens a completer populated with talk-mode commands (`/help`, `/q`), the quick-response hotkeys drawn from [`quick_responses.json`](../../pepper_wizard/config/quick_responses.json), and the animation tags drawn from [`emoticon_map.json`](../../pepper_wizard/config/emoticon_map.json). Hotkeys like `/Y` and `/N` speak the bound phrase and play the bound animation.
- **Emoticon triggers.** Inline tokens such as `:)` are matched against [`emoticon_map.json`](../../pepper_wizard/config/emoticon_map.json) and dispatched as non-blocking animations alongside the remaining speech. The same tokens are also offered as autocomplete entries under the `/` namespace.

A line with only a slash tag (`/happy`) plays the animation alone; a line with a tag and text (`/happy Hello there`) plays them together.

## LLM dialogue mode

Naturalistic conversation with Claude over Pepper's own front microphone. The `stt-service` runs voice-activity detection on the audio stream, publishes each detected utterance as a transcription event on ZMQ, and the CLI forwards the utterance to Claude via `LLMClient`. Pepper replies through its built-in text-to-speech; the microphone is muted while Pepper is speaking so the service does not self-trigger on its own voice.

Model, system prompt, sampling, and history length are configured in [`llm.json`](../../pepper_wizard/config/llm.json); per-key detail is in [`configuration.md`](configuration.md).

Entering the mode requires `ANTHROPIC_API_KEY` in the shell that ran `docker compose up` (compose forwards the variable into the `pepper-wizard` container). Without the key, selecting LLM from the menu prints `LLM unavailable: ANTHROPIC_API_KEY is not set` and returns to the main menu (raised at [`pepper_wizard/llm/client.py#L31`](../../pepper_wizard/llm/client.py#L31), caught at [`pepper_wizard/cli.py#L782`](../../pepper_wizard/cli.py#L782)). The rest of the CLI is unaffected.

Typing at the `LLM:` prompt sends the typed text as a turn, which gives the operator a keyboard path alongside the microphone path. `/reset` clears the rolling history; `/review` toggles the LLM-mode review gate at runtime; `/q` exits back to the main menu.

### Limitations

The microphone path depends on services that are not part of the base compose. The `audio-publisher-service` from the dev overlay publishes Pepper's audio frames on ZMQ `:5563`, which the `stt-service` subscribes to for streaming VAD. The base has no publisher on that port, so on the base alone the `LLM:` prompt appears and typed turns dispatch to Claude normally, but voice input never fires.

The same applies in sim mode, because `audio-publisher-service` has no NAOqi audio broker to connect to. Running LLM mode with live robot-mic input requires the dev overlay and a physical Pepper.

## Review gate

Two independent flags, both in [`stt.json`](../../pepper_wizard/config/stt.json) and both defaulting to `true`.

- `review_mode` gates Voice mode. Read at [`pepper_wizard/cli.py#L590`](../../pepper_wizard/cli.py#L590).
- `llm_review_mode` gates LLM mode. Read at [`pepper_wizard/cli.py#L817`](../../pepper_wizard/cli.py#L817). When `false`, VAD utterances dispatch to Claude directly from the subscriber thread.

Either flag can be flipped at runtime with `/review` inside its mode. Per-key detail is in [`configuration.md`](configuration.md).

## Reset and quit

`/reset` clears the rolling dialogue history in LLM mode; it has no effect in Voice or Text mode. `/q` exits the current mode and returns to the main menu in all three.
