"""Robot↔wizard clock-sync probe.

Sends N HTTP round-trips to a /time endpoint on the PepperBox shim.
Each round-trip records (t_send, t_recv, t_server) on the wizard wall-clock.
The minimum round-trip half-time is taken as the one-way latency estimate;
the offset is then inferred so that adding it to a robot timestamp yields
wall-clock UTC.

If no robot-side endpoint exists / probe fails, returns None.
"""
import json
import time
import urllib.error
import urllib.request


def probe_clock_sync(url, samples=10, timeout_s=2.0):
    """Probe the given /time URL N times; return a dict with offset estimate or None.

    Returns:
        {"robot_offset_ns": int, "min_rtt_ns": int, "samples": int}
        such that wizard_utc_ns ≈ robot_clock_ns + robot_offset_ns
        OR None if every attempt failed.
    """
    successes = []
    for _ in range(samples):
        t_send = time.time_ns()
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as resp:
                body = resp.read()
        except (urllib.error.URLError, OSError, TimeoutError):
            continue
        t_recv = time.time_ns()
        try:
            payload = json.loads(body)
            t_server = int(payload["now_ns"])
        except (ValueError, KeyError, TypeError):
            continue
        successes.append((t_send, t_recv, t_server))

    if not successes:
        return None

    successes.sort(key=lambda x: x[1] - x[0])
    t_send, t_recv, t_server = successes[0]
    min_rtt_ns = t_recv - t_send
    one_way_ns = min_rtt_ns // 2
    expected_wizard_ns_at_server = t_send + one_way_ns
    robot_offset_ns = expected_wizard_ns_at_server - t_server

    return {
        "robot_offset_ns": int(robot_offset_ns),
        "min_rtt_ns": int(min_rtt_ns),
        "samples": len(successes),
    }
