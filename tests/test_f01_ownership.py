"""F01 RED: executor cleanup must not touch directories it did not create.

Pre-existing candidates, self/nested aliases, and stale round dirs
must block with every byte preserved; only attempt-owned partial
copies may be removed.
"""
import json
import os
from pathlib import Path

import pytest

from vqs.repair.execute import apply_plan, tree_digest
from vqs.repair.rounds import run_rounds

VISUAL = "definition/pages/P1/visuals/cardx/visual.json"


def _make_report(root: Path, name: str = "original.Report") -> Path:
    report = root / name
    pages = report / "definition" / "pages"
    (pages / "P1" / "visuals" / "cardx").mkdir(parents=True)
    (pages / "pages.json").write_text(json.dumps({"pageOrder": ["P1"]}),
                                      encoding="utf-8")
    (pages / "P1" / "page.json").write_text(
        json.dumps({"displayName": "O", "width": 1280, "height": 720}),
        encoding="utf-8")
    (pages / "P1" / "visuals" / "cardx" / "visual.json").write_text(
        json.dumps({"name": "cardx",
                    "position": {"x": 1, "y": 2, "width": 3, "height": 4},
                    "visual": {
                        "visualType": "card",
                        "objects": {"labels": [{"properties": {
                            "fontSize": {"expr": {"Literal": {
                                "Value": "11D"}}}}}]},
                        "query": {"queryState": {"Values": {"projections": [
                            {"queryRef": "M.X",
                             "field": {"Measure": {}},
                             "active": True}]}}}}}),
        encoding="utf-8")
    return report


def _plan(**overrides):
    base = {
        "operations": [{
            "type": "typography.size", "target": "visual",
            "selector": {"page": "P1", "visual": "cardx"},
            "path": ["visual", "objects", "labels", 0, "properties",
                     "fontSize", "expr", "Literal", "Value"],
            "value": "14D", "writes": [VISUAL]}],
        "write_targets": [VISUAL],
        "rollback": "re-materialize from original",
    }
    base.update(overrides)
    return base


def test_f01_preexisting_candidate_preserved(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    candidate = tmp_path / "cand"
    candidate.mkdir()
    sentinel = candidate / "prior-evidence.json"
    sentinel.write_text(json.dumps({"owner": "another run"}),
                        encoding="utf-8")
    before = tree_digest(candidate)
    result = apply_plan(_plan(), str(original), str(candidate))
    assert result["verdict"] == "blocked"
    assert result["stage"] == "materialize"
    assert sentinel.is_file()
    assert tree_digest(candidate) == before


def test_f01_self_alias_candidate_preserved(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    before = tree_digest(original)
    result = apply_plan(_plan(), str(original), str(original))
    assert result["verdict"] == "blocked"
    assert tree_digest(original) == before
    assert (original / VISUAL).is_file()


def test_f01_nested_candidate_preserved(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    nested = original / "candidate-nest"
    nested.mkdir()
    (nested / "sentinel.txt").write_text("do not touch", encoding="utf-8")
    before = tree_digest(original)
    result = apply_plan(_plan(), str(original), str(nested))
    assert result["verdict"] == "blocked"
    assert tree_digest(original) == before
    assert (nested / "sentinel.txt").is_file()


@pytest.mark.skipif(os.path.normcase("A") != "a",
                    reason="requires case-insensitive path semantics")
def test_f01_case_alias_candidate_preserved(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    candidate = tmp_path / "CAND"
    candidate.mkdir()
    (candidate / "sentinel.txt").write_text("do not touch",
                                            encoding="utf-8")
    before = tree_digest(candidate)
    result = apply_plan(_plan(), str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert (candidate / "sentinel.txt").is_file()
    assert tree_digest(candidate) == before


@pytest.mark.skipif(os.name != "nt", reason="junctions need Windows")
def test_f01_junction_alias_preserved(tmp_path: Path) -> None:
    import subprocess

    original = _make_report(tmp_path)
    alias = tmp_path / "alias-cand"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(original)],
        capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        pytest.skip(f"mklink unavailable: {completed.stderr[:80]}")
    before = tree_digest(original)
    result = apply_plan(_plan(), str(original), str(alias))
    assert result["verdict"] == "blocked"
    assert os.path.lexists(alias)
    assert tree_digest(original) == before


def test_f01_stale_round_dir_preserved(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    stale = tmp_path / "cand-round1"
    stale.mkdir()
    (stale / "sentinel.txt").write_text("prior round", encoding="utf-8")

    def _verify(path: str) -> dict:
        return {"ok": True, "fingerprint": "fixed"}

    result = run_rounds([_plan()], str(original), str(tmp_path / "cand"),
                        _verify)
    assert result["verdict"] == "stopped"
    assert (stale / "sentinel.txt").is_file()


def test_f01_owned_partial_copy_still_removed(
        tmp_path: Path, monkeypatch) -> None:
    import shutil

    import vqs.repair.execute as execute

    original = _make_report(tmp_path)
    real_copy = shutil.copyfile

    def _flaky(source, target, **kwargs):
        if str(target).endswith("visual.json"):
            raise OSError("simulated copy failure")
        return real_copy(source, target, **kwargs)

    monkeypatch.setattr(execute.shutil, "copyfile", _flaky)
    with pytest.raises(Exception, match="simulated copy failure"):
        execute.materialize_candidate(str(original),
                                      str(tmp_path / "cand"))
    assert not (tmp_path / "cand").exists()
