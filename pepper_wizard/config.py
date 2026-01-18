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

class Config:
    """A class to hold the application configuration."""
    def __init__(self):
        self.animations = load_animations(CONFIG_DIR / "animations.json")
        self.quick_responses = load_quick_responses(CONFIG_DIR / "quick_responses.json")
        self.emoticon_map = load_emoticon_map(CONFIG_DIR / "emoticon_map.json")

def load_config():
    """Load all configurations."""
    return Config()