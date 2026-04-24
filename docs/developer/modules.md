# Modules

For specific modules, look at ([`stt-service.md`](stt-service.md), [`llm-integration.md`](llm-integration.md), [`probe.md`](probe.md), [`testing.md`](testing.md), [`contributing.md`](contributing.md)). Service topology is described in [`architecture.md`](architecture.md).

Thr following are grouped by function, not by directory.

## Package entry points

- [`pepper_wizard/main.py`](../../pepper_wizard/main.py). Argparse front end, log initialisation, `RobotClient` construction, `CommandHandler` wiring, and the main menu loop. The background status poller that updates battery and joint-temperature warnings every ten seconds lives at [`pepper_wizard/main.py#L66`](../../pepper_wizard/main.py#L66).
- [`pepper_wizard.py`](../../pepper_wizard.py) (repo root). Thin shim that re-exports [`pepper_wizard.main:main`](../../pepper_wizard/main.py#L11) so the CLI can be invoked as `python pepper_wizard.py` from outside the package. 
- [`pepper_wizard/__init__.py`](../../pepper_wizard/__init__.py). Empty marker file; the package is a namespace only.

## CLI and control flow

- [`pepper_wizard/cli.py`](../../pepper_wizard/cli.py). The `prompt_toolkit` interactive menu, the slash-command completer, and the three talk-mode session functions: [`pepper_talk_session`](../../pepper_wizard/cli.py#L447) (Text), [`voice_talk_session`](../../pepper_wizard/cli.py#L583) (Voice), and [`llm_talk_session`](../../pepper_wizard/cli.py#L771) (LLM). The main menu layout is built in [`show_main_menu`](../../pepper_wizard/cli.py#L75); talk-mode cycling reads from [`pepper_wizard/cli.py#L189`](../../pepper_wizard/cli.py#L189).
- [`pepper_wizard/command_handler.py`](../../pepper_wizard/command_handler.py). Dispatches menu selections to robot actions via [`CommandHandler.handle_command`](../../pepper_wizard/command_handler.py#L116) and hosts [`ZMQCommandListener`](../../pepper_wizard/command_handler.py#L12), the ZMQ REP socket on `:5561` that external experiment scripts drive.

## Robot I/O

- [`pepper_wizard/robot_client.py`](../../pepper_wizard/robot_client.py). HTTP client against `pepper-robot-env:5000`. Wraps a `NaoqiClient` proxy and exposes high-level helpers (`wake_up`, `rest`, `talk`, `animated_talk`, `set_tracking_mode`, battery and temperature reads) used everywhere else in the package.
- [`pepper_wizard/io/actuation.py`](../../pepper_wizard/io/actuation.py). [`RobotActuator`](../../pepper_wizard/io/actuation.py#L5), a fixed-rate consumer thread that reads the latest command from a size-1 queue and forwards it through `RobotClient`. Decouples high-frequency control producers from NAOqi call latency.
- [`pepper_wizard/state_buffer.py`](../../pepper_wizard/state_buffer.py). ZMQ subscriber on `:5560` that keeps a time-indexed ring buffer of head yaw and pitch. Supports interpolated lookups for latency-compensated control.
- [`pepper_wizard/state_estimator.py`](../../pepper_wizard/state_estimator.py). Constant-velocity Kalman filter used by the tracking loop for target-state estimation.

## STT, LLM, and probe integrations

- [`pepper_wizard/stt_client.py`](../../pepper_wizard/stt_client.py). ZMQ REQ wrapper for the `stt-service` container on `:5562`. Handles `ping`, `start_recording`, `stop_recording`, and `transcribe` actions. Service-side detail, audio flow, and GPU overlay behaviour live in [`stt-service.md`](stt-service.md).
- [`pepper_wizard/llm/client.py`](../../pepper_wizard/llm/client.py). [`LLMClient`](../../pepper_wizard/llm/client.py#L9), the Anthropic dialogue wrapper with rolling history and lazy `anthropic` import. A missing SDK or a missing `ANTHROPIC_API_KEY` raises [`LLMUnavailable`](../../pepper_wizard/llm/client.py#L5). To tune the llm, check [`llm-integration.md`](llm-integration.md).
- [`pepper_wizard/llm/__init__.py`](../../pepper_wizard/llm/__init__.py). Empty marker; the subpackage is a namespace only.
- [`pepper_wizard/probe/`](../../pepper_wizard/probe/). Self-contained host-capability detector. Detects GPU vendor and driver, audio capture, controller presence, and robot reachability, then recommends a compose overlay. Runnable via `python -m pepper_wizard.probe`. Full output format and detection logic are in [`probe.md`](probe.md).

## Behaviour subpackages

- [`pepper_wizard/core/`](../../pepper_wizard/core/). Domain logic for closed-loop control, free of ZMQ or NAOqi coupling. [`core/models.py`](../../pepper_wizard/core/models.py) holds the shared `Point`, `BBox`, and `Detection` dataclasses; [`core/control/`](../../pepper_wizard/core/control/) contains the PID, Kalman, native-NAOqi, filter, and CSV-telemetry building blocks; [`core/tracking/head_tracker.py`](../../pepper_wizard/core/tracking/head_tracker.py) composes them into the head-tracking policy.
- [`pepper_wizard/orchestrators/`](../../pepper_wizard/orchestrators/). Wiring between domain logic and the outside world. [`tracking_orchestrator.py`](../../pepper_wizard/orchestrators/tracking_orchestrator.py) connects [`VisionReceiver`](../../pepper_wizard/perception/vision_receiver.py), [`StateBuffer`](../../pepper_wizard/state_buffer.py), [`PerceptionClient`](../../pepper_wizard/perception/perception_client.py), [`HeadTracker`](../../pepper_wizard/core/tracking/head_tracker.py), and [`RobotActuator`](../../pepper_wizard/io/actuation.py) into a single closed loop.
- [`pepper_wizard/perception/`](../../pepper_wizard/perception/). Vision ingest and detection parsing. [`vision_receiver.py`](../../pepper_wizard/perception/vision_receiver.py) subscribes to the PepperBox video stream on `:5559`; [`perception_client.py`](../../pepper_wizard/perception/perception_client.py) issues REQ calls against the perception service on `:5557`; [`interpreter.py`](../../pepper_wizard/perception/interpreter.py) normalises MediaPipe and YOLO payloads into `Detection` objects; [`external_tracker.py`](../../pepper_wizard/perception/external_tracker.py) drives NAOqi's `ALTracker.lookAt` as an alternative to the native control loop.
- [`pepper_wizard/exp_behaviors/`](../../pepper_wizard/exp_behaviors/). One-off high-level behaviours triggered from the menu. [`behaviors.py`](../../pepper_wizard/exp_behaviors/behaviors.py) currently holds `gaze_at_marker`, the NAOqi landmark-search routine wired to the Gaze-at-Marker menu entry.

## Utilities

- [`pepper_wizard/config.py`](../../pepper_wizard/config.py). JSON loader for every file under [`pepper_wizard/config/`](../../pepper_wizard/config/). [`Config`](../../pepper_wizard/config.py#L121) is the aggregate container; per-file detail is in [`../user/configuration.md`](../user/configuration.md).
- [`pepper_wizard/logger.py`](../../pepper_wizard/logger.py). JSONL session logger. [`JSONFormatter`](../../pepper_wizard/logger.py#L7) emits the `{timestamp, level, component, event, data}` schema; `setup_logging` auto-names files in `logs/` or honours `--session-id`.
- [`pepper_wizard/spell_checker.py`](../../pepper_wizard/spell_checker.py). [`SpellChecker`](../../pepper_wizard/spell_checker.py#L4), a T5 grammar-correction wrapper (`vennify/t5-base-grammar-correction`) used by Text talk mode's live-suggestion prompt.
- [`pepper_wizard/teleop.py`](../../pepper_wizard/teleop.py). Base teleop classes and the ZMQ joystick controller. `BaseTeleopController` defines the axis-to-motion mapping; `ZMQTeleopController` subscribes to `dualshock-publisher` on `:5556`; the shared `teleop_running` event gates the loop.
- [`pepper_wizard/keyboard_teleop.py`](../../pepper_wizard/keyboard_teleop.py). [`KeyboardTeleopController`](../../pepper_wizard/keyboard_teleop.py#L11), a `prompt_toolkit`-driven teleop mode with a watchdog that cuts motion on key release.
- [`pepper_wizard/controllers.py`](../../pepper_wizard/controllers.py). Standalone `PIDController` class, duplicate of [`core/control/pid.py`](../../pepper_wizard/core/control/pid.py). No current imports in the tree; the live tracking loop consumes the `core/control/pid.py` version.
- [`pepper_wizard/tools/`](../../pepper_wizard/tools/). Standalone ZMQ viewers for manual debugging. [`proximity_viewer.py`](../../pepper_wizard/tools/proximity_viewer.py) renders sonar and laser readings from the state publisher; [`vision_viewer.py`](../../pepper_wizard/tools/vision_viewer.py) renders the video stream with perception overlays.
- [`pepper_wizard/utils/download_model.py`](../../pepper_wizard/utils/download_model.py). One-shot script that pre-downloads the spell-checker weights during image build so the first Text talk session does not pay the download cost.