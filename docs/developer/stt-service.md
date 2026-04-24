# STT service

The `stt-service` captures speech nearby the robot and transcripts this into text. The service is self contained, built from [`stt-service/`](../../stt-service/), it loads a Whisper model through `faster-whisper`, and exposes three ZMQ sockets: a REP command channel on `:5562`, an audio SUB on `:5563`, and a transcription PUB on `:5564`. The `pepper-wizard` CLI reaches the REP channel through [`STTClient`](../../pepper_wizard/stt_client.py#L8). The full port inventory sits in [`architecture.md#port-map`](architecture.md#port-map).

The service is part of the three-service base compose, so it starts with every deployment. The GPU overlay ([`docker-compose.gpu.yml`](../../docker-compose.gpu.yml)) patches only this service.

## Loading Whisper

Model construction is performed by [`_load_whisper`](../../stt-service/main.py#L154). The resolver honours three sources, in order: an explicit constructor argument, then the `STT_DEVICE` and `STT_COMPUTE_TYPE` environment variables, then the string `"auto"`. The environment is re-read on every call so tests can patch `os.environ` without reimporting the module.

Three branches follow from the resolved device:

- `"auto"`. Attempt CUDA with `compute_type="float16"`. On `RuntimeError` or `ValueError` from CTranslate2 at model construction, fall back to CPU with `compute_type="int8"`.
- `"cuda"`. Attempt CUDA. Any failure re-raises; the operator asked for GPU and a silent CPU fallback would hide the problem.
- `"cpu"`. Skip CUDA and construct the model on CPU with `int8` directly.

`"auto"` for `compute_type` resolves to `float16` on the CUDA path and `int8` on the CPU path. Any explicit value is passed through unchanged.

Every branch that returns a model emits the same log line: `Loaded whisper '<size>' on <device>/<compute>`. Run `docker compose logs stt-service | grep 'Loaded whisper'` to see the final device choice on the happy path, the CPU-fallback path, and the explicit-CPU path alike. The CUDA runtime is not installed directly; it arrives transitively through the image's `pip install -r requirements.txt` step, so [`stt-service/requirements.txt`](../../stt-service/requirements.txt) stays short.

## VAD segmenter

Utterance boundaries come from [`VadSegmenter`](../../stt-service/vad_segmenter.py#L23), a wrapper over Silero VAD that runs at 16 kHz with 32 ms (512-sample) windows. It has no dependency on Whisper or ZMQ; it takes `int16` PCM in and emits whole-utterance byte buffers through a callback.

For tuning use [`VadConfig`](../../stt-service/vad_segmenter.py#L14) or used the mirrored in `pepper_wizard/config/stt.json` under the `vad` key:

| Field | Meaning |
|---|---|
| `threshold` | Silero VAD probability above which a 32 ms window is labelled speech. |
| `min_silence_ms` | Trailing silence required before an utterance is considered complete. |
| `min_utterance_ms` | Lower bound below which a candidate utterance is discarded. |
| `max_utterance_ms` | Hard ceiling; an utterance is force-flushed once it reaches this length. |
| `preroll_ms` | Audio retained before speech onset so the start of the first word is not clipped. |

[`VadSegmenter._process_window`](../../stt-service/vad_segmenter.py#L58) is the decision point. Outside an utterance, non-speech windows accumulate into a trailing preroll ring buffer; the first speech window starts an utterance and prepends that buffer. Inside an utterance, consecutive non-speech windows bump a silence counter. When the counter exceeds `min_silence_ms / window_ms`, [`_emit`](../../stt-service/vad_segmenter.py#L91) flushes the utterance, provided its length meets `min_utterance_ms`. Hitting `max_utterance_ms` also emits.

We set the default in `pepper_wizard/config/stt.json` as `threshold: 0.2`, more permissive than the `0.5` fallback in [`DEFAULT_VAD`](../../stt-service/main.py#L199). The fallback is conservative because it is what the service uses when the config mount is missing; the present value is tuned against Pepper's front microphone, which sits further from the speaker than a headset mic and benefits from a lower gate. Edit `stt.json` rather than `DEFAULT_VAD` to tune for a new environment.

## Streaming worker

[`StreamingWorker`](../../stt-service/main.py#L32) is a daemon thread owned by `STTService`. It connects a SUB socket to the audio publisher at `tcp://localhost:5563` (filled by `audio-publisher-service` on the dev overlay, or by [`pepper_wizard/tools/host_mic_publisher.py`](../../pepper_wizard/tools/host_mic_publisher.py) in base mode) and binds a PUB socket on `tcp://*:5564`. Each inbound frame is an `int16` PCM chunk; the worker feeds it to a `VadSegmenter` instance, and every callback invocation runs one `self._whisper.transcribe(...)` synchronously and publishes the result.

Transcription uses `beam_size=3`, `language="en"`, and `vad_filter=False` (the Silero segmenter already did that job). The result is packed into an [`UtteranceEvent`](../../stt-service/events.py#L7) and encoded through [`encode_event`](../../stt-service/events.py#L21). If `transcribe` raises, the worker sends an error envelope instead, stamped with the utterance start time. The `source` field is always `"robot_mic"`.

The SUB socket uses `RCVTIMEO=200` (milliseconds). The run loop calls `recv(zmq.NOBLOCK)` and sleeps on the stop event between receives, so the worker wakes at least every 20 ms to observe `self._stop_evt`. A `_muted` flag on `STTService` gates frame processing without tearing the worker down, so the `mute` and `unmute` REP actions can pause streaming transcription without the cost of reloading Whisper.

The REP `enable_streaming` action lazily creates and starts the worker; `disable_streaming` calls `stop()` and `join(timeout=2.0)`.

## ZMQ surface

Three sockets. The port assignments are load-bearing; see [`architecture.md#port-map`](architecture.md#port-map) for the cross-service view.

### `:5562` REP — commands

Bound at [`STTService.__init__`](../../stt-service/main.py#L232). Requests are JSON with an `action` key, dispatched in [`_handle_action`](../../stt-service/main.py#L278).

| Action | Effect | Reply |
|---|---|---|
| `ping` | Liveness check. | `{"status": "ok"}` |
| `start` | Begin host-microphone capture for the push-to-talk path. | `{"status": "recording"}` |
| `stop` | End capture, transcribe the buffered audio, return the result. | `{"transcription": str, "duration": float}` |
| `enable_streaming` | Start the `StreamingWorker`. | `{"status": "streaming"}` |
| `disable_streaming` | Stop the `StreamingWorker`. | `{"status": "idle"}` |
| `mute` | Gate the streaming worker's frame processing without stopping it. | `{"status": "muted"}` |
| `unmute` | Reverse `mute`. | `{"status": "unmuted"}` |

[`STTClient`](../../pepper_wizard/stt_client.py#L8) wraps each action. The client-side method names (`start_recording`, `stop_and_transcribe`) differ from the wire-level action strings (`start`, `stop`); the wire is canonical.

### `:5563` SUB — audio in

Connected by the `StreamingWorker`'s SUB socket. Each frame is a raw `int16` little-endian PCM blob at 16 kHz, mono. The worker does not apply a ZMQ topic filter; every message on the socket is consumed.

### `:5564` PUB — transcriptions out

Bound by the `StreamingWorker`. Each message is a UTF-8 JSON string. Success messages match the `UtteranceEvent` shape: `text`, `duration_s`, `t_start`, `t_end`, `source`. Timestamps are ISO-8601 Zulu with millisecond precision. Errors have `error`, `detail`, and `t_start`. `pepper-wizard` consumes this PUB from the CLI's Voice and LLM talk-mode session loops.

## Shutdown semantics

Docker sends SIGTERM on `compose stop` and waits ten seconds before SIGKILL. [`main`](../../stt-service/main.py#L388) installs a single handler for SIGTERM and SIGINT that calls [`STTService.request_shutdown`](../../stt-service/main.py#L260), which only sets a flag.

The REP loop at [`STTService.run`](../../stt-service/main.py#L361) polls the socket with a 500 ms timeout rather than blocking on `recv_json`. Each tick checks `self._shutdown` and exits if the flag is set. The tick cadence keeps SIGTERM-to-exit latency under one second in p99, inside the ten-second grace window. After the loop exits, the service calls `self._worker.stop()` and `self._worker.join(timeout=2.0)` to drain the streaming worker, then closes the REP socket with `linger=0` and terminates the ZMQ context.

## Cache volume and offline mode

Whisper weights are downloaded by `faster-whisper` on first use into `~/.cache/huggingface`. The base compose mounts the named volume `huggingface-cache` at that path on the container side, weights persist across `docker compose down`, image rebuilds, and compose-file changes. The volume is declared at the bottom of [`docker-compose.yml`](../../docker-compose.yml) and bound into `stt-service` via `volumes:`.

Two environment variables control network access, both documented in [`.env.example`](../../.env.example) and forwarded through `docker-compose.yml` with `:-0` defaults:

- `HF_HUB_OFFLINE`. When set to `1`, `huggingface_hub` refuses every network call.
- `TRANSFORMERS_OFFLINE`. When set to `1`, the `transformers` library mirrors that refusal.

Defaults leave both off, so swapping `model_size` in `pepper_wizard/config/stt.json` to a model the volume has not seen downloads it on the next restart. Setting both to `1` in a project-level `.env` hardens the service against Hub outages and rate-limit stalls. The cost is that every model the operator might select must be pre-populated in the cache beforehand.

The compose entry uses `restart: on-failure`. If a first-run download is interrupted mid-transfer (network drop, the operator Ctrl-C's the stack), the partial blob stays in the volume and `faster-whisper` resumes from it on the next start. 