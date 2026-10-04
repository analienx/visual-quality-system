"""S10: whole-source inventory is required for bundle adjudication.

Omitting or nulling ``source_pages`` blocks through the actual CLI
adjudication route; undeclared, missing, and duplicate pages block;
metadata-only pages (no materialized image bindings) block. A
conformant image-capable bundle still lands the truthful static
checklist (blocked with a passing static_conformance label), never
a pass.
"""
import json
from pathlib import Path

from vqs.cli import main
from vqs.policy import POLICY_VERSION, REQUIRED

REASON = "All labels legible at the target size on the fresh full-canvas render."


def _observations():
    return [{"id": check, "criterion": check, "status": "pass",
             "reason": REASON, "severity": None, "region": None,
             "visual_id": "page", "proposed_fix": ""}
            for check in REQUIRED["report"]]


def _bundle(**overrides):
    bundle = {"source_sha256": "s", "surface": "report", "schema": 1,
              "policy_version": POLICY_VERSION, "fixer_id": "a",
              "source_pages": ["p1"],
              "reviewer": {"id": "b", "role": "independent_visual_reviewer"},
              "image_capability": {"available": True,
                                   "provider": "synthetic-test"},
              "calibration": {"canvas_width": 500, "canvas_height": 500,
                              "scale": 1, "viewport": "500x500@1x",
                              "method": "bridge-screenshot-all"},
              "data_readiness": {"populated": True, "method": "scoped-dax-probe",
                                 "checked_at": "2026-10-03T00:00:00Z"},
              "pages": [{"id": "p1", "image_source_sha256": "s",
                         "image_sha256": "d" * 64,
                         "pixels": [500, 500],
                         "observations": _observations()}]}
    bundle.update(overrides)
    return bundle


def _adjudicate(bundle: dict, root: Path, run_id: str, capsys) -> tuple:
    path = root / f"{run_id}.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    code = main(["adjudicate-bundle", str(path),
                 "--run-root", str(root / "runs"), "--run-id", run_id])
    return code, json.loads(capsys.readouterr().out)


def _checks(out: dict) -> set[str]:
    return {finding["check"] for finding in out["findings"]}


def test_omitted_inventory_blocks(tmp_path: Path, capsys) -> None:
    """S10: no source_pages key blocks, never passes metadata-only."""
    bundle = _bundle()
    del bundle["source_pages"]
    code, out = _adjudicate(bundle, tmp_path, "s10-omitted", capsys)
    assert code == 2
    assert out["verdict"] == "blocked"
    assert "source_pages_missing" in _checks(out)


def test_null_inventory_blocks(tmp_path: Path, capsys) -> None:
    """S10: an explicit null inventory blocks like an omitted one."""
    code, out = _adjudicate(_bundle(source_pages=None), tmp_path,
                            "s10-null", capsys)
    assert code == 2
    assert out["verdict"] == "blocked"
    assert "source_pages_missing" in _checks(out)


def test_conformant_bundle_lands_static_checklist(tmp_path: Path,
                                                 capsys) -> None:
    """S10 positive: image-capable conformance is a static checklist.

    The passing static_conformance label itself is pinned at the
    helper level (R12); the sealed CLI route carries the block.
    """
    code, out = _adjudicate(_bundle(), tmp_path, "s10-static", capsys)
    assert code == 2
    assert out["verdict"] == "blocked"
    assert "image_review_required" in _checks(out)


def test_undeclared_page_blocks(tmp_path: Path, capsys) -> None:
    """S10: page evidence outside the declared inventory blocks."""
    bundle = _bundle()
    bundle["pages"].append(dict(bundle["pages"][0], id="p2"))
    code, out = _adjudicate(bundle, tmp_path, "s10-undeclared", capsys)
    assert code == 2
    assert out["verdict"] == "blocked"
    assert "source_page_undeclared" in _checks(out)


def test_missing_declared_page_blocks(tmp_path: Path, capsys) -> None:
    """S10: a declared page without evidence blocks."""
    code, out = _adjudicate(_bundle(source_pages=["p1", "p2"]), tmp_path,
                            "s10-uncovered", capsys)
    assert code == 2
    assert out["verdict"] == "blocked"
    assert "source_page_uncovered" in _checks(out)


def test_duplicate_pages_block(tmp_path: Path, capsys) -> None:
    """S10: the same page twice blocks, never double-counts."""
    bundle = _bundle()
    bundle["pages"] = [dict(bundle["pages"][0]), dict(bundle["pages"][0])]
    code, out = _adjudicate(bundle, tmp_path, "s10-duplicate", capsys)
    assert code == 2
    assert out["verdict"] == "blocked"
    assert "duplicate_page_evidence" in _checks(out)


def test_metadata_only_pages_block(tmp_path: Path, capsys) -> None:
    """S10: observations without materialized image bindings block."""
    bundle = _bundle()
    for page in bundle["pages"]:
        page.pop("image_sha256", None)
        page.pop("pixels", None)
    code, out = _adjudicate(bundle, tmp_path, "s10-metadata", capsys)
    assert code == 2
    assert out["verdict"] == "blocked"
    assert "page_image_unbound" in _checks(out)
