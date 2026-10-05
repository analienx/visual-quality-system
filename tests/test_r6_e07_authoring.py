"""R6-E07: Microsoft-guided authoring with explicit fallback.

Oracle A07 (portable wiring): backend selection, Microsoft validation
adjudication, and repair integration through the public repair route
with a fake CLI port (fake-port tests prove wiring only; the hosted
real-CLI lane in .github/workflows/authoring.yml attempts the genuine
tool). Microsoft failures never silently fall back; warnings block
unless explicitly allowed; every record states the Desktop/render
limit. Model-target plans fail closed on the public path and the
executor cannot touch model bytes (no silent TMDL fallback under a
live authoritative session).
"""
import json
from pathlib import Path
from typing import Any

import pytest

from vqs.pipeline import repair_candidate
from vqs.powerbi.author import adapter, mscli
from vqs.repair.allowlist import validate_plan

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")
SCHEMA_INDEX = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.1.0/schema.json")
VISUAL_REL = "definition/pages/P1/visuals/v1/visual.json"
LEAF = ["visual", "objects", "categoryAxis", 0, "properties",
        "labelPrecision", "expr", "Literal", "Value"]
MODEL_TEXT = "table T\n\n\tmeasure Good = 1\n"


def _probe(available: bool) -> dict[str, Any]:
    return {"tool": "powerbi-report-author", "available": available,
            "path": "C:/tool" if available else None,
            "version": "9.9" if available else None,
            "probe_command": ["powerbi-report-author", "--help"],
            "returncode": 0 if available else None, "note": None}


def _validation(status: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tool": "powerbi-report-author", "command": ["x"], "status": status,
        "returncode": 0 if status == "valid" else 1, "errors": [],
        "warnings": [], "raw_tail": "tail", "note": None}
    base.update(extra)
    return base


def _project(root: Path) -> tuple[Path, Path]:
    proj = root / "proj"
    report = proj / "original.Report"
    visual_dir = report / "definition" / "pages" / "P1" / "visuals" / "v1"
    visual_dir.mkdir(parents=True)
    definition = report / "definition"
    (definition / "pages" / "pages.json").write_text(
        json.dumps({"$schema": SCHEMA_INDEX, "pageOrder": ["P1"]}),
        encoding="utf-8")
    (definition / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1"]}), encoding="utf-8")
    (definition / "version.json").write_text(json.dumps(
        {"$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                    "report/definition/versionMetadata/1.0.0/schema.json"),
         "version": "2.0.0"}), encoding="utf-8")
    (definition / "report.json").write_text(json.dumps(
        {"$schema": SCHEMA_REPORT, "layoutOptimization": "None",
         "themeCollection": {}}), encoding="utf-8")
    (definition / "pages" / "P1" / "page.json").write_text(
        json.dumps({"displayName": "P1", "width": 1280, "height": 720}),
        encoding="utf-8")
    (visual_dir / "visual.json").write_text(json.dumps({
        "name": "v1",
        "position": {"x": 0, "y": 0, "width": 100, "height": 100, "z": 1},
        "visual": {"visualType": "barChart",
                   "objects": {"categoryAxis": [{"properties": {
                       "labelPrecision": {"expr": {"Literal": {
                           "Value": "2"}}}}}]}}}), encoding="utf-8")
    tables = proj / "Model.SemanticModel" / "tables"
    tables.mkdir(parents=True)
    (tables / "T.tmdl").write_text(MODEL_TEXT, encoding="utf-8")
    plan = {"operations": [{
        "type": "axis.tick_format",
        "selector": {"page": "P1", "visual": "v1"},
        "target": "visual", "path": list(LEAF), "value": "3",
        "writes": [VISUAL_REL]}],
        "rollback": "re-materialize from original",
        "write_targets": [VISUAL_REL]}
    (proj / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return proj, report


def _repair(proj: Path, report: Path, tmp_path: Path, run_id: str,
            **kwargs: Any) -> dict[str, Any]:
    return repair_candidate(
        str(proj / "plan.json"), str(report),
        str(proj / f"candidate-{run_id}"),
        run_root=str(tmp_path / "runs"), run_id=run_id, **kwargs)


def test_select_explicit_and_auto() -> None:
    """Policy selection is recorded and never silent."""
    assert adapter.select("microsoft", _probe(False))["backend"] == "microsoft"
    assert adapter.select("direct", _probe(True))["backend"] == "direct"
    auto_hit = adapter.select("auto", _probe(True))
    assert auto_hit["backend"] == "microsoft"
    auto_miss = adapter.select("auto", _probe(False))
    assert auto_miss["backend"] == "direct"
    assert "fallback" in auto_miss["reason"]
    with pytest.raises(ValueError):
        adapter.select("sometimes", _probe(True))


def test_run_backend_valid_and_warnings() -> None:
    """Valid passes; warnings block unless explicitly allowed."""
    clean = adapter.run_backend(
        "candidate", policy="microsoft",
        prober=lambda: _probe(True),
        runner=lambda *a, **k: _validation("valid"))
    assert (clean["backend"], clean["verdict"]) == ("microsoft", "pass")
    assert "Desktop" in clean["record"]["limits"]
    warned = adapter.run_backend(
        "candidate", policy="microsoft",
        prober=lambda: _probe(True),
        runner=lambda *a, **k: _validation("valid", warnings=["W1"]))
    assert warned["verdict"] == "blocked"
    assert warned["reason"] == "authoring_warnings_require_review"
    assert warned["record"]["validation"]["warnings"] == ["W1"]
    allowed = adapter.run_backend(
        "candidate", policy="microsoft", allow_warnings=True,
        prober=lambda: _probe(True),
        runner=lambda *a, **k: _validation("valid", warnings=["W1"]))
    assert allowed["verdict"] == "pass"
    assert allowed["record"]["validation"]["warnings"] == ["W1"]


@pytest.mark.parametrize("status", ["missing", "timeout", "error"])
def test_run_backend_unavailable_blocks_never_falls_back(
        status: str) -> None:
    """Microsoft outages block; the backend stays microsoft."""
    decided = adapter.run_backend(
        "candidate", policy="microsoft",
        prober=lambda: _probe(False),
        runner=lambda *a, **k: _validation(status, note=status))
    assert decided["verdict"] == "blocked"
    assert decided["backend"] == "microsoft"
    assert decided["record"]["backend"] == "microsoft"


def test_run_backend_invalid_fails_and_total() -> None:
    """Rejection fails; runner crashes and garbage block safely."""
    rejected = adapter.run_backend(
        "candidate", policy="microsoft",
        prober=lambda: _probe(True),
        runner=lambda *a, **k: _validation("invalid", errors=["E9"]))
    assert rejected["verdict"] == "fail"
    assert rejected["record"]["validation"]["errors"] == ["E9"]
    crashed = adapter.run_backend(
        "candidate", policy="microsoft",
        prober=lambda: _probe(True),
        runner=lambda *a, **k: 1 / 0)
    assert crashed["verdict"] == "blocked"
    garbage = adapter.run_backend(
        "candidate", policy="microsoft",
        prober=lambda: _probe(True),
        runner=lambda *a, **k: ["not", "a", "dict"])
    assert garbage["verdict"] == "blocked"


def test_mscli_port_is_total_without_tool() -> None:
    """Probe/validate degrade honestly when the tool is absent."""
    missing = "definitely-not-a-real-tool-name-xyz"
    probed = mscli.probe(tool=missing)
    assert probed["available"] is False
    assert probed["path"] is None
    assert mscli.validate("candidate", tool=missing)["status"] == "missing"


def test_repair_records_direct_fallback_and_keeps_model_bytes(
        tmp_path: Path, monkeypatch) -> None:
    """Default auto records explicit direct fallback; model untouched."""
    monkeypatch.setattr("vqs.powerbi.author.adapter.probe",
                        lambda *a, **k: _probe(False))
    proj, report = _project(tmp_path)
    before = (proj / "Model.SemanticModel" / "tables" / "T.tmdl"
              ).read_bytes()
    envelope = _repair(proj, report, tmp_path, "direct1")
    assert envelope["verdict"] == "pass"
    assert envelope["authoring"]["backend"] == "direct"
    assert envelope["authoring"]["policy"] == "auto"
    after = (proj / "Model.SemanticModel" / "tables" / "T.tmdl"
             ).read_bytes()
    assert after == before
    run_dir = Path(envelope["run_dir"])
    sealed = json.loads((run_dir / "authoring.json").read_text(
        encoding="utf-8"))
    assert sealed["backend"] == "direct"
    manifest = json.loads((run_dir / "manifest.json").read_text(
        encoding="utf-8"))
    assert manifest["artifacts"]["authoring"]["path"] == "authoring.json"


def test_repair_microsoft_invalid_fails_and_preserves(
        tmp_path: Path, monkeypatch) -> None:
    """Microsoft rejection fails the repair; candidate is preserved."""
    monkeypatch.setattr(
        "vqs.powerbi.author.adapter.probe", lambda *a, **k: _probe(True))
    monkeypatch.setattr(
        "vqs.powerbi.author.adapter.validate",
        lambda *a, **k: _validation("invalid", errors=["bad node"]))
    proj, report = _project(tmp_path)
    envelope = _repair(proj, report, tmp_path, "msfail",
                       authoring_backend="microsoft")
    assert envelope["verdict"] == "fail"
    assert envelope["authoring"]["backend"] == "microsoft"
    assert envelope["authoring"]["validation"]["errors"] == ["bad node"]
    candidate = Path(envelope["provenance"]["candidate"])
    assert (candidate / VISUAL_REL).is_file()
    manifest = json.loads((Path(envelope["run_dir"]) / "manifest.json"
                           ).read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"


def test_repair_microsoft_warnings_block(tmp_path: Path,
                                         monkeypatch) -> None:
    """Microsoft warnings block without the explicit allow flag."""
    monkeypatch.setattr(
        "vqs.powerbi.author.adapter.probe", lambda *a, **k: _probe(True))
    monkeypatch.setattr(
        "vqs.powerbi.author.adapter.validate",
        lambda *a, **k: _validation("valid", warnings=["suspicious"]))
    proj, report = _project(tmp_path)
    envelope = _repair(proj, report, tmp_path, "mswarn",
                       authoring_backend="microsoft")
    assert envelope["verdict"] == "blocked"
    assert "authoring_warnings_require_review" in envelope["blocked_reasons"][0]
    allowed = _repair(proj, report, tmp_path, "mswarn2",
                      authoring_backend="microsoft",
                      authoring_allow_warnings=True)
    assert allowed["verdict"] == "pass"


def test_repair_rejects_bad_authoring_policy(tmp_path: Path) -> None:
    """Invalid authoring options block before any filesystem touch."""
    proj, report = _project(tmp_path)
    for kwargs in ({"authoring_backend": "sometimes"},
                   {"authoring_timeout": 0},
                   {"authoring_timeout": "300"},
                   {"authoring_allow_warnings": "yes"}):
        envelope = _repair(proj, report, tmp_path, "bad", **kwargs)
        assert envelope["verdict"] == "blocked"


def test_model_target_plan_fails_closed_without_touch(tmp_path: Path) -> None:
    """Model targets cannot reach execution on the public repair path."""
    proj, report = _project(tmp_path)
    plan = {"operations": [{
        "type": "axis.tick_format",
        "selector": {"page": "P1", "visual": "v1"},
        "target": "model", "path": list(LEAF), "value": "3",
        "writes": [VISUAL_REL]}],
        "rollback": "re-materialize from original",
        "write_targets": [VISUAL_REL]}
    assert validate_plan(plan, str(report), str(proj / "candidate-x"))
    plan_path = proj / "model-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    envelope = repair_candidate(
        str(plan_path), str(report), str(proj / "candidate-x"),
        run_root=str(tmp_path / "runs"), run_id="model1")
    assert envelope["verdict"] == "fail"
    assert not (proj / "candidate-x").exists()
