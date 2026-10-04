"""F10 RED: missing pages and unsupported sources must block inventory.

report_context omits page_doc_missing, page_dir_missing,
visual_doc_missing, and unsupported_schema from fatal issues and
silently skips missing pages, so a two-page report is reduced to one
expected page and captured as complete. M2 rejects
incomplete/unsupported inventory before Bridge calls or manifest
output, preserving declared page order and exact missing IDs in the
blocked result.
"""
import json
from pathlib import Path

import pytest

from vqs.pbir import report_context

SCHEMA_PAGE = ("https://developer.microsoft.com/json-schemas/fabric/item/"
               "report/definition/page/2.1.0/schema.json")
SCHEMA_PAGE_FUTURE = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                      "report/definition/page/9.0.0/schema.json")


def _report(root: Path, order: list[str],
            pages: dict[str, dict | None]) -> Path:
    report = root / "R.Report"
    pages_root = report / "definition" / "pages"
    (pages_root).mkdir(parents=True)
    (pages_root.parent / "pages.json").write_text(
        json.dumps({"pageOrder": order}), encoding="utf-8")
    for page_id, doc in pages.items():
        page_dir = pages_root / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        if doc is not None:
            (page_dir / "page.json").write_text(json.dumps(doc),
                                                encoding="utf-8")
    return report


def _page(schema: str = SCHEMA_PAGE) -> dict:
    return {"displayName": "P", "width": 1280, "height": 720,
            "$schema": schema}


def test_f10_complete_report_lists_pages_in_order(tmp_path: Path) -> None:
    """Control (passes now): a complete report inventories in order."""
    report = _report(tmp_path, ["P2", "P1"],
                     {"P1": _page(), "P2": _page()})
    info = report_context(report)
    assert [page["id"] for page in info["pages"]] == ["P2", "P1"]


def test_f10_missing_page_dir_blocks(tmp_path: Path) -> None:
    """RED: a declared page without a directory must block naming it."""
    report = _report(tmp_path, ["P1", "P2"], {"P1": _page()})
    with pytest.raises(ValueError, match="P2"):
        report_context(report)


def test_f10_missing_page_doc_blocks(tmp_path: Path) -> None:
    """RED: a page directory without page.json must block naming it."""
    report = _report(tmp_path, ["P1", "P2"],
                     {"P1": _page(), "P2": None})
    with pytest.raises(ValueError, match="P2"):
        report_context(report)


def test_f10_missing_visual_doc_blocks(tmp_path: Path) -> None:
    """RED: a visual directory without visual.json must block naming it."""
    report = _report(tmp_path, ["P1"], {"P1": _page()})
    (report / "definition" / "pages" / "P1" / "visuals" / "ghost").mkdir(
        parents=True)
    with pytest.raises(ValueError, match="ghost"):
        report_context(report)


def test_f10_unsupported_page_schema_blocks(tmp_path: Path) -> None:
    """RED: an unsupported page schema major must block the inventory."""
    report = _report(tmp_path, ["P1"],
                     {"P1": _page(schema=SCHEMA_PAGE_FUTURE)})
    with pytest.raises(ValueError, match="unsupported_schema"):
        report_context(report)
