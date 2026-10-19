"""P17: real Word pagination receipt, no fake Word/LibreOffice acceptance."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from vqs.document import native_word
from vqs.document.native_word import WordNativeError, _word_receipt, run


def _docx(path: Path) -> Path:
    """Tiny but genuine OOXML package with a heading."""
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'<w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        b'<w:r><w:t>Synthetic heading</w:t></w:r>'
        b'</w:p></w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return path


def _payload(source: Path) -> dict:
    return {
        "schema": native_word.WORD_SCHEMA, "renderer": "Microsoft Word",
        "native_word_pid": 4042, "word_version": "16.0",
        "read_only": True, "source_full_name": str(source.resolve()),
        "page_count": 1, "paragraphs": 1, "tables": 0,
        "headings": [{"paragraph": 1, "page": 1, "y_points": 72.0,
                      "style": "Heading 1"}],
        "table_pages": [],
        "sections": [{
            "index": 1, "width_points": 612.0, "height_points": 792.0,
            "top_points": 72.0, "bottom_points": 72.0,
            "left_points": 72.0, "right_points": 72.0,
        }],
        "utc": "2026-10-19T09:00:00Z",
    }


def _pdf_content() -> bytes:
    return b"%PDF-1.7\n" + b"A" * 2048 + b"\n%%EOF\n"


def _run(tmp_path: Path, change=None, *, broken_pdf=False,
         source_mutation=False):
    source = _docx(tmp_path / "synthetic.docx")
    output = tmp_path / "native.pdf"

    def fake(source_arg: Path, temp_pdf: Path) -> dict:
        assert source_arg == source.resolve()
        assert temp_pdf != output
        payload = _payload(source)
        if change:
            change(payload)
        if source_mutation:
            source.write_bytes(source.read_bytes() + b"changed")
        temp_pdf.write_bytes(b"not a PDF" if broken_pdf else _pdf_content())
        return payload

    return source, output, run(source, output, invoke=fake)


def test_realistic_word_receipt_exports_complete_private_pdf_without_promotion(tmp_path):
    source, output, evidence = _run(tmp_path)
    assert evidence["native_word_render"] == "pass"
    assert evidence["backend_equivalence"] == {
        "verdict": "pass", "backend": "Microsoft Word",
    }
    assert evidence["page_count"] == 1
    assert evidence["heading_position_coverage"] == "complete"
    assert evidence["headings"][0]["page"] == 1
    assert evidence["pdf_sha256"] == hashlib.sha256(_pdf_content()).hexdigest()
    assert evidence["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert output.read_bytes() == _pdf_content()
    assert evidence["independent_paginated_review"] == "blocked"
    assert evidence["document_report_consistency"] == "blocked"
    assert evidence["independent_acceptance"] == "blocked"


@pytest.mark.parametrize("change,expected", [
    (lambda x: x.__setitem__("renderer", "LibreOffice"), "fail"),
    (lambda x: x.__setitem__("native_word_pid", 0), "fail"),
    (lambda x: x.__setitem__("read_only", False), "fail"),
    (lambda x: x.__setitem__("source_full_name", "C:/wrong.docx"), "fail"),
    (lambda x: x.__setitem__("page_count", 0), "blocked"),
    (lambda x: x["headings"][0].__setitem__("page", 2), "blocked"),
    (lambda x: x["headings"][0].__setitem__("y_points", "imagined"), "blocked"),
    (lambda x: x["headings"][0].__setitem__("y_points", -1), "pass"),
    (lambda x: x.__setitem__("headings", []), "blocked"),
    (lambda x: x["sections"][0].__setitem__("left_points", 600), "fail"),
    (lambda x: x.__setitem__("tables", 2), "fail"),
    (lambda x: x["sections"][0].__setitem__("width_points", float("nan")), "blocked"),
])
def test_wrong_renderer_or_pagination_positions_fail_closed(tmp_path, change, expected):
    _, output, evidence = _run(tmp_path, change)
    assert evidence["native_word_render"] == expected
    assert output.exists() is (expected == "pass")
    if expected == "pass":
        assert evidence["heading_position_coverage"] == "partial"


def test_no_invented_pdf_or_source_change_can_pass(tmp_path):
    _, output, evidence = _run(tmp_path, broken_pdf=True)
    assert evidence["native_word_render"] == "blocked"
    assert not output.exists()
    next_dir = tmp_path / "modified"
    next_dir.mkdir()
    _, output, evidence = _run(next_dir, source_mutation=True)
    assert evidence["native_word_render"] == "fail"
    assert not output.exists()


def test_refuses_existing_target_without_launching_word(tmp_path):
    source = _docx(tmp_path / "sample.docx")
    output = tmp_path / "keep.pdf"
    output.write_bytes(b"user-owned PDF")
    result = run(source, output, invoke=lambda *_: pytest.fail("never launch Word"))
    assert result["native_word_render"] == "blocked"
    assert output.read_bytes() == b"user-owned PDF"


def test_corrupt_docx_blocks_without_launch(tmp_path):
    source = tmp_path / "corrupt.docx"
    source.write_bytes(b"bad zip not a DOCX")
    result = run(source, tmp_path / "output.pdf",
                 invoke=lambda *_: pytest.fail("must not invoke Word"))
    assert result["native_word_render"] == "blocked"


def test_failed_pdf_publication_removes_only_our_new_partial_file(monkeypatch, tmp_path):
    source = _docx(tmp_path / "synthetic.docx")
    output = tmp_path / "private.pdf"
    original = native_word._pdf

    def sabotage(path):
        if path == output:
            raise WordNativeError("fail", "simulated output tampering")
        return original(path)

    monkeypatch.setattr(native_word, "_pdf", sabotage)

    def fake(src, dest):
        dest.write_bytes(_pdf_content())
        return _payload(source)

    evidence = run(source, output, invoke=fake)
    assert evidence["native_word_render"] == "fail"
    assert not output.exists()


def test_source_change_during_pdf_publication_never_promotes(monkeypatch, tmp_path):
    source = _docx(tmp_path / "synthetic.docx")
    output = tmp_path / "private.pdf"
    original = native_word._source
    calls = 0

    def change_on_last_read(path):
        nonlocal calls
        calls += 1
        if calls == 3:
            source.write_bytes(source.read_bytes() + b"late mutation")
        return original(path)

    monkeypatch.setattr(native_word, "_source", change_on_last_read)

    def fake(src, dest):
        dest.write_bytes(_pdf_content())
        return _payload(source)

    evidence = run(source, output, invoke=fake)
    assert evidence["native_word_render"] == "fail"
    assert not output.exists()


def test_native_backend_is_explicitly_windows_only(monkeypatch, tmp_path):
    monkeypatch.setattr(native_word.os, "name", "posix")
    with pytest.raises(WordNativeError, match="requires Windows"):
        native_word._invoke_native(tmp_path / "test.docx", tmp_path / "out.pdf")


def test_multi_page_table_is_detected_as_review_candidate_not_false_failure(tmp_path):
    source = _docx(tmp_path / "synthetic.docx")
    evidence = _payload(source)
    evidence["tables"] = 1
    evidence["page_count"] = 4
    evidence["table_pages"] = [{"index": 1, "start_page": 1, "end_page": 4}]
    result = _word_receipt(evidence, source,
                           {"paragraphs": 1, "headings": 1, "tables": 1})
    assert result["page_count"] == 4
    assert result["split_table_indices"] == [1]


def test_word_paragraph_and_table_inventory_cannot_be_fabricated(tmp_path):
    source = _docx(tmp_path / "a.docx")
    values = _payload(source)
    with pytest.raises(WordNativeError, match="different table"):
        _word_receipt({**values, "tables": 1}, source,
                      {"paragraphs": 1, "headings": 1, "tables": 0})
