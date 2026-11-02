"""PR gate: only findings a change introduces fail; SARIF/annotations shape."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vqs import gate
from vqs.cli import main
from vqs.pbir import source_digest
from vqs.repair.decisions import ANSWERS_SCHEMA, decision_id

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "contoso-retail"
NEW_SUBJECT = "typography.format_declaration_consistency|cohort=card/labels.fontSize"


def _copy(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(EXAMPLE, target)
    return target / "Contoso Retail.Report"


def _set_size(report: Path, visual: str, obj: str, prop: str, raw: str) -> None:
    path = next(report.rglob(f"visuals/{visual}/visual.json"))
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    doc["visual"]["objects"][obj][0]["properties"][prop]["expr"]["Literal"]["Value"] = raw
    path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    base, head = _copy(tmp_path, "base"), _copy(tmp_path, "head")
    _set_size(head, "card-096ca6e7", "labels", "fontSize", "30D")
    return base, head


def test_unchanged_revision_passes_with_known_issues(tmp_path: Path) -> None:
    base = _copy(tmp_path, "base")
    result = gate.run(str(base), baseline=base)
    assert result["verdict"] == "pass"
    assert result["head_verdict"] == "fail"  # known issues still exist
    assert result["counts"]["new"] == 0
    assert result["counts"]["unchanged"] == 5


def test_only_the_introduced_regression_is_new(pair, tmp_path: Path) -> None:
    base, head = pair
    result = gate.run(str(head), baseline=base)
    assert result["verdict"] == "fail"
    assert [item["subject"] for item in result["new"]] == [NEW_SUBJECT]
    assert result["counts"]["unchanged"] == 5
    log = gate.sarif(result, tmp_path)
    assert log["version"] == "2.1.0"
    results = log["runs"][0]["results"]
    assert [r["baselineState"] for r in results].count("new") == 1
    new = next(r for r in results if r["baselineState"] == "new")
    assert new["level"] == "error"
    assert new["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == (
        "head/Contoso Retail.Report/definition/report.json")
    assert len(new["partialFingerprints"]["vqsSubject/v1"]) == 64
    assert {rule["id"] for rule in log["runs"][0]["tool"]["driver"]["rules"]} >= {
        new["ruleId"]}


def test_fixed_issue_is_reported_and_passes(tmp_path: Path) -> None:
    base, head = _copy(tmp_path, "base"), _copy(tmp_path, "head")
    _set_size(head, "product-opportunity", "grid", "textSize", "10D")
    result = gate.run(str(head), baseline=base)
    assert result["verdict"] == "pass"
    assert "typography.format_declaration_consistency|cohort=pivotTable/grid.textSize" in (
        result["fixed"])


def test_emitted_baseline_round_trips(pair, tmp_path: Path, capsys) -> None:
    base, head = pair
    stored = tmp_path / "baseline.json"
    assert main(["gate", str(base), "--emit-baseline", str(stored)]) == 1
    capsys.readouterr()
    data = json.loads(stored.read_text(encoding="utf-8"))
    assert data["schema"] == gate.BASELINE_SCHEMA and len(data["items"]) == 5
    from_json = gate.run(str(head), baseline=stored)
    from_tree = gate.run(str(head), baseline=base)
    assert from_json["new"] == from_tree["new"]


def test_owner_waiver_bound_to_head_excuses_only_that_subject(pair) -> None:
    base, head = pair
    answers = {"schema": ANSWERS_SCHEMA, "owner": "owner",
               "source_sha256": source_digest(head), "answers": [
                   {"decision_id": decision_id(NEW_SUBJECT, source_digest(head)),
                    "option": "accept"}]}
    result = gate.run(str(head), baseline=base, decisions=answers)
    assert result["verdict"] == "pass"
    assert [item["subject"] for item in result["waived"]] == [NEW_SUBJECT]
    # The same answer written for the base revision matches nothing.
    stale = dict(answers, answers=[{"decision_id": decision_id(
        NEW_SUBJECT, source_digest(base)), "option": "accept"}])
    result = gate.run(str(head), baseline=base, decisions=stale)
    assert result["verdict"] == "fail"
    assert result["unmatched_waivers"] == 1


def test_no_baseline_means_everything_is_new(tmp_path: Path) -> None:
    base = _copy(tmp_path, "base")
    result = gate.run(str(base))
    assert result["verdict"] == "fail"
    assert result["counts"]["new"] == 5


@pytest.mark.parametrize("which", ["head", "baseline-json"])
def test_unreadable_inputs_block(tmp_path: Path, which: str) -> None:
    base = _copy(tmp_path, "base")
    if which == "head":
        result = gate.run(str(tmp_path / "missing"), baseline=base)
    else:
        bad = tmp_path / "baseline.json"
        bad.write_text('{"schema": "other"}', encoding="utf-8")
        result = gate.run(str(base), baseline=bad)
    assert result["verdict"] == "blocked"


def test_github_annotation_escapes_workflow_commands(pair, tmp_path: Path) -> None:
    base, head = pair
    result = gate.run(str(head), baseline=base)
    result["new"][0]["message"] = "line1\nline2 100%"
    (line,) = gate.github_annotations(result, tmp_path)
    assert line.startswith("::error file=head/Contoso Retail.Report/definition/report.json,")
    assert line.endswith("::line1%0Aline2 100%25")
    assert "title=typography.format_declaration_consistency" in line


def test_cli_exit_codes_and_sarif(pair, tmp_path: Path, capsys) -> None:
    base, head = pair
    sarif = tmp_path / "out.sarif"
    code = main(["gate", str(head), "--baseline", str(base), "--sarif", str(sarif),
                 "--sarif-root", str(tmp_path), "--github"])
    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith("::error ")
    assert json.loads(sarif.read_text(encoding="utf-8"))["version"] == "2.1.0"
    assert main(["gate", str(base), "--baseline", str(base)]) == 0
    capsys.readouterr()
    assert main(["gate", str(tmp_path / "nope")]) == 2
