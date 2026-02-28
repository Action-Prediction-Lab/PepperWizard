"""
Unit tests for STTClient using a mock ZMQ REP server.
"""

import json
import threading
import time

import zmq
import pytest

from pepper_wizard.stt_client import STTClient


# ───────────────────────────────── Helpers ──────────────────────────────────

def _run_mock_stt_server(port, actions_responses, ready_event, stop_event):
    """
    Minimal ZMQ REP server that replies to requests with pre-defined responses.

    Args:
        port: TCP port to bind on.
        actions_responses: dict mapping action names to response dicts.
        ready_event: threading.Event set once the server is bound and ready.
        stop_event: threading.Event — server exits when this is set.
    """
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(f"tcp://*:{port}")
    ready_event.set()

    while not stop_event.is_set():
        if socket.poll(200):
            msg = socket.recv_json()
            action = msg.get("action", "")
            reply = actions_responses.get(action, {"error": f"Unknown: {action}"})
            socket.send_json(reply)

    socket.close()
    context.term()


@pytest.fixture
def mock_stt_service():
    """Fixture that starts a mock STT server and yields (address, stop_fn)."""
    port = 15562  # Use a non-conflicting test port
    actions_responses = {
        "ping": {"status": "ok"},
        "start": {"status": "recording"},
        "stop": {
            "transcription": "Hello world",
            "duration": 1.5,
        },
    }

    ready = threading.Event()
    stop = threading.Event()

    thread = threading.Thread(
        target=_run_mock_stt_server,
        args=(port, actions_responses, ready, stop),
        daemon=True,
    )
    thread.start()
    ready.wait(timeout=5)

    yield f"tcp://localhost:{port}"

    stop.set()
    thread.join(timeout=3)


# ──────────────────────────────── Tests ─────────────────────────────────────

class TestSTTClient:
    def test_ping(self, mock_stt_service):
        client = STTClient(mock_stt_service, timeout_ms=5000)
        assert client.ping() is True
        assert client.is_connected is True
        client.close()

    def test_start_recording(self, mock_stt_service):
        client = STTClient(mock_stt_service, timeout_ms=5000)
        assert client.start_recording() is True
        client.close()

    def test_stop_and_transcribe(self, mock_stt_service):
        client = STTClient(mock_stt_service, timeout_ms=5000)
        client.start_recording()
        result = client.stop_and_transcribe()
        assert result["transcription"] == "Hello world"
        assert result["duration"] == 1.5
        assert "error" not in result
        client.close()

    def test_full_flow(self, mock_stt_service):
        """Simulate a complete ping → start → stop → transcribe flow."""
        client = STTClient(mock_stt_service, timeout_ms=5000)

        assert client.ping() is True
        assert client.start_recording() is True

        result = client.stop_and_transcribe()
        assert result["transcription"] == "Hello world"
        assert isinstance(result["duration"], float)

        client.close()

    def test_timeout_on_unreachable_server(self):
        """Client should handle a downed server gracefully."""
        client = STTClient("tcp://localhost:19999", timeout_ms=1000)
        assert client.ping() is False
        assert client.is_connected is False
        client.close()
