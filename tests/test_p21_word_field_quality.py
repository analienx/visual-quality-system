"""P21: real Word field failures cannot hide behind good page geometry."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from vqs.document.field_quality import scan_text
from vqs.document.inspect import inspect_docx


def test_known_word_reference_failures_detected_without_raw_text_in_receipt():
    scan = scan_text(
        "Table of Contents\r\nError! Bookmark not defined.\n"
        "Error!  Bookmark   not defined\r\n"
        "ERROR! Reference source not found.\n"
        "Error! No table of contents entries found.\n")
    assert scan == {
        "errors": {
            "word_bookmark_not_defined": 2,
            "word_reference_source_not_found": 1,
            "word_toc_entries_not_found": 1,
        },
        "placeholders": {},
    }
    assert "Table of Contents" not in str(scan)


def test_visible_placeholders_are_review_candidates_not_auto_field_failures():
    scan = scan_text("ORG logo — [To be confirmed] — [Document Owner]")
    assert scan["errors"] == {}
    assert scan["placeholders"] == {
        "unconfirmed_owner_or_value": 1,
        "document_owner_placeholder": 1,
        "organization_logo_placeholder": 1,
    }


def test_normalized_word_field_output_and_bounds():
    assert scan_text("Ｅｒｒｏｒ！ Bookmark not defined.")["errors"] == {
        "word_bookmark_not_defined": 1,
    }
    assert scan_text("This guide illustrates the word error only")["errors"] == {}
    assert scan_text("Chyba! Záložka není definována")["errors"] == {}
    with pytest.raises(ValueError, match="bounded"):
        scan_text("x" * 4_000_001)
    with pytest.raises(TypeError, match="string"):
        scan_text(None)


def _docx(path: Path, body: str) -> Path:
    xml = (f'<w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return path


def test_ooxml_broken_internal_links_without_bookmark_definitions(tmp_path):
    body = "".join(f'<w:p><w:hyperlink w:anchor="_Toc{i}">'
                   f'<w:r><w:t>Heading {i}</w:t></w:r></w:hyperlink></w:p>'
                   for i in range(26))
    source = _docx(tmp_path / "generated_toc.docx", body)
    result = inspect_docx(source)
    assert result["issues"] == []
    assert result["inventory"]["bookmark_definitions"] == 0
    assert result["inventory"]["internal_bookmark_links"] == 26
    assert result["inventory"]["unresolved_internal_bookmark_links"] == 26


def test_defined_bookmark_is_not_a_false_internal_link_failure(tmp_path):
    body = ('<w:p><w:bookmarkStart w:id="1" w:name="_Toc1"/>'
            '<w:r><w:t>Heading</w:t></w:r>'
            '<w:bookmarkEnd w:id="1"/></w:p>'
            '<w:p><w:hyperlink w:anchor="_Toc1">'
            '<w:r><w:t>TOC</w:t></w:r></w:hyperlink></w:p>')
    source = _docx(tmp_path / "valid_toc.docx", body)
    result = inspect_docx(source)
    assert result["inventory"]["bookmark_definitions"] == 1
    assert result["inventory"]["internal_bookmark_links"] == 1
    assert result["inventory"]["unresolved_internal_bookmark_links"] == 0


def test_external_hyperlinks_not_misclassified_as_missing_bookmarks(tmp_path):
    body = ('<w:p><w:hyperlink r:id="rIdExternal" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<w:r><w:t>external</w:t></w:r></w:hyperlink></w:p>')
    result = inspect_docx(_docx(tmp_path / "external.docx", body))
    assert result["inventory"]["internal_bookmark_links"] == 0
    assert result["inventory"]["unresolved_internal_bookmark_links"] == 0
