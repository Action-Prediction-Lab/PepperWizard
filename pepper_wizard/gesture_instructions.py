"""Asks the experiment for the PepperBox GestureSwitch instructions to put into a reply before Pepper speaks it."""
import math
import time

import zmq


class GestureInstructionsUnavailable(Exception):
    pass


def request_instructions(config: dict, text: str) -> dict:
    """Sends text and a deadline to config["endpoint"] and returns the answer, the text with its instructions and whether to call GestureSwitch.off_now() first; raises GestureInstructionsUnavailable for a config without an endpoint and a timeout_s from 0.001 to 3600 s, or without a usable answer within timeout_s."""
    try:
        endpoint, timeout_s = str(config["endpoint"]), float(config["timeout_s"])
    except (KeyError, TypeError, ValueError):
        raise GestureInstructionsUnavailable(f"gesture_instructions needs endpoint and timeout_s, got {config!r}")
    if not math.isfinite(timeout_s) or not 0.001 <= timeout_s <= 3600:
        raise GestureInstructionsUnavailable(f"gesture_instructions timeout_s must be between 0.001 and 3600 s, got {timeout_s!r}")
    timeout_ms = int(timeout_s * 1000)
    sock = None
    try:
        sock = zmq.Context.instance().socket(zmq.REQ)
        sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
        sock.setsockopt(zmq.SNDTIMEO, timeout_ms)
        sock.setsockopt(zmq.LINGER, 0)
        sock.connect(endpoint)
        sock.send_json({"action": "gesture_instructions", "text": text, "deadline": time.time() + timeout_s})
        answer = sock.recv_json()
    except zmq.Again:
        raise GestureInstructionsUnavailable(f"no answer from {endpoint} within {timeout_s} s")
    except zmq.ZMQError as e:
        raise GestureInstructionsUnavailable(f"cannot ask {endpoint}: {e}")
    except ValueError as e:
        raise GestureInstructionsUnavailable(f"the answer from {endpoint} is not JSON: {e}")
    finally:
        if sock is not None:
            sock.close()
    if not isinstance(answer, dict) or answer.get("status") != "ok":
        raise GestureInstructionsUnavailable(f"the experiment answered {answer!r}")
    if not isinstance(answer.get("text"), str) or not isinstance(answer.get("off_now"), bool):
        raise GestureInstructionsUnavailable(f"the answer lacks text or off_now: {answer!r}")
    return answer
