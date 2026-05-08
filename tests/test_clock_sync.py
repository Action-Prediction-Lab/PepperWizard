"""Unit tests for the clock-sync probe.

A mock HTTP server with controlled artificial delay simulates the PepperBox
shim. The probe should estimate the offset within the controlled tolerance.
"""
import http.server
import json
import socketserver
import threading
import time
import unittest

from pepper_wizard.recording.clock_sync import probe_clock_sync


class _FakeShimHandler(http.server.BaseHTTPRequestHandler):
    SERVER_OFFSET_NS = 0
    INJECTED_DELAY_S = 0.005

    def log_message(self, *args, **kwargs):
        pass

    def do_GET(self):
        if self.path != "/time":
            self.send_error(404)
            return
        time.sleep(self.INJECTED_DELAY_S)
        body = json.dumps({
            "now_ns": time.time_ns() + self.SERVER_OFFSET_NS,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _FakeShim:
    def __init__(self, offset_ns=0, delay_s=0.005):
        _FakeShimHandler.SERVER_OFFSET_NS = offset_ns
        _FakeShimHandler.INJECTED_DELAY_S = delay_s
        self._server = socketserver.TCPServer(("127.0.0.1", 0), _FakeShimHandler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()


class TestClockSyncProbe(unittest.TestCase):
    def test_zero_offset(self):
        shim = _FakeShim(offset_ns=0, delay_s=0.005)
        try:
            result = probe_clock_sync(f"http://127.0.0.1:{shim.port}/time", samples=8)
        finally:
            shim.stop()
        self.assertIsNotNone(result)
        self.assertEqual(result["samples"], 8)
        self.assertLess(abs(result["robot_offset_ns"]), 5_000_000)

    def test_positive_offset(self):
        # Server clock runs `injected` ahead of wizard. By the spec convention
        # wizard_utc_ns ≈ robot_clock_ns + robot_offset_ns, the estimate must
        # therefore be ≈ -injected (subtract the server-ahead bias to recover wizard).
        injected = 50_000_000
        shim = _FakeShim(offset_ns=injected, delay_s=0.002)
        try:
            result = probe_clock_sync(f"http://127.0.0.1:{shim.port}/time", samples=10)
        finally:
            shim.stop()
        self.assertLess(abs(result["robot_offset_ns"] + injected), 10_000_000)

    def test_unreachable_endpoint_returns_none(self):
        result = probe_clock_sync("http://127.0.0.1:1/time", samples=3, timeout_s=0.2)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
