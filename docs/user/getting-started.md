# Getting started

## Prerequisites

Linux host with Docker and the Compose plugin. A Pepper on your network, or a qiBullet simulator reachable via the dev overlay.

## Point the stack at your robot

Copy the example and edit the two values:

```bash
cp robot.env.example robot.env
```

```bash
# robot.env
NAOQI_IP=192.168.123.50   # robot IP on your LAN
NAOQI_PORT=9559           # 9559 on a physical robot
```

Setting `NAOQI_IP=127.0.0.1` triggers sim mode under the dev overlay (see below). `NAOQI_PORT` is unused in sim mode; the key must still be present because the `env_file` parser requires it.

For LLM talk mode, export `ANTHROPIC_API_KEY` in your shell before `docker compose up`. The key is optional; every other feature works without it.

## Base: three-service launch

```bash
docker compose up -d --build                 # build images and start the background services
docker compose stop pepper-wizard            # free port 5561 for the interactive container
docker compose run --rm -it pepper-wizard    # launch the interactive CLI
```

Subsequent sessions run the third command alone.

Teleop defaults to keyboard. Menu entries for joystick, tracking, and perception stay hidden until their services are reachable, so the three-service base launches cleanly on its own.

**Why the `stop` step?** `docker compose up` starts `pepper-wizard` as a background container that binds `:5561` for external commands. `docker compose run` creates a second interactive container that wants the same port, and both use `network_mode: host`. Stopping the first frees the port for the second.

## GPU STT (optional)

On hosts with an NVIDIA GPU and `nvidia-container-runtime`, chain `docker-compose.gpu.yml` after the base file to run Whisper on CUDA. The overlay adds only a GPU device reservation to `stt-service`; everything else inherits from the base.

Whisper weights persist in the named `huggingface-cache` volume and survive container recreation.

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.gpu.yml stop pepper-wizard
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm -it pepper-wizard
```

The default model is `medium.en`, set in `pepper_wizard/config/stt.json`. Edit that file to change the size per VRAM budget.

To avoid repeating `-f` flags, write a gitignored `.env` at the repo root:

```
COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml
```

Docker Compose reads `.env` automatically, so plain `docker compose <cmd>` then picks up both files. `.env.example` at the repo root documents the other supported knobs (STT device override, HuggingFace offline mode).

## Simulator (dev overlay, no physical robot needed)

The dev overlay (`docker-compose.dev.yml`) swaps `pepper-robot-env` for the sim-capable `pepper-box:latest` image, which boots qiBullet when it sees `NAOQI_IP=127.0.0.1` in `robot.env`. Set that, then:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml stop pepper-wizard
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm -it pepper-wizard
```

On first boot the entrypoint seeds `../PepperBox/.qibullet/` with the Pepper URDF and meshes. Docker creates that directory root-owned, which blocks the container's `pepperdev` user (UID 1000) from writing. Fix it once:

```bash
sudo chown -R 1000:1000 ../PepperBox/.qibullet/
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate pepper-robot-env
```

In sim mode, `proprioception-service` and `audio-publisher-service` both restart-loop. `proprioception-service` is redundant because the qiBullet shim already publishes joint state on `:5560`, and `audio-publisher-service` has no NAOqi broker to connect to. Both restart loops are expected; do not chase.

## Check your host first (recommended)

Run the host probe before the first `docker compose up`:

```bash
python -m pepper_wizard.probe
```

It reports GPU vendor and driver stack, audio capture availability, controller detection, and whether the robot endpoint in `robot.env` is reachable, then recommends a compose profile. See [../developer/probe.md](../developer/probe.md) for the full output format and the detection logic behind each field.
