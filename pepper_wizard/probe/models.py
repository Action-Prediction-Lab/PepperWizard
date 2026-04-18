from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DetectorResult:
    value: str
    detail: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Recommendation:
    stack: str
    missing: List[str]
    settings: Dict[str, str]
