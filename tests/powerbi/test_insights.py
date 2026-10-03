"""Emitter tests: page-insight inventory, trees, maps, categories."""
import json
from pathlib import Path

import pytest

from vqs.powerbi.insights import _column_categories, page_insights
from vqs.powerbi.measure import measure_report

FIXTURES = Path(__file__).parent / "fixtures"
REPORT = str(FIXTURES / "insight_report")
MINI = str(FIXTURES / "mini_report")


def test_inventory_records_titles_roles_and_refs() -> None:
    pages = page_insights(REPORT)["pages"]
    assert [(p["page"], p["display_name"]) for p in pages] == [
        ("P1", "Dup page"), ("P2", "Weak page")]
    by_id = {v["visual"]: v for v in pages[0]["visuals"]}
    assert by_id["mapvis"]["title"] == "Sales by region"
    assert by_id["mapvis"]["measures"] == ["Fact Sales.Revenue"]
    assert by_id["mapvis"]["dimensions"] == ["Dim Store.Region"]
    assert by_id["treevis"]["roles"]["ExplainBy"]["dimensions"] == [
        "Dim Store.Region", "Dim Product.Category"]
    assert by_id["note"] == {"visual": "note", "type": "textbox",
                             "title": None, "measures": [], "dimensions": [],
                             "roles": {}, "customized": False}
    assert by_id["mapvis"]["customized"] is False


def test_grain_list_skips_visuals_without_bindings() -> None:
    visuals = page_insights(REPORT)["visuals"]
    assert [(v["page"], v["visual"]) for v in visuals] == [
        ("P1", "cardx"), ("P1", "mapvis"), ("P1", "treevis"),
        ("P2", "lostmap"), ("P2", "thintree")]
    assert all(v["valued_filters"] == 0 for v in visuals)


def test_tree_and_map_params() -> None:
    inventory = page_insights(REPORT)
    assert inventory["trees"] == [
        {"page": "P1", "visual": "treevis",
         "analyze": ["Fact Sales.Revenue"],
         "explain_by": ["Dim Product.Category", "Dim Store.Region"],
         "unrecognized_roles": False},
        {"page": "P2", "visual": "thintree",
         "analyze": ["Fact Sales.Revenue"],
         "explain_by": ["Dim Store.Region"],
         "unrecognized_roles": False}]
    assert inventory["maps"] == [
        {"page": "P1", "visual": "mapvis", "type": "map",
         "locations": ["Dim Store.Region"],
         "categories": {"Dim Store.Region": None},
         "labels_shown": False, "heatmap": False},
        {"page": "P2", "visual": "lostmap", "type": "map",
         "locations": [], "categories": {},
         "labels_shown": False, "heatmap": False}]


def test_unrecognized_tree_roles_flagged(tmp_path: Path) -> None:
    page = tmp_path / "definition" / "pages" / "P1" / "visuals" / "oddtree"
    page.mkdir(parents=True)
    (tmp_path / "definition" / "pages" / "P1" / "page.json").write_text(
        json.dumps({"displayName": "Odd"}), encoding="utf-8")
    (page / "visual.json").write_text(json.dumps({
        "visual": {"visualType": "decompositionTreeVisual",
                   "query": {"queryState": {
                       "Values": {"projections": [{
                           "field": {"Measure": {
                               "Expression": {"SourceRef": {
                                   "Entity": "F"}},
                               "Property": "M"}}}]}}}}}),
        encoding="utf-8")
    trees = page_insights(str(tmp_path))["trees"]
    assert trees == [{"page": "P1", "visual": "oddtree", "analyze": [],
                      "explain_by": [], "unrecognized_roles": True}]


def test_column_categories_resolve_case_insensitively(tmp_path: Path) -> None:
    model = tmp_path / "model"
    (model / "tables").mkdir(parents=True)
    (model / "tables" / "Dim Store.tmdl").write_text(
        "table 'Dim Store'\n\n\tcolumn Country\n\t\tdataType: string\n"
        "\t\tdataCategory: Country\n\n\tcolumn Region\n\t\tdataType: string\n",
        encoding="utf-8")
    categories = _column_categories(str(model))
    assert categories[("Dim Store", "Country")] == "Country"
    assert categories[("dim store", "country")] == "Country"
    assert ("Dim Store", "Region") not in categories


def test_valued_filters_count_only_restricting_entries(tmp_path: Path) -> None:
    import shutil
    clone = tmp_path / "report"
    shutil.copytree(REPORT, clone)
    path = (clone / "definition" / "pages" / "P1" / "visuals" / "cardx"
            / "visual.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["filterConfig"] = {"filters": [
        {"name": "a", "field": {}, "type": "Categorical"},
        {"name": "b", "field": {}, "type": "Advanced", "values": ["x"]}]}
    path.write_text(json.dumps(doc), encoding="utf-8")
    visuals = {v["visual"]: v
               for v in page_insights(str(clone))["visuals"]}
    assert visuals["cardx"]["valued_filters"] == 1


def test_mini_report_omits_tree_and_map_sections() -> None:
    facts = measure_report(MINI)
    assert "chart.decomposition_tree_dimensions" not in facts["rules"]
    assert "chart.map_location_binding" not in facts["rules"]
    assert facts["insights"]["pages"][0]["display_name"] == "Page one"
    titles = {v["visual"]: v["title"]
              for v in facts["insights"]["pages"][0]["visuals"]}
    assert titles["cardx"] == "Revenue"
    assert titles["slicera"] is None


def test_measure_emits_insight_sections() -> None:
    facts = measure_report(REPORT)
    assert "insight.no_duplicate_grain" in facts["rules"]
    assert "chart.decomposition_tree_dimensions" in facts["rules"]
    assert "chart.map_location_binding" in facts["rules"]
    assert len(facts["insights"]["pages"]) == 2


def test_missing_report_dir_raises() -> None:
    with pytest.raises(OSError):
        page_insights(str(FIXTURES / "absent"))

def test_malformed_query_shapes_do_not_crash(tmp_path: Path) -> None:
    page = tmp_path / "definition" / "pages" / "P1"
    (page / "visuals" / "weird").mkdir(parents=True)
    (page / "page.json").write_text(json.dumps({"displayName": "W"}),
                                     encoding="utf-8")
    (page / "visuals" / "weird" / "visual.json").write_text(json.dumps({
        "visual": {"visualType": "decompositionTreeVisual",
                   "query": {"queryState": {
                       "Values": ["not-a-dict"],
                       "Analyze": {"projections": [
                           {"field": {"Measure": {
                               "Expression": {"SourceRef": "str-instead"},
                               "Property": "M"}}},
                           {"field": {"Measure": {
                               "Expression": {"SourceRef": {"Entity": 5}},
                               "Property": "M"}}},
                           {"field": {"Measure": {"Property": "M"}}}]}}}}}),
        encoding="utf-8")
    inventory = page_insights(str(tmp_path))
    assert inventory["visuals"] == []
    assert inventory["trees"] == [{"page": "P1", "visual": "weird",
                                   "analyze": [], "explain_by": [],
                                   "unrecognized_roles": False}]


def test_model_categories_flow_from_tmdl_to_map_verdict(tmp_path: Path) -> None:
    from vqs.design_rules import map_location_binding
    model = tmp_path / "model"
    (model / "tables").mkdir(parents=True)
    (model / "tables" / "Dim Store.tmdl").write_text(
        "table 'Dim Store'\n\n\tcolumn 'Region'\n\t\tdataType: string\n"
        "\t\tdataCategory: Country\n", encoding="utf-8")
    inventory = page_insights(REPORT, str(model))
    params = {"maps": [m for m in inventory["maps"]
                       if m["visual"] == "mapvis"]}
    assert params == {"maps": [{"page": "P1", "visual": "mapvis",
                                "type": "map",
                                "locations": ["Dim Store.Region"],
                                "categories": {"Dim Store.Region": "Country"},
                                "labels_shown": False, "heatmap": False}]}
    assert map_location_binding(params["maps"])["status"] == "pass"
    params["maps"][0]["categories"] = {"Dim Store.Region": "ImageUrl"}
    failed = map_location_binding(params["maps"])
    assert failed["status"] == "fail"
    assert failed["evidence"]["conflicts"][0]["kind"] == \
        "non_geographic_binding"

def test_geometry_and_label_facts(tmp_path: Path) -> None:
    page = tmp_path / "definition" / "pages" / "P1"
    (page / "visuals" / "mapx").mkdir(parents=True)
    (page / "visuals" / "plain").mkdir(parents=True)
    (page / "page.json").write_text(json.dumps(
        {"displayName": "G", "width": 1280, "height": 720}), encoding="utf-8")
    (page / "visuals" / "mapx" / "visual.json").write_text(json.dumps({
        "position": {"x": 0, "y": 0, "width": 100, "height": 100},
        "visual": {"visualType": "map",
                   "objects": {"categoryLabels": [{"properties": {
                       "show": {"expr": {"Literal": {"Value": "true"}}}}}]},
                   "query": {"queryState": {"Category": {"projections": [{
                       "field": {"Column": {
                           "Expression": {"SourceRef": {"Entity": "D"}},
                           "Property": "C"}}}]}}}}}), encoding="utf-8")
    (page / "visuals" / "plain" / "visual.json").write_text(json.dumps({
        "visual": {"visualType": "textbox", "objects": {}}}),
        encoding="utf-8")
    inventory = page_insights(str(tmp_path))
    assert inventory["layout"] == [{"page": "P1", "visual": "mapx",
                                    "bound": True, "x": 0.0, "y": 0.0,
                                    "width": 100.0, "height": 100.0,
                                    "z": 0.0}]
    assert inventory["page_bounds"] == [{"page": "P1", "width": 1280.0,
                                         "height": 720.0, "visuals": [
                                             {"visual": "mapx", "x": 0.0,
                                              "y": 0.0, "width": 100.0,
                                              "height": 100.0}]}]
    assert inventory["maps"][0]["labels_shown"] is True
    by_id = {v["visual"]: v for v in inventory["pages"][0]["visuals"]}
    assert by_id["mapx"]["customized"] is True
    assert by_id["plain"]["customized"] is False


def test_measure_emits_cross_page_and_label_sections() -> None:
    rules = measure_report(REPORT)["rules"]
    assert "insight.no_cross_page_duplicate_grain" in rules
    assert rules["chart.map_location_labels"] == {"maps": [
        {"page": "P1", "visual": "mapvis",
         "labels_shown": False, "heatmap": False},
        {"page": "P2", "visual": "lostmap",
         "labels_shown": False, "heatmap": False}]}
    # Fixture visuals carry no positions: layout sections stay omitted.
    assert "layout.no_visual_overlap" not in rules
    assert "layout.visuals_within_page" not in rules
