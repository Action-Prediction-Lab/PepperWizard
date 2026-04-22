"""Event schema for stt-service transcription PUB (:5564)."""
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class UtteranceEvent:
    text: str
    duration_s: float
    t_start: datetime
    t_end: datetime
    source: str  # "robot_mic" | "typed" (the CLI stamps "typed"; stt-service always stamps "robot_mic")


def _iso_z(dt: datetime) -> str:
    # Zulu with milliseconds, matching the spec's example.
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def encode_event(evt: UtteranceEvent) -> str:
    return json.dumps({
        "text": evt.text,
        "duration_s": round(evt.duration_s, 3),
        "t_start": _iso_z(evt.t_start),
        "t_end":   _iso_z(evt.t_end),
        "source":  evt.source,
    })


def encode_error(error: str, detail: str, t_start: datetime) -> str:
    return json.dumps({
        "error":   error,
        "detail":  detail,
        "t_start": _iso_z(t_start),
    })
