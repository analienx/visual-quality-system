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
    # Capturing a baseline is its own operation, not a comparison: the
    # documented "store a baseline" command must not fail the CI step
    # that just wrote the file.
    assert main(["gate", str(base), "--emit-baseline", str(stored)]) == 0
    assert json.loads(capsys.readouterr().out)["baseline_written"] == str(stored)
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


def test_owner_waiver_bound_to_base_acknowledges_only_unchanged(pair) -> None:
    """Zephyrus 2 Nov 2026: the owner answers on the original, `vqs fix`
    builds the candidate, the PR head is the candidate. Those answers name
    the base digest; they must still record the waiver for the unchanged
    subject, and never excuse anything the head introduces."""
    base, head = pair
    known = next(item["subject"] for item in gate.evaluate(str(base))["items"]
                 if item["check"] == "insight.no_cross_page_duplicate_grain")
    answers = {"schema": ANSWERS_SCHEMA, "owner": "owner",
               "source_sha256": source_digest(base), "answers": [
                   {"decision_id": decision_id(known, source_digest(base)),
                    "option": "accept"},
                   {"decision_id": decision_id(NEW_SUBJECT, source_digest(base)),
                    "option": "accept"}]}
    result = gate.run(str(head), baseline=base, decisions=answers)
    assert [item["subject"] for item in result["waived"]] == [known]
    assert [item["subject"] for item in result["new"]] == [NEW_SUBJECT]
    assert result["verdict"] == "fail"
    assert result["unmatched_waivers"] == 1  # the NEW_SUBJECT answer
    assert known not in [item["subject"] for item in result["unchanged"]]


def test_base_waivers_need_a_reviewed_base_revision(pair, tmp_path: Path,
                                                    capsys) -> None:
    """A stored JSON baseline has no reviewed source, so base-digest answers
    cannot be verified against it and acknowledge nothing (fail closed)."""
    base, head = pair
    stored = tmp_path / "baseline.json"
    main(["gate", str(base), "--emit-baseline", str(stored)])
    capsys.readouterr()
    known = next(item["subject"] for item in gate.evaluate(str(base))["items"]
                 if item["check"] == "insight.no_cross_page_duplicate_grain")
    answers = {"schema": ANSWERS_SCHEMA, "owner": "owner",
               "source_sha256": source_digest(base), "answers": [
                   {"decision_id": decision_id(known, source_digest(base)),
                    "option": "accept"}]}
    result = gate.run(str(head), baseline=stored, decisions=answers)
    assert result["waived"] == []
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


_RUNNER_COMMANDS = {"error", "warning", "notice", "debug", "group", "endgroup",
                    "add-mask", "add-matcher", "remove-matcher", "echo",
                    "save-state", "set-output", "add-path", "set-env",
                    "stop-commands"}


def _runner_parse(line: str) -> dict | None:
    """What the GitHub Actions runner makes of one stdout line.

    Port of ``ActionCommand.TryParseV2``: the command name is everything
    between the leading ``::`` and the first space (or the closing
    ``::``); unknown names are printed as plain log text, never
    annotations. Properties are unescaped in the runner's order.
    """
    message = line.lstrip()
    end = message.find("::", 2) if message.startswith("::") else -1
    if end < 0:
        return None
    info = message[2:end]
    name, _, props = info.partition(" ")
    if name not in _RUNNER_COMMANDS:
        return None

    def unescape(text: str, mappings: tuple[tuple[str, str], ...]) -> str:
        for token, replacement in mappings:
            text = text.replace(replacement, token)
        return text

    prop_map = (("\r", "%0D"), ("\n", "%0A"), (":", "%3A"), (",", "%2C"), ("%", "%25"))
    data_map = (("\r", "%0D"), ("\n", "%0A"), ("%", "%25"))
    properties = {}
    for entry in filter(None, props.split(",")):
        key, _, value = entry.partition("=")
        properties[key] = unescape(value, prop_map)
    return {"command": name, "properties": properties,
            "data": unescape(message[end + 2:], data_map)}


def test_annotations_are_commands_the_runner_recognises(tmp_path: Path) -> None:
    """Every emitted line must become an annotation, not plain log text.

    ``::error,title=...`` (no space) is an unknown command to the runner,
    so the blocked gate - and any new item without a file - was silently
    not annotated although the docs promise it is.
    """
    blocked = {"verdict": "blocked", "reason": "head: visual_doc_unreadable: P/v\n2nd 100%"}
    (line,) = gate.github_annotations(blocked, tmp_path)
    parsed = _runner_parse(line)
    assert parsed == {"command": "error",
                      "properties": {"title": gate.BLOCKED_RULE},
                      "data": blocked["reason"]}

    item = {"check": "odd:check,name", "subject": "s", "message": "m: 50%, ok\nnext"}
    fileless = {"verdict": "fail", "report": None, "new": [item],
                "unchanged": [], "waived": []}
    (line,) = gate.github_annotations(fileless, tmp_path)
    assert _runner_parse(line) == {"command": "error",
                                   "properties": {"title": "odd:check,name"},
                                   "data": item["message"]}

    located = dict(fileless, report=str(tmp_path / "R, 1.Report"),
                   new=[dict(item, page="P1")])
    (line,) = gate.github_annotations(located, tmp_path)
    parsed = _runner_parse(line)
    assert parsed is not None and parsed["command"] == "error"
    assert parsed["properties"] == {
        "file": "R, 1.Report/definition/pages/P1/page.json",
        "title": "odd:check,name"}
    assert parsed["data"] == item["message"]
    # Negative control: the old shape is exactly what the runner ignores.
    assert _runner_parse("::error,title=vqs.gate.blocked::reason") is None


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


def test_blocked_gate_still_annotates_ci(pair, tmp_path: Path, capsys) -> None:
    """A gate that cannot compare is the most severe outcome, not a silent one.

    An unreadable visual document blocks `inspect_report`, so `evaluate`
    never reaches `_items` and the result carries no `new` list. The gate
    previously skipped `--sarif` and `--github` entirely, so CI got exit 2
    with nothing to annotate — it could not tell "the PR broke the report"
    from "the head path is unreadable".
    """
    base, head = pair
    visual = min(Path(head).rglob("visual.json"))
    doc = json.loads(visual.read_text(encoding="utf-8-sig"))
    doc.setdefault("visual", {})["query"] = 7
    visual.write_text(json.dumps(doc), encoding="utf-8")
    sarif_out = tmp_path / "out.sarif"
    code = main(["gate", str(head), "--baseline", str(base),
                 "--sarif", str(sarif_out), "--github"])
    out = capsys.readouterr().out
    assert code == 2
    annotations = [parsed for parsed in map(_runner_parse, out.splitlines()) if parsed]
    assert len(annotations) == 1
    assert annotations[0]["command"] == "error"
    assert annotations[0]["properties"] == {"title": gate.BLOCKED_RULE}
    assert "visual_doc_unreadable" in annotations[0]["data"]
    log = json.loads(sarif_out.read_text(encoding="utf-8"))
    results = log["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["ruleId"] == gate.BLOCKED_RULE
    assert results[0]["level"] == "error"
    assert "no regression claim is possible" in results[0]["message"]["text"]
    assert log["runs"][0]["tool"]["driver"]["rules"][0]["id"] == gate.BLOCKED_RULE
