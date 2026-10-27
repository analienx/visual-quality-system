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
    rec = restore_from_reference(ref, cand, disposable_root=tmp_path / "scratch_candidate")
    repaired = json.loads(cand.read_text())
    assert rec["selector_count"] == 3
    assert rec["color_ids"] == {"Europe": 2, "North America": 3, "Asia Pacific": 4}
    assert repaired["visual"]["objects"]["dataPoint"] == original["visual"]["objects"]["dataPoint"]
    del repaired["visual"]["objects"]["dataPoint"]
    assert repaired == before
    assert ref.read_bytes() == baseline
    with pytest.raises(CategoryColorRepairError, match="already has"):
        restore_from_reference(ref, cand, disposable_root=tmp_path / "scratch_candidate")


def test_wrong_source_field_or_report_shape_refused_no_mutation(tmp_path):
    ref, cand, _o, _m = _fixture(tmp_path)
    data = json.loads(cand.read_text())
    data["visual"]["query"]["queryState"]["Category"]["projections"][0][
        "field"]["Column"]["Property"] = "Country"
    cand.write_text(json.dumps(data))
    before = cand.read_bytes()
    with pytest.raises(CategoryColorRepairError, match="semantic query"):
        restore_from_reference(ref, cand, disposable_root=tmp_path / "scratch_candidate")
    assert cand.read_bytes() == before


def test_unknown_selector_and_duplicate_theme_id_refused(tmp_path):
    ref, cand, _o, _m = _fixture(tmp_path)
    doc = json.loads(ref.read_text())
    points = doc["visual"]["objects"]["dataPoint"]
    points[2]["properties"]["fill"]["solid"]["color"]["expr"]["ThemeDataColor"]["ColorId"] = 2
    ref.write_text(json.dumps(doc))
    before = cand.read_bytes()
    with pytest.raises(CategoryColorRepairError, match="share a color"):
        restore_from_reference(ref, cand, disposable_root=tmp_path / "scratch_candidate")
    assert cand.read_bytes() == before


def test_never_modify_original_or_same_file(tmp_path):
    ref, cand, _o, _m = _fixture(tmp_path)
    with pytest.raises(CategoryColorRepairError, match="disposable root"):
        restore_from_reference(ref, ref, disposable_root=tmp_path / "scratch_candidate")
    with pytest.raises(CategoryColorRepairError, match="reference must be outside"):
        restore_from_reference(cand, cand, disposable_root=tmp_path / "scratch_candidate")

def test_no_implicit_disposable_authorization(tmp_path):
    ref, cand, _o, _m = _fixture(tmp_path)
    before = cand.read_bytes()
    with pytest.raises(TypeError, match="disposable_root"):
        restore_from_reference(ref, cand)  # type: ignore[call-arg]
    assert cand.read_bytes() == before


def test_out_of_root_candidate_rejected_without_mutation(tmp_path):
    ref, cand, _o, _m = _fixture(tmp_path)
    another = tmp_path / "separate_candidate"
    another.mkdir()
    before = cand.read_bytes()
    with pytest.raises(CategoryColorRepairError, match="outside explicitly"):
        restore_from_reference(ref, cand, disposable_root=another)
    assert cand.read_bytes() == before


def test_overbroad_disposable_root_cannot_enclose_trusted_reference(tmp_path):
    ref, cand, _o, _m = _fixture(tmp_path)
    before = cand.read_bytes()
    with pytest.raises(CategoryColorRepairError, match="reference must be outside"):
        restore_from_reference(ref, cand, disposable_root=tmp_path)
    assert cand.read_bytes() == before


def test_symlink_escape_from_disposable_root_rejected(tmp_path):
    ref, _cand, _o, _m = _fixture(tmp_path)
    root = tmp_path / "scratch_candidate"
    link = root / "link-escape.json"
    try:
        link.symlink_to(ref)
    except (OSError, NotImplementedError):
        pytest.skip("Windows filesystem does not allow creating symlinks")
    before = ref.read_bytes()
    with pytest.raises(CategoryColorRepairError, match="outside explicitly"):
        restore_from_reference(ref, link, disposable_root=root)
    assert ref.read_bytes() == before



def test_cli_explicit_disposable_root_applies_only_to_candidate(tmp_path):
    import json

    from scripts.restore_categorical_colors import main

    ref, cand, original, _missing = _fixture(tmp_path)
    snapshot = ref.read_bytes()
    receipt = tmp_path / "private-receipt.json"
    assert main([
        "--reference", str(ref),
        "--candidate", str(cand),
        "--disposable-root", str(tmp_path / "scratch_candidate"),
        "--receipt", str(receipt),
    ]) == 0
    data = json.loads(receipt.read_text(encoding="utf8"))
    assert data["status"] == "repaired"
    assert data["selector_count"] == 3
    assert ref.read_bytes() == snapshot
    assert json.loads(cand.read_text())["visual"]["objects"]["dataPoint"] == (
        original["visual"]["objects"]["dataPoint"])


def test_cli_without_authorized_disposable_root_exits_before_mutation(tmp_path):
    from scripts.restore_categorical_colors import main

    ref, cand, _original, _missing = _fixture(tmp_path)
    before = cand.read_bytes()
    receipt = tmp_path / "forbidden-receipt.json"
    with pytest.raises(SystemExit) as error:
        main(["--reference", str(ref), "--candidate", str(cand),
              "--receipt", str(receipt)])
    assert error.value.code == 2
    assert not receipt.exists()
    assert cand.read_bytes() == before


def test_cli_rejects_broad_root_including_original_reference(tmp_path):
    from scripts.restore_categorical_colors import main

    ref, cand, _original, _missing = _fixture(tmp_path)
    before = cand.read_bytes()
    receipt = tmp_path / "forbidden-receipt.json"
    assert main([
        "--reference", str(ref), "--candidate", str(cand),
        "--disposable-root", str(tmp_path), "--receipt", str(receipt),
    ]) == 2
    assert cand.read_bytes() == before
    assert not receipt.exists()
