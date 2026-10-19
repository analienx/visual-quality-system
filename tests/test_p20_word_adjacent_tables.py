"""P20: explain real Word 42 logical tables vs 50 adjacent OOXML elements."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from vqs.document.inspect import inspect_docx
from vqs.document.native_word import WordNativeError, _word_receipt

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TABLE = "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
PARA = "<w:p><w:r><w:t>separating paragraph</w:t></w:r></w:p>"


def _docx(path: Path, body: str) -> Path:
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return path


def _payload(source: Path, *, paragraphs: int, tables: int) -> dict:
    return {
        "schema": "vqs.native-word-pagination/1", "renderer": "Microsoft Word",
        "native_word_pid": 5112, "word_version": "16.0",
        "read_only": True, "source_full_name": str(source.resolve()),
        "page_count": 2, "paragraphs": paragraphs, "tables": tables,
        "headings": [], "table_pages": [
            {"index": i, "start_page": 1, "end_page": 2} for i in range(1, tables + 1)],
        "sections": [{
            "index": 1, "width_points": 612.0, "height_points": 792.0,
            "top_points": 72.0, "bottom_points": 72.0,
            "left_points": 72.0, "right_points": 72.0,
        }],
        "utc": "2026-10-19T11:00:00Z",
    }


def test_contoso_shaped_50_xml_tables_are_42_native_word_groups(tmp_path):
    # The actual private Contoso DOCX had 50 sibling w:tbl elements, grouped
    # into 42 consecutive runs without interstitial paragraphs. Recreate the
    # exact group topology, not private content, as a checked-in regression.
    blocks = [TABLE * (2 if i < 8 else 1) for i in range(42)]
    source = _docx(tmp_path / "adjacent.docx", PARA.join(blocks))
    inventory = inspect_docx(source)
    assert inventory["issues"] == []
    assert inventory["inventory"]["tables"] == 50
    assert inventory["inventory"]["word_main_story_table_groups"] == 42
    receipt = _word_receipt(_payload(source, paragraphs=inventory["inventory"]["paragraphs"],
                                    tables=42), source, inventory["inventory"])
    assert receipt["tables"] == 42
    assert receipt["ooxml_table_elements"] == 50
    assert receipt["ooxml_adjacent_table_groups"] == 42
    assert receipt["page_count"] == 2


def test_intervening_paragraph_preserves_distinct_logical_tables(tmp_path):
    source = _docx(tmp_path / "separate.docx", TABLE + PARA + TABLE)
    inventory = inspect_docx(source)["inventory"]
    assert inventory["tables"] == 2
    assert inventory["word_main_story_table_groups"] == 2
    payload = _payload(source, paragraphs=inventory["paragraphs"], tables=1)
    with pytest.raises(WordNativeError, match="logical table count"):
        _word_receipt(payload, source, inventory)


def test_raw_xml_count_never_replaces_word_logical_count(tmp_path):
    source = _docx(tmp_path / "merged.docx", TABLE + TABLE)
    inventory = inspect_docx(source)["inventory"]
    assert inventory["tables"] == 2
    assert inventory["word_main_story_table_groups"] == 1
    payload = _payload(source, paragraphs=inventory["paragraphs"], tables=2)
    with pytest.raises(WordNativeError, match="logical table count"):
        _word_receipt(payload, source, inventory)


@pytest.mark.parametrize("body", [
    # Nested tables are counted by the OOXML inventory but not guaranteed to
    # be included by Word's main-story Tables collection.
    TABLE.replace("</w:tc>", TABLE + "</w:tc>"),
    # Block-level content controls and wrappers are not yet a modelled table
    # collection; never use a guessed direct-child count as validation.
    f"<w:sdt><w:sdtContent>{TABLE}</w:sdtContent></w:sdt>",
])
def test_unsupported_table_topology_blocks_without_false_pass(tmp_path, body):
    source = _docx(tmp_path / "complex.docx", body)
    inventory = inspect_docx(source)["inventory"]
    assert inventory["word_main_story_table_groups"] is None
    payload = _payload(source, paragraphs=inventory["paragraphs"], tables=1)
    with pytest.raises(WordNativeError, match="supported flat OOXML body"):
        _word_receipt(payload, source, inventory)


def test_no_body_is_structural_problem(tmp_path):
    source = _docx(tmp_path / "no_body.docx", "")
    # Remove the body rather than passing its empty content.
    with zipfile.ZipFile(source, "r") as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    xml = xml.replace("<w:body></w:body>", "")
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    result = inspect_docx(source)
    assert {issue["rule"] for issue in result["issues"]} == {"missing_body"}
    assert result["inventory"]["word_main_story_table_groups"] is None


def test_stale_xml_table_topology_cannot_pass_with_fabricated_groups(tmp_path):
    source = _docx(tmp_path / "single.docx", TABLE)
    inventory = inspect_docx(source)["inventory"]
    assert inventory["word_main_story_table_groups"] == 1
    receipt = _payload(source, paragraphs=inventory["paragraphs"], tables=1)
    for invalid in (-1, 2, None, "1", True):
        mutated = {**inventory, "word_main_story_table_groups": invalid}
        with pytest.raises(WordNativeError, match="supported flat OOXML body"):
            _word_receipt(receipt, source, mutated)
