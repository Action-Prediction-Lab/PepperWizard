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

### Installation & Running

1.  Clone this repository.
2.  Build and run the services using Docker Compose:

    ```bash
    docker compose up -d --build
    ```

3.  The `pepper-wizard` application will start, and you can interact with it via the terminal.

## Usage

Once the application is running, you can enter commands into the terminal.

### Available Commands

*   `A`    - Toggle Autonomous/Social State
*   `J`    - Start Joystick Teleoperation
*   `W`    - Wake Up Robot
*   `R`    - Put Robot to Rest
*   `T`    - Enter Unified Talk Mode (supports emoticon-triggered animations)
*   `Bat`  - Check Robot Battery Status
*   `q`    - Quit Joystick Teleoperation
*   `help` - Show the help message
*   `exit` - Exit the PepperWizard application

## Usage

Once the application is running, you can enter commands into the terminal. For the Unified Talk Mode (`T` command):

*   **Plain Speech:** Enter any text, and the robot will speak it without animation.
*   **Animated Speech:** Prefix your text with a recognized emoticon (e.g., `:) Hello there!`). The robot will speak the message with the animation mapped to that emoticon. Available emoticons are defined in `emoticon_map.json`.

### Available Commands

*   `A`    - Toggle Autonomous/Social State
*   `J`    - Start Joystick Teleoperation
*   `W`    - Wake Up Robot
*   `R`    - Put Robot to Rest
*   `T`    - Enter Unified Talk Mode
*   `Bat`  - Check Robot Battery Status
*   `q`    - Quit Joystick Teleoperation
*   `help` - Show the help message
*   `exit` - Exit the PepperWizard application

## Configuration

You can customise some of the robot's behaviors by editing the JSON files:

*   **`animations.json`**: Maps animation names to single-character keys. These tags are used internally and by `emoticon_map.json`.
*   **`emoticon_map.json`**: Maps emoticons (e.g., `:)`, `:(`) to animation names (e.g., `happy`, `sad`). This allows for dynamic animation triggering in Unified Talk Mode.
*   **`quick_responses.json`**: Defines a set of pre-canned phrases and animations that can be triggered by a single key. (Note: The functionality to trigger these directly is not yet fully implemented in the CLI).
