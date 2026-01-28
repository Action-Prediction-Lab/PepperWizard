from dataclasses import dataclass, field
from typing import Optional, List, Tuple

@dataclass(frozen=True)
class Point:
    x: float
    y: float

@dataclass(frozen=True)
class BBox:
    """Bounding Box in image coordinates."""
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def center(self) -> Point:
        return Point((self.xmin + self.xmax) / 2.0, (self.ymin + self.ymax) / 2.0)

    @property
    def width(self) -> float:
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        return self.ymax - self.ymin

@dataclass(frozen=True)
class Detection:
    """A single tracking detection."""
    label: str
    confidence: float
    bbox: BBox
    timestamp: float
    # Optional raw sensor data at time of capture
    source_angles: Optional[Tuple[float, float]] = None

@dataclass(frozen=True)
class ControlCommand:
    """Unified output from a tracker."""
    type: str  # "position" or "velocity"
    yaw: float
    pitch: float
    speed: Optional[float] = 0.1
    debug_info: dict = field(default_factory=dict)
