"""Engine abstraction for stt-service.

Defines the STTBackend Protocol and WhisperBackend / ParakeetBackend
implementations. make_backend(config) factory selects between
them based on stt.json's `engine` key.
"""
import sys
from typing import Any, Iterable, Protocol, Tuple

import numpy as np
from faster_whisper import WhisperModel

from config_loader import (
    DEFAULT_PARAKEET_MODEL,
    _resolve_whisper_model,
)


class Segment(Protocol):
    text: str


class STTBackend(Protocol):
    def transcribe(
        self,
        audio: np.ndarray,
        beam_size: int = 3,
        language: str = "en",
        vad_filter: bool = False,
    ) -> Tuple[Iterable[Segment], Any]:
        ...


class EngineLoadError(RuntimeError):
    """Raised when the configured engine cannot be loaded.

    Caught at the top of main() to produce a loud, actionable exit.
    """


class WhisperBackend:
    """Wraps faster_whisper.WhisperModel. Delegates transcribe() directly."""

    def __init__(self, model_size: str, device: str = "cpu", compute_type: str = "int8"):
        print(f"[STTService] Loading whisper model '{model_size}' ({device}, {compute_type})...",
              file=sys.stderr)
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        print(f"[STTService] Whisper model loaded.", file=sys.stderr)

    def transcribe(
        self,
        audio: np.ndarray,
        beam_size: int = 3,
        language: str = "en",
        vad_filter: bool = False,
    ) -> Tuple[Iterable[Segment], Any]:
        return self._model.transcribe(
            audio, beam_size=beam_size, language=language, vad_filter=vad_filter,
        )


class ParakeetBackend:
    """Wraps NeMo ASRModel. Lazy-imports nemo inside __init__ so Whisper-only
    deployments don't pay NeMo's import cost.
    """

    def __init__(self, model_name: str, device: str = "cuda"):
        print(f"[STTService] Loading parakeet model '{model_name}' ({device})...",
              file=sys.stderr)
        import nemo.collections.asr  # noqa: F401 
        from nemo.collections.asr.models import ASRModel
        # Stage on CPU then cast to FP16 before moving to GPU. 
        # Params selected for Ada500
        model = ASRModel.from_pretrained(model_name, map_location="cpu")
        if device != "cpu":
            model = model.half().to(device)
        self._model = model
        print(f"[STTService] Parakeet model loaded.", file=sys.stderr)

    def transcribe(
        self,
        audio: np.ndarray,
        beam_size: int = 3,
        language: str = "en",
        vad_filter: bool = False,
    ) -> Tuple[Iterable[Segment], Any]:
        # NeMo expects a list of audio inputs; we batch one item.
        hypotheses = self._model.transcribe([audio])
        text = hypotheses[0].text if hypotheses else ""
        seg = type("Seg", (), {"text": text})()
        return [seg], None


def make_backend(config: dict) -> STTBackend:
    """Select and construct the configured engine.

    Raises EngineLoadError on misconfiguration or precondition failure. Caller
    is expected to print the message and exit non-zero before binding ZMQ.
    """
    engine = config.get("engine", "whisper")

    if engine == "whisper":
        return WhisperBackend(
            model_size=_resolve_whisper_model(config),
            device="cpu",
            compute_type="int8",
        )

    if engine == "parakeet":
        import torch
        if not torch.cuda.is_available():
            raise EngineLoadError(
                "engine: parakeet requires CUDA. "
                "torch.cuda.is_available() returned False. "
                "Fix the nvidia runtime: ensure STT_DOCKER_RUNTIME=nvidia "
                "and STT_GPU_DEVICES=all are set in .env (check `nvidia-smi` "
                "on the host first), or set `engine: whisper` in stt.json."
            )
        return ParakeetBackend(
            model_name=config.get("parakeet_model", DEFAULT_PARAKEET_MODEL),
            device="cuda",
        )

    raise EngineLoadError(
        f"Unknown engine: {engine!r}. Valid values: 'whisper', 'parakeet'."
    )
