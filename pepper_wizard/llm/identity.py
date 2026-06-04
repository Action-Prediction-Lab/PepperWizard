"""Source-agnostic identity for an LLM dialogue config.

The identifier is a short content hash of the *resolved* config (the behavioural
fields actually sent to the model), so a turn can be attributed to its config
regardless of where the prompt came from: llm.json, a default, or a future
orchestrator. `name` is a human label, kept out of the hash so renaming a persona
does not change its behavioural fingerprint while editing a prompt does.
"""

import hashlib
import json
from typing import List, Optional

_DEFAULTS = {
    "model": "claude-haiku-4-5",
    "system_prompt": "You are Pepper, a humanoid robot. Keep replies brief and conversational.",
    "max_tokens": 256,
    "temperature": 0.7,
    "history_turns": 10,
}

# Fields that define model behaviour, and therefore the identity.
_BEHAVIOURAL_KEYS = ("model", "system_prompt", "max_tokens", "temperature", "history_turns")


def resolve_config(raw: dict) -> dict:
    """Apply defaults, returning only the behavioural fields the model sees."""
    return {key: raw.get(key, _DEFAULTS[key]) for key in _BEHAVIOURAL_KEYS}


def config_fingerprint(config: dict) -> str:
    """Short deterministic identity hash of a config.

    Resolves defaults first, so the hash always reflects what the model
    receives whether a raw or already-resolved dict is passed (resolve_config
    is idempotent). This removes any raw-vs-resolved mis-attribution surface.
    """
    resolved = resolve_config(config)
    canonical = json.dumps(resolved, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def build_config_snapshot(raw: dict, reason: str, *, source: str = "file", changed: Optional[List[str]] = None) -> dict:
    """Assemble an LLMConfigSnapshot data dict from a raw config dict."""
    resolved = resolve_config(raw)
    snapshot = {
        "config_hash": config_fingerprint(resolved),
        "config_name": raw.get("name"),
        "config_source": source,
        "reason": reason,
        "config": resolved,
    }
    if changed is not None:
        snapshot["changed"] = changed
    return snapshot
