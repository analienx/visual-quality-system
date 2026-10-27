"""Adversarial restore of actual checked-in Contoso Region PBIR colors."""
import json
import shutil
from pathlib import Path

import pytest

from vqs.powerbi.category_color_repair import (
    CategoryColorRepairError,
    restore_from_reference,
)

EXAMPLE = (Path(__file__).resolve().parents[1] / "examples" /
           "contoso-retail" / "Contoso Retail.Report" / "definition" /
           "pages" / "d9bc3b8f90439bcc" / "visuals" /
           "what-drives-sales" / "visual.json")


def _fixture(tmp_path):
    ref = tmp_path / "approved" / "visual.json"
    cand = tmp_path / "scratch_candidate" / "visual.json"
    ref.parent.mkdir()
    cand.parent.mkdir()
    shutil.copy2(EXAMPLE, ref)
    original = json.loads(ref.read_text(encoding="utf8"))
    modified = json.loads(ref.read_text(encoding="utf8"))
    del modified["visual"]["objects"]["dataPoint"]
    cand.write_text(json.dumps(modified), encoding="utf8")
    return ref, cand, original, modified


def test_repair_real_contoso_restores_three_distinct_scoped_region_colors(tmp_path):
    ref, cand, original, _modified = _fixture(tmp_path)
    baseline = ref.read_bytes()
    before = json.loads(cand.read_text())
    rec = restore_from_reference(ref, cand)
    repaired = json.loads(cand.read_text())
    assert rec["selector_count"] == 3
    assert rec["color_ids"] == {"Europe": 2, "North America": 3, "Asia Pacific": 4}
    assert repaired["visual"]["objects"]["dataPoint"] == original["visual"]["objects"]["dataPoint"]
    del repaired["visual"]["objects"]["dataPoint"]
    assert repaired == before
    assert ref.read_bytes() == baseline
    with pytest.raises(CategoryColorRepairError, match="already has"):
        restore_from_reference(ref, cand)


def test_wrong_source_field_or_report_shape_refused_no_mutation(tmp_path):
    ref, cand, _o, _m = _fixture(tmp_path)
    data = json.loads(cand.read_text())
    data["visual"]["query"]["queryState"]["Category"]["projections"][0][
        "field"]["Column"]["Property"] = "Country"
    cand.write_text(json.dumps(data))
    before = cand.read_bytes()
    with pytest.raises(CategoryColorRepairError, match="semantic query"):
        restore_from_reference(ref, cand)
    assert cand.read_bytes() == before


def test_unknown_selector_and_duplicate_theme_id_refused(tmp_path):
    ref, cand, _o, _m = _fixture(tmp_path)
    doc = json.loads(ref.read_text())
    points = doc["visual"]["objects"]["dataPoint"]
    points[2]["properties"]["fill"]["solid"]["color"]["expr"]["ThemeDataColor"]["ColorId"] = 2
    ref.write_text(json.dumps(doc))
    before = cand.read_bytes()
    with pytest.raises(CategoryColorRepairError, match="share a color"):
        restore_from_reference(ref, cand)
    assert cand.read_bytes() == before


def test_never_modify_original_or_same_file(tmp_path):
    ref, cand, _o, _m = _fixture(tmp_path)
    with pytest.raises(CategoryColorRepairError, match="disjoint"):
        restore_from_reference(ref, ref)
    with pytest.raises(CategoryColorRepairError, match="disjoint"):
        restore_from_reference(cand, cand)
