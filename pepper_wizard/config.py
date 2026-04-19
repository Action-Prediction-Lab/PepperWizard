# Configuration loading (animations, etc.)
import json

from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "config"

def load_animations(file_path):
    """Load animations from a JSON file."""
    try:
        with open(file_path, "r") as f:
            animations = json.load(f)
        print("Animations loaded successfully.")
        return animations
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading animations from {file_path}: {e}")
        return {}

def load_quick_responses(file_path):
    """Load quick responses from a JSON file."""
    try:
        with open(file_path, "r") as f:
            responses = json.load(f)
        print("Quick responses loaded successfully.")
        return responses
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading quick responses from {file_path}: {e}")
        return {}

def load_emoticon_map(file_path):
    """Load emoticon to animation tag mappings from a JSON file."""
    try:
        with open(file_path, "r") as f:
            emoticon_map = json.load(f)
        print("Emoticon map loaded successfully.")
        return emoticon_map
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading emoticon map from {file_path}: {e}")
        return {}

def load_teleop_config(file_path):
    """Load teleoperation configuration from a JSON file."""
    try:
        with open(file_path, "r") as f:
            teleop_config = json.load(f)
        print("Teleop config loaded successfully.")
        return teleop_config
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading teleop config from {file_path}: {e}")
        return {}

def load_dualshock_config(file_path):
    """Load dualshock configuration from a JSON file."""
    try:
        with open(file_path, "r") as f:
            ds_config = json.load(f)
        print("DualShock config loaded successfully.")
        return ds_config
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading dualshock config from {file_path}: {e}")
        return {}

def load_keyboard_config(file_path):
    """Load keyboard configuration from a JSON file."""
    try:
        with open(file_path, "r") as f:
            kb_config = json.load(f)
        print("Keyboard config loaded successfully.")
        return kb_config
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading keyboard config from {file_path}: {e}")
        return {}

def load_temperature_config(file_path):
    """Load temperature configuration from a JSON file."""
    try:
        with open(file_path, "r") as f:
            temp_config = json.load(f)
        print("Temperature config loaded successfully.")
        return temp_config
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading temperature config from {file_path}: {e}")
        return {"thresholds": {"warm": 65, "hot": 80}} # Safe defaults

def load_llm_config(file_path):
    """Load LLM dialogue configuration from a JSON file."""
    defaults = {
        "model": "claude-haiku-4-5",
        "system_prompt": "You are Pepper, a humanoid robot. Keep replies brief and conversational.",
        "max_tokens": 256,
        "temperature": 0.7,
        "history_turns": 10,
    }
    try:
        with open(file_path, "r") as f:
            llm_config = json.load(f)
        print("LLM config loaded successfully.")
        return llm_config
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading LLM config from {file_path}: {e}")
        return defaults

def load_stt_config(file_path):
    """Loads speech-to-text configuration from a JSON file."""
    defaults = {
        "zmq_address": "tcp://localhost:5562",
        "review_mode": True,
        "model_size": "base.en",
        "sample_rate": 16000,
        "push_to_talk_key": "space",
    }
    try:
        with open(file_path, "r") as f:
            stt_config = json.load(f)
        print("STT config loaded successfully.")
        return stt_config
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading STT config from {file_path}: {e}")
        return defaults

class Config:
    """A class to hold the application configuration."""
    def __init__(self):
        self.animations = load_animations(CONFIG_DIR / "animations.json")
        self.quick_responses = load_quick_responses(CONFIG_DIR / "quick_responses.json")
        self.emoticon_map = load_emoticon_map(CONFIG_DIR / "emoticon_map.json")
        self.teleop_config = load_teleop_config(CONFIG_DIR / "teleop.json")
        self.dualshock_config = load_dualshock_config(CONFIG_DIR / "dualshock.json")
        self.keyboard_config = load_keyboard_config(CONFIG_DIR / "keyboard.json")
        self.temperature_config = load_temperature_config(CONFIG_DIR / "temperature.json")
        self.stt_config = load_stt_config(CONFIG_DIR / "stt.json")
        self.llm_config = load_llm_config(CONFIG_DIR / "llm.json")

def load_config():
    """Load all configurations."""
    return Config()