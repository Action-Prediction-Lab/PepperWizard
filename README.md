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

### Main Menu Commands

*   `A`    - Toggle Autonomous/Social State
*   `J`    - Start Joystick Teleoperation
*   `W`    - Wake Up Robot
*   `R`    - Put Robot to Rest
*   `T`    - Enter Unified Talk Mode
*   `Bat`  - Check Robot Battery Status
*   `q`    - Quit Joystick Teleoperation
*   `help` - Show this help message
*   `exit` - Exit the PepperWizard application

### Unified Talk Mode (`T` command)

When in Unified Talk Mode, you can speak sentences and trigger animations:

*   **Plain Speech:** Enter any text, and the robot will speak it without animation.
*   **Emoticon-Triggered Animation:** Include a recognized emoticon (e.g., `:)`, `XD`) anywhere in your sentence. The robot will speak the message (with the emoticon removed) and play the corresponding animation concurrently. Available emoticons are defined in `emoticon_map.json`.
*   **Hotkey-Triggered Blocking Animation:** Include a hotkey (e.g., `/N`, `/Y`) anywhere in your sentence. The robot will speak the message (with the hotkey removed) and then play the corresponding animation for its full duration. Hotkeys are defined in `quick_responses.json`.

*   `/help` - Show contextual help for the talk mode.
*   `/q`    - Quit talk mode and return to the main menu.

## Configuration

You can customise some of the robot's behaviors by editing the JSON files:

*   **`animations.json`**: Maps animation names to single-character keys. These tags are used internally and by `emoticon_map.json`.
*   **`emoticon_map.json`**: Maps emoticons (e.g., `:)`, `:(`) to animation names (e.g., `happy`, `sad`). This allows for dynamic animation triggering in Unified Talk Mode.
*   **`quick_responses.json`**: Defines phrases and animations that can be triggered by hotkeys (e.g., `/N`) in the Unified Talk Mode. The `animation` field in each entry is used to determine which animation to play.
