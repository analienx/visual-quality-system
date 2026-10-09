"""S15: trusted-root containment for run and object lookups.

A linked ``objects`` ancestor, or a producer run reached through a
symlink/junction child, must never back acceptance: object lookup
raises before reading, and acceptance blocks with producer_run_escaped
before any foreign seal is read. Ordinary rooted evidence keeps working.
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from vqs.acceptance import run_acceptance
from vqs.evidence import SealedEvidenceStore
from vqs.run_store import append_event, create_run, seal_run

SOURCE = "a" * 64
ENV = {"renderer": "desktop-bridge", "renderer_version": "1.0.0",
       "locale": "en-US", "view_state": "default"}
SCOPE = {"role": "analyst", "refresh_id": "refresh-1", "filters": {},
         "query_context": "analyst-review", "query_hash": "q" * 64}


def _envelope(run_id: str) -> dict[str, Any]:
    return {
        "source_sha256": SOURCE, "environment": dict(ENV),
        "producer": {"run_id": run_id, "gate": "G2",
                     "status": "pass", "control": None},
        "result": {"gate": "G2", "status": "pass"},
        "data_scope": {**SCOPE, "filters": {}},
    }


def _sealed(root: Path, run_id: str) -> str:
    """Materialize objects/envelope plus a valid sealed run; return sha."""
    raw = json.dumps(_envelope(run_id), sort_keys=True,
                     separators=(",", ":"), ensure_ascii=False).encode()
    sha = hashlib.sha256(raw).hexdigest()
    objects = root / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / sha).write_bytes(raw)
    run_dir = create_run(root, run_id, {"pipeline": "vqs.check/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"envelope_sha256": sha, "gate": "G2",
                        "status": "pass", "control": None})
    return sha


def _record(sha: str, run_id: str) -> dict[str, Any]:
    gate: dict[str, Any] = {
        "id": "G2", "subject_id": "p1", "status": "pass",
        "environment": dict(ENV),
        "data_scope": {**SCOPE, "filters": {}},
        "evidence_ref": {"sha256": sha, "source_sha256": SOURCE},
    }
    return {"subjects": [
        {"kind": "pbip", "id": "p1", "layout_digest": "1" * 16,
         "source_sha256": SOURCE},
        {"kind": "pbip", "id": "p2", "layout_digest": "2" * 16,
         "source_sha256": "b" * 64},
        {"kind": "docx", "id": "d1", "source_sha256": "c" * 64},
    ], "gates": [gate], "editor_id": "agent-a",
        "reviewer_id": "agent-b", "user_approved": True}


def _rules(verdict: dict) -> set[str]:
    return {finding["rule"] for finding in verdict["findings"]}


def test_linked_objects_dir_rejected(tmp_path: Path) -> None:
    """S15: an objects dir linking outside never resolves."""
    outside = tmp_path / "outside"
    outside.mkdir()
    sha = _sealed(outside, "prod-1")
    root = tmp_path / "root"
    root.mkdir()
    try:
        os.symlink(str(outside / "objects"), str(root / "objects"))
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    with pytest.raises(ValueError, match="trusted root"):
        SealedEvidenceStore(root).resolve(sha)


def test_linked_run_id_blocked(tmp_path: Path) -> None:
    """S15: a producer run reached through a link cannot back a gate."""
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    sha = _sealed(outside, "evil-1")
    objects = root / "objects"
    objects.mkdir()
    (objects / sha).write_bytes(
        json.dumps(_envelope("evil-1"), sort_keys=True,
                   separators=(",", ":"),
                   ensure_ascii=False).encode())
    try:
        os.symlink(str(outside / "evil-1"), str(root / "evil-1"))
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    verdict = run_acceptance(_record(sha, "evil-1"),
                             SealedEvidenceStore(root))
    assert verdict["verdict"] == "blocked"
    assert "producer_run_escaped" in _rules(verdict)


@pytest.mark.skipif(os.name != "nt", reason="junctions need Windows")
def test_junction_run_id_blocked(tmp_path: Path) -> None:
    """S15: a producer run reached through a junction cannot back a gate."""
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    sha = _sealed(outside, "evil-1")
    objects = root / "objects"
    objects.mkdir()
    (objects / sha).write_bytes(
        json.dumps(_envelope("evil-1"), sort_keys=True,
                   separators=(",", ":"),
                   ensure_ascii=False).encode())
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root / "evil-1"),
         str(outside / "evil-1")],
        capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        pytest.skip(f"mklink unavailable: {completed.stderr[:80]}")
    verdict = run_acceptance(_record(sha, "evil-1"),
                             SealedEvidenceStore(root))
    assert verdict["verdict"] == "blocked"
    assert "producer_run_escaped" in _rules(verdict)


def test_ordinary_rooted_evidence_resolves(tmp_path: Path) -> None:
    """S15 control: plain inside-the-root evidence still resolves."""
    root = tmp_path / "root"
    root.mkdir()
    sha = _sealed(root, "prod-1")
    envelope = SealedEvidenceStore(root).resolve(sha)
    assert envelope["producer"]["run_id"] == "prod-1"
