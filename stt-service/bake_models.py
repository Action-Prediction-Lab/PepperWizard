"""Build-time entry point that pre-populates ${HF_HOME} with both stt model engine
checkpoints. Reads model names from stt.json and falls back to library
defaults if a key is absent. Intended to run inside the Dockerfile.

Bakes Whisper and Parakeet so the resulting
image carries weights for both at runtime.
"""
import sys

from config_loader import (
    DEFAULT_PARAKEET_MODEL,
    DEFAULT_WHISPER_MODEL,
    _load_config,
    _resolve_whisper_model,
)


def _log(msg: str) -> None:
    # flush=True so Docker buildkit can stream progress in real time.
    print(f"[bake_models] {msg}", flush=True)


def _bake_whisper(model_size: str) -> None:
    _log(f"importing faster_whisper")
    from faster_whisper import WhisperModel
    _log(f"Baking whisper checkpoint: {model_size}")
    WhisperModel(model_size, device="cpu", compute_type="int8")
    _log("whisper bake done")


def _bake_parakeet(model_name: str) -> None:
    _log("importing nemo.collections.asr.models (slow, ~30s)")
    from nemo.collections.asr.models import ASRModel
    _log(f"Baking parakeet checkpoint: {model_name}")
    ASRModel.from_pretrained(model_name)
    _log("parakeet bake done")


def main() -> int:
    if len(sys.argv) < 2:
        print("[bake_models] usage: bake_models.py <path-to-stt.json>",
              file=sys.stderr)
        return 2

    config_path = sys.argv[1]
    config = _load_config(config_path)

    whisper_model = _resolve_whisper_model(config)
    parakeet_model = config.get("parakeet_model", DEFAULT_PARAKEET_MODEL)

    _bake_whisper(whisper_model)
    _bake_parakeet(parakeet_model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
