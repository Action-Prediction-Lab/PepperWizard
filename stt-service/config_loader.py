"""Configuration loading and resolution for stt-service.

Shared by main.py at runtime and bake_models.py at image build time.
"""
import json
import sys

from vad_segmenter import VadConfig


DEFAULT_WHISPER_MODEL = "base.en"
DEFAULT_PARAKEET_MODEL = "nvidia/parakeet-tdt-0.6b-v2"

DEFAULT_VAD = {
    "threshold": 0.5,
    "min_silence_ms": 700,
    "min_utterance_ms": 300,
    "max_utterance_ms": 15000,
    "preroll_ms": 200,
}


def _load_config(path: str = "/app/pepper_config/stt.json") -> dict:
    """Read stt.json. Return {} on missing file or malformed JSON."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _resolve_whisper_model(config: dict) -> str:
    """Resolve the Whisper checkpoint, honouring the legacy `model_size` alias."""
    if "whisper_model" in config:
        return config["whisper_model"]
    if "model_size" in config:
        print(
            "[STTService] DEPRECATED: 'model_size' in stt.json is now "
            "'whisper_model'. The old key still works but will be removed "
            "in a future release.",
            file=sys.stderr,
        )
        return config["model_size"]
    return DEFAULT_WHISPER_MODEL


def _load_vad_config(config: dict) -> VadConfig:
    """Build a VadConfig by merging the `vad` sub-dict over DEFAULT_VAD."""
    params = dict(DEFAULT_VAD)
    params.update(config.get("vad", {}))
    return VadConfig(**params)
