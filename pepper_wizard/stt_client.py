"""
STT Client — ZMQ REQ client for communicating with the STT service.
"""

import zmq


class STTClient:
    """Thin wrapper around the ZMQ REQ socket to the STT service."""

    def __init__(self, zmq_address: str, timeout_ms: int = 30000):
        """
        Args:
            zmq_address: ZMQ address of the STT service (e.g. tcp://localhost:5562).
            timeout_ms: Receive timeout in milliseconds (default 30s for transcription).
        """
        self.zmq_address = zmq_address
        self.timeout_ms = timeout_ms
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.socket.setsockopt(zmq.SNDTIMEO, 5000)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.connect(zmq_address)
        self._connected = False

    def ping(self) -> bool:
        """Check if the STT service is reachable."""
        try:
            self.socket.send_json({"action": "ping"})
            reply = self.socket.recv_json()
            self._connected = reply.get("status") == "ok"
            return self._connected
        except zmq.ZMQError:
            self._connected = False
            return False

    def start_recording(self) -> bool:
        """
        Send start command to the STT service.
        Returns True if the service acknowledged and is recording.
        """
        try:
            self.socket.send_json({"action": "start"})
            reply = self.socket.recv_json()
            return reply.get("status") == "recording"
        except zmq.ZMQError as e:
            print(f"[STTClient] Start error: {e}")
            return False

    def stop_and_transcribe(self) -> dict:
        """
        Send stop command and wait for the transcription.

        Returns:
            dict with keys:
                - 'transcription' (str): The transcribed text.
                - 'duration' (float): Duration of recording in seconds.
                - 'error' (str, optional): Error message if any.
        """
        try:
            self.socket.send_json({"action": "stop"})
            reply = self.socket.recv_json()
            return reply
        except zmq.ZMQError as e:
            print(f"[STTClient] Stop/transcribe error: {e}")
            return {"transcription": "", "error": str(e)}

    def enable_streaming(self) -> bool:
        """
        Send enable_streaming action to the STT service.
        Returns True if streaming is enabled.
        """
        return self._simple_action("enable_streaming", expected_status="streaming")

    def disable_streaming(self) -> bool:
        """
        Send disable_streaming action to the STT service.
        Returns True if streaming is disabled.
        """
        return self._simple_action("disable_streaming", expected_status="idle")

    def mute(self) -> bool:
        """
        Send mute action to the STT service.
        Returns True if mute was successful.
        """
        return self._simple_action("mute", expected_status="muted")

    def unmute(self) -> bool:
        """
        Send unmute action to the STT service.
        Returns True if unmute was successful.
        """
        return self._simple_action("unmute", expected_status="unmuted")

    def _simple_action(self, action: str, expected_status: str) -> bool:
        """
        Generic action sender for simple status-check actions.

        Args:
            action: Action name to send.
            expected_status: Expected status value in the reply.

        Returns:
            True if the reply status matches expected_status, False otherwise.
        """
        try:
            self.socket.send_json({"action": action})
            reply = self.socket.recv_json()
            return reply.get("status") == expected_status
        except zmq.ZMQError as e:
            print(f"[STTClient] {action} error: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def close(self):
        """Close ZMQ socket and context."""
        self.socket.close()
        self.context.term()
