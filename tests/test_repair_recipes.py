"""Typed-recipe tests: source binding, type preservation, bounds.

Plans bind exact component/property/value; recipes reject missing
selectors, container restructuring, type changes, non-finite numbers,
and out-of-canvas geometry.
"""
import pytest

from vqs.repair.recipes import (
    RecipeError,
    affected_pages,
    bind_operation,
)


def _visual(**overrides):
    doc = {
        "name": "cardx",
        "position": {"x": 24, "y": 104, "width": 296, "height": 96,
                     "tabOrder": 4, "z": 4},
        "visual": {
            "visualType": "card",
            "objects": {
                "labels": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "24D"}}},
                    "rotation": {"expr": {"Literal": {"Value": 0}}},
                    "show": {"expr": {"Literal": {"Value": True}}}}}],
            },
            "query": {"queryState": {"Values": {"projections": []}}},
        },
    }
    doc.update(overrides)
    return doc


def _op(op_type, path, value):
    return {"type": op_type, "target": "visual",
            "selector": {"page": "P1", "visual": "cardx"},
            "path": path, "value": value}


LEAF = ["visual", "objects", "labels", 0, "properties", "fontSize",
        "expr", "Literal", "Value"]


def test_leaf_size_and_bool_replacement() -> None:
    bound = bind_operation(_op("typography.size", LEAF, "28D"), _visual())
    assert (bound["page"], bound["visual"], bound["old"],
            bound["new"]) == ("P1", "cardx", "24D", "28D")
    show = ["visual", "objects", "labels", 0, "properties", "show",
            "expr", "Literal", "Value"]
    bound = bind_operation(_op("theme.set", show, False), _visual())
    assert (bound["old"], bound["new"]) == (True, False)


def test_missing_selector_or_path_blocks() -> None:
    with pytest.raises(RecipeError, match="source binding"):
        bind_operation({"type": "theme.set", "path": LEAF,
                        "value": "x"}, _visual())
    with pytest.raises(RecipeError, match="source binding"):
        bind_operation(_op("theme.set", LEAF, "x") | {"selector": {}},
                       _visual())
    with pytest.raises(RecipeError, match="precondition failed"):
        bind_operation(_op("theme.set", LEAF[:-1] + ["Missing"], "x"),
                       _visual())
    with pytest.raises(RecipeError, match="must address visual"):
        bind_operation(_op("theme.set", ["visual", "query"], "x"),
                       _visual())
    with pytest.raises(RecipeError, match="missing value"):
        bind_operation({"type": "theme.set", "target": "v",
                        "selector": {"page": "P1", "visual": "c"},
                        "path": LEAF}, _visual())


def test_type_preservation_and_schemas() -> None:
    with pytest.raises(RecipeError, match="would replace"):
        bind_operation(_op("typography.size", LEAF, 28), _visual())
    with pytest.raises(RecipeError, match="'ND'"):
        bind_operation(_op("typography.size", LEAF, "huge"), _visual())
    with pytest.raises(RecipeError, match="'ND'"):
        bind_operation(_op("typography.size", LEAF, "4D"), _visual())
    with pytest.raises(RecipeError, match="scalar leaf"):
        bind_operation(_op("theme.set", ["visual", "objects"], "x"),
                       _visual())
    with pytest.raises(RecipeError, match="would replace"):
        bind_operation(_op("theme.set", LEAF, {"evil": 1}), _visual())
    with pytest.raises(RecipeError, match="#RRGGBB"):
        bind_operation(_op("palette.assign", LEAF, "red"), _visual())
    with pytest.raises(RecipeError, match="control characters"):
        bind_operation(_op("axis.title", LEAF, "a\x07b"), _visual())
    numeric = LEAF[:-4] + ["rotation", "expr", "Literal", "Value"]
    with pytest.raises(RecipeError, match="non-finite"):
        bind_operation(_op("axis.precision", numeric, float("nan")),
                       _visual())
    with pytest.raises(RecipeError, match="rotation|property|axis"):
        bind_operation(_op("axis.precision", numeric, 2), _visual())
    # F02: precision on an unrelated rotation property is rejected above.
    with pytest.raises(RecipeError, match="would replace"):
        bind_operation(_op("axis.precision", LEAF, 2), _visual())


def test_geometry_stays_finite_and_in_canvas() -> None:
    bound = bind_operation(_op("chart.resize", ["position", "width"], 300),
                           _visual(), (1280, 720))
    assert (bound["old"], bound["new"]) == (296, 300)
    bound = bind_operation(_op("spacing.adjust", ["position", "x"], 30),
                           _visual(), (1280, 720))
    assert bound["new"] == 30
    with pytest.raises(RecipeError, match="leave the canvas"):
        bind_operation(_op("chart.resize", ["position", "width"], 2000),
                       _visual(), (1280, 720))
    with pytest.raises(RecipeError, match="positive size"):
        bind_operation(_op("chart.resize", ["position", "height"], 0),
                       _visual(), (1280, 720))
    with pytest.raises(RecipeError, match="finite numeric"):
        bind_operation(_op("spacing.adjust", ["position", "y"],
                           float("inf")), _visual(), (1280, 720))
    with pytest.raises(RecipeError, match=r"\['position', width/height\]"):
        bind_operation(_op("chart.resize", ["position", "x"], 5),
                       _visual(), (1280, 720))
    with pytest.raises(RecipeError, match="no position"):
        bind_operation(_op("chart.resize", ["position", "width"], 5),
                       {"name": "c"}, (1280, 720))
    poisoned = _visual()
    poisoned["position"]["x"] = float("nan")
    with pytest.raises(RecipeError, match="lacks finite"):
        bind_operation(_op("spacing.adjust", ["position", "y"], 110),
                       poisoned, (1280, 720))
    stringy = _visual()
    stringy["position"]["width"] = "296"
    with pytest.raises(RecipeError, match="lacks finite"):
        bind_operation(_op("spacing.adjust", ["position", "y"], 110),
                       stringy, (1280, 720))


def test_sort_definition_and_replace_shapes() -> None:
    path = ["visual", "query", "sortDefinition"]
    sort = {"sort": [{"field": {"Measure": {"ref": "Revenue"}},
                      "direction": 1}],
            "isDefaultSort": True}
    bound = bind_operation(_op("sort.set", path, sort), _visual())
    assert bound["old"] is None
    assert bound["new"] == sort
    with pytest.raises(RecipeError, match="must be a JSON object"):
        bind_operation(_op("sort.set", path, ["x"]), _visual())
    with pytest.raises(RecipeError, match="allows only"):
        bind_operation(_op("sort.set", path, {"by": "Revenue"}),
                       _visual())
    with pytest.raises(RecipeError, match="non-empty 'sort' array"):
        bind_operation(_op("sort.set", path, {"sort": []}), _visual())
    with pytest.raises(RecipeError, match="integer 'direction'"):
        bind_operation(_op("sort.set", path,
                           {"sort": [{"field": {}, "direction": "up"}]}),
                       _visual())
    with pytest.raises(RecipeError, match="'field' object"):
        bind_operation(_op("sort.set", path,
                           {"sort": [{"direction": 1}]}), _visual())
    with pytest.raises(RecipeError, match="no query"):
        bind_operation(_op("sort.set", path, {}), {"visual": {}})
    replace = {"type": "chart.replace", "target": "visual",
               "selector": {"page": "P1", "visual": "cardx"},
               "template": {"name": "kpi-card", "version": "1.0.0"}}
    bound = bind_operation(replace, None)
    assert (bound["template"], bound["version"]) == ("kpi-card", "1.0.0")
    with pytest.raises(RecipeError, match="template"):
        bind_operation({**replace, "template": {"name": ""}}, None)
    with pytest.raises(RecipeError, match="unknown operation"):
        bind_operation({"type": "teleport"}, None)


def test_affected_pages_shared_theme() -> None:
    op = _op("typography.size", LEAF, "28D")
    assert affected_pages(op, ["P1", "P2"]) == {
        "pages": ["P1"], "shared": False, "reason": "bound page only"}
    theme = _op("theme.set", LEAF, "x")
    assert affected_pages(theme, ["P1", "P2"]) == {
        "pages": ["P1", "P2"], "shared": True,
        "reason": "shared presentation change invalidates all pages"}
    with pytest.raises(RecipeError, match="source binding"):
        affected_pages({"type": "theme.set"}, ["P1"])
