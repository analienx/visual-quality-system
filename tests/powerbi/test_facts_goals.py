"""GOAL regressions for the facts lane (WP-01/WP-05/WP-19).

Each test pins one required regression-corpus outcome (goal.md) against
synthetic fixtures built here or cloned from the read-only mini report.
"""
import json
import math
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPORT = str(FIXTURES / "mini_report")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


# GOAL 6: changed registered image asset invalidates source; unrelated
# sibling model does not.
def test_goal06_source_identity_image_and_sibling(tmp_path: Path) -> None:
    from vqs.pbir import source_inventory

    report = tmp_path / "R.Report"
    _write_json(report / "definition.pbir", {
        "datasetReference": {"byPath": {"path": "../ModelA.SemanticModel"}}})
    image = (report / "StaticResources" / "RegisteredResources" / "img.png")
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\x89PNG-first")
    model_a = tmp_path / "ModelA.SemanticModel" / "definition"
    _write(model_a / "tables" / "T.tmdl", "table T\n")
    model_b = tmp_path / "ModelB.SemanticModel" / "definition"
    _write(model_b / "tables" / "T.tmdl", "table T\n")

    first = source_inventory(report)
    assert first["model_dir"] == str(model_a)
    assert "StaticResources/RegisteredResources/img.png" in first[
        "report_files"]
    assert "tables/T.tmdl" in first["model_files"]

    image.write_bytes(b"\x89PNG-second")
    assert source_inventory(report)["digest"] != first["digest"]

    second = source_inventory(report)["digest"]
    (model_b / "tables" / "T.tmdl").write_text("table T2\n", encoding="utf-8")
    assert source_inventory(report)["digest"] == second

    (model_a / "tables" / "T.tmdl").write_text("table T2\n", encoding="utf-8")
    assert source_inventory(report)["digest"] != second

    third = source_inventory(report)["digest"]
    _write(report / ".pbi" / "settings.json", "{}")
    assert source_inventory(report)["digest"] == third


# GOAL 7: malformed visual and incomplete required report metadata cannot
# silently pass.
def test_goal07_malformed_sources_are_flagged_not_silent(
        tmp_path: Path) -> None:
    import hashlib

    from vqs.pbir import read_report_files

    _write_json(tmp_path / "definition" / "pages" / "P1" / "page.json", {})
    bad = tmp_path / "definition" / "pages" / "P1" / "visuals" / "bad"
    _write(bad / "visual.json", "{not json")
    good = tmp_path / "definition" / "pages" / "P1" / "visuals" / "noname"
    _write_json(good / "visual.json",
                {"position": {"x": 0, "y": 0, "width": 1, "height": 1},
                 "visual": {"visualType": "card"}})
    found = read_report_files(tmp_path)
    rules = [issue["rule"] for issue in found["issues"]]
    assert "visual_doc_unreadable" in rules
    assert "page_metadata_incomplete" in rules
    assert "visual_metadata_incomplete" in rules
    assert ("P1", "bad") not in found["visuals"]
    assert ("P1", "noname") in found["visuals"]
    rel = "definition/pages/P1/visuals/bad/visual.json"
    assert found["files"][rel] == hashlib.sha256(b"{not json").hexdigest()


# GOAL 8: A.X='B'[Y], A.Y=1, B.Y='A'[X] must detect the cycle; unsupported
# parse coverage must block.
def test_goal08_qualified_cycle_and_coverage_block(tmp_path: Path) -> None:
    from vqs.powerbi.cycles import check_model

    _write(tmp_path / "tables" / "A.tmdl",
           "table A\n\n\tmeasure X = 'B'[Y]\n\n\tmeasure Y = 1\n")
    _write(tmp_path / "tables" / "B.tmdl",
           "table B\n\n\tmeasure Y = 'A'[X]\n")
    result = check_model(str(tmp_path))
    assert result["acyclic"] is False
    assert ["measure:A.X", "measure:B.Y", "measure:A.X"] in result[
        "dax_cycles"]
    assert result["coverage"]["complete"] is True

    _write(tmp_path / "tables" / "Broken.tmdl", "model 'weird'\n")
    with pytest.raises(OSError):
        check_model(str(tmp_path))


# GOAL 9: multiline measure and calculated-column binding; dotted/escaped
# identifiers and comments.
def test_goal09_tmdl_bindings_and_identifiers() -> None:
    from vqs.data.tmdl import check_bindings, parse_tmdl, split_table_field

    text = ("\tmeasure Early = 0\n"
            "table 'Dim Product'\n"
            "\n"
            "\t// full-line comments declare nothing\n"
            "\tmeasure M = SUM (\n"
            "\t\t[Revenue]\n"
            "\t) // trailing comment\n"
            "\tmeasure 'Total Revenue' = [M]\n"
            "\tcolumn C =\n"
            "\t\t[Revenue] * 2\n"
            "\tcolumn Revenue\n")
    parsed = parse_tmdl(text)
    assert sorted(parsed["tables"]) == ["Dim Product"]
    content = parsed["tables"]["Dim Product"]
    assert "[Revenue]" in content["measures"]["M"]
    assert "SUM (" in content["measures"]["M"]
    assert content["columns"]["C"] == "[Revenue] * 2"
    assert "Total Revenue" in content["measures"]
    assert [i["rule"] for i in parsed["issues"]] == ["orphan_declaration"]

    table, field = split_table_field("Dim Product.Revenue",
                                     parsed["tables"])
    assert (table, field) == ("Dim Product", "Revenue")
    findings = check_bindings(
        [{"query_ref": "Dim Product.Revenue"},
         {"query_ref": "Dim Product.M"},
         {"query_ref": "Dim Product.Missing"}],
        {"tables": parsed["tables"]})
    by_ref = {item["query_ref"]: item for item in findings}
    assert by_ref["Dim Product.Revenue"]["status"] == "pass"
    assert by_ref["Dim Product.M"]["status"] == "pass"
    assert by_ref["Dim Product.Missing"]["status"] == "fail"


# GOAL 10: majority black plus minority white text on white must expose
# the minority defect; active-theme selection and surface coverage.
def test_goal10_minority_contrast_defect_exposed(tmp_path: Path) -> None:
    from vqs.design_rules import text_contrast
    from vqs.powerbi.measure import measure_report

    clone = tmp_path / "report"
    shutil.copytree(REPORT, clone)
    path = (clone / "definition" / "pages" / "P1" / "visuals" / "titlebox"
            / "visual.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    paras = doc["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
    runs = [{"text": f"n{i}", "textStyle": {"color": "#000000"}}
            for i in range(5)]
    runs.append({"text": "dim", "textStyle": {"color": "#FFFFFF"}})
    paras.append({"textRuns": runs})
    path.write_text(json.dumps(doc), encoding="utf-8")

    rules = measure_report(str(clone))["rules"]
    readings = rules["typography.text_contrast"]["readings"]
    minority = [r for r in readings if r["foreground"] == "#FFFFFF"]
    assert minority == [{"foreground": "#FFFFFF", "background": "#FFFFFF",
                         "page": "P1", "visual": "titlebox",
                         "paragraph": 2, "role": "body", "count": 1}]
    verdict = text_contrast(readings=readings)
    assert verdict["status"] == "fail"
    assert verdict["evidence"]["failures"][0]["foreground"] == "#FFFFFF"

    control = measure_report(REPORT)["rules"][
        "typography.text_contrast"]["readings"]
    assert text_contrast(readings=control)["status"] == "pass"


def test_goal10_theme_selection_and_inherited_surface(
        tmp_path: Path) -> None:
    from vqs.powerbi.measure import measure_report

    facts = measure_report(REPORT)
    theme = facts["coverage"]["theme"]
    assert theme["selection"] in ("pointer", "single")
    assert theme["theme"]

    clone = tmp_path / "report"
    shutil.copytree(REPORT, clone)
    page_path = clone / "definition" / "pages" / "P1" / "page.json"
    doc = json.loads(page_path.read_text(encoding="utf-8"))
    doc.pop("objects", None)
    page_path.write_text(json.dumps(doc), encoding="utf-8")
    readings = measure_report(str(clone))["rules"][
        "typography.text_contrast"]["readings"]
    assert readings
    assert all(item["background"] == "#FFFFFF" for item in readings)


# GOAL 12: NaN/Infinity geometry must not pass.
def test_goal12_nonfinite_geometry_never_passes() -> None:
    from vqs.design_rules import layout_no_visual_overlap, layout_visuals_within_page

    nan = math.nan
    for bad in ({"x": nan, "y": 0.0, "width": 10.0, "height": 10.0},
                {"x": 0.0, "y": 0.0, "width": math.inf, "height": 10.0}):
        result = layout_no_visual_overlap(
            [{"page": "P", "visual": "a", **bad}])
        assert result["status"] == "unknown", bad
    result = layout_visuals_within_page([{
        "page": "P", "width": 100.0, "height": 100.0, "visuals": [
            {"visual": "a", "x": 0.0, "y": 0.0, "width": nan,
             "height": 10.0}]}])
    assert result["status"] == "unknown"
    result = layout_visuals_within_page([{
        "page": "P", "width": nan, "height": 100.0, "visuals": []}])
    assert result["status"] == "unknown"


# GOAL 13: valid overview/detail grains with distinct filter context and
# intentional background/card overlap must remain valid.
def test_goal13_valid_grains_and_background_overlap() -> None:
    from vqs.design_rules import insight_no_duplicate_grain, layout_no_visual_overlap

    grains = insight_no_duplicate_grain([
        {"page": "P", "visual": "over", "type": "card",
         "measures": ["S.Revenue"], "dimensions": [],
         "valued_filters": 0},
        {"page": "P", "visual": "detail", "type": "table",
         "measures": ["S.Revenue"], "dimensions": ["D.Year"],
         "valued_filters": 0}])
    assert grains["status"] == "pass"
    filtered = insight_no_duplicate_grain([
        {"page": "P", "visual": "twin_a", "type": "card",
         "measures": ["S.Revenue"], "dimensions": [],
         "valued_filters": 0},
        {"page": "P", "visual": "twin_b", "type": "card",
         "measures": ["S.Revenue"], "dimensions": [],
         "valued_filters": 1}])
    assert filtered["status"] == "pass"
    assert filtered["evidence"]["skipped_filtered_pairs"] == 1

    overlap = layout_no_visual_overlap([
        {"page": "P", "visual": "bg", "x": 0.0, "y": 0.0,
         "width": 100.0, "height": 100.0, "z": 0.0, "bound": False},
        {"page": "P", "visual": "card", "x": 10.0, "y": 10.0,
         "width": 20.0, "height": 20.0, "z": 1.0, "bound": True}])
    assert overlap["status"] == "pass"
    assert overlap["evidence"]["skipped_background_pairs"] == 1

    strict = layout_no_visual_overlap([
        {"page": "P", "visual": "first", "x": 0.0, "y": 0.0,
         "width": 100.0, "height": 100.0, "z": 0.0, "bound": True},
        {"page": "P", "visual": "second", "x": 10.0, "y": 10.0,
         "width": 20.0, "height": 20.0, "z": 1.0, "bound": True}])
    assert strict["status"] == "fail"
    assert len(strict["evidence"]["conflicts"]) == 1


# GOAL 16 (fact side): category/bookmark/interaction/answer facts for the
# repair lane. Map dataCategory flow is pinned by
# test_model_categories_flow_from_tmdl_to_map_verdict.
def test_goal16_bookmark_interaction_and_answer_facts(
        tmp_path: Path) -> None:
    from vqs.powerbi.insights import page_insights

    _write_json(tmp_path / "definition" / "report.json", {
        "filterConfig": {"filters": [
            {"name": "rf", "field": {"Column": {}}, "type": "basic",
             "operator": "In", "values": ["a"]}]}})
    page = tmp_path / "definition" / "pages" / "P1"
    _write_json(page / "page.json", {
        "displayName": "P", "width": 1280, "height": 720,
        "visualInteractions": [
            {"type": "NoFilter", "source": "av", "target": "bv"}]})
    _write_json(page / "visuals" / "av" / "visual.json", {
        "name": "av", "position": {"x": 0, "y": 0, "width": 10,
                                  "height": 10},
        "visual": {"visualType": "card",
                   "query": {"queryState": {"Values": {"projections": [{
                       "field": {"Measure": {
                           "Expression": {"SourceRef": {"Entity": "S"}},
                           "Property": "Revenue"}}}]}}},
                   "objects": {}}})
    bookmarks = tmp_path / "definition" / "bookmarks"
    _write_json(bookmarks / "bookmarks.json", {"groups": [
        {"name": "G", "displayName": "Group",
         "children": [{"name": "B1"}]}]})
    _write_json(bookmarks / "B1.bookmark.json", {
        "name": "B1", "displayName": "First",
        "options": {"targetVisualNames": ["av"]},
        "explorationState": {
            "activeSection": "P1",
            "filters": {"byColumn": [{"expression": {"Column": {
                "Expression": {"SourceRef": {"Entity": "D"}},
                "Property": "C"}}}]}}})
    _write(bookmarks / "Broken.bookmark.json", "{oops")

    inventory = page_insights(str(tmp_path))
    assert inventory["bookmarks"] == [{
        "id": "B1", "display_name": "First", "target_visuals": ["av"],
        "active_section": "P1", "filter_entities": ["D"],
        "group": "Group"}]
    assert inventory["pages"][0]["interactions"] == [
        {"type": "NoFilter", "source": "av", "target": "bv"}]
    assert inventory["visuals"] == [{
        "page": "P1", "visual": "av", "type": "card",
        "measures": ["S.Revenue"], "dimensions": [],
        "valued_filters": 0,
        "filter_scopes": {"visual": 0, "page": 0, "report": 1}}]
    rules = [issue["rule"] for issue in inventory["coverage"]["issues"]]
    assert "bookmark_doc_unreadable" in rules


def test_goal16_malformed_interactions_are_flagged(tmp_path: Path) -> None:
    from vqs.powerbi.insights import page_insights

    page = tmp_path / "definition" / "pages" / "P1"
    _write_json(page / "page.json", {"displayName": "P", "width": 10,
                                    "height": 10,
                                    "visualInteractions": "nope"})
    inventory = page_insights(str(tmp_path))
    assert inventory["pages"][0]["interactions"] == []
    rules = [issue["rule"] for issue in inventory["coverage"]["issues"]]
    assert "interactions_unsupported" in rules


# Reviewer follow-up F1: malformed bookmark filter shapes cannot crash
# the inventory; the well-formed half is still exposed plus an issue.
def test_review_f1_malformed_bookmark_filters_flagged(tmp_path: Path) -> None:
    from vqs.powerbi.insights import page_insights

    bookmarks = tmp_path / "definition" / "bookmarks"
    _write_json(bookmarks / "Odd.bookmark.json", {
        "name": "Odd", "displayName": "Odd",
        "explorationState": {"filters": {
            "byExpr": [{"expression": {"Measure": {
                "Expression": {"SourceRef": {"Entity": "S"}},
                "Property": "Revenue"}}}],
            "byColumn": {"not": "a list"}}}})
    inventory = page_insights(str(tmp_path))
    assert inventory["bookmarks"] == [{
        "id": "Odd", "display_name": "Odd", "target_visuals": [],
        "active_section": None, "filter_entities": ["S"],
        "group": None}]
    rules = [issue["rule"] for issue in inventory["coverage"]["issues"]]
    assert "bookmark_filters_unsupported" in rules


# Reviewer follow-up F2a: annotations and unknown properties are not
# expression text; an expression-less measure stays unknown.
def test_review_f2a_annotations_are_not_expressions() -> None:
    from vqs.data.tmdl import check_bindings, parse_tmdl

    parsed = parse_tmdl(
        "table A\n"
        "\n"
        "\tmeasure M\n"
        "\t\tdescription: hello\n"
        "\t\tannotation 'PBI_Id' = 1\n"
        "\t\tdetailRowsExpression: [X]\n")
    assert parsed["tables"]["A"]["measures"]["M"] == ""
    findings = check_bindings([{"query_ref": "A.M"}],
                              {"tables": parsed["tables"]})
    assert findings == [{"rule": "measure_without_expression",
                         "status": "unknown", "query_ref": "A.M",
                         "reason": "Values require a live authorized query"}]


# Reviewer follow-up F2b: annotation prose adds no dependency edges.
def test_review_f2b_annotations_add_no_cycle_edges(tmp_path: Path) -> None:
    from vqs.powerbi.cycles import check_model, dax_edges, dax_objects

    _write(tmp_path / "tables" / "A.tmdl",
           "table A\n\n\tmeasure M = 1\n\t\tannotation 'note' = 'B'[Y]\n")
    _write(tmp_path / "tables" / "B.tmdl", "table B\n\n\tmeasure Y = 2\n")
    objects = dax_objects(str(tmp_path))
    assert objects[("measure", "A", "M")] == "1"
    assert dax_edges(objects)[("measure", "A", "M")] == set()
    assert check_model(str(tmp_path))["acyclic"] is True
