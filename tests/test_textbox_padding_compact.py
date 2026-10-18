"""P7: native textbox padding repair, exact observable scope and refusal."""
import json

import pytest

from tests.test_s16_candidate_model import _project, _repair_cli, _sealed
from vqs.repair.execute import tree_digest
from vqs.repair.recipes import RecipeError, bind_operation

REL="definition/pages/P1/visuals/v1/visual.json"


def _textbox():
    return {
      "name":"v1",
      "position":{"x":24,"y":72,"width":820,"height":32,"z":0},
      "visual":{
        "visualType":"textbox",
        "objects":{"general":[{"properties":{"paragraphs":[{"textRuns":[
          {"value":"What drives sales", "textStyle":{
             "fontSize":"12px","fontFamily":"Segoe UI",
             "color":"#52617A"}}
        ]}]}}]},
        "visualContainerObjects":{"title":[{"properties":{
            "show":{"expr":{"Literal":{"Value":"false"}}}}}]},
      },
    }


def _op():
    return {
      "type":"textbox.padding.compact","target":"visual",
      "selector":{"page":"P1","visual":"v1"},
      "path":["visual","visualContainerObjects","padding"],
      "value":2,"expected_height":32,"expected_font_size":"12px",
      "writes":[REL],
    }


def test_compact_padding_typed_candidate_and_model_preservation(tmp_path,capsys):
    original,model=_project(tmp_path,"table T\n")
    f=original/REL
    f.write_text(json.dumps(_textbox()),encoding="utf-8")
    source_digest=tree_digest(original)
    before_model=(model/"definition"/"tables"/"T.tmdl").read_bytes()
    op=_op()
    plan={"operations":[op],"write_targets":[REL],
          "rollback":"re-materialize from original"}
    plan_path=tmp_path/"padding-plan.json"
    plan_path.write_text(json.dumps(plan),encoding="utf-8")
    candidate=tmp_path/"typed-padding.Report"
    assert _repair_cli(plan_path,original,tmp_path,"p7-padding",candidate)==0
    capsys.readouterr()
    verdict,output=_sealed(tmp_path,"p7-padding",capsys)
    assert verdict==0,output
    doc=json.loads((candidate/REL).read_text())
    old=_textbox()
    assert doc["visual"]["objects"]==old["visual"]["objects"]
    assert doc["position"]==old["position"]
    assert doc["visual"]["visualContainerObjects"]["title"]==(
        old["visual"]["visualContainerObjects"]["title"])
    assert doc["visual"]["visualContainerObjects"]["padding"]==[{
      "properties":{k:{"expr":{"Literal":{"Value":"2D"}}}
                    for k in ("top","bottom","left","right")}}]
    assert tree_digest(original)==source_digest
    assert (model/"definition"/"tables"/"T.tmdl").read_bytes()==before_model
    assert json.loads(output)["verdict"]=="pass"


@pytest.mark.parametrize("case,reason",[
 ("wrong_type","native textbox"),
 ("wrong_height","height drift"),
 ("already_padded","undeclared"),
 ("wrong_font","unsupported textbox run"),
 ("wrong_value","only proved"),
 ("no_text","unsupported textbox run"),
 ("dynamic_value","unsupported textbox run"),
 ("extra_paragraph","one simple paragraph"),
 ("missing_properties","textbox properties missing"),
])
def test_compact_padding_refuses_unsafe_or_unproved_inputs(case,reason):
    doc=_textbox()
    op=_op()
    if case=="wrong_type":doc["visual"]["visualType"]="card"
    elif case=="wrong_height":doc["position"]["height"]=31
    elif case=="already_padded":doc["visual"]["visualContainerObjects"]["padding"]=[]
    elif case=="wrong_font":
        doc["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["textStyle"]["fontSize"]="16px"
    elif case=="wrong_value":op["value"]=20
    elif case=="no_text":
        doc["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["value"]=""
    elif case=="dynamic_value":
        doc["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["value"]={"expr":"bad"}
    elif case=="extra_paragraph":
        doc["visual"]["objects"]["general"][0]["properties"]["paragraphs"].append({"textRuns":[]})
    else:
        doc["visual"]["objects"]["general"][0]["properties"]=None
    with pytest.raises(RecipeError,match=reason):
        bind_operation(op,doc,(1280,720))
