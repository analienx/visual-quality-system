"""F02 RED: recipe paths must be schema-validated, not subtree-accepted.

Field selectors, references, filters, conditional expressions, and
properties unrelated to the recipe must be rejected; valid literal
title/precision/color repairs keep working.
"""
import json
from pathlib import Path

import pytest

from vqs.repair.recipes import RecipeError, bind_operation

LEAF = ["visual", "objects", "labels", 0, "properties"]


def _labels_properties() -> dict:
    # Every RED path below addresses an EXISTING scalar leaf, so a
    # rejection proves recipe-schema enforcement, never a missing path.
    return {
        "fontSize": {"expr": {"Literal": {"Value": "11D"},
                              "Conditional": {"branches": "b1"}}},
        "title": {"expr": {"Literal": {"Value": "Old"}}},
        "precision": {"expr": {"Literal": {"Value": 1}}},
        "color": {"expr": {"Literal": {"Value": "#00FF00"}}},
        "rotation": {"expr": {"Literal": {"Value": 0}}},
        "selector": {"metadata": {"id": "sel-1"}},
        "dataLabel": {"queryRef": "M.X"},
        "filter": {"where": {"clause": "c0"}},
    }


def _visual() -> dict:
    return {
        "name": "cardx",
        "position": {"x": 1, "y": 2, "width": 3, "height": 4},
        "visual": {
            "visualType": "card",
            "objects": {
                "labels": [{"properties": _labels_properties()}],
                "categoryAxis": [{"properties": {
                    "labelPrecision": {
                        "expr": {"Literal": {"Value": "2"}}}}}],
            },
            "query": {"queryState": {"Values": {"projections": [
                {"queryRef": "M.X", "field": {"Measure": {}},
                 "active": True}]}}}},
    }


def _op(op_type: str, path: list, value):
    return {"type": op_type, "target": "visual",
            "selector": {"page": "P1", "visual": "cardx"},
            "path": path, "value": value,
            "writes": ["definition/pages/P1/visuals/cardx/visual.json"]}


def test_f02_selector_metadata_rejected() -> None:
    path = [*LEAF, "selector", "metadata", "id"]
    with pytest.raises(RecipeError, match="recipe"):
        bind_operation(_op("typography.size", path, "14D"), _visual())


def test_f02_conditional_expression_rejected() -> None:
    path = [*LEAF, "fontSize", "expr", "Conditional", "branches"]
    with pytest.raises(RecipeError, match="recipe|leaf"):
        bind_operation(_op("typography.size", path, "14D"), _visual())


def test_f02_query_reference_rejected() -> None:
    path = [*LEAF, "dataLabel", "queryRef"]
    with pytest.raises(RecipeError, match="recipe|leaf"):
        bind_operation(_op("typography.size", path, "14D"), _visual())


def test_f02_filter_path_rejected() -> None:
    path = [*LEAF, "filter", "where", "clause"]
    with pytest.raises(RecipeError, match="recipe|leaf"):
        bind_operation(_op("typography.size", path, "14D"), _visual())


def test_f02_precision_on_rotation_rejected() -> None:
    path = [*LEAF, "rotation", "expr", "Literal", "Value"]
    with pytest.raises(RecipeError, match="rotation|property|axis|recipe"):
        bind_operation(_op("axis.precision", path, 2), _visual())


def test_f02_valid_literal_repairs_still_bind() -> None:
    size = [*LEAF, "fontSize", "expr", "Literal", "Value"]
    assert bind_operation(
        _op("typography.size", size, "14D"), _visual())["new"] == "14D"
    title = [*LEAF, "title", "expr", "Literal", "Value"]
    assert bind_operation(
        _op("axis.title", title, "Sales"), _visual())["new"] == "Sales"
    precision = [*LEAF, "precision", "expr", "Literal", "Value"]
    assert bind_operation(
        _op("axis.precision", precision, 2), _visual())["new"] == 2
    color = [*LEAF, "color", "expr", "Literal", "Value"]
    assert bind_operation(
        _op("palette.assign", color, "#FF0000"), _visual())["new"] == "#FF0000"


def _make_report(root: Path) -> Path:
    report = root / "original.Report"
    pages = report / "definition" / "pages"
    (pages / "P1" / "visuals" / "cardx").mkdir(parents=True)
    (pages / "pages.json").write_text(json.dumps({"pageOrder": ["P1"]}),
                                      encoding="utf-8")
    (pages / "P1" / "page.json").write_text(
        json.dumps({"displayName": "O", "width": 1280, "height": 720}),
        encoding="utf-8")
    props = {"selector": {"metadata": {"id": "orig"}}}
    visual_doc = {"name": "cardx",
                  "visual": {"visualType": "card",
                             "objects": {"labels": [{"properties": props}]}}}
    (pages / "P1" / "visuals" / "cardx" / "visual.json").write_text(
        json.dumps(visual_doc), encoding="utf-8")
    return report


def test_f02_undeclared_forbidden_path_fails_verify(tmp_path: Path) -> None:
    import shutil

    from vqs.repair.regress import verify_candidate

    original = _make_report(tmp_path)
    candidate = tmp_path / "cand"
    shutil.copytree(original, candidate)
    visual_file = (candidate
                   / "definition/pages/P1/visuals/cardx/visual.json")
    doc = json.loads(visual_file.read_text(encoding="utf-8"))
    props = doc["visual"]["objects"]["labels"][0]["properties"]
    props["selector"]["metadata"]["id"] = "smuggled"
    visual_file.write_text(json.dumps(doc), encoding="utf-8")
    edits = [{"file": "definition/pages/P1/visuals/cardx/visual.json",
              "op": "typography.size",
              "path": [*LEAF, "selector", "metadata", "id"]}]
    verdict = verify_candidate(str(original), str(candidate), edits)
    assert verdict["verdict"] == "fail"
    assert verdict["problems"][0]["rule"] == "edits_unreadable"


def test_f02_apply_plan_rejects_semantic_op(tmp_path: Path) -> None:
    """A02: production apply_plan blocks a selector-mutating op at apply."""
    from vqs.repair.execute import apply_plan

    original = _make_report(tmp_path)
    plan = {
        "operations": [{
            "type": "typography.size", "target": "visual",
            "selector": {"page": "P1", "visual": "cardx"},
            "path": [*LEAF, "selector", "metadata", "id"],
            "value": "14D",
            "writes": ["definition/pages/P1/visuals/cardx/visual.json"]}],
        "write_targets": ["definition/pages/P1/visuals/cardx/visual.json"],
        "rollback": "re-materialize from original",
    }
    result = apply_plan(plan, str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert result["stage"] == "apply"
    assert result["index"] == 0
    assert "RecipeError" in result["reason"]


def test_f02_label_format_scoped_to_labels_object() -> None:
    """label.format v2 contract: labels leaves bind, others reject."""
    size = [*LEAF, "fontSize", "expr", "Literal", "Value"]
    assert bind_operation(
        _op("label.format", size, "14D"), _visual())["new"] == "14D"
    other = ["visual", "objects", "categoryAxis", 0, "properties",
             "labelPrecision", "expr", "Literal", "Value"]
    with pytest.raises(RecipeError, match="labels"):
        bind_operation(_op("label.format", other, "3"), _visual())
    selector = [*LEAF, "selector", "metadata", "id"]
    with pytest.raises(RecipeError, match="recipe"):
        bind_operation(_op("label.format", selector, "14D"), _visual())
