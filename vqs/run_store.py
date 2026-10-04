"""Private run-evidence store: append-only events plus atomic manifests (WP-02).

Layout per run (under a private root that Git ignores)::

    <root>/<run-id>/events.jsonl    # appended JSON lines, fsynced per write
    <root>/<run-id>/manifest.json   # written atomically via tmp + os.replace

The store never executes, renders, or approves anything. A killed run simply
stops appending; reopening replays every event written before the kill, and an
attempt without a terminal event reads back as ``blocked``, never green.
Artifact claims use exclusive lock files: a second claimant is refused (it
must queue), so two agents can never own one artifact or Desktop PID.

Integrity rules (issue #22): run/lock ids are single path segments on both
Windows and POSIX (traversal is rejected, never sanitized); only a terminal
``completed``/``failed``/``blocked`` status seals a run, and only when the
FINAL event is that terminal event; sealed runs are immutable (further
appends are rejected, never silently applied); the sealed manifest binds an
event-log digest so post-seal tampering is detectable via :func:`verify_seal`.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

TERMINAL_EVENTS = frozenset({"completed", "failed", "blocked"})


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _validate_name(name: object, what: str) -> str:
    """Accept one safe path segment; reject traversal/absolute/empty ids."""
    if not isinstance(name, str) or not name:
        raise ValueError(f"{what} must be a non-empty string")
    if "\x00" in name:
        raise ValueError(f"{what} contains NUL: {name!r}")
    if "/" in name or "\\" in name or ":" in name:
        raise ValueError(f"{what} must be one path segment: {name!r}")
    if name in (".", "..") or Path(name).is_absolute() or Path(name).name != name:
        raise ValueError(f"{what} is not a plain name: {name!r}")
    return name


def _within(root: Path, path: Path) -> bool:
    """True when path resolves inside root (Windows/POSIX aware)."""
    base = os.path.normcase(os.path.abspath(str(root)))
    target = os.path.normcase(os.path.abspath(str(path)))
    return os.path.commonpath([base, target]) == base


def create_run(root: Path, run_id: str, manifest: dict) -> Path:
    """Create a run directory with an atomic manifest; fail if it exists."""
    _validate_name(run_id, "run_id")
    run_dir = Path(root) / run_id
    if not _within(Path(root), run_dir):
        raise ValueError(f"run_id escapes the run root: {run_id!r}")
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = dict(manifest)
    payload.setdefault("run_id", run_id)
    payload.setdefault("status", "active")
    _atomic_write(run_dir / "manifest.json", json.dumps(payload, indent=2))
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    return run_dir


def append_event(run_dir: Path, event: dict) -> None:
    """Append one JSON event; reject unknown, sealed, or terminal runs."""
    log = Path(run_dir) / "events.jsonl"
    if not log.is_file():
        raise FileNotFoundError(f"Unknown run directory: {run_dir}")
    if not isinstance(event, dict):
        raise TypeError(f"Event must be an object: {type(event).__name__}")
    try:
        manifest = json.loads((Path(run_dir) / "manifest.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Run manifest unreadable: {run_dir}") from exc
    if isinstance(manifest, dict) and manifest.get("sealed") is True:
        raise ValueError(f"Run is sealed; start a new attempt: {run_dir}")
    events = read_events(run_dir)
    if events and events[-1].get("kind") in TERMINAL_EVENTS:
        raise ValueError("Run already has a terminal event; "
                         f"start a new attempt: {run_dir}")
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_events(run_dir: Path) -> list[dict]:
    """Replay every event in order; corrupt lines raise instead of skipping."""
    events = []
    for line in (Path(run_dir) / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Corrupt event line in {run_dir}")
            events.append(value)
    return events


def seal_run(run_dir: Path, status: str, artifacts: dict | None = None,
             environment: dict | None = None,
             bindings: dict[str, Any] | None = None) -> dict:
    """Seal a run manifest; the final event must be the matching terminal one.

    Records ``status`` (completed/failed/blocked only), artifact digests,
    backend versions, optional input/tool bindings (P1-13), the event count,
    and a digest of the raw event log so the manifest can never contradict
    the log and post-seal tampering is detectable.
    """
    if status not in TERMINAL_EVENTS:
        raise ValueError(f"Only a terminal status seals a run: {status!r}")
    manifest_path = Path(run_dir) / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Run manifest unreadable: {run_dir}") from exc
    manifest_ok = isinstance(manifest, dict)
    if not manifest_ok:
        raise ValueError(f"Run manifest is not an object: {run_dir}")
    if manifest.get("sealed") is True:
        raise ValueError(f"Run is already sealed: {run_dir}")
    events = read_events(run_dir)
    if not events or events[-1].get("kind") != status:
        raise ValueError("Sealing requires the final event itself to be the "
                         f"matching terminal event: {status!r}")
    manifest["status"] = status
    manifest["artifacts"] = dict(artifacts or {})
    manifest["environment"] = dict(environment or {})
    if bindings is not None:
        manifest["bindings"] = dict(bindings)
    manifest["event_count"] = len(events)
    manifest["events_sha256"] = digest_bytes(
        (Path(run_dir) / "events.jsonl").read_bytes())
    manifest["sealed"] = True
    _atomic_write(manifest_path, json.dumps(manifest, indent=2))
    return manifest


def verify_seal(run_dir: Path) -> list[dict[str, Any]]:
    """Recompute seal bindings; an empty list means the seal is valid."""
    try:
        manifest = json.loads((Path(run_dir) / "manifest.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return [{"rule": "seal_manifest_unreadable"}]
    if not isinstance(manifest, dict) or manifest.get("sealed") is not True:
        return [{"rule": "seal_missing"}]
    issues: list[dict[str, Any]] = []
    try:
        events = read_events(run_dir)
        raw = (Path(run_dir) / "events.jsonl").read_bytes()
    except (OSError, ValueError):
        return [{"rule": "seal_log_unreadable"}]
    if manifest.get("status") not in TERMINAL_EVENTS:
        issues.append({"rule": "seal_status_invalid"})
    if manifest.get("event_count") != len(events):
        issues.append({"rule": "seal_count_mismatch"})
    if manifest.get("events_sha256") != digest_bytes(raw):
        issues.append({"rule": "seal_log_tampered"})
    if not events or events[-1].get("kind") != manifest.get("status"):
        issues.append({"rule": "seal_terminal_mismatch"})
    return issues


def run_status(run_dir: Path) -> str:
    """Final event kind when terminal, else ``blocked`` (never a stale green)."""
    events = read_events(run_dir)
    if events and events[-1].get("kind") in TERMINAL_EVENTS:
        return str(events[-1]["kind"])
    return "blocked"


def claim_artifact(lock_dir: Path, artifact_id: str, owner: str) -> bool:
    """Claim exclusive ownership; False means another owner holds it (queue)."""
    _validate_name(artifact_id, "artifact_id")
    Path(lock_dir).mkdir(parents=True, exist_ok=True)
    lock = Path(lock_dir) / (artifact_id + ".lock")
    if not _within(Path(lock_dir), lock):
        raise ValueError(f"artifact_id escapes the lock directory: {artifact_id!r}")
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps({"artifact": artifact_id, "owner": owner}))
    return True


def release_artifact(lock_dir: Path, artifact_id: str, owner: str) -> bool:
    """Release a claim; False when held by someone else or not held."""
    _validate_name(artifact_id, "artifact_id")
    lock = Path(lock_dir) / (artifact_id + ".lock")
    if not _within(Path(lock_dir), lock):
        raise ValueError(f"artifact_id escapes the lock directory: {artifact_id!r}")
    try:
        record = json.loads(lock.read_text(encoding="utf-8"))
    except OSError:
        return False
    if record.get("owner") != owner:
        return False
    lock.unlink()
    return True


def digest_bytes(data: bytes) -> str:
    """SHA256 helper for pinning source/model/contract bytes."""
    return hashlib.sha256(data).hexdigest()
