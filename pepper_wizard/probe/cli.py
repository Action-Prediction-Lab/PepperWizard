import argparse
import json
import sys
from typing import Optional, Sequence

from .profile import Profile


def format_report(profile: Profile) -> str:
    rec = profile.recommend()
    width = 14
    lines = [
        "PepperWizard Host Probe",
        "",
        f"  GPU          : {profile.gpu.value:<{width}} {profile.gpu.detail}",
        f"  Robot        : {profile.robot.value:<{width}} {profile.robot.detail}",
        f"  Controller   : {profile.controller.value:<{width}} {profile.controller.detail}",
        f"  CPU tier     : {profile.cpu_tier.value:<{width}} {profile.cpu_tier.detail}",
        f"  Audio        : {profile.audio.value:<{width}} {profile.audio.detail}",
        "",
        f"Recommended stack: {rec.stack}",
        f"  Whisper model  : {rec.settings['whisper_model']}",
        f"  Whisper device : {rec.settings['whisper_device']}",
        f"  Teleop default : {rec.settings['teleop_default']}",
    ]
    if rec.settings.get("whisper_device") == "cuda":
        lines.append("")
        lines.append("Suggested: add COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml to .env to enable GPU STT.")
    if rec.missing:
        lines.append("")
        lines.append("Missing prerequisites:")
        for item in rec.missing:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pepper_wizard.probe",
        description="Inspect this host and recommend a PepperWizard stack profile.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit the profile and recommendation as JSON.",
    )
    parser.add_argument(
        "--robot-env", type=str, default=None,
        help="Path to robot.env (default: ./robot.env if present).",
    )
    args = parser.parse_args(argv)

    profile = Profile.probe(robot_env_path=args.robot_env)

    if args.json:
        rec = profile.recommend()
        print(json.dumps({
            "profile": profile.to_dict(),
            "recommendation": {
                "stack": rec.stack,
                "missing": rec.missing,
                "settings": rec.settings,
            },
        }, indent=2))
    else:
        print(format_report(profile))
    return 0


if __name__ == "__main__":
    sys.exit(main())
