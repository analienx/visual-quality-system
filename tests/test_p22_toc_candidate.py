"""P22: source confinement, native attestation, negative repair controls."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from vqs.document import toc_candidate as tc


def _xml(*, broken=True, toc=True) -> str:
    target = "_TocMissing" if broken else "_TocValid"
    definition = "" if broken else f'<w:bookmarkStart w:id="1" w:name="{target}"/>'
    instr = ('<w:r><w:instrText> TOC \\o "1-3" </w:instrText></w:r>' if toc else "")
    return (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>{definition}'
        '<w:r><w:t>Revenue</w:t></w:r></w:p>'
        f'<w:p>{instr}<w:hyperlink w:anchor="{target}">'
        '<w:r><w:t>Revenue TOC entry</w:t></w:r></w:hyperlink></w:p>'
        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>$6.82M</w:t></w:r>'
        '</w:p></w:tc></w:tr></w:tbl>'
        '</w:body></w:document>'
    )


def _write(path: Path, source: str) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", source)
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt(source: Path, candidate: Path) -> dict:
    return {"schema": tc.NATIVE_SCHEMA, "renderer": "Microsoft Word",
            "native_word_pid": 3109, "word_version": "16.0",
            "source_full_name": str(source.resolve()),
            "candidate_full_name": str(candidate.resolve()),
            "source_opened_read_only": True,
            "toc_count_before": 1, "toc_count_after": 1,
            "utc": "2026-10-20T07:00:00Z"}


def _invoke(source: Path, candidate: Path, *, mutate=None) -> dict:
    xml = _xml(broken=False)
    if mutate is not None:
        xml = mutate(xml)
    _write(candidate, xml)
    return _receipt(source, candidate)


@pytest.fixture
def files(tmp_path):
    return _write(tmp_path / "source.docx", _xml()), tmp_path / "candidate.docx"


def test_new_candidate_repairs_one_toc_preserving_source_semantics(files):
    source, candidate = files
    original = _sha(source)
    result = tc.run(source, candidate, invoke=_invoke)
    assert result["toc_candidate_update"] == "pass", result
    assert result["source_sha256"] == original == _sha(source)
    assert result["candidate_sha256"] == _sha(candidate)
    assert result["source_bookmark_links_unresolved"] == 1
    assert result["candidate_bookmark_links_unresolved"] == 0
    assert result["candidate_bookmark_definitions"] == 1
    assert result["preserved_content"]["heading_texts"] == 1
    assert result["preserved_content"]["table_cell_texts"] == 1
    assert result["logical_table_groups"] == 1
    assert result["non_table_body_delta"]["independent_prose_review"] == "not_triggered"
    assert result["native_paginated_review"] == "blocked"
    assert result["rendered_field_integrity"] == "blocked"
    assert result["independent_acceptance"] == "blocked"


@pytest.mark.parametrize("xml", [_xml(broken=False), _xml(toc=False)])
def test_no_repairable_source_does_not_launch_word(tmp_path, xml):
    source = _write(tmp_path / "source.docx", xml)
    candidate = tmp_path / "candidate.docx"
    result = tc.run(source, candidate, invoke=lambda *_: pytest.fail("Word launched"))
    assert result["toc_candidate_update"] == "blocked"
    assert not candidate.exists()


def test_existing_candidate_not_overwritten(files):
    source, candidate = files
    candidate.write_bytes(b"user-owned")
    result = tc.run(source, candidate, invoke=lambda *_: pytest.fail("Word launched"))
    assert result["toc_candidate_update"] == "blocked"
    assert candidate.read_bytes() == b"user-owned"


@pytest.mark.parametrize("change", [
    lambda s: s.replace("Revenue</w:t>", "Changed</w:t>"),
    lambda s: s.replace("$6.82M", "$0"),
    lambda s: s.replace('<w:bookmarkStart w:id="1" w:name="_TocValid"/>', ""),
    lambda s: s.replace(" TOC ", " OTHER "),
])
def test_semantically_changed_candidate_does_not_publish(files, change):
    source, candidate = files
    result = tc.run(source, candidate,
                    invoke=lambda src, out: _invoke(src, out, mutate=change))
    assert result["toc_candidate_update"] == "fail", result
    assert not candidate.exists()


def test_other_prose_changes_are_explicitly_review_required(files):
    source, candidate = files
    result = tc.run(source, candidate, invoke=lambda src, out: _invoke(
        src, out, mutate=lambda s: s.replace(
            "<w:tbl>", "<w:p><w:r><w:t>Added prose"
            "</w:t></w:r></w:p><w:tbl>")))
    assert result["toc_candidate_update"] == "pass"
    assert result["non_table_body_delta"]["changed_hunks"] == 1
    assert result["non_table_body_delta"]["independent_prose_review"] == "required"
    assert result["independent_acceptance"] == "blocked"


@pytest.mark.parametrize("change", [
    lambda p: p.__setitem__("renderer", "LibreOffice"),
    lambda p: p.__setitem__("native_word_pid", 0),
    lambda p: p.__setitem__("source_opened_read_only", False),
    lambda p: p.__setitem__("toc_count_before", 0),
    lambda p: p.__setitem__("candidate_full_name", "C:/wrong.docx"),
])
def test_contradicted_native_receipt_rejected(files, change):
    source, candidate = files

    def broken(src, out):
        item = _invoke(src, out)
        change(item)
        return item

    result = tc.run(source, candidate, invoke=broken)
    assert result["toc_candidate_update"] == "fail"
    assert not candidate.exists()


def test_source_mutation_rejected_without_candidate(files):
    source, candidate = files

    def tamper(src, out):
        response = _invoke(src, out)
        src.write_bytes(src.read_bytes() + b"tampered")
        return response

    result = tc.run(source, candidate, invoke=tamper)
    assert result["toc_candidate_update"] == "fail"
    assert not candidate.exists()


def test_partial_publication_cleanup_only_own_candidate(files, monkeypatch):
    source, candidate = files
    original = tc._source

    def fail_publish(path):
        if path == candidate:
            raise tc.TocCandidateError("fail", "postcopy tamper simulated")
        return original(path)

    monkeypatch.setattr(tc, "_source", fail_publish)
    result = tc.run(source, candidate, invoke=_invoke)
    assert result["toc_candidate_update"] == "fail"
    assert not candidate.exists()


def test_no_native_word_on_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(tc.os, "name", "posix")
    with pytest.raises(tc.TocCandidateError, match="requires Windows"):
        tc._invoke_native(tmp_path / "source.docx", tmp_path / "candidate.docx")
