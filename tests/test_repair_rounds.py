"""Bounded-rounds tests: three attempts max, stops restore the candidate.

Unchanged fingerprints, failed invariants, verifier errors, and
exhausted variants stop the cluster; half-applied candidates are
removed, never kept.
"""
import json
from pathlib import Path

import pytest

from vqs.repair.rounds import MAX_ROUNDS, run_rounds

VISUAL = "definition/pages/P1/visuals/cardx/visual.json"
LEAF = ["visual", "objects", "labels", 0, "properties", "fontSize",
        "expr", "Literal", "Value"]


def _make_report(root: Path) -> Path:
    report = root / "original.Report"
    pages = report / "definition" / "pages"
    (pages / "P1" / "visuals" / "cardx").mkdir(parents=True)
    (pages.parent / "pages.json").write_text(json.dumps({"pageOrder": ["P1"]}),
                                      encoding="utf-8")
    (pages.parent / "version.json").write_text(json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "1.0"}),
                                        encoding="utf-8")
    (pages.parent / "report.json").write_text(json.dumps({
        "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                    "report/definition/report/3.3.0/schema.json"),
        "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")
    (pages / "P1" / "page.json").write_text(
        json.dumps({"displayName": "Overview", "width": 1280, "height": 720}),
        encoding="utf-8")
    (pages / "P1" / "visuals" / "cardx" / "visual.json").write_text(
        json.dumps({"name": "cardx",
                    "position": {"x": 24, "y": 104, "width": 296,
                                 "height": 96},
                    "visual": {
                        "visualType": "card",
                        "objects": {"labels": [{"properties": {
                            "fontSize": {"expr": {"Literal": {
                                "Value": "11D"}}}}}]},
                        "query": {"queryState": {}}}}),
        encoding="utf-8")
    return report


def _plan(value):
    return {
        "operations": [{
            "type": "typography.size", "target": "visual",
            "selector": {"page": "P1", "visual": "cardx"},
            "path": LEAF, "value": value, "writes": [VISUAL]}],
        "write_targets": [VISUAL],
        "rollback": "re-materialize from original",
    }


def test_first_passing_variant_repairs(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    calls = []

    def verify(path):
        calls.append(path)
        return {"ok": True, "fingerprint": "fixed",
                "detail": "contrast now passes"}

    result = run_rounds([_plan("14D")], str(original),
                        str(tmp_path / "cand"), verify)
    assert result["verdict"] == "repaired"
    assert result["rounds"] == 1
    assert Path(result["candidate"]).is_dir()
    assert len(calls) == 2  # baseline + round one


def test_second_variant_repairs_after_first_fails(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    scripted = iter([{"ok": False, "fingerprint": "defect"},
                     {"ok": False, "fingerprint": "closer"},
                     {"ok": True, "fingerprint": "fixed"}])

    def verify(path):
        return next(scripted)

    result = run_rounds([_plan("12D"), _plan("14D")], str(original),
                        str(tmp_path / "cand"), verify)
    assert result["verdict"] == "repaired"
    assert result["rounds"] == 2
    assert not Path(str(tmp_path / "cand") + "-round1").exists()
    assert Path(result["candidate"]).is_dir()


def test_unchanged_fingerprint_stops_and_restores(tmp_path: Path) -> None:
    original = _make_report(tmp_path)

    def verify(path):
        return {"ok": False, "fingerprint": "defect"}

    result = run_rounds([_plan("14D"), _plan("16D")], str(original),
                        str(tmp_path / "cand"), verify)
    assert result["verdict"] == "stopped"
    assert "unchanged" in result["reason"]
    assert len(result["records"]) == 1
    assert not Path(str(tmp_path / "cand") + "-round1").exists()


def test_failed_invariants_and_verifier_errors_stop(tmp_path: Path) -> None:
    original = _make_report(tmp_path)

    def bad_verify(path):
        if "round" in path:
            return {"ok": False, "fingerprint": "other",
                    "failed_invariants": True}
        return {"ok": False, "fingerprint": "defect"}

    result = run_rounds([_plan("14D")], str(original),
                        str(tmp_path / "cand"), bad_verify)
    assert result["verdict"] == "stopped"
    assert "invariants" in result["reason"]

    def boom(path):
        raise RuntimeError("verifier exploded")

    result = run_rounds([_plan("14D")], str(original),
                        str(tmp_path / "cand2"), boom)
    assert result["verdict"] == "stopped"
    assert "verifier error" in result["reason"]


def test_contradictory_ok_with_failed_invariants_stops(
        tmp_path: Path) -> None:
    original = _make_report(tmp_path)

    def lying_verify(path):
        if "round" in path:
            return {"ok": True, "fingerprint": "fixed",
                    "failed_invariants": ["answers"]}
        return {"ok": False, "fingerprint": "defect"}

    result = run_rounds([_plan("14D")], str(original),
                        str(tmp_path / "cand"), lying_verify)
    assert result["verdict"] == "stopped"
    assert "invariants" in result["reason"]
    assert not Path(str(tmp_path / "cand") + "-round1").exists()


def test_repeated_non_baseline_fingerprint_stops(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    scripted = iter([{"ok": False, "fingerprint": "defect"},
                     {"ok": False, "fingerprint": "closer"},
                     {"ok": False, "fingerprint": "closer"}])

    def verify(path):
        return next(scripted)

    result = run_rounds([_plan("12D"), _plan("14D"), _plan("16D")],
                        str(original), str(tmp_path / "cand"), verify)
    assert result["verdict"] == "stopped"
    assert "unchanged" in result["reason"]
    assert len(result["records"]) == 2
    assert not Path(str(tmp_path / "cand") + "-round2").exists()


def test_round_policy_bounds(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    assert MAX_ROUNDS == 3
    with pytest.raises(ValueError, match="max_rounds"):
        run_rounds([_plan("14D")], str(original), str(tmp_path / "c"),
                   lambda path: {}, max_rounds=4)
    with pytest.raises(ValueError, match="max_rounds"):
        run_rounds([_plan("14D")], str(original), str(tmp_path / "c"),
                   lambda path: {}, max_rounds=0)
    assert run_rounds([], str(original), str(tmp_path / "c"),
                      lambda path: {})["verdict"] == "stopped"
    count = 0

    def always_fingerprintless(path):
        return {"ok": False, "fingerprint": ""}

    result = run_rounds([_plan("14D")], str(original),
                        str(tmp_path / "c2"), always_fingerprintless)
    assert result["reason"] == "defect fingerprint missing"

    def drifting(path):
        nonlocal count
        count += 1
        return {"ok": False, "fingerprint": f"shape-{count}"}

    variants = [_plan("12D"), _plan("14D"), _plan("16D"), _plan("18D")]
    result = run_rounds(variants, str(original), str(tmp_path / "c3"),
                        drifting)
    assert result["verdict"] == "stopped"
    assert result["reason"] == "rounds exhausted"
    assert len(result["records"]) == 3


def test_blocked_application_stops(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    bad = {"operations": [{"type": "shell", "target": "os"}],
           "write_targets": [VISUAL], "rollback": "x"}
    result = run_rounds([bad], str(original), str(tmp_path / "cand"),
                        lambda path: {"ok": True, "fingerprint": "f"})
    assert result["verdict"] == "stopped"
    assert result["reason"] == "plan application blocked"
