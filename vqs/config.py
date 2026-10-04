"""Project configuration (vqs.json): profiles, states, oracles, permissions.

``load_config`` reads an explicit path, a ``vqs.json`` in the current
directory, or falls back to defaults when no file exists — a missing
file is never an error. Present-but-malformed files yield issues and
the safe defaults, never a crash and never silently-ignored content:
callers surface the issues as blocked reasons.

Schema ``vqs.config/1`` keys (unknown top-level keys are rejected):

- ``design_profile``: opaque dict recorded into review provenance so
  later lanes can resolve thresholds; the current rules do not consume
  it and it is never silently applied.
- ``supported_states``: saved-state names a review may target
  (default ``["default"]``).
- ``questions``/``oracles``: lists appended to review facts; base
  pipeline oracles validate their own entries.
- ``recipes``: opaque dict of repair recipe allowlists, recorded only
  (the repair engine of Task 6 consumes it).
- ``data_permissions``: ``allow_cloud``/``allow_desktop`` booleans
  (default False); review scopes requiring them block otherwise.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "vqs.config/1"

_KNOWN_KEYS = frozenset({
    "schema_version", "design_profile", "supported_states", "questions",
    "oracles", "recipes", "data_permissions",
})


def default_config() -> dict[str, Any]:
    """Safe defaults used when no vqs.json exists."""
    return {"schema_version": SCHEMA_VERSION,
            "design_profile": {},
            "supported_states": ["default"],
            "questions": [],
            "oracles": [],
            "recipes": {},
            "data_permissions": {"allow_cloud": False,
                                 "allow_desktop": False}}


def _issues_for(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["config document is not an object"]
    issues = []
    for key in sorted(data):
        if key not in _KNOWN_KEYS:
            issues.append(f"unknown config key: {key}")
    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        issues.append(f"unsupported schema_version: {version!r}")
    for key in ("design_profile", "recipes"):
        if key in data and not isinstance(data[key], dict):
            issues.append(f"{key} must be an object")
    states = data.get("supported_states", ["default"])
    if (not isinstance(states, list) or not states
            or not all(isinstance(s, str) and s for s in states)):
        issues.append("supported_states must be a non-empty string list")
    for key in ("questions", "oracles"):
        if key in data and not isinstance(data[key], list):
            issues.append(f"{key} must be a list")
    permissions = data.get("data_permissions", {})
    if not isinstance(permissions, dict):
        issues.append("data_permissions must be an object")
    else:
        for key in ("allow_cloud", "allow_desktop"):
            if key in permissions and not isinstance(permissions[key], bool):
                issues.append(f"data_permissions.{key} must be a boolean")
    return issues


def load_config(path: str | Path | None = None) -> tuple[dict[str, Any],
                                                         list[str]]:
    """Load vqs.json; (config, issues). Missing file -> defaults, no issues."""
    candidate = Path(path) if path is not None else Path.cwd() / "vqs.json"
    if path is None and not candidate.is_file():
        return default_config(), []
    try:
        data = json.loads(candidate.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return default_config(), [f"unreadable config: {exc}"]
    except ValueError as exc:
        return default_config(), [f"invalid config JSON: {exc}"]
    issues = _issues_for(data)
    if issues:
        return default_config(), issues
    merged = default_config()
    merged.update({k: v for k, v in data.items() if k in _KNOWN_KEYS})
    permissions = dict(merged["data_permissions"])
    permissions.update(data.get("data_permissions", {}))
    merged["data_permissions"] = permissions
    return merged, []
