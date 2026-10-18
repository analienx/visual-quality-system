"""Pipeline: measured facts to sealed verdict with no unknown-to-pass coercion."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vqs.pipeline import run_check
from vqs.run_store import read_events


def _facts(**overrides):
    facts = {
        "rules": {
            "axis.display_values_not_distinct": {
                "numeric_ticks": [1.0, 2.0], "displayed_labels": ["1", "2"]},
            "typography.text_contrast": {
                "foreground": "#000000", "background": "#ffffff"},
            "axis.category_label_space": {
                "label_widths_px": [40.0, 40.0], "available_width_px": 200.0},
            "palette.semantic_consistency": {
                "assignments": [{"state": "good", "color": "#00ff00", "page": "p1"},
                                {"state": "good", "color": "#00ff00", "page": "p2"}]},
            "encoding.metric_unit_consistency": {
                "readings": [{"measure": "sales", "unit": "USD", "page": "p1"}]},
            "typography.format_declaration_consistency": {
                "readings": [{"cohort": "slicer/header.textSize", "visual": "a",
                              "page": "p1", "value": None}]},
        },
        "oracles": [
            {"question": "Total revenue?", "known_measures": ["revenue"]},
            {"oracle_scope": "abc", "run_scope": "abc"},
        ],
    }
    facts.update(overrides)
    return facts


def test_full_pass_seals_completed_manifest(tmp_path):
    result = run_check(_facts(), tmp_path, run_id="pass1")
    assert result["verdict"] == "pass"
    manifest = result["manifest"]
    assert manifest["status"] == "completed"
    assert manifest["run_id"] == "pass1"
    assert len(manifest["artifacts"]["verdict_sha256"]) == 64
    assert manifest["event_count"] == len(read_events(Path(result["run_dir"])))


def test_failing_rule_fails_run(tmp_path):
    facts = _facts()
    facts["rules"]["typography.text_contrast"] = {
        "foreground": "#777777", "background": "#888888"}
    result = run_check(facts, tmp_path, run_id="fail1")
    assert result["verdict"] == "fail"
    assert result["manifest"]["status"] == "failed"
    contrast = next(f for f in result["findings"]
                    if f["check"] == "typography.text_contrast")
    assert contrast["status"] == "fail"


def test_unknown_facts_block_without_coercion(tmp_path):
    facts = _facts()
    facts["rules"]["axis.display_values_not_distinct"] = {
        "numeric_ticks": None, "displayed_labels": None}
    result = run_check(facts, tmp_path, run_id="unk1")
    assert result["verdict"] == "blocked"
    assert result["manifest"]["status"] == "blocked"


def test_unknown_rule_id_blocks_and_names_rule(tmp_path):
    result = run_check({"rules": {"chart.judgment": {}}}, tmp_path, run_id="unk2")
    assert result["verdict"] == "blocked"
    assert result["findings"][0]["check"] == "chart.judgment"


def test_scope_mismatch_fails_clarification_blocks(tmp_path):
    mismatch = run_check({"oracles": [{"oracle_scope": "a", "run_scope": "b"}]},
                         tmp_path, run_id="o1")
    assert mismatch["verdict"] == "fail"
    vague = run_check({"oracles": [{"question": "How are we doing?",
                                    "known_measures": ["revenue"]}]},
                      tmp_path, run_id="o2")
    assert vague["verdict"] == "blocked"


def test_non_object_facts_block_without_run(tmp_path):
    result = run_check(["not", "facts"], tmp_path, run_id="nope")
    assert result == {"verdict": "blocked", "run_dir": None,
                      "findings": [{"check": "facts", "status": "blocked",
                                    "reason": "Facts document is not an object"}]}
    assert list(tmp_path.iterdir()) == []


def test_duplicate_run_id_refuses_second_claim(tmp_path):
    run_check(_facts(), tmp_path, run_id="dup")
    result = run_check(_facts(), tmp_path, run_id="dup")
    assert result["verdict"] == "blocked"
    assert result["run_dir"] is None
    assert result["findings"][0]["check"] == "run_id"


def test_scalar_params_block_instead_of_raising(tmp_path):
    hostile = {
        "axis.display_values_not_distinct": {"numeric_ticks": 5, "displayed_labels": 5},
        "axis.category_label_space": {"label_widths_px": 5, "available_width_px": 5},
        "encoding.metric_unit_consistency": {"readings": 5},
        "palette.semantic_consistency": {"assignments": 5},
    }
    for index, (rule_id, params) in enumerate(hostile.items()):
        result = run_check({"rules": {rule_id: params}}, tmp_path, run_id=f"hostile{index}")
        assert result["verdict"] == "blocked", rule_id
        assert result["findings"][0]["status"] == "blocked", rule_id


def test_non_string_oracle_question_blocks(tmp_path):
    result = run_check({"oracles": [{"question": 5, "known_measures": ["m"]}]},
                       tmp_path, run_id="oq")
    assert result["verdict"] == "blocked"


def test_empty_facts_block_with_no_findings(tmp_path):
    result = run_check({}, tmp_path, run_id="empty")
    assert result["verdict"] == "blocked"
    assert result["findings"] == []
    assert result["manifest"]["status"] == "blocked"


def test_malformed_oracle_entries_block(tmp_path):
    for index, oracles in enumerate((["not-an-entry"], [{"unrelated": True}], "not-a-list")):
        result = run_check({"oracles": oracles}, tmp_path, run_id=f"mo{index}")
        assert result["verdict"] == "blocked", oracles


def test_malformed_rule_entries_block(tmp_path):
    result = run_check({"rules": ["not-an-object"]}, tmp_path, run_id="mr0")
    assert result["verdict"] == "blocked"
    assert result["findings"][0]["check"] == "rules"
    result = run_check({"rules": {"typography.text_contrast": "params"}}, tmp_path,
                       run_id="mr1")
    assert result["verdict"] == "blocked"


def test_cli_fail_and_blocked_exits(tmp_path, capsys, monkeypatch):
    from vqs.cli import main

    monkeypatch.chdir(tmp_path)
    facts = _facts()
    facts["rules"]["typography.text_contrast"] = {
        "foreground": "#777777", "background": "#888888"}
    fail_file = tmp_path / "fail.json"
    fail_file.write_text(json.dumps(facts), encoding="utf-8")
    assert main(["check", str(fail_file), "--run-id", "cli-fail"]) == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "fail"
    blocked_file = tmp_path / "blocked.json"
    blocked_file.write_text("{}", encoding="utf-8")
    assert main(["check", str(blocked_file), "--run-id", "cli-blocked"]) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "blocked"


def test_cli_missing_and_unparseable_facts_block(tmp_path, capsys, monkeypatch):
    from vqs.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["check", str(tmp_path / "absent.json")]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{oops", encoding="utf-8")
    assert main(["check", str(bad_file)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


def _write_docx(path, *, with_document=True):
    import zipfile

    types = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Override PartName="/word/document.xml" ContentType="application/xml"/>'
             "</Types>")
    body = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Hi</w:t></w:r></w:p></w:body></w:document>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types)
        if with_document:
            archive.writestr("word/document.xml", body)


def test_wellformed_document_passes(tmp_path):
    docx = tmp_path / "good.docx"
    _write_docx(docx)
    result = run_check({"documents": [{"path": str(docx)}]}, tmp_path, run_id="doc0")
    assert result["verdict"] == "pass"
    assert result["findings"][0]["check"] == "document:0"


def test_broken_document_fails(tmp_path):
    docx = tmp_path / "bad.docx"
    _write_docx(docx, with_document=False)
    result = run_check({"documents": [{"path": str(docx)}]}, tmp_path, run_id="doc1")
    assert result["verdict"] == "fail"
    assert result["findings"][0]["detail"]["issues"] == [
        {"rule": "missing_required_part", "part": "word/document.xml"}]


def test_unreadable_and_malformed_documents_block(tmp_path):
    missing = run_check({"documents": [{"path": str(tmp_path / "absent.docx")}]},
                        tmp_path, run_id="doc2")
    assert missing["verdict"] == "blocked"
    no_path = run_check({"documents": [{"label": "no path"}]}, tmp_path, run_id="doc3")
    assert no_path["verdict"] == "blocked"
    not_list = run_check({"documents": {"path": "x"}}, tmp_path, run_id="doc4")
    assert not_list["verdict"] == "blocked"
    assert not_list["findings"][0]["check"] == "documents"
    for index, bad in enumerate((5, ["x"], None)):
        typed = run_check({"documents": [{"path": bad}]}, tmp_path,
                          run_id=f"doc5{index}")
        assert typed["verdict"] == "blocked", bad


def _write_model(model_dir):
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "sales.tmdl").write_text(
        "table Sales\n\tcolumn Amount\n\tmeasure Total = SUM(Sales[Amount])\n"
        "\tmeasure Bare =\n", encoding="utf-8")
    return str(model_dir)


def test_resolved_bindings_pass(tmp_path):
    model = _write_model(tmp_path / "model")
    entry = {"model_dir": model,
             "bindings": [{"query_ref": "Sales.Amount"},
                          {"query_ref": "Sales.Total"}]}
    result = run_check({"models": [entry]}, tmp_path, run_id="m0")
    assert result["verdict"] == "pass"
    assert result["findings"][0]["check"] == "model:0"


def test_unknown_binding_fails(tmp_path):
    model = _write_model(tmp_path / "model")
    entry = {"model_dir": model, "bindings": [{"query_ref": "Nope.X"}]}
    result = run_check({"models": [entry]}, tmp_path, run_id="m1")
    assert result["verdict"] == "fail"
    assert result["findings"][0]["detail"]["checks"][0]["rule"] == \
        "missing_dimension_or_measure"


def test_expressionless_measure_blocks(tmp_path):
    model = _write_model(tmp_path / "model")
    entry = {"model_dir": model, "bindings": [{"query_ref": "Sales.Bare"}]}
    result = run_check({"models": [entry]}, tmp_path, run_id="m2")
    assert result["verdict"] == "blocked"


def test_stale_freshness_fails_missing_role_blocks(tmp_path):
    model = _write_model(tmp_path / "model")
    stale = {"model_dir": model, "bindings": [{"query_ref": "Sales.Amount"}],
             "freshness": {"bound_sha256": "a", "current_sha256": "b",
                           "label": "snap"}}
    assert run_check({"models": [stale]}, tmp_path, run_id="m3")["verdict"] == "fail"
    norole = {"model_dir": model, "bindings": [{"query_ref": "Sales.Amount"}],
              "rls_role": ""}
    assert run_check({"models": [norole]}, tmp_path, run_id="m4")["verdict"] == "blocked"


def test_missing_and_malformed_models_block(tmp_path):
    absent = run_check({"models": [{"model_dir": str(tmp_path / "nope"),
                                    "bindings": []}]}, tmp_path, run_id="m5")
    assert absent["verdict"] == "blocked"
    no_dir = run_check({"models": [{"bindings": []}]}, tmp_path, run_id="m6")
    assert no_dir["verdict"] == "blocked"
    not_list = run_check({"models": {"model_dir": "x"}}, tmp_path, run_id="m7")
    assert not_list["verdict"] == "blocked"
    assert not_list["findings"][0]["check"] == "models"
    model = _write_model(tmp_path / "model")
    vacuous = run_check({"models": [{"model_dir": model, "bindings": []}]},
                        tmp_path, run_id="m8")
    assert vacuous["verdict"] == "blocked"


def test_cli_check_end_to_end(tmp_path, capsys, monkeypatch):
    from vqs.cli import main

    facts_file = tmp_path / "facts.json"
    facts_file.write_text(json.dumps(_facts()), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["check", str(facts_file)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "pass"
    assert (tmp_path / ".vqs-runs" / out["run_id"] / "manifest.json").is_file()
    with pytest.raises(SystemExit):
        main([])
def test_slash_pipeline_auto_id_is_sanitized(tmp_path):
    """Review finding: generated ids never contain path separators."""
    from vqs.pipeline import seal_verdict
    result = seal_verdict(tmp_path, None, "vqs.validate-plan/1", "pass", [])
    assert result["verdict"] == "pass"
    assert "/" not in result["run_id"]
    assert (tmp_path / result["run_id"] / "manifest.json").is_file()


def test_traversal_run_id_blocks_without_raise(tmp_path):
    """Review finding: hostile run ids block, never raise or escape."""
    from vqs.pipeline import seal_verdict
    result = run_check(_facts(), tmp_path, run_id="../escaped")
    assert result["verdict"] == "blocked"
    assert result["run_dir"] is None
    result = seal_verdict(tmp_path, "../escaped", "vqs.check/1", "pass", [])
    assert result["verdict"] == "blocked"
    assert result["run_dir"] is None
