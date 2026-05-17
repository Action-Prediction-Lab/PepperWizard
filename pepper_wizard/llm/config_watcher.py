import json
from pathlib import Path
from typing import Callable, Optional

from ..logger import get_logger
from .client import LLMUnavailable

_logger = get_logger("pepper_wizard.llm.config_watcher")

OnChange = Callable[[dict, dict], None]


class LLMConfigWatcher:
    """File-backed config source that re-reads `llm.json` on mtime change.

    Designed for hot-swapping the LLM dialogue config mid-session. The watcher
    is the only thing that touches the filesystem; consumers call `current()`
    each turn and treat the returned dict as authoritative for that turn.
    """

    def __init__(self, path: Path, on_change: Optional[OnChange] = None):
        self._path = Path(path)
        self._on_change = on_change
        try:
            stat = self._path.stat()
            with self._path.open() as f:
                self._cached = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise LLMUnavailable(
                f"Could not load LLM config from {self._path}: {exc}"
            ) from exc
        self._mtime_ns = stat.st_mtime_ns

    def current(self) -> dict:
        """Return the current config, re-reading from disk if the file changed."""
        try:
            stat = self._path.stat()
        except OSError as exc:
            _logger.warning("Could not stat %s: %s", self._path, exc)
            return self._cached

        if stat.st_mtime_ns == self._mtime_ns:
            return self._cached

        try:
            with self._path.open() as f:
                new_cfg = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning("Could not reload %s: %s", self._path, exc)
            return self._cached

        old_cfg = self._cached
        self._cached = new_cfg
        self._mtime_ns = stat.st_mtime_ns

        if self._on_change is not None:
            try:
                self._on_change(old_cfg, new_cfg)
            except Exception as exc:
                _logger.warning("on_change callback raised: %s", exc)

        return new_cfg
