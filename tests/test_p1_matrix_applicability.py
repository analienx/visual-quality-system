"""A non-matrix page cannot inflate G2 matrix checks or self-attest N/A."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_review_canvas_bundle import _ready_bundle
from vqs.review.bundle import pack
from vqs.review.muse import CHECKS, MuseVisionReviewer
from vqs.review.port import ReviewError, review_bundle


def _bundle(tmp_path: Path) -> Path:
    report, renders, bundle = _ready_bundle(tmp_path)
    pack(str(report), str(renders), str(bundle), "separate-fixer")
    return bundle


class _NeutralPort:
    reviewer_id = "independent-auditor"

    def __init__(self, check: str):
        self.check = check

    def review(self, _bundle: str) -> dict:
        return {"observations": [{
            "page_id": "p1", "check": self.check,
            "verdict": "not_applicable",
            "detail": {"reason": "no matching visual"},
        }]}


def test_sealed_inventory_allows_matrix_na_but_not_a_green_release(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    port = _NeutralPort("table_matrix_overflow")
    result = review_bundle(bundle_dir=str(bundle), reviewer=port,
                           reviewer_id=port.reviewer_id,
                           fixer_id="separate-fixer")
    assert result["tally"]["pass"] == 0
    assert result["tally"]["not_applicable"] == 1
    assert result["visual"] == "blocked"


def test_unrelated_check_cannot_be_declared_na(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    port = _NeutralPort("text_clipping")
    with pytest.raises(ReviewError, match="not_applicable"):
        review_bundle(bundle_dir=str(bundle), reviewer=port,
                      reviewer_id=port.reviewer_id, fixer_id="separate-fixer")


def test_unsealed_inventory_edit_is_rejected(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    port = _NeutralPort("table_matrix_overflow")
    path = bundle / "inventory.json"
    path.write_text(path.read_text(encoding="utf8") + " ", encoding="utf8")
    with pytest.raises(ReviewError, match="bundle invalid"):
        review_bundle(bundle_dir=str(bundle), reviewer=port,
                      reviewer_id=port.reviewer_id, fixer_id="separate-fixer")


def test_model_matrix_defect_without_matrix_source_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle(tmp_path)
    monkeypatch.setenv("VQS_ALLOW_VISION_UPLOAD", "1")

    def runner(*_args: object, **_kw: object) -> SimpleNamespace:
        items = [
            {
                "check": name, "verdict": (
                    "fail" if name == "table_matrix_overflow" else "pass"
                ),
                "detail": "The matrix body row is clipped above the footer."
                if name == "table_matrix_overflow"
                else "The visible content is readable on the captured page.",
            }
            for name in CHECKS
        ]
        return SimpleNamespace(returncode=0,
                               stdout=json.dumps({"checks": items}), stderr="")

    muse = MuseVisionReviewer(executable="synthetic-test-muse", runner=runner)
    result = review_bundle(bundle_dir=str(bundle), reviewer=muse,
                           reviewer_id=muse.reviewer_id,
                           fixer_id="separate-fixer")
    matrix = next(x for x in result["observations"]
                  if x["check"] == "table_matrix_overflow")
    assert matrix["verdict"] == "blocked"
    assert matrix["detail"]["source_conflict"] == (
        "matrix_claim_without_declared_matrix")
    assert result["visual"] == "blocked"
