import os
import socket
import subprocess
from pathlib import Path
from typing import Optional

from .models import DetectorResult

_SUBPROCESS_TIMEOUT = 2.0
_DEFAULT_ROBOT_CONNECT_TIMEOUT = 0.5


def _run(cmd, timeout=_SUBPROCESS_TIMEOUT):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def detect_gpu() -> DetectorResult:
    raw = {}

    try:
        result = _run([
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ])
        if result.returncode == 0 and result.stdout.strip():
            first = result.stdout.strip().splitlines()[0]
            raw["nvidia-smi"] = first
            return DetectorResult(
                value="nvidia-cuda",
                detail=f"NVIDIA: {first}",
                raw=raw,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        raw["nvidia-smi-err"] = f"{type(e).__name__}: {e}"

    try:
        result = _run(["rocm-smi", "--showproductname"])
        if result.returncode == 0 and result.stdout.strip():
            first = result.stdout.strip().splitlines()[0]
            raw["rocm-smi"] = first
            return DetectorResult(
                value="amd-rocm",
                detail=f"AMD ROCm: {first}",
                raw=raw,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        raw["rocm-smi-err"] = f"{type(e).__name__}: {e}"

    try:
        result = _run(["lspci"])
        if result.returncode == 0:
            matches = [
                line for line in result.stdout.splitlines()
                if any(k in line.lower() for k in ("vga", "3d controller", "display"))
            ]
            if matches:
                raw["lspci"] = matches[:3]
                name = matches[0].split(": ", 1)[-1]
                return DetectorResult(
                    value="cpu-only",
                    detail=f"CPU-only (GPU present but no CUDA/ROCm: {name})",
                    raw=raw,
                )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        raw["lspci-err"] = f"{type(e).__name__}: {e}"

    return DetectorResult(
        value="cpu-only",
        detail="CPU-only (no GPU detected)",
        raw=raw,
    )


def _parse_env_file(path: Path):
    result = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return result


def detect_robot(
    ip: Optional[str] = None,
    port: Optional[int] = None,
    timeout: float = _DEFAULT_ROBOT_CONNECT_TIMEOUT,
    robot_env_path: Optional[str] = None,
) -> DetectorResult:
    raw = {}
    if ip is None or port is None:
        env_path = Path(robot_env_path) if robot_env_path else Path("robot.env")
        raw["robot_env_path"] = str(env_path)
        raw["robot_env_exists"] = env_path.exists()
        if env_path.exists():
            env = _parse_env_file(env_path)
            raw["robot_env"] = env
            ip = ip or env.get("NAOQI_IP")
            port_raw = env.get("NAOQI_PORT")
            if port is None and port_raw and port_raw.isdigit():
                port = int(port_raw)

    if not ip or not port:
        return DetectorResult(
            value="missing-config",
            detail="NAOQI_IP/NAOQI_PORT not set (no robot.env or incomplete)",
            raw=raw,
        )

    raw["target"] = f"{ip}:{port}"
    try:
        sock = socket.create_connection((ip, int(port)), timeout=timeout)
        sock.close()
        return DetectorResult(
            value="reachable",
            detail=f"Reached {ip}:{port}",
            raw=raw,
        )
    except (OSError, socket.timeout) as e:
        return DetectorResult(
            value="unreachable",
            detail=f"{ip}:{port} ({type(e).__name__}: {e})",
            raw=raw,
        )


_SONY_VID = "054c"


def detect_controller() -> DetectorResult:
    raw = {}
    input_dir = Path("/dev/input")
    js_devices = sorted(str(p) for p in input_dir.glob("js*")) if input_dir.exists() else []
    raw["js_devices"] = js_devices

    devices_file = Path("/proc/bus/input/devices")
    has_sony = False
    has_other_joystick = False
    if devices_file.exists():
        try:
            content = devices_file.read_text()
            for block in content.split("\n\n"):
                handlers = ""
                for line in block.splitlines():
                    if line.startswith("H:"):
                        handlers = line
                        break
                is_joystick = "js" in handlers
                if not is_joystick:
                    continue
                if f"Vendor={_SONY_VID}" in block.lower() or f"vendor={_SONY_VID}" in block.lower():
                    has_sony = True
                else:
                    has_other_joystick = True
        except OSError as e:
            raw["proc_read_err"] = f"{type(e).__name__}: {e}"

    if has_sony:
        return DetectorResult(
            value="dualshock",
            detail=f"Sony controller present ({len(js_devices)} js device(s))",
            raw=raw,
        )
    if has_other_joystick or js_devices:
        return DetectorResult(
            value="other",
            detail=f"Non-DualShock controller present ({len(js_devices)} js device(s))",
            raw=raw,
        )
    return DetectorResult(
        value="none",
        detail="No game controller found",
        raw=raw,
    )


def detect_cpu_tier() -> DetectorResult:
    raw = {}
    cores = os.cpu_count() or 1
    raw["cores"] = cores

    mem_total_kb = 0
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            for line in meminfo.read_text().splitlines():
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        mem_total_kb = int(parts[1])
                        break
        except OSError as e:
            raw["meminfo_err"] = f"{type(e).__name__}: {e}"
    mem_gb = mem_total_kb / (1024 * 1024) if mem_total_kb else 0.0
    raw["mem_gb"] = round(mem_gb, 2)

    has_avx2 = False
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        try:
            for line in cpuinfo.read_text().splitlines():
                if line.startswith("flags") or line.startswith("Features"):
                    flags = line.split(":", 1)[-1].split()
                    if "avx2" in flags:
                        has_avx2 = True
                        break
        except OSError as e:
            raw["cpuinfo_err"] = f"{type(e).__name__}: {e}"
    raw["avx2"] = has_avx2

    if cores <= 4 or not has_avx2 or mem_gb < 8:
        tier = "low"
    elif cores <= 8 or mem_gb < 16:
        tier = "mid"
    else:
        tier = "high"

    return DetectorResult(
        value=tier,
        detail=f"{cores} cores, {mem_gb:.1f}G RAM, avx2={'yes' if has_avx2 else 'no'}",
        raw=raw,
    )


def detect_audio() -> DetectorResult:
    raw = {}
    try:
        uid = os.geteuid()
    except AttributeError:
        uid = 0
    pulse_socket = Path(f"/run/user/{uid}/pulse/native")
    pulse_ok = False
    try:
        pulse_ok = pulse_socket.exists() and pulse_socket.is_socket()
    except OSError:
        pass
    raw["pulse_socket"] = {"path": str(pulse_socket), "ok": pulse_ok}

    arecord_devices = []
    try:
        result = _run(["arecord", "-l"])
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("card "):
                    arecord_devices.append(line.strip())
            raw["arecord_devices"] = arecord_devices
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        raw["arecord_err"] = f"{type(e).__name__}: {e}"

    has_capture = bool(arecord_devices)

    if pulse_ok:
        suffix = f" ({len(arecord_devices)} ALSA capture device(s))" if has_capture else ""
        return DetectorResult(
            value="pulse",
            detail=f"PulseAudio/PipeWire socket at {pulse_socket}{suffix}",
            raw=raw,
        )
    if has_capture:
        return DetectorResult(
            value="alsa-only",
            detail=f"No Pulse socket; {len(arecord_devices)} ALSA capture device(s)",
            raw=raw,
        )
    return DetectorResult(
        value="none",
        detail="No audio capture device found",
        raw=raw,
    )
