"""P19 all-page Word PDF witnesses: real decoder, adversarial identity/geometry."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.word_p19_page_evidence import main
from vqs.document import page_evidence as pe


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _docx(path: Path, *, broken_link=False) -> Path:
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'<w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        b'<w:r><w:t>Native Word evidence source</w:t></w:r></w:p>'
        + (b'<w:p><w:hyperlink w:anchor="_TocMissing">'
           b'<w:r><w:t>Broken TOC link</w:t></w:r></w:hyperlink></w:p>'
           if broken_link else b'') +
        b'</w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return path


def _pdf(path: Path, *, pages=2, blank_last=False, width=612, height=792,
         page_texts=None) -> Path:
    """Construct tiny real PDF objects/xref using stdlib; no AGPL test tools."""
    objects: list[bytes] = [b""] * (3 + pages * 2)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = b" ".join(f"{4 + index * 2} 0 R".encode() for index in range(pages))
    objects[1] = (b"<< /Type /Pages /Kids [" + kids + b"] /Count "
                  + str(pages).encode() + b" >>")
    objects[2] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for index in range(pages):
        page_id = 4 + index * 2
        content_id = page_id + 1
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode()
        )
        value = page_texts[index] if page_texts is not None else f"Word page {index + 1}"
        data = (b"" if blank_last and index == pages - 1 else
                (f"BT /F1 11 Tf 72 {height - 72} Td ({value}) Tj ET".encode()))
        objects[content_id - 1] = (b"<< /Length " + str(len(data)).encode()
                                   + b" >>\nstream\n" + data + b"\nendstream")
    raw = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(raw))
        raw.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    startxref = len(raw)
    raw.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        raw.extend(f"{offset:010d} 00000 n \n".encode())
    raw.extend((f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                f"startxref\n{startxref}\n%%EOF\n").encode())
    path.write_bytes(raw)
    return path


def _receipt(docx: Path, pdf: Path, *, pages=2) -> dict:
    return {
        "schema": "vqs.word-native-render-evidence/1",
        "native_word_render": "pass",
        "backend_equivalence": {"verdict": "pass", "backend": "Microsoft Word"},
        "independent_paginated_review": "blocked",
        "document_report_consistency": "blocked",
        "independent_acceptance": "blocked",
        "source_sha256": _sha(docx), "pdf_sha256": _sha(pdf),
        "pdf_path": str(pdf), "page_count": pages,
        "sections": [{"width_points": 612.0, "height_points": 792.0}],
        "word_version": "16.0", "native_word_pid": 4932,
    }


@pytest.fixture
def example(tmp_path):
    source = _docx(tmp_path / "source.docx")
    pdf = _pdf(tmp_path / "native.pdf")
    return source, pdf, _receipt(source, pdf), tmp_path / "page-captures"


def test_real_pdf_renders_every_page_and_binds_bytes_and_review_status(example):
    source, pdf, receipt, output = example
    result = pe.run(source, pdf, receipt, output)
    assert result["all_page_capture"] == "pass", result
    assert result["page_count"] == 2
    assert len(result["captured_pages"]) == 2
    assert result["independent_paginated_review"] == "blocked"
    assert result["document_report_consistency"] == "blocked"
    assert result["independent_acceptance"] == "blocked"
    assert result["source_sha256"] == _sha(source)
    assert result["pdf_sha256"] == _sha(pdf)
    assert result["dpi"] == 120
    assert sorted(p.name for p in output.iterdir()) == [
        "index.json", "page-0001.png", "page-0002.png",
    ]
    assert json.loads((output / "index.json").read_text()) == result
    for n, page in enumerate(result["captured_pages"], 1):
        png = output / page["png"]
        assert page["page"] == n
        assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert page["sha256"] == _sha(png)
        assert page["text_word_count"] == 3
        assert page["pixel_width"] > 1000
        assert not page["flags"]


@pytest.mark.parametrize("alter,expected", [
    (lambda r: r.__setitem__("native_word_render", "blocked"), "blocked"),
    (lambda r: r.__setitem__("independent_acceptance", "pass"), "blocked"),
    (lambda r: r.__setitem__("source_sha256", "a" * 64), "fail"),
    (lambda r: r.__setitem__("pdf_sha256", "a" * 64), "fail"),
    (lambda r: r.__setitem__("pdf_path", "/wrong/output.pdf"), "fail"),
    (lambda r: r.__setitem__("page_count", 3), "fail"),
    (lambda r: r.__setitem__("page_count", 251), "blocked"),
    (lambda r: r.__setitem__("sections", []), "blocked"),
    (lambda r: r.__setitem__("native_word_pid", 0), "blocked"),
    (lambda r: r.__setitem__("sections", [{"width_points": 400,
                                          "height_points": 400}]), "fail"),
    (lambda r: r.__setitem__("backend_equivalence", {"verdict": "pass",
                                                    "backend": "LibreOffice"}), "blocked"),
])
def test_native_receipt_contradictions_fail_closed(example, alter, expected):
    source, pdf, receipt, output = example
    alter(receipt)
    result = pe.run(source, pdf, receipt, output)
    assert result["all_page_capture"] == expected, result
    assert not output.exists()


def test_blank_page_is_review_candidate_not_an_independent_pass(tmp_path):
    source = _docx(tmp_path / "source.docx")
    pdf = _pdf(tmp_path / "native.pdf", blank_last=True)
    result = pe.run(source, pdf, _receipt(source, pdf), tmp_path / "pages")
    assert result["all_page_capture"] == "pass"
    assert result["captured_pages"][0]["flags"] == []
    assert result["captured_pages"][1]["flags"] == ["possibly_blank_page"]
    assert result["review_flags"] == 1
    assert result["independent_paginated_review"] == "blocked"


def test_changed_docx_or_pdf_cannot_pass(example):
    source, pdf, receipt, output = example
    source.write_bytes(source.read_bytes() + b"changed")
    assert pe.run(source, pdf, receipt, output)["all_page_capture"] == "fail"
    assert not output.exists()
    receipt["source_sha256"] = _sha(source)
    pdf.write_bytes(pdf.read_bytes() + b"changed")
    assert pe.run(source, pdf, receipt, output)["all_page_capture"] == "fail"
    assert not output.exists()


def test_header_shaped_but_undecodable_pdf_fails_without_files(example):
    source, pdf, receipt, output = example
    pdf.write_bytes(b"%PDF-1.7\n" + b"A" * 2048 + b"\n%%EOF\n")
    receipt["pdf_sha256"] = _sha(pdf)
    result = pe.run(source, pdf, receipt, output)
    assert result["all_page_capture"] == "fail"
    assert not output.exists()


def test_existing_output_is_preserved_and_no_overwrite(example):
    source, pdf, receipt, output = example
    output.mkdir()
    marker = output / "important.txt"
    marker.write_text("keep")
    result = pe.run(source, pdf, receipt, output)
    assert result["all_page_capture"] == "blocked"
    assert marker.read_text() == "keep"


def test_generated_images_are_removed_if_source_changes_mid_capture(
        monkeypatch, example):
    source, pdf, receipt, output = example
    original = pe._file_hash
    checks = 0

    def mutate(path, **kwargs):
        nonlocal checks
        checks += 1
        if checks == 3:
            source.write_bytes(source.read_bytes() + b"late")
        return original(path, **kwargs)

    monkeypatch.setattr(pe, "_file_hash", mutate)
    result = pe.run(source, pdf, receipt, output)
    assert result["all_page_capture"] == "fail"
    assert not output.exists()
    assert source.read_bytes().endswith(b"late")


def test_failed_last_index_write_never_returns_pass_or_leaves_pages(monkeypatch, example):
    source, pdf, receipt, output = example
    before = (_sha(source), _sha(pdf))

    def deny_index(*_args, **_kwargs):
        raise OSError("simulated full disk during final index publication")

    monkeypatch.setattr(pe.json, "dump", deny_index)
    result = pe.run(source, pdf, receipt, output)
    assert result["all_page_capture"] == "blocked"
    assert not output.exists()
    assert (_sha(source), _sha(pdf)) == before


def test_raster_cap_stops_before_output(monkeypatch, example):
    source, pdf, receipt, output = example
    monkeypatch.setattr(pe, "MAX_PIXELS_PER_PAGE", 100)
    result = pe.run(source, pdf, receipt, output)
    assert result["all_page_capture"] == "blocked"
    assert not output.exists()


def test_cli_exports_only_to_new_directory(example, tmp_path, capsys):
    source, pdf, receipt, output = example
    native = tmp_path / "receipt.json"
    native.write_text(json.dumps(receipt))
    code = main([str(source), "--pdf", str(pdf),
                 "--native-receipt", str(native), "--pages-dir", str(output)])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["all_page_capture"] == "pass"
    assert summary["independent_paginated_review"] == "blocked"
    assert summary["document_report_consistency"] == "blocked"
    assert Path(summary["index"]).is_file()
    assert main([str(source), "--pdf", str(pdf),
                 "--native-receipt", str(native), "--pages-dir", str(output)]) == 2


def test_page_size_match_requires_real_finite_width_and_height():
    assert pe._page_size_matches(612, 792, [{"width_points": 612.2,
                                            "height_points": 792.2}])
    assert pe._page_size_matches(792, 612, [{"width_points": 612,
                                            "height_points": 792}])
    assert not pe._page_size_matches(612, 792, [{"width_points": float("nan"),
                                                "height_points": 792}])
    assert not pe._page_size_matches(612, 792, [{"width_points": "612",
                                                "height_points": 792}])


def test_visible_word_bookmark_errors_override_clean_pixel_flags(tmp_path):
    source = _docx(tmp_path / "broken-bookmarks.docx", broken_link=True)
    pdf = _pdf(tmp_path / "native.pdf", page_texts=[
        "Error! Bookmark not defined. Error! Bookmark not defined.",
        "Owner: [To be confirmed]",
    ])
    result = pe.run(source, pdf, _receipt(source, pdf), tmp_path / "pages")
    assert result["all_page_capture"] == "pass"
    assert result["rendered_field_integrity"] == "fail"
    assert result["document_bookmark_integrity"] == "fail"
    assert result["unresolved_internal_bookmark_links"] == 1
    assert result["field_error_counts"] == {"word_bookmark_not_defined": 2}
    assert result["placeholder_counts"] == {"unconfirmed_owner_or_value": 1}
    assert "field_error:word_bookmark_not_defined" in result["captured_pages"][0]["flags"]
    assert "placeholder:unconfirmed_owner_or_value" in result["captured_pages"][1]["flags"]
    assert result["independent_paginated_review"] == "blocked"
    assert result["document_report_consistency"] == "blocked"
    assert result["independent_acceptance"] == "blocked"
