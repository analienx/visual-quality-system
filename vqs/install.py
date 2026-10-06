"""Installation identity: which VQS code is running, never a setup step.

Reports the installed distribution version, the imported package
root, known engine/tool schema versions, and a best-effort git SHA.
An installed distribution that resolves ``vqs`` to different code
than the running import (including a stale editable install pointing
at another checkout) is reported stale with both paths. Read-only:
nothing here installs, downloads, patches, or modifies anything —
staleness is reported, never repaired.
"""
from __future__ import annotations

import json
import os
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DISTRIBUTION = "visual-quality-system"

# (report key, module, attribute) for engine/tool schema versions.
_SCHEMA_SOURCES = (
    ("config", "vqs.config", "SCHEMA_VERSION"),
    ("tool", "vqs.pipeline", "TOOL_SCHEMA_VERSION"),
    ("plan", "vqs.repair.synthesize", "PLAN_SCHEMA_VERSION"),
    ("reviewer", "vqs.review.port", "REVIEWER_VERSION"),
    ("policy", "vqs.policy", "POLICY_VERSION"),
    ("ledger", "vqs.ledger", "SCHEMA_VERSION"),
    ("contracts", "vqs.contracts.types", "SCHEMA_VERSION"),
    ("mcp_protocol", "vqs.mcp.server", "PROTOCOL_VERSION"),
)


def package_version() -> str | None:
    """Installed distribution version; None when not installed."""
    try:
        return metadata.version(DISTRIBUTION)
    except Exception:  # noqa: BLE001 - absence is a reportable state
        return None


def schema_versions() -> dict[str, str]:
    """Known engine/tool schema versions; unknown when unimportable."""
    import importlib

    versions: dict[str, str] = {}
    for key, module, attribute in _SCHEMA_SOURCES:
        try:
            versions[key] = str(getattr(
                importlib.import_module(module), attribute))
        except Exception:  # noqa: BLE001 - unknown is reportable
            versions[key] = "unknown"
    return versions


def git_sha(start: str | Path | None = None) -> str | None:
    """Best-effort HEAD SHA of the checkout containing the code."""
    root = Path(start) if start else Path(__file__).resolve().parent
    for _ in range(5):
        if (root / ".git").exists():
            break
        if root.parent == root:
            return None
        root = root.parent
    else:
        return None
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            timeout=10, check=False, cwd=str(root))
    except (OSError, subprocess.SubprocessError):
        return None
    sha = completed.stdout.strip()
    return sha if completed.returncode == 0 and sha else None


def _direct_url(dist: Any) -> dict[str, Any]:
    """PEP 610 direct-URL metadata; {} when absent or unreadable."""
    try:
        text = dist.read_text("direct_url.json")
    except Exception:  # noqa: BLE001 - absence is reportable
        return {}
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def installation_report() -> dict[str, Any]:
    """Describe the running install; stale editables are flagged, not fixed."""
    import_root = str(Path(__file__).resolve().parent)
    report: dict[str, Any] = {
        "distribution": DISTRIBUTION, "installed": False,
        "version": None, "import_root": import_root,
        "install_location": None, "editable": False,
        "project_dir": None, "stale": False, "stale_reason": None,
        "git_sha": git_sha(import_root), "schemas": schema_versions(),
        "note": ("read-only: VQS reports install identity here and "
                 "never modifies installs"),
    }
    try:
        dist = metadata.distribution(DISTRIBUTION)
    except Exception:  # noqa: BLE001 - source runs are reportable
        report["note"] += "; no installed distribution found"
        return report
    report["installed"] = True
    try:
        report["version"] = dist.version
    except Exception:  # noqa: BLE001 - partial metadata is reportable
        report["version"] = None
    try:
        report["install_location"] = str(dist.locate_file(""))
    except Exception:  # noqa: BLE001 - partial metadata is reportable
        report["install_location"] = None
    direct = _direct_url(dist)
    report["editable"] = bool(isinstance(direct.get("dir_info"), dict)
                              and direct["dir_info"].get("editable", False))
    url = direct.get("url", "")
    if isinstance(url, str) and url.startswith("file://"):
        try:
            report["project_dir"] = urlparse(url).path or None
        except Exception:  # noqa: BLE001 - unparsable URL is reportable
            report["project_dir"] = None
    resolved = None
    try:
        candidate = Path(str(dist.locate_file("vqs")))
        if candidate.is_dir():
            resolved = os.path.realpath(candidate)
    except Exception:  # noqa: BLE001 - unresolvable layout is reportable
        resolved = None
    current = os.path.realpath(import_root)
    if resolved is not None and resolved != current:
        report["stale"] = True
        report["stale_reason"] = (
            "installed distribution resolves vqs to "
            f"{resolved}, but the running import resolves to {current}; "
            "reinstall or run from the installed checkout")
    return report
