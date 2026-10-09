"""R01-R03 RED: canonical PBIR index and required report/version files.

Official layout: optional index at definition/pages/pages.json
(pageOrder + activePageName); definition/pages.json is legacy;
absent index orders by display name; listed-but-missing dirs are
ignored; report.json (with $schema/layoutOptimization/
themeCollection) and version.json are required. Every test here
fails on the pre-R3 reader and passes after the fix.
"""
import json
from pathlib import Path

import pytest

from vqs.pbir import read_report_files, report_context

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")
SCHEMA_INDEX = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.1.0/schema.json")

_MISSING = object()


def _report(root: Path, pages: dict[str, str],
            canonical: object = _MISSING, legacy: object = _MISSING,
            version: object = _MISSING,
            report_doc: object = _MISSING) -> Path:
    report = root / "R.Report"
    pages_root = report / "definition" / "pages"
    for page_id, display in pages.items():
        page_dir = pages_root / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(
            json.dumps({"displayName": display,
                        "width": 1280, "height": 720}),
            encoding="utf-8")
    if canonical is not _MISSING:
        target = pages_root / "pages.json"
        target.write_text(canonical if isinstance(canonical, str)
                          else json.dumps(canonical), encoding="utf-8")
    if legacy is not _MISSING:
        target = report / "definition" / "pages.json"
        target.write_text(legacy if isinstance(legacy, str)
                          else json.dumps(legacy), encoding="utf-8")
    else:
        (report / "definition").mkdir(parents=True, exist_ok=True)
    if version is not _MISSING:
        target = report / "definition" / "version.json"
        target.write_text(version if isinstance(version, str)
                          else json.dumps(version), encoding="utf-8")
    if report_doc is not _MISSING:
        target = report / "definition" / "report.json"
        target.write_text(report_doc if isinstance(report_doc, str)
                          else json.dumps(report_doc), encoding="utf-8")
    return report


def _valid(version: bool = True, report_doc: bool = True) -> dict:
    extra: dict = {}
    if version:
        extra["version"] = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}
    if report_doc:
        extra["report_doc"] = {
            "$schema": SCHEMA_REPORT,
            "layoutOptimization": "None",
            "themeCollection": {},
        }
    return extra


def test_canonical_index_order_honored(tmp_path: Path) -> None:
    """RED R01: canonical pages/pages.json order must win."""
    report = _report(tmp_path, {"P1": "Beta", "P2": "Alpha"},
                     canonical={"$schema": SCHEMA_INDEX,
                                "pageOrder": ["P2", "P1"]},
                     **_valid())
    info = report_context(report)
    assert [page["id"] for page in info["pages"]] == ["P2", "P1"]


def test_legacy_index_honored_with_info(tmp_path: Path) -> None:
    """RED R01: legacy definition/pages.json keeps working, flagged."""
    report = _report(tmp_path, {"P1": "Beta", "P2": "Alpha"},
                     legacy={"pageOrder": ["P2", "P1"]}, **_valid())
    info = report_context(report)
    assert [page["id"] for page in info["pages"]] == ["P2", "P1"]
    rules = [issue["rule"] for issue in
             read_report_files(str(report)).get("issues", [])]
    assert "legacy_pages_index" in rules


def test_unindexed_displayname_order_no_block(tmp_path: Path) -> None:
    """RED R01: absent index orders by display name, blocking nothing."""
    report = _report(tmp_path, {"P1": "Beta", "P2": "Alpha"}, **_valid())
    info = report_context(report)
    assert [page["id"] for page in info["pages"]] == ["P2", "P1"]
    rules = [issue["rule"] for issue in
             read_report_files(str(report)).get("issues", [])]
    assert not any("index" in rule for rule in rules)


def test_malformed_canonical_index_blocks(tmp_path: Path) -> None:
    """RED R01: a present-but-malformed canonical index must block."""
    report = _report(tmp_path, {"P1": "Beta"},
                     canonical="[1, 2, 3]", **_valid())
    with pytest.raises(ValueError, match="pages_index_invalid"):
        report_context(report)


def test_duplicate_order_ids_block(tmp_path: Path) -> None:
    """RED R01/R02: duplicated order IDs must block, never dedupe."""
    report = _report(tmp_path, {"P1": "Beta"},
                     legacy={"pageOrder": ["P1", "P1"]}, **_valid())
    with pytest.raises(ValueError, match="page_order_duplicate"):
        report_context(report)


def test_unlisted_valid_pages_inventoried(tmp_path: Path) -> None:
    """RED R02: valid pages outside pageOrder must be inspected."""
    report = _report(tmp_path, {"P1": "Beta", "P2": "Gamma",
                                "P3": "Aardvark"},
                     legacy={"pageOrder": ["P1"]}, **_valid())
    info = report_context(report)
    assert [page["id"] for page in info["pages"]] == ["P1", "P3", "P2"]


def test_missing_version_blocks(tmp_path: Path) -> None:
    """RED R03: missing version.json must block the inventory."""
    report = _report(tmp_path, {"P1": "Beta"},
                     legacy={"pageOrder": ["P1"]},
                     **_valid(version=False))
    with pytest.raises(ValueError, match="version_missing"):
        report_context(report)


def test_malformed_version_blocks(tmp_path: Path) -> None:
    """RED R03: unreadable version.json must block, naming the file."""
    report = _report(tmp_path, {"P1": "Beta"},
                     legacy={"pageOrder": ["P1"]}, version="{oops",
                     **_valid(version=False, report_doc=True))
    with pytest.raises(ValueError, match="version_unreadable"):
        report_context(report)


def test_missing_report_json_blocks(tmp_path: Path) -> None:
    """RED R03: missing report.json must block the inventory."""
    report = _report(tmp_path, {"P1": "Beta"},
                     legacy={"pageOrder": ["P1"]},
                     **_valid(report_doc=False))
    with pytest.raises(ValueError, match="report_doc_missing"):
        report_context(report)


def test_obsolete_report_schema_blocked(tmp_path: Path) -> None:
    """S01: obsolete report/1.0.0 $schema must block, not pass."""
    obsolete = {"$schema": SCHEMA_REPORT.replace("3.3.0", "1.0.0"),
                "layoutOptimization": "None", "themeCollection": {}}
    report = _report(tmp_path, {"P1": "Beta"},
                     legacy={"pageOrder": ["P1"]}, report_doc=obsolete,
                     **_valid(report_doc=False))
    with pytest.raises(ValueError, match="unsupported_report_version"):
        report_context(report)
