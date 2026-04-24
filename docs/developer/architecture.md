# Architecture

## Compose topology

PepperWizard is a cluster of Docker services layered across three compose files: `docker-compose.yml` (the base), `docker-compose.dev.yml` (the dev overlay), and `docker-compose.gpu.yml` (the GPU overlay).

### Base (three services)

Self-contained; no sibling repositories required. Every service runs under `network_mode: host`, so ports are bound on the host directly and no user-defined bridge is involved.

- **`pepper-robot-env`** (image `jwgcurrie/pepper-box:01-26-latest`). Python 2.7 NAOqi shim. Exposes an HTTP endpoint on `:5000` (Flask) that `pepper-wizard` drives. On a physical robot, it also runs the video publisher on `:5559` and the state publisher on `:5560`.
- **`stt-service`** (locally built from `./stt-service`). Whisper CPU STT. Binds ZMQ REP on `:5562` for command/response, subscribes to audio frames on `:5563`, and publishes finalised transcriptions on `:5564`.
- **`pepper-wizard`** (locally built from the repo root). The Python 3 CLI. Reads `ANTHROPIC_API_KEY` from the host environment for optional LLM dialogue.

### Dev overlay (four optional services)

The overlay swaps `pepper-robot-env` for the sim-capable `pepper-box:latest` image (qiBullet) and live-mounts sibling checkouts of `../PepperBox` and `../PepperPerception` into the relevant services. The `dualshock-publisher` image is pulled from the registry.

- **`proprioception-service`** (image `pepper-box:latest`). Python 2 NAOqi joint-state publisher. Binds ZMQ PUB on `:5560`.
- **`audio-publisher-service`** (image `pepper-box:latest`). Python 2 NAOqi audio publisher reading Pepper's front microphone. Binds ZMQ PUB on `:5563`. Depends on `pepper-robot-env`.
- **`dualshock-publisher`** (image `jwgcurrie/dualshock_publisher:latest`, sibling repo `Dualshock-ZMQ`). Reads `/dev/input` and publishes joystick events on ZMQ `:5556`. Runs with `privileged: true` to access the input devices.
- **`perception-service`** (locally built from `../PepperPerception`). YOLOv8 plus MediaPipe perception. Binds ZMQ REP on `:5557`. Gated behind the `gpu` profile and only started with `--profile gpu` (requires the NVIDIA container runtime).

### GPU overlay (one patch)

`docker-compose.gpu.yml` adds an NVIDIA device reservation to `stt-service` so Whisper loads on CUDA. It patches only that service and stacks independently of the dev overlay: base plus GPU, or base plus dev plus GPU.

## Port map

| Port | Protocol | Direction | Bound by | Connected by |
|---|---|---|---|---|
| `5000` | HTTP | in | `pepper-robot-env` | `pepper-wizard` |
| `5556` | ZMQ PUB | out | `dualshock-publisher` (dev) | `pepper-wizard` (SUB) |
| `5557` | ZMQ REP | in | `perception-service` (dev, `gpu` profile) | `pepper-wizard` (REQ) |
| `5559` | ZMQ PUB | out | `pepper-robot-env` (video streamer) | `pepper-wizard` (SUB) |
| `5560` | ZMQ PUB | out | `pepper-robot-env` state shim, or `proprioception-service` (dev) | `pepper-wizard` (SUB) |
| `5561` | ZMQ REP | in | `pepper-wizard` via [`ZMQCommandListener`](../../pepper_wizard/command_handler.py#L12) | external experiment scripts (REQ) |
| `5562` | ZMQ REP | in | `stt-service` | `pepper-wizard` (REQ) |
| `5563` | ZMQ PUB | in to `stt-service` | `audio-publisher-service` (dev) or [`pepper_wizard/tools/host_mic_publisher.py`](../../pepper_wizard/tools/host_mic_publisher.py) | `stt-service` (SUB) |
| `5564` | ZMQ PUB | out | `stt-service` | `pepper-wizard` (SUB) |

The `5559` / `5560` pair shares a compose caveat: only one process can bind each port under `network_mode: host`, so the base shim's state publisher and the dev overlay's `proprioception-service` are mutually exclusive. See the [Sim mode notes in getting started](../user/getting-started.md#simulator-dev-overlay-no-physical-robot-needed) for why `proprioception-service` restart-loops under sim mode.

## Data flow

### Live session (operator in the loop)

Operator action to robot motion:

1. Operator confirms an entry on the CLI menu (for example a teleop command or a quick-response hotkey).
2. `pepper-wizard` issues an HTTP request to `pepper-robot-env:5000`.
3. The Python 2.7 NAOqi shim dispatches the corresponding NAOqi call on its Python 2 broker.
4. Pepper actuates.

Microphone audio to speech and animation:

1. Audio source: the host microphone via PulseAudio on the base, or Pepper's front microphone via `audio-publisher-service` on the dev overlay.
2. Audio frames arrive at `stt-service` on ZMQ `:5563`.
3. The service runs voice-activity detection, transcribes each utterance, and publishes the transcription on ZMQ `:5564`.
4. `pepper-wizard` consumes the transcription, passes it through the review gate (see [Talk modes](../user/talk-modes.md#review-gate)), and dispatches the resulting phrase and animation through the same HTTP shim on `:5000`.

### Scripted session (experiment script drives)

External experiment scripts drive reproducible runs without an operator at the keyboard:

1. Script opens a ZMQ REQ socket to `tcp://<wizard-host>:5561`.
2. [`ZMQCommandListener`](../../pepper_wizard/command_handler.py#L12) on `pepper-wizard` receives the JSON command, dispatches it through the same command-handler path a menu selection would take, and sends a JSON status reply.
3. The command lands on the HTTP shim on `:5000`, following the same path as a live-session action.

## Graceful degradation

Only one menu entry hides at startup when its backing service is unreachable: **Track Object**. The check sits at [`pepper_wizard/cli.py#L175`](../../pepper_wizard/cli.py#L175); when `perception-service` is not reachable the tracker fails to initialise and the entry is omitted from the menu.

Every other entry is always visible. Missing services manifest at entry-time rather than at menu-build time:

- Teleop Mode cycles Keyboard and Joystick regardless of whether `dualshock-publisher` is running. Selecting Joystick without the publisher reaches the teleop loop but receives no input, so the robot does not respond to controller events.
- Talk Mode always cycles Voice, Text, and LLM ([`pepper_wizard/cli.py#L189`](../../pepper_wizard/cli.py#L189)). Entering LLM without `ANTHROPIC_API_KEY` raises [`LLMUnavailable`](../../pepper_wizard/llm/client.py#L31), which is caught at [`pepper_wizard/cli.py#L782`](../../pepper_wizard/cli.py#L782); the CLI prints the error and returns to the main menu.
- Joint Temperatures reads through the `pepper-robot-env` HTTP shim, not `proprioception-service`, so it remains available on the base alone.

See [Getting started](../user/getting-started.md) for how to tell from the operator's side whether each service is up, and the [host probe](../user/getting-started.md#check-your-host-first-recommended) for a pre-launch capability check.
