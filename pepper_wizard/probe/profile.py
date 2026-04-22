from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from . import detect
from .models import DetectorResult, Recommendation


_WHISPER_BY_TIER = {"low": "tiny.en", "mid": "base.en", "high": "small.en"}


@dataclass
class Profile:
    gpu: DetectorResult
    robot: DetectorResult
    controller: DetectorResult
    cpu_tier: DetectorResult
    audio: DetectorResult

    @classmethod
    def probe(cls, robot_env_path: Optional[str] = None) -> "Profile":
        return cls(
            gpu=detect.detect_gpu(),
            robot=detect.detect_robot(robot_env_path=robot_env_path),
            controller=detect.detect_controller(),
            cpu_tier=detect.detect_cpu_tier(),
            audio=detect.detect_audio(),
        )

    def recommend(self) -> Recommendation:
        missing = []
        if self.robot.value == "missing-config":
            missing.append("Robot endpoint not configured — set NAOQI_IP/NAOQI_PORT in robot.env")
        elif self.robot.value == "unreachable":
            missing.append(f"Robot unreachable — {self.robot.detail}")
        if self.audio.value == "none":
            missing.append("No audio capture device — STT will not work")

        if self.gpu.value == "nvidia-cuda" and self.controller.value == "dualshock":
            stack = "full"
        else:
            stack = "lite"

        whisper_model = _WHISPER_BY_TIER.get(self.cpu_tier.value, "tiny.en")
        teleop_default = "Joystick" if self.controller.value == "dualshock" else "Keyboard"

        return Recommendation(
            stack=stack,
            missing=missing,
            settings={
                "whisper_model": whisper_model,
                "teleop_default": teleop_default,
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gpu": asdict(self.gpu),
            "robot": asdict(self.robot),
            "controller": asdict(self.controller),
            "cpu_tier": asdict(self.cpu_tier),
            "audio": asdict(self.audio),
        }
