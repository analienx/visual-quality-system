"""Premium design contract is useful, honest, and fail-closed on stale intent."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from vqs.cli import main
from vqs.pbir import report_context
from vqs.premium import audit, contract_template, markdown

SOURCE = Path(__file__).parent / "powerbi" / "fixtures" / "mini_report"


def _report(tmp_path: Path) -> Path:
    target = tmp_path / "A.Report"
    shutil.copytree(SOURCE, target)
    return target


def _write_cards(report: Path, *, off_grid: bool) -> None:
    original = report / "definition/pages/P1/visuals/cardx/visual.json"
    for index, x in enumerate((344, 708 if off_grid else 664), 1):
        folder = original.parent.parent / f"peer{index}"
        folder.mkdir()
        card = json.loads(original.read_text(encoding="utf-8"))
        card["name"] = f"peer{index}"
        card["position"].update({"x": x, "y": 104, "z": index + 4})
        (folder / "visual.json").write_text(json.dumps(card), encoding="utf-8")


def test_template_is_source_bound_and_does_not_invent_intent(tmp_path):
    report = _report(tmp_path)
    template = contract_template(report_context(report))
    assert template["pages"][0]["audience"] is None
    assert template["pages"][0]["focal_visual_id"] is None
    result = audit(str(report), contract=template)
    assert result["status"] == "advisory"
    assert result["source_sha256"] == template["source_sha256"]
    assert "G2/G4/G6" in " ".join(result["known_limits"])
    assert "does **not** certify" in markdown(result)


def test_gutter_regression_detected_with_visual_ids(tmp_path):
    report = _report(tmp_path)
    _write_cards(report, off_grid=True)
    result = audit(str(report))
    hit = next(f for f in result["findings"] if f["rule"] == "spacing.peer_gutters")
    assert hit["importance"] == "high"
    assert {"cardx", "peer1", "peer2"} == set(hit["visual_ids"])
    assert hit["evidence"]["gaps_pbir"] == [24.0, 68.0]
    assert result["top_three"][0] == hit
    # Deliberate alignment must clear the exact same source-level detector.
    good = _report(tmp_path / "aligned")
    _write_cards(good, off_grid=False)
    assert not any(f["rule"] == "spacing.peer_gutters" for f in audit(str(good))["findings"])


def test_contract_budget_and_owner_focal_are_proven_not_guessed(tmp_path):
    report = _report(tmp_path)
    _write_cards(report, off_grid=False)
    # Make a grouped card look like a peer chart, preserving a small focal
    # footprint and comparing its declared area against other data visuals.
    chart_dir = report / "definition/pages/P1/visuals/peer1"
    chart = json.loads((chart_dir / "visual.json").read_text(encoding="utf-8"))
    chart["visual"]["visualType"] = "clusteredBarChart"
    (chart_dir / "visual.json").write_text(json.dumps(chart), encoding="utf-8")
    chart_dir = report / "definition/pages/P1/visuals/peer2"
    chart = json.loads((chart_dir / "visual.json").read_text(encoding="utf-8"))
    chart["visual"]["visualType"] = "clusteredBarChart"
    chart["position"].update({"width": 450, "height": 250})
    (chart_dir / "visual.json").write_text(json.dumps(chart), encoding="utf-8")
    template = contract_template(report_context(report))
    template["pages"][0]["archetype"] = "executive"
    template["pages"][0]["focal_visual_id"] = "peer1"
    template["pages"][0]["max_data_coverage_pct"] = 10
    result = audit(str(report), contract=template)
    assert {"hierarchy.focal", "density.data_coverage"} <= {
        f["rule"] for f in result["findings"]}
    template["pages"][0]["exceptions"] = [
        "hierarchy.focal", "density.data_coverage"]
    filtered = audit(str(report), contract=template)
    assert not {"hierarchy.focal", "density.data_coverage"} & {
        f["rule"] for f in filtered["findings"]}


def test_stale_and_malformed_contracts_block_instead_of_pass(tmp_path):
    report = _report(tmp_path)
    template = contract_template(report_context(report))
    template["source_sha256"] = "0" * 64
    import pytest
    with pytest.raises(ValueError, match="stale"):
        audit(str(report), contract=template)
    template = contract_template(report_context(report))
    template["pages"][0]["focal_visual_id"] = "ghost"
    with pytest.raises(ValueError, match="not present"):
        audit(str(report), contract=template)


def test_cli_init_contract_and_advisory_report_never_overwrite(tmp_path, capsys):
    report = _report(tmp_path)
    intent = tmp_path / "intent.json"
    assert main(["premium", str(report), "--init-contract", str(intent)]) == 0
    assert intent.is_file()
    assert main(["premium", str(report), "--init-contract", str(intent)]) == 2
    capsys.readouterr()
    output = tmp_path / "audit.md"
    assert main(["premium", str(report), "--contract", str(intent),
                 "--out", str(output)]) == 0
    assert output.read_text(encoding="utf-8").startswith("# Premium Power BI")
    assert main(["premium", str(report), "--contract", str(intent),
                 "--out", str(output)]) == 2
    assert main(["premium", str(report), "--format", "json"]) == 0
    output_json = capsys.readouterr().out
    assert "\"schema\": \"vqs.premium-preflight/1\"" in output_json


def test_render_claim_is_never_inferred_from_preflight(tmp_path):
    report = _report(tmp_path)
    result = audit(str(report))
    assert result["status"] == "advisory"
    assert "desktop renders" in " ".join(result["known_limits"]).lower()
    assert result["top_three"] == result["findings"][:3]


def test_cli_reports_findings_without_granting_release(tmp_path, capsys):
    report = _report(tmp_path)
    _write_cards(report, off_grid=True)
    rc = main(["premium", str(report), "--format", "json"])
    assert rc == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "findings"
    assert any(f["rule"] == "spacing.peer_gutters" for f in result["top_three"])
    assert "G2/G4/G6" in " ".join(result["known_limits"])


def test_series_collision_is_reported_with_true_theme_source(
        tmp_path: Path) -> None:
    report = _report(tmp_path)
    theme_name = "CollisionTest.json"
    definition = report / "definition/report.json"
    metadata = json.loads(definition.read_text(encoding="utf-8"))
    metadata.setdefault("themeCollection", {})["customTheme"] = {
        "name": theme_name, "type": "RegisteredResources"}
    definition.write_text(json.dumps(metadata), encoding="utf-8")
    resource_dir = report / "StaticResources/RegisteredResources"
    resource_dir.mkdir(parents=True, exist_ok=True)
    (resource_dir / theme_name).write_text(json.dumps({
        "dataColors": ["#777777", "#797979", "#828282", "#848484",
                       "#898989", "#8A8A8A", "#909090", "#919191"]}),
        encoding="utf-8")
    visual = report / "definition/pages/P1/visuals/cardx/visual.json"
    v = json.loads(visual.read_text(encoding="utf-8"))
    v["visual"]["visualType"] = "lineChart"
    visual.write_text(json.dumps(v), encoding="utf-8")
    result = audit(str(report))
    risk = next(f for f in result["findings"]
                if f["rule"] == "color.palette_series_collision")
    assert risk["page_id"] == "P1"
    assert risk["importance"] == "high"
    assert risk["evidence"]["scope"] == (
        "candidate theme palette, not rendered pixels")
    assert risk["evidence"]["worst_pairs"]


def test_numeric_category_gradients_are_advisory_not_semantic_overrides() -> None:
    report = (Path(__file__).parents[1]
              / "examples/contoso-retail/Contoso Retail.Report")
    result = audit(str(report))
    risks = [f for f in result["findings"]
             if f["rule"] == "color.numeric_gradient_category_ambiguity"]
    assert risks
    assert all(f["importance"] == "low" for f in risks)
    assert all(f["evidence"]["rendered_distinction"] == "not verified"
               for f in risks)
