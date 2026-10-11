"""Native card label fix: exact typed plan, model preservation, refusal cases."""
import json
from pathlib import Path

import pytest

from tests.test_s16_candidate_model import _project, _repair_cli, _sealed
from vqs.repair.execute import tree_digest
from vqs.repair.recipes import RecipeError, bind_operation


def _card() -> dict:
    return {
        "name": "v1",
        "position": {"x": 5, "y": 5, "width": 200, "height": 90, "z": 0},
        "visual": {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": [
                {"queryRef": "Sales.Total Sales"}]}}},
            "objects": {"labels": [{"properties": {
                "fontSize": {"expr": {"Literal": {"Value": "24D"}}}}}]},
            "visualContainerObjects": {"title": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": "'Sales'"}}}}}]},
        },
    }


def _op() -> dict:
    file = "definition/pages/P1/visuals/v1/visual.json"
    return {
        "type": "card.category_label.hide",
        "target": "visual",
        "selector": {"page": "P1", "visual": "v1"},
        "path": ["visual", "objects", "categoryLabels"],
        "value": False,
        "writes": [file],
    }


def test_label_hide_is_one_typed_candidate_change(tmp_path: Path, capsys):
    original, model = _project(tmp_path, "table T\n")
    path = original / _op()["writes"][0]
    path.write_text(json.dumps(_card()), encoding="utf-8")
    before_model = (model/"definition"/"tables"/"T.tmdl").read_bytes()
    before = tree_digest(original)
    plan = {"operations": [_op()], "write_targets": _op()["writes"],
            "rollback": "re-materialize from original"}
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    cand = tmp_path / "cand"
    assert _repair_cli(plan_path, original, tmp_path, "card-hide", cand) == 0
    capsys.readouterr()
    result, output = _sealed(tmp_path, "card-hide", capsys)
    assert result == 0, output
    after = json.loads((cand / _op()["writes"][0]).read_text())
    before_doc = json.loads(path.read_text())
    assert before_doc["visual"]["query"] == after["visual"]["query"]
    assert after["visual"]["objects"]["categoryLabels"] == [
        {"properties": {"show": {"expr": {
            "Literal": {"Value": "false"}}}}}]
    assert tree_digest(original) == before
    assert (model/"definition"/"tables"/"T.tmdl").read_bytes() == before_model
    assert json.loads(output)["verdict"] == "pass"


@pytest.mark.parametrize("mutation,detail", [
    ("wrong-type", "native card"),
    ("already-specified", "undeclared"),
    ("no-visible-title", "displayed card title"),
    ("wrong-value", "only categoryLabels"),
])
def test_card_label_hide_refuses_unsupported_cases(mutation, detail):
    card = _card()
    op = _op()
    if mutation == "wrong-type":
        card["visual"]["visualType"] = "clusteredBarChart"
    elif mutation == "already-specified":
        card["visual"]["objects"]["categoryLabels"] = []
    elif mutation == "no-visible-title":
        card["visual"]["visualContainerObjects"]["title"][0]["properties"][
            "show"]["expr"]["Literal"]["Value"] = "false"
    else:
        op["value"] = True
    with pytest.raises(RecipeError, match=detail):
        bind_operation(op, card, (1280, 720))
