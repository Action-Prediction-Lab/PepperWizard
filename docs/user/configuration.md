# Configuration

## Layout

Runtime behaviour lives in ten JSON files under [`pepper_wizard/config/`](../../pepper_wizard/config/). Each file is plain JSON, read once on startup.

## File-by-file reference

### animations.json

Maps animation names to the single-character keys used by the emoticon and quick-response layers. It is the namespace that [`emoticon_map.json`](#emoticon_mapjson) and [`quick_responses.json`](#quick_responsesjson) resolve against.

Shape: a flat `{ "<animation-name>": "<key>" }` object. Keys are one character; names are arbitrary identifiers referenced from the other two files.

### dualshock.json

Binds the DualShock publisher to the CLI's teleop loop.

| Key | Type | Default | What it controls |
|---|---|---|---|
| `zmq_address` | string | `"tcp://localhost:5556"` | Address the CLI subscribes to for joystick events. |
| `deadzone` | number | `0.1` | Absolute axis value below which input is treated as zero. |
| `axes.strafe` | string | `"left_stick_x"` | Axis mapped to lateral motion. |
| `axes.drive` | string | `"left_stick_y"` | Axis mapped to forward/backward motion. |
| `axes.turn` | string | `"right_stick_x"` | Axis mapped to yaw rotation. |

### emoticon_map.json

Maps emoticon tokens typed in talk mode to animation names resolved via `animations.json`.

Shape: a flat `{ "<emoticon>": "<animation-name>" }` object. Tokens are matched literally in outgoing text; the associated animation name is looked up in `animations.json` and dispatched alongside the speech.

### keyboard.json

Drives the keyboard teleop mode.

| Key | Type | Default | What it controls |
|---|---|---|---|
| `key_mapping` | object | see below | Maps keyboard keys to motion primitives. |
| `watchdog_timeout` | number | `0.2` | Seconds without a key event before motion is cut. |
| `speed_step` | number | `0.1` | Multiplier increment for `+`/`-`. |
| `min_speed_multiplier` | number | `0.1` | Lower bound on the speed multiplier. |
| `max_speed_multiplier` | number | `2.0` | Upper bound on the speed multiplier. |

`key_mapping` is a `{ "<key>": "<action>" }` object. Actions are drawn from a fixed vocabulary: `forward`, `backward`, `turn_left`, `turn_right`, `strafe_left`, `strafe_right`, `forward_strafe_left`, `forward_strafe_right`, `backward_strafe_left`, `backward_strafe_right`, `increase_speed`, and `decrease_speed`.

### llm.json

Configures the Anthropic client used by LLM talk mode. The LLM path is optional; without `ANTHROPIC_API_KEY` in the host environment the CLI hides LLM entries and the rest of the stack runs unchanged.

| Key | Type | Default | What it controls |
|---|---|---|---|
| `model` | string | `"claude-haiku-4-5"` | Anthropic model identifier used for every request. |
| `system_prompt` | string | see file | The persona and formatting contract sent as the system message on every turn. It pins Pepper's voice and keeps replies short and free of markdown. |
| `max_tokens` | integer | `256` | Maximum tokens generated per reply. |
| `temperature` | number | `0.7` | Sampling temperature passed to the API. |
| `history_turns` | integer | `10` | Number of prior user/assistant turns retained as context. |

### quick_responses.json

Binds hotkeys (`/Y`, `/N`, `/H`, ...) to scripted phrase-plus-animation bundles used during Wizard-of-Oz sessions.

Shape: a `{ "<key>": { "phrase": ..., "animation": ..., "tuning": ..., "stop": ... } }` object. Fields per entry:

| Field | Type | What it controls |
|---|---|---|
| `phrase` | string | Text spoken by the TTS engine. |
| `animation` | string | Animation name resolved via `animations.json`. |
| `tuning` | string | NAOqi tag string prepended to the phrase. Backslashes are JSON-escaped: `\\rspd=100\\ ` in the file unescapes to `\rspd=100\ ` at runtime to set speech rate. |
| `stop` | string | Termination tag (`stopTag` or `waitTag`) governing how the utterance ends. |

### stt.json

Configures the Whisper STT service and the two review gates that sit between transcription and dispatch.

| Key | Type | Default | What it controls |
|---|---|---|---|
| `zmq_address` | string | `"tcp://localhost:5562"` | REQ/REP address the CLI uses to drive the STT service. |
| `audio_zmq_address` | string | `"tcp://localhost:5563"` | Audio-chunk stream consumed by the STT service. |
| `transcription_zmq_address` | string | `"tcp://localhost:5564"` | PUB stream of finalised transcriptions. |
| `review_mode` | bool | `true` | Voice talk mode: if `true`, each transcription is shown for operator approval before it is spoken. Read at [`pepper_wizard/cli.py#L590`](../../pepper_wizard/cli.py#L590). |
| `llm_review_mode` | bool | `true` | LLM talk mode: if `true`, each transcription is held for review before being sent to the LLM; if `false`, transcriptions auto-dispatch from the subscriber thread. Read at [`pepper_wizard/cli.py#L817`](../../pepper_wizard/cli.py#L817). |
| `model_size` | string | `"medium.en"` | Whisper checkpoint loaded by the STT container. |
| `sample_rate` | integer | `16000` | Audio capture rate in Hz. |
| `push_to_talk_key` | string | `"space"` | Key that starts a push-to-talk recording. |
| `vad.threshold` | number | `0.2` | Voice-activity probability threshold. |
| `vad.min_silence_ms` | integer | `1200` | Trailing silence required to end an utterance. |
| `vad.min_utterance_ms` | integer | `300` | Minimum utterance length kept. |
| `vad.max_utterance_ms` | integer | `15000` | Hard cap on utterance length. |
| `vad.preroll_ms` | integer | `200` | Audio retained before VAD detects speech. |

### teleop.json

Default speeds and mode selection for the teleop loop.

| Key | Type | Default | What it controls |
|---|---|---|---|
| `speeds.v_x` | number | `0.2` | Default forward/backward velocity (m/s). |
| `speeds.v_y` | number | `0.2` | Default lateral velocity (m/s). |
| `speeds.v_theta` | number | `0.5` | Default yaw velocity (rad/s). |
| `default_mode` | string | `"Keyboard"` | Mode selected at startup. Switches to `Joystick` at runtime only when `dualshock-publisher` is reachable. |
| `joystick_first_message_timeout` | number | `3.0` | Seconds the CLI waits for a joystick message before falling back to keyboard. |

### temperature.json

Joint-temperature warning thresholds, consumed by the status poller.

| Key | Type | Default | What it controls |
|---|---|---|---|
| `thresholds.warm` | integer | `65` | Temperature (degrees C) above which a joint is flagged warm. |
| `thresholds.hot` | integer | `80` | Temperature (degrees C) above which a joint is flagged hot. |

### tuning.json

Control-loop parameters for the head-tracking orchestrator. Grouped by subsystem.

| Key | Type | Default | What it controls |
|---|---|---|---|
| `adaptive` | bool | `false` | Enables adaptive gain scheduling. |
| `control_mode` | string | `"native"` | Selects the control backend. |
| `native.fov_x` | number | `0.85` | Horizontal field of view (radians) used to scale pixel error. |
| `native.fov_y` | number | `0.65` | Vertical field of view (radians). |
| `native.fraction_max_speed` | number | `0.25` | Fraction of the joint's declared max speed the loop is allowed to command. |
| `native.deadzone_x` | number | `0.08` | Normalised horizontal pixel error below which no correction is issued. |
| `native.deadzone_y` | number | `0.10` | Normalised vertical pixel error below which no correction is issued. |
| `native.smoothing_x` | number | `0.8` | EMA coefficient on horizontal command. |
| `native.smoothing_y` | number | `0.8` | EMA coefficient on vertical command. |
| `native.max_vel_deg_s` | number | `115.0` | Velocity cap (deg/s) applied to head joints. |
| `native.max_accel_deg_s2` | number | `275.0` | Acceleration cap (deg/s^2). |
| `native.max_jerk_deg_s3` | number | `5000.0` | Jerk cap (deg/s^3). |
| `native.gain_p` | number | `3.2` | Proportional gain on pixel error. |
| `native.gain_v` | number | `0.05` | Feed-forward velocity gain. |
| `native.vel_decay` | number | `0.6` | Decay applied to the velocity estimate each tick. |
| `native.target_lost_timeout` | number | `0.5` | Seconds without a detection before the loop holds position. |
| `native.estimator_limit_multiplier` | number | `1.5` | Slack factor on the state-estimator limits. |
| `stiffness.min` | number | `0.60` | Lower bound on head-joint stiffness command. |
| `stiffness.max` | number | `0.60` | Upper bound on head-joint stiffness command. |
| `stiffness.sensitivity` | number | `0.0` | Error-driven stiffness modulation. |
| `stiffness.smoothing` | number | `0.0` | EMA coefficient on stiffness changes. |
| `kalman.process_noise` | number | `0.1` | Kalman filter process-noise variance. |
| `kalman.measurement_noise` | number | `150.0` | Kalman filter measurement-noise variance. |
| `kalman.latency_comp` | number | `0.12` | Seconds of measurement latency compensated by the filter. |
| `pid.base_kp` | number | `0.045` | Baseline proportional gain. |
| `pid.boost_kp` | number | `0.0` | Additional proportional gain applied under boost conditions. |
| `pid.kd` | number | `0.03` | Derivative gain. |
| `pid.ki` | number | `0.015` | Integral gain. |
| `pid.max_output` | number | `0.20` | Absolute cap on PID output. |
| `pid.output_smoothing` | number | `0.0` | EMA coefficient on PID output. |
| `pid.default_speed` | number | `0.3` | Default commanded speed when the PID path is active. |
| `body.enabled` | bool | `false` | Enables body-yaw coupling to head tracking. |
| `body.deadzone_yaw` | number | `0.35` | Head-yaw magnitude (radians) below which the body does not turn. |
| `body.kp_base` | number | `0.2` | Proportional gain on body yaw. |
| `body.max_speed` | number | `0.2` | Cap on body yaw rate. |
| `body.feed_forward` | bool | `true` | Forwards head-yaw velocity into body command. |
| `safety.min_dt` | number | `0.001` | Lower bound on the loop timestep. |
| `safety.max_dt` | number | `0.05` | Upper bound on the loop timestep before a tick is discarded. |
| `safety.safe_dt_propagation` | number | `0.05` | Timestep used when propagating state under degraded timing. |

## Reload semantics

Every file under `pepper_wizard/config/` is read once, on CLI startup. Editing a value takes effect on the next `docker compose run --rm -it pepper-wizard`.
