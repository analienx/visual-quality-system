"""F10 RED: missing pages and unsupported sources must block inventory.

R01/R02: the canonical page index wins, the legacy index is
honored with an info flag, and absent indexes order by display
name; dangling index names are ignored per Microsoft while
missing/unreadable page and visual docs, and unsupported schema
majors all block report_context before any Bridge or manifest
work, preserving declared page order in the blocked result.
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
    (pages_root.parent / "version.json").write_text(
        json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}), encoding="utf-8")
    (pages_root.parent / "report.json").write_text(json.dumps({
        "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                    "report/definition/report/3.3.0/schema.json"),
        "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")
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


def test_f10_dangling_page_ignored(tmp_path: Path) -> None:
    """S02: a declared page without a directory is ignored, not blocked."""
    report = _report(tmp_path, ["P1", "P2"], {"P1": _page()})
    info = report_context(report)
    assert [page["id"] for page in info["pages"]] == ["P1"]


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
