"""Unit tests for the thread-safe JSONL sidecar writer."""
import json
import os
import tempfile
import threading
import time
import unittest

from pepper_wizard.recording.sidecar import SidecarWriter


class TestSidecarWriter(unittest.TestCase):
    def setUp(self):
        self.fd, self.path = tempfile.mkstemp(suffix=".jsonl")
        os.close(self.fd)

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def _read_lines(self):
        with open(self.path, "r") as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_writes_header_and_records(self):
        w = SidecarWriter(self.path)
        w.write_header({"version": 1, "session_id": "X"})
        w.write({"type": "video", "ingest_utc_ns": 1, "frame_index": 0})
        w.write({"type": "video", "ingest_utc_ns": 2, "frame_index": 1})
        w.close()

        lines = self._read_lines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0]["type"], "header")
        self.assertEqual(lines[0]["version"], 1)
        self.assertEqual(lines[0]["session_id"], "X")
        self.assertEqual(lines[1]["type"], "video")
        self.assertEqual(lines[2]["frame_index"], 1)

    def test_concurrent_writes_no_torn_lines(self):
        """Many threads write simultaneously; every line must be valid JSON."""
        w = SidecarWriter(self.path)
        w.write_header({"version": 1})
        N = 8
        per_thread = 200
        barrier = threading.Barrier(N)

        def worker(tid):
            barrier.wait()
            for i in range(per_thread):
                w.write({"type": "video", "ingest_utc_ns": time.time_ns(),
                         "tid": tid, "i": i})

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        w.close()

        lines = self._read_lines()
        self.assertEqual(len(lines), 1 + N * per_thread)

    def test_close_is_idempotent(self):
        w = SidecarWriter(self.path)
        w.write_header({"version": 1})
        w.close()
        w.close()


if __name__ == "__main__":
    unittest.main()
