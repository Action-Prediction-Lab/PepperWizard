import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pepper_wizard.probe import detect
from pepper_wizard.probe.models import DetectorResult
from pepper_wizard.probe.profile import Profile


def _cp(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def _subprocess_router(table):
    """Build a subprocess.run side-effect fn from {command_name: CompletedProcess | Exception}."""
    def side_effect(cmd, *args, **kwargs):
        key = cmd[0] if isinstance(cmd, (list, tuple)) else cmd
        if key in table:
            value = table[key]
            if isinstance(value, Exception):
                raise value
            return value
        raise FileNotFoundError(f"mocked: {key} not found")
    return side_effect


class TestDetectGpu(unittest.TestCase):
    def test_nvidia_present(self):
        table = {"nvidia-smi": _cp(stdout="RTX 4090, 24576 MiB, 550.54\n")}
        with mock.patch.object(subprocess, "run", side_effect=_subprocess_router(table)):
            r = detect.detect_gpu()
        self.assertEqual(r.value, "nvidia-cuda")
        self.assertIn("RTX 4090", r.detail)

    def test_amd_rocm_present(self):
        table = {
            "nvidia-smi": FileNotFoundError(),
            "rocm-smi": _cp(stdout="GPU[0]: AMD Radeon RX 7900\n"),
        }
        with mock.patch.object(subprocess, "run", side_effect=_subprocess_router(table)):
            r = detect.detect_gpu()
        self.assertEqual(r.value, "amd-rocm")

    def test_lspci_shows_gpu_but_no_cuda(self):
        table = {
            "nvidia-smi": FileNotFoundError(),
            "rocm-smi": FileNotFoundError(),
            "lspci": _cp(stdout="01:00.0 VGA compatible controller: AMD Radeon R7 370\n"),
        }
        with mock.patch.object(subprocess, "run", side_effect=_subprocess_router(table)):
            r = detect.detect_gpu()
        self.assertEqual(r.value, "cpu-only")
        self.assertIn("R7 370", r.detail)

    def test_nothing_detected(self):
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError()):
            r = detect.detect_gpu()
        self.assertEqual(r.value, "cpu-only")


class TestDetectRobot(unittest.TestCase):
    def test_missing_config(self):
        with mock.patch.object(Path, "exists", return_value=False):
            r = detect.detect_robot(robot_env_path="/nonexistent/robot.env")
        self.assertEqual(r.value, "missing-config")

    def test_reachable(self):
        # Bind an ephemeral local TCP port so connect() succeeds
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        try:
            r = detect.detect_robot(ip="127.0.0.1", port=port, timeout=1.0)
        finally:
            server.close()
        self.assertEqual(r.value, "reachable")

    def test_unreachable(self):
        # Port 1 is almost certainly closed
        r = detect.detect_robot(ip="127.0.0.1", port=1, timeout=0.1)
        self.assertEqual(r.value, "unreachable")


class TestDetectController(unittest.TestCase):
    def test_none(self):
        with mock.patch.object(Path, "exists", return_value=False), \
             mock.patch.object(Path, "glob", return_value=iter([])):
            r = detect.detect_controller()
        self.assertEqual(r.value, "none")


class TestDetectCpuTier(unittest.TestCase):
    def test_this_machine_classifies_low(self):
        # On the real box, we expect this to be "low" (no AVX2 on FX-4350).
        # Mock /proc/cpuinfo to a fixed no-AVX2 content to make the test
        # deterministic regardless of host.
        def fake_read_text(self):
            if self.name == "meminfo":
                return "MemTotal:       15728640 kB\n"
            if self.name == "cpuinfo":
                return "flags\t\t: fpu vme de pse tsc\n"
            raise FileNotFoundError(self)

        with mock.patch.object(os, "cpu_count", return_value=4), \
             mock.patch.object(Path, "exists", return_value=True), \
             mock.patch.object(Path, "read_text", fake_read_text):
            r = detect.detect_cpu_tier()
        self.assertEqual(r.value, "low")

    def test_high_tier(self):
        def fake_read_text(self):
            if self.name == "meminfo":
                return "MemTotal:       33554432 kB\n"
            if self.name == "cpuinfo":
                return "flags\t\t: fpu avx avx2 bmi1 bmi2\n"
            raise FileNotFoundError(self)

        with mock.patch.object(os, "cpu_count", return_value=16), \
             mock.patch.object(Path, "exists", return_value=True), \
             mock.patch.object(Path, "read_text", fake_read_text):
            r = detect.detect_cpu_tier()
        self.assertEqual(r.value, "high")


class TestDetectAudio(unittest.TestCase):
    def test_no_audio(self):
        with mock.patch.object(Path, "exists", return_value=False), \
             mock.patch.object(Path, "is_socket", return_value=False), \
             mock.patch.object(subprocess, "run", side_effect=FileNotFoundError()):
            r = detect.detect_audio()
        self.assertEqual(r.value, "none")


def _r(value):
    return DetectorResult(value=value, detail="", raw={})


class TestProfileRecommend(unittest.TestCase):
    def _profile(self, gpu, robot, controller, cpu, audio):
        return Profile(
            gpu=_r(gpu), robot=_r(robot), controller=_r(controller),
            cpu_tier=_r(cpu), audio=_r(audio),
        )

    def test_this_machine(self):
        p = self._profile("cpu-only", "missing-config", "none", "low", "pulse")
        rec = p.recommend()
        self.assertEqual(rec.stack, "lite")
        self.assertEqual(rec.settings["whisper_model"], "tiny.en")
        self.assertEqual(rec.settings["teleop_default"], "Keyboard")
        self.assertTrue(any("Robot endpoint" in m for m in rec.missing))

    def test_dev_laptop_sim_reachable(self):
        p = self._profile("cpu-only", "reachable", "none", "mid", "pulse")
        rec = p.recommend()
        self.assertEqual(rec.stack, "lite")
        self.assertEqual(rec.settings["whisper_model"], "base.en")
        self.assertEqual(rec.settings["teleop_default"], "Keyboard")
        self.assertEqual(rec.missing, [])

    def test_lab_workstation(self):
        p = self._profile("nvidia-cuda", "reachable", "dualshock", "high", "pulse")
        rec = p.recommend()
        self.assertEqual(rec.stack, "full")
        self.assertEqual(rec.settings["whisper_model"], "small.en")
        self.assertEqual(rec.settings["teleop_default"], "Joystick")
        self.assertEqual(rec.missing, [])

    def test_no_audio_flagged(self):
        p = self._profile("cpu-only", "reachable", "none", "mid", "none")
        rec = p.recommend()
        self.assertTrue(any("audio" in m.lower() for m in rec.missing))

    def test_recommend_includes_whisper_device_cuda_when_nvidia_cuda(self):
        p = self._profile("nvidia-cuda", "reachable", "dualshock", "mid", "pulse")
        rec = p.recommend()
        self.assertEqual(rec.settings["whisper_device"], "cuda")

    def test_recommend_includes_whisper_device_cpu_when_no_gpu(self):
        p = self._profile("none", "reachable", "keyboard-only", "mid", "pulse")
        rec = p.recommend()
        self.assertEqual(rec.settings["whisper_device"], "cpu")


class TestFormatReport(unittest.TestCase):
    def _profile(self, gpu, robot, controller, cpu, audio):
        return Profile(
            gpu=_r(gpu), robot=_r(robot), controller=_r(controller),
            cpu_tier=_r(cpu), audio=_r(audio),
        )

    def test_report_shows_whisper_device(self):
        from pepper_wizard.probe.cli import format_report
        p = self._profile("nvidia-cuda", "reachable", "dualshock", "mid", "pulse")
        report = format_report(p)
        self.assertIn("Whisper device", report)
        self.assertIn("cuda", report)

    def test_report_shows_gpu_compose_hint_when_cuda(self):
        from pepper_wizard.probe.cli import format_report
        p = self._profile("nvidia-cuda", "reachable", "dualshock", "mid", "pulse")
        report = format_report(p)
        self.assertIn("docker-compose.gpu.yml", report)

    def test_report_omits_gpu_hint_when_no_gpu(self):
        from pepper_wizard.probe.cli import format_report
        p = self._profile("none", "reachable", "keyboard-only", "mid", "pulse")
        report = format_report(p)
        self.assertNotIn("docker-compose.gpu.yml", report)


if __name__ == "__main__":
    unittest.main()
