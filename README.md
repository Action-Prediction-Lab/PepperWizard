# PepperWizard

PepperWizard is a Python-based application for teleoperating the Pepper robot. It provides a command-line interface to enable teleoperation via a DualShock controller, as well as to trigger speech, animations, and other actions.

## Features

*   **Joystick Teleoperation:** Control the robot's movement in real-time using a DualShock controller.
*   **Interactive CLI:** A command-line interface for triggering various robot actions.
*   **Text-to-Speech (TTS):** Make the robot speak any text you provide.
*   **Animated Speech:** Combine speech with pre-defined animations for more expressive interactions.
*   **Social State Control:** Toggle the robot's autonomous social behaviors.
*   **Battery Status:** Check the robot's current battery level.
*   **Dockerised:** The entire application and its dependencies are managed through Docker and Docker Compose for easy setup and execution.

## Architecture

The PepperWizard system is composed of three main services orchestrated by `docker-compose.yml`:

1.  **`pepper-robot-env`**: This service runs a Python 2.7 environment and a "shim server" to act as a bridge to the Pepper robot's native NAOqi OS. This is necessary because the robot's core libraries use Python 2.7.
2.  **`dualshock-publisher`**: This service reads input from a connected DualShock controller (`/dev/input`) and publishes the data to a ZeroMQ message queue.
3.  **`pepper-wizard`**: This is the main application, written in Python 3. It subscribes to the `dualshock-publisher`'s ZeroMQ messages for teleoperation and provides the interactive CLI for the user. It communicates with the `pepper-robot-env` service to send commands to the robot.

The `pepper-wizard` application itself is structured as follows:

*   `main.py`: The main application entry point.
*   `robot_client.py`: A client class that handles all direct communication with the robot.
*   `teleop.py`: Manages the teleoperation (joystick) logic in a separate thread.
*   `command_handler.py`: Maps user commands to specific actions.
*   `cli.py`: Handles all command-line interface (UI) elements.
*   `config.py`: Loads configuration files.

## Getting Started

### Prerequisites

*   Docker
*   Docker Compose
*   A DualShock controller connected to the host machine.

> **Note**: This project depends on the `jwgcurrie/pepper-box` Docker image for the Naoqi bridge. Docker Compose will automatically pull this image from DockerHub.

### Connection Configuration (Simulated vs Physical)



The connection to the robot (or simulator) is configured via the `robot.env` file. This file interacts with the `pepper-robot-env` service, which acts as a bridge.

1.  **Create or edit `robot.env`** in the root directory:
    ```bash
    NAOQI_IP=127.0.0.1
    NAOQI_PORT=39961
    ```

2.  **Configuration Scenarios**:
    *   **Simulated Robot (Choregraphe)**:
        *   Ensure your simulator is running.
        *   Set `NAOQI_IP=127.0.0.1`.
        *   Set `NAOQI_PORT` to your simulator's port (e.g., `39961`).
    *   **Physical Robot**:
        *   Set `NAOQI_IP` to the robot's IP address (e.g., `192.168.1.101`).
        *   Set `NAOQI_PORT=9559` (default NAOqi port).

### Installation & Running

1.  Clone this repository.
2.  Build and run the services using Docker Compose:

    ```bash
    docker compose up -d --build
    ```
    This starts the background services (`pepper-robot-env` and `dualshock-publisher`).

3.  **Run the Wizard**:
    Launch the interactive CLI:
    ```bash
    docker compose run --rm -it pepper-wizard
    ```



## Usage

Once the application is running, you can enter commands into the terminal.

The application uses an interactive selection menu.

*   **Arrow Keys** (`↑` / `↓`): Navigate selection.
*   **Enter**: Confirm selection.

```text
Select Action:
 > Unified Talk Mode
   Joystick Teleop
   Toggle Social State
   Set Tracking Mode
   Wake Up Robot
   Rest Robot
   Gaze at Marker
   Check Battery
   Exit Application
```

### Unified Talk Mode

When in Unified Talk Mode, you can speak sentences and trigger animations:


### Advanced Features

#### 1. Proactive Spellcheck & Confirmation
As you type, the system checks your grammar. If a correction is found:
*   **Interactive UI**: You will see a prompt like `Pepper (Suggestion) [tag]:`.
*   **Tab-Toggle**: Press `[Tab]` to switch between the **Suggestion** (Cyan) and your **Raw Input** (White).
*   **Confirm**: Press `[Enter]` to confirm the selected text.

#### 2. Slash-Autocomplete
Type `/` at any time to see a menu of available commands and animations.
*   **Context Aware**: Works at the start of a line or mid-sentence (e.g., `Hello /`).
*   **Tags**: Includes full animation tags (e.g., `/happy`, `/bow`).
*   **Safety**: Only triggers when you explicitly type `/`, preventing accidental activations.

#### 3. Available Inputs
*   **Plain Speech:** Enter any text.
*   **Emoticon-Triggered Animation:** Include a recognized emoticon (e.g., `:)`, `XD`).
*   **Hotkey-Triggered Blocking Animation:** Include a hotkey (e.g., `/N`, `/Y`).
*   **Tag-Triggered Animation:** Use the autocomplete menu to select a tag (e.g., `/happy`).

*   `/help` - Show contextual help for the talk mode.
*   `/q`    - Quit talk mode and return to the main menu.

## Configuration

You can customise some of the robot's behaviors by editing the JSON files:

*   **`animations.json`**: Maps animation names to single-character keys. These tags are used internally and by `emoticon_map.json`.
*   **`emoticon_map.json`**: Maps emoticons (e.g., `:)`, `:(`) to animation names (e.g., `happy`, `sad`). This allows for dynamic animation triggering in Unified Talk Mode.
*   **`quick_responses.json`**: Defines phrases and animations that can be triggered by hotkeys (e.g., `/N`) in the Unified Talk Mode. The `animation` field in each entry is used to determine which animation to play.

## Logging

PepperWizard includes a logging system that captures robot interactions, user commands, and application events.

### Log Files
Logs are automatically saved to the `logs/` directory in JSON Lines (JSONL) format.

*   **Default Naming**: Log files are automatically timestamped:
    `logs/session_YYYY-MM-DD_HH-MM-SS.jsonl`
*   **Custom Session ID**: You can specify a custom session ID to create a specific filename (e.g., `logs/session_P01.jsonl`):
    ```bash
    docker compose run --rm -it pepper-wizard python3 -m pepper_wizard.main --proxy-ip host.docker.internal --proxy-port 5000 --session-id P01
    ```

### Console Output
By default, the console output is minimal, only showing critical warnings or errors.
*   **Verbose Mode**: To see all logs (INFO/DEBUG) in the console in real-time, use the `--verbose` flag:
    ```bash
    docker compose run --rm -it pepper-wizard python3 -m pepper_wizard.main --proxy-ip host.docker.internal --proxy-port 5000 --verbose
    ```

## Testing

To verify PepperWizard end-to-end, run the automated integration test. This simulates a full user session (connecting to the robot, speaking, moving, etc.) and verifies the log output. It is recommended to run this in simulation in case your robot accidentally runs into a wall.

```bash
docker compose run --rm pepper-wizard python3 tests/integration_test.py
```

