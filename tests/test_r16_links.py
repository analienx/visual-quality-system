"""R16 RED: resolved filesystem confinement for seal/acceptance paths.

Artifact entries that resolve outside the run directory through a
symlink or junction child must be refused, never rehashed and
verified. POSIX symlinks and Windows junctions are both covered;
cleanup never deletes or traverses foreign targets.
"""
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from vqs.run_store import append_event, create_run, seal_run, verify_seal


def _seal_with_link(run_dir: Path, rel: str, payload: bytes) -> None:
    (run_dir / rel).write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"blob": {"sha256": digest, "path": rel}})


def test_symlink_member_refused(tmp_path: Path) -> None:
    """RED R16: an artifact behind a POSIX symlink child is refused."""
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"stale bytes")
    run_dir = create_run(tmp_path, "run-link", {"pipeline": "t"})
    try:
        os.symlink(str(outside), str(run_dir / "link"))
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    try:
        _seal_with_link(run_dir, "link", b"foreign bytes")
    except ValueError:
        return
    assert verify_seal(run_dir) != []


def test_junction_member_refused(tmp_path: Path) -> None:
    """RED R16: an artifact behind a Windows junction child is refused."""
    if os.name != "nt":
        pytest.skip("junctions need Windows")
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "blob.bin").write_bytes(b"stale bytes")
    run_dir = create_run(tmp_path, "run-junction", {"pipeline": "t"})
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(run_dir / "link"), str(foreign)],
        capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        pytest.skip(f"mklink unavailable: {completed.stderr[:80]}")
    try:
        _seal_with_link(run_dir, "link/blob.bin", b"foreign bytes")
    except ValueError:
        return
    assert verify_seal(run_dir) != []
    assert (foreign / "blob.bin").read_bytes() == b"foreign bytes"


def test_plain_member_still_verifies(tmp_path: Path) -> None:
    """Control: a real inside-the-run artifact still verifies."""
    run_dir = create_run(tmp_path, "run-plain", {"pipeline": "t"})
    (run_dir / "reads").mkdir()
    _seal_with_link(run_dir, "reads/blob.bin", b"inside bytes")
    assert verify_seal(run_dir) == []
