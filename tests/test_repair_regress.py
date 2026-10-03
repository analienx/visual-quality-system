"""Regression-gate tests (criterion 16): confinement, IDs, geometry.

Undeclared changes, hidden categories, broken bookmarks, and cropped
neighbors fail; rerender requirements name affected pages plus
neighbors; render verification blocks without fresh manifests.
"""
import json
from pathlib import Path

from vqs.repair.execute import apply_plan
from vqs.repair.regress import (
    rerender_requirements,
    verify_candidate,
    verify_renders,
)

VISUAL = "definition/pages/P1/visuals/cardx/visual.json"
LEAF = ["visual", "objects", "labels", 0, "properties", "fontSize",
        "expr", "Literal", "Value"]


def _visual_doc(name, x=24, y=104):
    return {"name": name,
            "position": {"x": x, "y": y, "width": 296, "height": 96,
                         "tabOrder": 4, "z": 4},
            "visual": {
                "visualType": "card",
                "objects": {"labels": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "11D"}}}}}]},
                "query": {"queryState": {"Values": {"projections": [
                    {"queryRef": "Fact Sales.Revenue",
                     "field": {"Measure": {}}, "active": True}]}}}}}


def _make_report(root: Path, name: str = "original.Report") -> Path:
    report = root / name
    pages = report / "definition" / "pages"
    (pages / "P1" / "visuals" / "cardx").mkdir(parents=True)
    (pages / "P1" / "visuals" / "neighbor").mkdir(parents=True)
    (pages / "pages.json").write_text(json.dumps({"pageOrder": ["P1"]}),
                                      encoding="utf-8")
    (pages / "P1" / "page.json").write_text(
        json.dumps({"displayName": "Overview", "width": 1280, "height": 720}),
        encoding="utf-8")
    (pages / "P1" / "visuals" / "cardx" / "visual.json").write_text(
        json.dumps(_visual_doc("cardx")), encoding="utf-8")
    (pages / "P1" / "visuals" / "neighbor" / "visual.json").write_text(
        json.dumps(_visual_doc("neighbor", x=400)), encoding="utf-8")
    (pages / "P1" / "bookmarks.json").write_text(
        json.dumps({"bookmarks": [{"name": "b1", "visuals": ["cardx"]}]}),
        encoding="utf-8")
    return report


def _plan(**overrides):
    base = {
        "operations": [{
            "type": "typography.size", "target": "visual",
            "selector": {"page": "P1", "visual": "cardx"},
            "path": LEAF, "value": "14D", "writes": [VISUAL]}],
        "write_targets": [VISUAL],
        "rollback": "re-materialize from original",
    }
    base.update(overrides)
    return base


def _applied(tmp_path: Path):
    original = _make_report(tmp_path)
    result = apply_plan(_plan(), str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "applied"
    return original, tmp_path / "cand", result["edits"]


def test_declared_repair_passes(tmp_path: Path) -> None:
    original, candidate, edits = _applied(tmp_path)
    verdict = verify_candidate(original, candidate, edits)
    assert verdict["verdict"] == "pass"
    assert verdict["checks"] == ["inventory", "confinement", "identities",
                                 "geometry"]


def test_undeclared_neighbor_and_bookmark_changes_fail(
        tmp_path: Path) -> None:
    original, candidate, edits = _applied(tmp_path)
    neighbor = candidate / "definition/pages/P1/visuals/neighbor/visual.json"
    doc = json.loads(neighbor.read_text(encoding="utf-8"))
    doc["position"]["x"] = 900
    neighbor.write_text(json.dumps(doc), encoding="utf-8")
    verdict = verify_candidate(original, candidate, edits)
    assert verdict["verdict"] == "fail"
    assert verdict["problems"][0]["rule"] == "undeclared_change"
    bookmarks = candidate / "definition/pages/P1/bookmarks.json"
    bookmarks.write_text(json.dumps({"bookmarks": []}), encoding="utf-8")
    verdict = verify_candidate(original, candidate, edits)
    assert verdict["verdict"] == "fail"
    assert any(row["file"].endswith("bookmarks.json")
               for row in verdict["problems"])


def test_hidden_category_in_touched_file_fails(tmp_path: Path) -> None:
    original, candidate, edits = _applied(tmp_path)
    target = candidate / VISUAL
    doc = json.loads(target.read_text(encoding="utf-8"))
    doc["visual"]["query"]["queryState"]["Values"]["projections"] = []
    target.write_text(json.dumps(doc), encoding="utf-8")
    verdict = verify_candidate(original, candidate, edits)
    assert verdict["verdict"] == "fail"
    assert any(row["rule"] == "undeclared_change"
               and "query" in row["path"]
               for row in verdict["problems"])


def test_added_or_removed_files_fail(tmp_path: Path) -> None:
    original, candidate, edits = _applied(tmp_path)
    newcomer = candidate / "definition/pages/P1/visuals/newbie"
    newcomer.mkdir()
    (newcomer / "visual.json").write_text("{}", encoding="utf-8")
    verdict = verify_candidate(original, candidate, edits)
    assert verdict["verdict"] == "fail"
    assert verdict["problems"][0]["rule"] == "file_added"
    (newcomer / "visual.json").unlink()
    newcomer.rmdir()
    (candidate / VISUAL).unlink()
    verdict = verify_candidate(original, candidate, edits)
    assert verdict["verdict"] == "fail"
    assert verdict["problems"][0]["rule"] == "file_removed"
    verdict = verify_candidate(original, candidate, edits,
                               approved_removals={"cardx"})
    assert verdict["verdict"] == "fail"
    assert any(row["rule"] == "declared_target_missing"
               for row in verdict["problems"])


def test_approved_removal_of_unedited_visual_passes(
        tmp_path: Path) -> None:
    original, candidate, edits = _applied(tmp_path)
    (candidate / "definition/pages/P1/visuals/neighbor"
     / "visual.json").unlink()
    verdict = verify_candidate(original, candidate, edits,
                               approved_removals={"neighbor"})
    assert verdict["verdict"] == "pass"


def test_bad_geometry_fails(tmp_path: Path) -> None:
    original, candidate, edits = _applied(tmp_path)
    target = candidate / VISUAL
    doc = json.loads(target.read_text(encoding="utf-8"))
    doc["position"]["width"] = 5000
    target.write_text(json.dumps(doc), encoding="utf-8")
    verdict = verify_candidate(original, candidate, edits)
    assert verdict["verdict"] == "fail"
    assert any(row["rule"] == "visual_cropped_or_outside"
               for row in verdict["problems"])
    doc["position"]["width"] = float("nan")
    target.write_text(json.dumps(doc), encoding="utf-8")
    verdict = verify_candidate(original, candidate, edits)
    assert verdict["verdict"] == "fail"
    assert any(row["rule"] == "visual_position_nonfinite"
               for row in verdict["problems"])


def test_rerender_requirements_cover_neighbors_and_shared(
        tmp_path: Path) -> None:
    op = _plan()["operations"][0]
    assert rerender_requirements([op], ["P1", "P2", "P3"]) == {
        "verdict": "ready", "pages": ["P1", "P2"], "shared": False,
        "reasons": ["bound page only"]}
    op2 = dict(op, selector={"page": "P2", "visual": "cardx"})
    assert rerender_requirements([op2], ["P1", "P2", "P3"])["pages"] == [
        "P1", "P2", "P3"]
    theme = dict(op, type="theme.set")
    assert rerender_requirements([theme], ["P1", "P2"]) == {
        "verdict": "ready", "pages": ["P1", "P2"], "shared": True,
        "reasons": ["shared presentation change invalidates all pages"]}
    assert rerender_requirements([{"type": "theme.set"}],
                                 ["P1"])["verdict"] == "blocked"


def test_verify_renders_blocks_without_fresh_manifests() -> None:
    fresh = {"source_sha256": "cand-digest",
             "page_images": {"P1": "p1.png", "P2": "p2.png"}}
    assert verify_renders(["P1", "P2"], [fresh],
                          "cand-digest")["verdict"] == "pass"
    stale = {"source_sha256": "orig-digest",
             "page_images": {"P1": "p1.png", "P2": "p2.png"}}
    verdict = verify_renders(["P1", "P2"], [stale], "cand-digest")
    assert verdict["verdict"] == "blocked"
    assert verdict["missing_pages"] == ["P1", "P2"]
    partial = {"source_sha256": "cand-digest",
               "page_images": {"P1": "p1.png"}}
    verdict = verify_renders(["P1", "P2"], [partial, "junk", {}],
                             "cand-digest")
    assert verdict["verdict"] == "blocked"
    assert verdict["missing_pages"] == ["P2"]
