"""P18: a detector failure becomes a bounded candidate, never a redesign.

The archived, checksum-pinned pre-repair Contoso PBIP gives us independent
source geometry and query bindings, not a synthetic best-case grid.
"""
from __future__ import annotations

import copy
import json
import zipfile
from pathlib import Path

import pytest

from scripts.contoso_p12_layout_repair import FIXTURE, PAGE, VISUALS, migrate
from scripts.contoso_p18_candidate_probe import run as pinned_probe
from vqs.design_rules import layout_composition
from vqs.pipeline import propose_candidates, review_report
from vqs.powerbi.measure import measure_report
from vqs.repair.composition_reflow import solve_composition
from vqs.repair.execute import apply_plan, tree_digest
from vqs.repair.recipes import RecipeError, bind_geometry, bind_leaf
from vqs.repair.regress import verify_candidate
from vqs.repair.synthesize import synthesize_plan


@pytest.fixture()
def p10(tmp_path: Path) -> Path:
    project = tmp_path / "p10"
    project.mkdir()
    with zipfile.ZipFile(FIXTURE) as archive:
        archive.extractall(project)
    return project


def _measured(project: Path) -> tuple[dict, dict]:
    facts = measure_report(str(project / "Contoso Retail.Report"))
    rule = layout_composition(facts["rules"]["layout.composition"]["pages"])
    return facts, rule


def _plan(project: Path) -> dict:
    facts, rule = _measured(project)
    assert rule["status"] == "fail"
    return synthesize_plan(
        [{"check": "layout.composition", "status": "fail", "detail": rule}],
        facts, source_run_id="p18-isolated", source_sha256="pinned-source")


def _read_visual(project: Path, name: str) -> dict:
    return json.loads((project / VISUALS / name / "visual.json")
                      .read_text(encoding="utf-8-sig"))


def _change_visual(project: Path, name: str, mutator) -> None:
    path = project / VISUALS / name / "visual.json"
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    mutator(doc)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_p10_source_bound_reflow_repairs_three_defects_and_preserves_query(p10, tmp_path):
    result = _plan(p10)
    assert not result["decisions"]
    assert result["plan"] is not None
    ops = result["plan"]["operations"]
    assert len(ops) == 13
    assert {op["type"] for op in ops} == {
        "theme.set", "chart.resize", "spacing.adjust"}
    assert {op["selector"]["page"] for op in ops} == {PAGE}
    assert len(result["plan"]["write_targets"]) == 8
    assert all("old" in op and op["writes"] for op in ops)
    assert result["plan"]["rollback"] == "re-materialize from original"

    before = tree_digest(p10 / "Contoso Retail.Report")
    candidate = tmp_path / "candidate" / "Contoso Retail.Report"
    applied = apply_plan(result["plan"], str(p10 / "Contoso Retail.Report"),
                         str(candidate))
    assert applied["verdict"] == "applied", applied
    assert len(applied["edits"]) == 13
    assert verify_candidate(p10 / "Contoso Retail.Report", candidate,
                            applied["edits"])["verdict"] == "pass"
    assert tree_digest(p10 / "Contoso Retail.Report") == before
    _, policy = _measured(candidate.parent)
    assert policy["status"] == "pass", policy

    # Exact semantics (visual query, filters, formatting and model) remain
    # unchanged; only eight declared visual.json geometry/title leaves change.
    for vid in {op["selector"]["visual"] for op in ops}:
        src, dst = _read_visual(p10, vid), _read_visual(candidate.parent, vid)
        assert src["visual"].get("query") == dst["visual"].get("query")
        assert src.get("filterConfig") == dst.get("filterConfig")
        assert src.get("parentGroupName") == dst.get("parentGroupName")
    assert _read_visual(candidate.parent, "sales-by-country")["position"] == {
        **_read_visual(p10, "sales-by-country")["position"],
        "width": 608, "y": 252}
    assert _read_visual(candidate.parent, "sales-by-channel")["position"]["x"] == 648
    assert _read_visual(candidate.parent, "what-drives-sales")["position"]["y"] == 448
    assert _read_visual(candidate.parent, "card-sales")["position"]["height"] == 108
    assert (_read_visual(candidate.parent, "slicer-year")["visual"]
            ["visualContainerObjects"]["title"][0]
            ["properties"]["show"]["expr"]["Literal"]["Value"] == "false")


def test_repeated_sources_yield_byte_for_byte_identical_reflow(p10):
    first, second = _plan(p10), _plan(p10)
    assert first["plan"] == second["plan"]
    assert first["candidates"] == second["candidates"]


def test_pinned_probe_produces_reviewable_disposable_receipt(tmp_path):
    workspace = tmp_path / "isolated-probe"
    result = pinned_probe(workspace)
    assert result["verdict"] == "candidate_only", result
    assert result["source_unchanged"] is True
    assert result["composition_before"] == "fail"
    assert result["composition_after"] == "pass"
    assert result["repair_confinement"] == "pass"
    assert result["changed_visual_files"] == 8
    assert result["operations"] == 13
    assert result["independent_acceptance"] == "blocked"
    with pytest.raises(FileExistsError):
        pinned_probe(workspace)


def test_existing_review_to_propose_route_includes_composition_fixes(p10, tmp_path):
    facts, rule = _measured(p10)
    assert rule["status"] == "fail"
    directory = str(tmp_path / "sealed-runs")
    reviewed = review_report(facts=facts, run_root=directory, run_id="p18-layout")
    assert reviewed["run_dir"]
    proposed = propose_candidates(directory, "p18-layout", facts)
    assert proposed["verdict"] == "pass", proposed
    assert proposed["plan"] is not None
    assert "layout.composition" in proposed["plan"]["finding_checks"]
    assert any(item["op"] == "chart.resize" for item in proposed["candidates"])
    assert any(item["op"] == "spacing.adjust" for item in proposed["candidates"])
    assert any(item["op"] == "theme.set" for item in proposed["candidates"])


def test_composition_only_measured_facts_still_invalidate_all_pages(p10):
    facts, verdict = _measured(p10)
    pages = facts["rules"]["layout.composition"]["pages"]
    result = synthesize_plan(
        [{"check": "layout.composition", "status": "fail", "detail": verdict}],
        {"rules": {"layout.composition": {"pages": pages}}})
    assert result["plan"] is not None
    assert set(result["plan"]["affected_pages"]) == {
        page["page"] for page in pages}  # the caption op is conservatively shared


def test_already_repaired_p12_has_no_candidate(tmp_path):
    project = tmp_path / "p12"
    migrate(project)
    facts, rule = _measured(project)
    assert rule["status"] == "pass"
    edits, held = solve_composition(facts["rules"]["layout.composition"]["pages"])
    assert edits == held == []


def test_single_too_tall_card_is_repaired_without_moving_other_panels(tmp_path):
    project = tmp_path / "p12"
    migrate(project)
    _change_visual(project, "card-units", lambda doc: doc["position"].update(height=140))
    result = _plan(project)
    assert not result["decisions"], result["decisions"]
    assert [(op["selector"]["visual"], op["path"], op["value"])
            for op in result["plan"]["operations"]] == [
                ("card-units", ["position", "height"], 108)]


def test_horizontal_drift_does_not_move_vertical_geometry(tmp_path):
    project = tmp_path / "p12"
    migrate(project)
    _change_visual(project, "sales-by-channel", lambda doc: doc["position"].update(
        x=664, width=592))
    _change_visual(project, "what-drives-sales", lambda doc: doc["position"].update(
        x=664, width=592))
    result = _plan(project)
    assert result["plan"] is not None
    assert len(result["plan"]["operations"]) == 4
    assert all(op["path"][-1] in ("x", "width")
               for op in result["plan"]["operations"])


def test_intermediate_placement_moves_left_before_expanding_width(tmp_path):
    project = tmp_path / "p12"
    migrate(project)
    for vid in ("sales-by-channel", "what-drives-sales"):
        _change_visual(project, vid, lambda doc: doc["position"].update(
            x=680, width=576))
    ops = _plan(project)["plan"]["operations"]
    for vid in ("sales-by-channel", "what-drives-sales"):
        axes = [op["path"][-1] for op in ops if op["selector"]["visual"] == vid]
        assert axes == ["x", "width"]  # expanding at x=680 would exceed 1280
    applied = apply_plan({"operations": ops,
                          "write_targets": sorted({target for op in ops
                                                   for target in op["writes"]}),
                          "rollback": "re-materialize from original"},
                         str(project / "Contoso Retail.Report"),
                         str(tmp_path / "candidate" / "Contoso Retail.Report"))
    assert applied["verdict"] == "applied", applied


def test_collision_refuses_all_geometry_but_keeps_independent_caption(p10):
    facts, rule = _measured(p10)
    assert rule["status"] == "fail"
    page = next(p for p in facts["rules"]["layout.composition"]["pages"]
                if p["page"] == PAGE)
    page["visuals"].append({"visual": "protected-gap", "type": "textbox",
                             "position": {"x": 948, "y": 260, "width": 8,
                                          "height": 12}})
    generated = synthesize_plan(
        [{"check": "layout.composition", "status": "fail", "detail": rule}], facts)
    assert len(generated["candidates"]) == 1  # the separate caption fix
    assert generated["candidates"][0]["op"] == "theme.set"
    assert any("increase overlap" in d["reason"] for d in generated["decisions"])


def test_missing_other_visual_geometry_blocks_reflow(p10):
    facts, rule = _measured(p10)
    page = next(p for p in facts["rules"]["layout.composition"]["pages"]
                if p["page"] == PAGE)
    page["visuals"].append({"visual": "opaque-widget", "type": "textbox",
                             "position": None})
    result = synthesize_plan(
        [{"check": "layout.composition", "status": "fail", "detail": rule}], facts)
    assert result["plan"] is None
    assert any("unmeasured" in d["reason"] for d in result["decisions"])


def test_measured_geometry_drift_refuses_stale_op():
    doc = {"position": {"x": 24, "y": 120, "width": 296, "height": 104}}
    op = {"type": "chart.resize", "target": "visual",
          "selector": {"page": "P1", "visual": "card"},
          "path": ["position", "height"], "old": 140, "value": 108}
    with pytest.raises(RecipeError, match="precondition failed"):
        bind_geometry(op, doc, (1280, 720))


def test_redundant_title_repair_refuses_stale_literal(p10):
    doc = _read_visual(p10, "slicer-year")
    doc["visual"]["visualContainerObjects"]["title"][0][
        "properties"]["show"]["expr"]["Literal"]["Value"] = "false"
    op = {"type": "theme.set", "target": "visual",
          "selector": {"page": PAGE, "visual": "slicer-year"},
          "path": ["visual", "visualContainerObjects", "title", 0,
                   "properties", "show", "expr", "Literal", "Value"],
          "old": "true", "value": "false"}
    with pytest.raises(RecipeError, match="precondition failed"):
        bind_leaf(op, doc)


@pytest.mark.parametrize("tamper", [
    lambda p: p["visuals"][0].update(visual="bad/selector"),
    lambda p: p.update(width=float("nan")),
])
def test_invalid_or_unsafe_source_bindings_never_emit_geometry(p10, tamper):
    facts, _rule = _measured(p10)
    pages = copy.deepcopy(facts["rules"]["layout.composition"]["pages"])
    page = next(p for p in pages if p["page"] == PAGE)
    tamper(page)
    edits, held = solve_composition(pages)
    assert all(edit["page"] != PAGE for edit in edits)
    assert held
