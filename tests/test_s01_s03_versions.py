"""S01-S03: supported report versions, versionMetadata contract, pageOrder optionality.

All tests drive the public preflight route (report_context); a helper
that never reaches report_context cannot close these rows.
"""
import json
from pathlib import Path

import pytest

from vqs.pbir import report_context

FAIR_USE = "https://developer.microsoft.com/json-schemas/fabric/item/"
REPORT_SCHEMA = FAIR_USE + "report/definition/report/{}.0/schema.json"
VERSION_SCHEMA = (FAIR_USE +
                  "report/definition/versionMetadata/1.0.0/schema.json")
INDEX_SCHEMA = (FAIR_USE +
                "report/definition/pagesMetadata/1.1.0/schema.json")


def _report(root: Path, pages=("P1",), report_doc=None, version=None,
            canonical=None) -> Path:
    report = root / "S.Report"
    pages_root = report / "definition" / "pages"
    for page_id in pages:
        page_dir = pages_root / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(
            json.dumps({"displayName": page_id, "width": 1280,
                        "height": 720}), encoding="utf-8")
    if canonical is not None:
        (pages_root / "pages.json").write_text(
            canonical if isinstance(canonical, str)
            else json.dumps(canonical), encoding="utf-8")
    else:
        pages_root.mkdir(parents=True, exist_ok=True)
    if version is None:
        version = {"$schema": VERSION_SCHEMA, "version": "1.0"}
    (report / "definition" / "version.json").write_text(
        version if isinstance(version, str) else json.dumps(version),
        encoding="utf-8")
    if report_doc is None:
        report_doc = {"$schema": REPORT_SCHEMA.format("3.3"),
                      "layoutOptimization": "None", "themeCollection": {}}
    (report / "definition" / "report.json").write_text(
        report_doc if isinstance(report_doc, str)
        else json.dumps(report_doc), encoding="utf-8")
    return report


@pytest.mark.parametrize("schema_version", ["2.0", "3.0", "3.3"])
def test_supported_report_versions_accepted(tmp_path: Path,
                                            schema_version: str) -> None:
    """S01: each claimed supported report version passes preflight."""
    doc = {"$schema": REPORT_SCHEMA.format(schema_version),
           "layoutOptimization": "None", "themeCollection": {}}
    info = report_context(_report(tmp_path, report_doc=doc))
    assert [page["id"] for page in info["pages"]] == ["P1"]


def test_report_without_layout_optimization_accepted(tmp_path: Path) -> None:
    """S01: layoutOptimization is optional on modern report schemas."""
    doc = {"$schema": REPORT_SCHEMA.format("3.3"), "themeCollection": {}}
    info = report_context(_report(tmp_path, report_doc=doc))
    assert [page["id"] for page in info["pages"]] == ["P1"]


def test_report_missing_schema_blocked(tmp_path: Path) -> None:
    """S01: report.json without $schema blocks, never defaults."""
    doc = {"layoutOptimization": "None", "themeCollection": {}}
    with pytest.raises(ValueError, match="report_doc_invalid"):
        report_context(_report(tmp_path, report_doc=doc))


def test_report_banana_schema_blocked(tmp_path: Path) -> None:
    """S01: a non-report $schema blocks with the schema attached."""
    doc = {"$schema": "banana", "layoutOptimization": "None",
           "themeCollection": {}}
    with pytest.raises(ValueError, match="unsupported_report_version"):
        report_context(_report(tmp_path, report_doc=doc))


def test_version_empty_blocked(tmp_path: Path) -> None:
    """S03: {} version.json blocks (missing $schema and version)."""
    with pytest.raises(ValueError, match="version_invalid"):
        report_context(_report(tmp_path, version={}))


def test_version_banana_blocked(tmp_path: Path) -> None:
    """S03: version 'banana' blocks even with a valid $schema."""
    version = {"$schema": VERSION_SCHEMA, "version": "banana"}
    with pytest.raises(ValueError, match="version_invalid"):
        report_context(_report(tmp_path, version=version))


def test_version_wrong_schema_blocked(tmp_path: Path) -> None:
    """S03: a non-versionMetadata $schema blocks version.json."""
    version = {"$schema": REPORT_SCHEMA.format("3.3"), "version": "1.0"}
    with pytest.raises(ValueError, match="version_invalid"):
        report_context(_report(tmp_path, version=version))


def test_version_incompatible_blocked(tmp_path: Path) -> None:
    """S03: version 2.0 against schema 1.0.0 blocks as incompatible."""
    version = {"$schema": VERSION_SCHEMA, "version": "2.0"}
    with pytest.raises(ValueError, match="version_invalid"):
        report_context(_report(tmp_path, version=version))


def test_canonical_index_without_pageorder_accepted(tmp_path: Path) -> None:
    """S02: a present index without pageOrder falls back, never blocks."""
    canonical = {"$schema": INDEX_SCHEMA, "activePageName": "P1"}
    info = report_context(_report(tmp_path, canonical=canonical))
    assert [page["id"] for page in info["pages"]] == ["P1"]


def test_index_null_pageorder_blocked(tmp_path: Path) -> None:
    """S02: explicit null pageOrder is malformed, not missing."""
    with pytest.raises(ValueError, match="pages_index_invalid"):
        report_context(_report(tmp_path,
                               canonical={"pageOrder": None}))


def test_dangling_index_name_ignored(tmp_path: Path) -> None:
    """S02: index names with no page are ignored per Microsoft."""
    canonical = {"$schema": INDEX_SCHEMA, "pageOrder": ["P1", "GHOST"]}
    info = report_context(_report(tmp_path, canonical=canonical))
    assert [page["id"] for page in info["pages"]] == ["P1"]
