"""Thread-safe JSONL sidecar writer.

Producer threads call write() / write_header(); a single consumer thread drains
the queue and flushes one JSON object per line. Lines are flushed individually
so the file remains useful even if the process crashes mid-recording.
"""
import json
import queue
import threading


_SENTINEL = object()


class SidecarWriter:
    def __init__(self, file_path):
        self._path = file_path
        self._queue = queue.Queue()
        self._closed = threading.Event()
        self._fh = open(file_path, "w", buffering=1)
        self._consumer = threading.Thread(target=self._drain, daemon=True)
        self._consumer.start()

    def write_header(self, header):
        if self._closed.is_set():
            raise RuntimeError("SidecarWriter is closed")
        record = {"type": "header", **header}
        self._queue.put(record)

    def write(self, record):
        if self._closed.is_set():
            raise RuntimeError("SidecarWriter is closed")
        self._queue.put(record)

    def close(self):
        if self._closed.is_set():
            return
        self._closed.set()
        self._queue.put(_SENTINEL)
        self._consumer.join(timeout=5.0)
        try:
            self._fh.close()
        except Exception:
            pass

    def _drain(self):
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            try:
                line = json.dumps(item, separators=(",", ":"))
                self._fh.write(line + "\n")
            except Exception as e:
                self._fh.write(json.dumps({"type": "error", "msg": str(e)}) + "\n")
