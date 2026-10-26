"""Do not silently attest a same-named but undeclared semantic model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import desktop_source_attestation as receipt


def fixture_project(tmp_path: Path, reference: str | None) -> Path:
    project = tmp_path / "Project"
    report = project / "Sales.Report"
    (report / "definition").mkdir(parents=True)
    (project / "Sales.pbip").write_text("{}", encoding="utf8")
    (report / "definition/pages.json").write_text("{}", encoding="utf8")
    if reference is not None:
        if reference == "remote":
            dataset = {"byConnection": {"connectionString": "placeholder"}}
        else:
            dataset = {"byPath": {"path": reference}}
        (report / "definition.pbir").write_text(
            json.dumps({"datasetReference": dataset}), encoding="utf8"
        )
    wrong = project / "Sales.SemanticModel"
    wrong.mkdir()
    (wrong / "wrong.tmdl").write_text("DO NOT HASH THIS", encoding="utf8")
    target = project / "RealDifferent.SemanticModel"
    target.mkdir()
    (target / "actual.tmdl").write_text("ACTUAL SEMANTIC MODEL", encoding="utf8")
    return project


def fake_collect(*_args: object) -> dict[str, object]:
    return {"status": "pass", "loaded_file_attested": True, "reason": "synthetic"}


def check_receipt(
    monkeypatch: pytest.MonkeyPatch, project: Path, output: Path
) -> tuple[int, dict[str, object]]:
    monkeypatch.setattr(receipt, "collect", fake_collect)
    rc = receipt.main([str(project), "--desktop-pid", "1234", "--output", str(output)])
    return rc, json.loads(output.read_text(encoding="utf8"))


def test_by_path_hashes_declared_differently_named_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = fixture_project(tmp_path, "../RealDifferent.SemanticModel")
    rc, evidence = check_receipt(monkeypatch, project, tmp_path / "receipt.json")
    assert rc == 0
    assert evidence["status"] == "pass"
    assert evidence["model_reference_status"] == "byPath_source_checked"
    relative = b"actual.tmdl"
    data = b"ACTUAL SEMANTIC MODEL"
    h = hashlib.sha256()
    h.update(len(relative).to_bytes(4, "big"))
    h.update(relative)
    h.update(len(data).to_bytes(8, "big"))
    h.update(data)
    assert evidence["model_source_sha256"] == h.hexdigest()
    assert evidence["wrapper_sha256"]
    assert evidence["report_source_sha256"]


@pytest.mark.parametrize("reference,kind", [
    ("remote", "byConnection_not_locally_verified"),
    (None, "legacy_unverified_reference"),
])
def test_unverified_or_remote_model_cannot_claim_local_model_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    reference: str | None, kind: str
) -> None:
    project = fixture_project(tmp_path, reference)
    rc, evidence = check_receipt(monkeypatch, project, tmp_path / "receipt.json")
    assert rc == 0
    assert evidence["model_reference_status"] == kind
    assert evidence["model_source_sha256"] is None


def test_invalid_by_path_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = fixture_project(tmp_path, "../../Different.SemanticModel")
    rc, evidence = check_receipt(monkeypatch, project, tmp_path / "receipt.json")
    assert rc == 2
    assert evidence["loaded_file_attested"] is False
    assert evidence["status"] == "blocked"
    assert "source inventory unavailable" in evidence["reason"]


def test_symlinked_declared_model_is_not_attested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = fixture_project(tmp_path, "../RealDifferent.SemanticModel")
    target = project / "RealDifferent.SemanticModel"
    alternate = project / "Shadow.SemanticModel"
    try:
        target.rename(alternate)
        target.symlink_to(alternate, target_is_directory=True)
    except OSError:
        pytest.skip("symlink permissions unavailable on this host")
    rc, evidence = check_receipt(monkeypatch, project, tmp_path / "receipt.json")
    assert rc == 2
    assert evidence["loaded_file_attested"] is False
