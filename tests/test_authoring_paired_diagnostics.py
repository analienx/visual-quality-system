"""Paired Microsoft validation: inheritance without false approval or source mutation."""
from __future__ import annotations

import json

import pytest

from tests.test_s16_candidate_model import VISUAL, _project
from vqs.cli import main
from vqs.pbir import source_digest
from vqs.powerbi.author.compare import compare_authoring


def _pair(tmp_path):
    original, _ = _project(tmp_path / "original", "table T\n")
    candidate, _ = _project(tmp_path / "candidate", "table T\n")
    path = candidate / VISUAL
    doc = json.loads(path.read_text())
    doc["visual"]["objects"]["categoryAxis"][0]["properties"][
        "labelPrecision"]["expr"]["Literal"]["Value"] = "3"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return original, candidate


def _result(path, inherited=True, *, new_warning=False, new_error=False):
    # Both reports generate the same diagnostic with different absolute paths.
    diagnostics = [f"PBIR_INHERITED: unreadable from {path / VISUAL}"] if inherited else []
    if new_error:
        diagnostics += ["PBIR_NEW: introduced bad visual type"]
    warnings = [f"PBIR_WARNING: short label in {path / VISUAL}"]
    if new_warning:
        warnings += ["PBIR_NEW_WARNING: category label was cut"]
    return {
        "status": "invalid" if diagnostics else "valid",
        "errors": diagnostics,
        "warnings": warnings,
        "errorCount": len(diagnostics),
        "warningCount": len(warnings),
    }


def test_inherited_failure_is_not_silently_promoted(tmp_path):
    old, new = _pair(tmp_path)
    sha = source_digest(old)
    calls = []

    def validator(path, *, tool):
        calls.append((path,tool))
        return _result(path)

    receipt = compare_authoring(old, new, [VISUAL], runner=validator,
                                tool="microsoft-cli-pinned")
    assert receipt["comparison"] == "no_new_diagnostics"
    assert receipt["release_verdict"] == "blocked"
    assert receipt["baseline"]["error_count"] == 1
    assert receipt["candidate"]["error_count"] == 1
    assert receipt["new_errors"] == []
    assert receipt["new_warnings"] == []
    assert receipt["baseline_warnings_still_block_production"]
    assert [c[1] for c in calls] == ["microsoft-cli-pinned"] * 2
    assert source_digest(old) == sha


def test_introduced_diagnostics_are_exposed(tmp_path):
    old, new = _pair(tmp_path)

    def validator(path, *, tool):
        return _result(path, new_error=path == new,
                       new_warning=path == new)

    receipt = compare_authoring(old, new, [VISUAL], runner=validator)
    assert receipt["comparison"] == "introduced_diagnostics"
    assert len(receipt["new_errors"]) == 1
    assert len(receipt["new_warnings"]) == 1
    assert receipt["release_verdict"] == "blocked"


def test_fixed_diagnostic_does_not_create_a_false_new_error(tmp_path):
    old,new = _pair(tmp_path)

    def validator(path, *, tool):
        return _result(path, inherited=path == old)

    receipt = compare_authoring(old,new,[VISUAL],runner=validator)
    assert receipt["comparison"] == "no_new_diagnostics"
    assert len(receipt["cleared_errors"]) == 1
    assert receipt["candidate"]["status"] == "valid"
    assert receipt["release_verdict"] == "blocked"


@pytest.mark.parametrize("failure", [
    "unexpected_file", "missing_declaration", "duplicate_declaration",
    "missing_visual", "symlink_escape", "same_root",
])
def test_refuses_ambiguous_or_unsafe_candidate(tmp_path,failure):
    old,new = _pair(tmp_path)
    files=[VISUAL]
    if failure == "unexpected_file":
        (new / "definition"/"report.json").write_text("{}")
    elif failure == "missing_declaration":
        files=["definition/pages/P1/visuals/other/visual.json"]
    elif failure == "duplicate_declaration":
        files=[VISUAL,VISUAL]
    elif failure == "missing_visual":
        (new / VISUAL).unlink()
    elif failure == "symlink_escape":
        path=new/"definition"/"pages"/"P1"/"visuals"/"v1"/"extraneous.json"
        try:
            path.symlink_to(old / VISUAL)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not permitted on this host")
    else:
        new=old
    with pytest.raises(ValueError):
        compare_authoring(old,new,files,
                          runner=lambda path,*,tool: _result(path))


@pytest.mark.parametrize("case", [
    "unavailable", "truncated", "malformed", "contradictory"
])
def test_malformed_provider_cannot_prove_equivalence(tmp_path,case):
    old,new = _pair(tmp_path)

    def validator(path, *, tool):
        payload = _result(path)
        if case == "unavailable":
            payload["status"] = "timeout"
        elif case == "truncated":
            payload["errorCount"] += 1
        elif case == "malformed":
            payload["warnings"] = "warning-not-list"
        else:
            payload["status"] = "valid"
        return payload

    with pytest.raises((ValueError, TypeError),match="validation|diagnostic|contradiction"):
        compare_authoring(old,new,[VISUAL],runner=validator)


def test_cli_read_only_receipt_refuses_existing_output(tmp_path,monkeypatch,capsys):
    old,new = _pair(tmp_path)
    from vqs.powerbi.author import mscli
    monkeypatch.setattr(mscli,"probe",lambda:{
        "available":True,"path":"pinned-microsoft-cli","version":"0.5.0"})
    monkeypatch.setattr(mscli,"validate",lambda path,*,tool,timeout=300:_result(path))
    out=tmp_path/"private-receipt.json"
    args=["compare-authoring",str(old),str(new),"--visual",VISUAL,"--out",str(out)]
    assert main(args)==0
    data=json.loads(out.read_text())
    assert data["comparison"]=="no_new_diagnostics"
    assert data["release_verdict"]=="blocked"
    assert main(args)==2
    assert "blocked" in capsys.readouterr().out


def test_complete_cli_diagnostic_avoids_path_length_false_delta(tmp_path):
    old,new=_pair(tmp_path)
    suffix="a very detailed explanation " * 11

    def validator(path, *, tool):
        message=f"PBIR_THEME: {suffix} theme mismatch at {path / VISUAL}"
        return {
            "status":"invalid", "errors":[message[:300]],"warnings":[],
            "errorCount":1,"warningCount":0,
            "diagnostics_full":{"errors":[message],"warnings":[]}
        }

    result=compare_authoring(old,new,[VISUAL],runner=validator)
    assert result["comparison"]=="no_new_diagnostics"
    assert result["new_errors"]==[]


def test_old_truncated_validator_does_not_fake_delta(tmp_path):
    old,new=_pair(tmp_path)

    def validator(path, *, tool):
        return {"status":"invalid","errors":["E: " + "x"*297],
                "warnings":[],"errorCount":1,"warningCount":0}

    with pytest.raises(ValueError,match="truncated"):
        compare_authoring(old,new,[VISUAL],runner=validator)


def test_mscli_keeps_full_diagnostics_separate_from_bounded_summary():
    from vqs.powerbi.author.mscli import _structured
    msg="Theme file name mismatch in very long local project: " + "x"*370
    data={"data":{"result":"failed","errorCount":1,"warningCount":0,
                  "diagnostics":{"PBIR_THEME_FILE_NAME_MISMATCH":{
                      "severity":"error","items":[{"message":msg}]}}}}
    result=_structured(json.dumps(data),1)
    assert result["status"]=="invalid"
    assert len(result["errors"][0])==300
    assert result["diagnostics_full"]["errors"]==[
        "PBIR_THEME_FILE_NAME_MISMATCH: " + msg]


def test_cli_oversized_untrusted_microsoft_message_fails_closed():
    from vqs.powerbi.author.mscli import _structured
    msg="x"*5000
    data={"data":{"result":"failed","errorCount":1,"warningCount":0,
                  "diagnostics":{"TOO_LARGE":{"severity":"error",
                                               "items":[{"message":msg}]}}}}
    result=_structured(json.dumps(data),1)
    assert result["status"]=="error"
    assert "oversized" in result["note"]


def test_microsoft_project_shortcut_is_part_of_validation_input(tmp_path):
    old,new=_pair(tmp_path)
    old.with_suffix(".pbip").write_text('{"version":"1.0"}')
    new.with_suffix(".pbip").write_text('{"version":"1.1"}')
    with pytest.raises(ValueError,match="shortcuts differ"):
        compare_authoring(old,new,[VISUAL],runner=lambda path,*,tool:_result(path))


def test_referenced_model_change_rejected_even_if_visual_delta_is_valid(tmp_path):
    old,new=_pair(tmp_path)
    model=new.parent/"Model.SemanticModel"/"definition"/"tables"/"T.tmdl"
    assert model.is_file()
    model.write_text("table T\n\tmeasure Changed = 123\n",encoding="utf-8")
    with pytest.raises(ValueError,match="semantic model bytes differ"):
        compare_authoring(old,new,[VISUAL],runner=lambda path,*,tool:_result(path))


def test_real_model_definition_files_are_bound_to_pair(tmp_path):
    old,new=_pair(tmp_path)
    result=compare_authoring(old,new,[VISUAL],runner=lambda path,*,tool:_result(path))
    assert result["semantic_model_definition_files_identical"] is True
    assert result["semantic_model_file_count"] >= 1
