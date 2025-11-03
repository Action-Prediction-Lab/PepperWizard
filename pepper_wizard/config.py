# Configuration loading (animations, etc.)
import json

def load_animations(file_path="animations.json"):
    """Load animations from a JSON file."""
    try:
        with open(file_path, "r") as f:
            animations = json.load(f)
        print("Animations loaded successfully.")
        return animations
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading animations from {file_path}: {e}")
        return {}

def load_quick_responses(file_path="quick_responses.json"):
    """Load quick responses from a JSON file."""
    try:
        with open(file_path, "r") as f:
            responses = json.load(f)
        print("Quick responses loaded successfully.")
        return responses
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading quick responses from {file_path}: {e}")
        return {}

class Config:
    """A class to hold the application configuration."""
    def __init__(self, animations_path="animations.json", quick_responses_path="quick_responses.json"):
        self.animations = load_animations(animations_path)
        self.quick_responses = load_quick_responses(quick_responses_path)

def load_config():
    """Load all configurations."""
    return Config()