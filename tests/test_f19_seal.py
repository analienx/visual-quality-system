"""F19 RED: seals must protect metadata and referenced artifacts.

verify_seal checks terminal status/count/log bytes only, leaving
artifacts/environment/bindings editable without a finding. M3 seals a
canonical digest over the complete manifest payload and recomputes
file-backed artifact bytes: artifacts entries of the form
{"sha256":..., "path":...} (run-dir-confined) are re-hashed at verify.
"""
import hashlib
import json
from pathlib import Path

from vqs.pipeline import run_check
from vqs.run_store import (
    append_event,
    create_run,
    seal_run,
    verify_seal,
)


def _sealed_check(tmp_path: Path) -> Path:
    result = run_check({"rules": {}}, tmp_path / "runs", run_id="check-1")
    return Path(result["run_dir"])


def _rewrite_manifest(run_dir: Path, mutate) -> None:
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def test_f19_clean_seal_verifies(tmp_path: Path) -> None:
    """Control (passes now and post-fix): an untouched seal is valid."""
    assert verify_seal(_sealed_check(tmp_path)) == []


def test_f19_artifact_label_mutation_rejects(tmp_path: Path) -> None:
    """RED: editing a sealed artifact digest must reject."""
    run_dir = _sealed_check(tmp_path)
    _rewrite_manifest(
        run_dir, lambda manifest: manifest["artifacts"].update(
            {"verdict_sha256": "0" * 64}))
    assert verify_seal(run_dir) != []


def test_f19_environment_mutation_rejects(tmp_path: Path) -> None:
    """RED: editing sealed environment metadata must reject."""
    run_dir = _sealed_check(tmp_path)
    _rewrite_manifest(
        run_dir, lambda manifest: manifest["environment"].update(
            {"renderer": "forged-renderer"}))
    assert verify_seal(run_dir) != []


def test_f19_manifest_metadata_mutation_rejects(tmp_path: Path) -> None:
    """RED: editing sealed manifest metadata must reject."""
    run_dir = _sealed_check(tmp_path)
    _rewrite_manifest(
        run_dir, lambda manifest: manifest.update({"pipeline": "forged/9"}))
    assert verify_seal(run_dir) != []


def test_f19_artifact_bytes_mutation_rejects(tmp_path: Path) -> None:
    """RED: editing bytes behind a bound artifact must reject."""
    run_dir = create_run(tmp_path / "runs", "art-1", {"pipeline": "t/1"})
    payload = run_dir / "payload.json"
    payload.write_bytes(b'{"n": 1}')
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "blocked"})
    seal_run(run_dir, "blocked",
             artifacts={"payload": {"sha256": digest, "path": "payload.json"}})
    assert verify_seal(run_dir) == []
    payload.write_bytes(b'{"n": 2}')
    assert verify_seal(run_dir) != []
