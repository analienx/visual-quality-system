"""OOXML inspection tests (WP-08 static half): synthetic packages only.

DOC-01 boundary is pinned in code: these tests prove well-formedness and
reference resolution, never pagination. Real page geometry needs spike #9.
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from vqs.document import inspect_docx

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Title</w:t></w:r></w:p>
<w:p><w:r><w:t>Body text.</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<w:p><w:r><w:drawing><w:inline><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:blipFill><a:blip r:embed="{embed}"/></pic:blipFill></pic:pic></a:graphicData>
</a:graphic></w:inline></w:drawing></w:r></w:p>
</w:body></w:document>"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>"""

STYLES = """<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:styleId="Heading1"/><w:style w:styleId="Normal"/>
</w:styles>"""

IMAGE = b"\x89PNG\r\n\x1a\nfakepixels"


def _make_docx(path: Path, *, embed: str = "rId4", include_rels: bool = True,
               include_document: bool = True) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        if include_document:
            archive.writestr("word/document.xml", DOCUMENT.format(embed=embed))
        if include_rels:
            archive.writestr("word/_rels/document.xml.rels", RELS)
        archive.writestr("word/media/image1.png", IMAGE)
        archive.writestr("word/styles.xml", STYLES)


def test_valid_package_inventoried_without_issues(tmp_path: Path) -> None:
    docx = tmp_path / "report.docx"
    _make_docx(docx)
    result = inspect_docx(docx)
    assert result["issues"] == []
    inventory = result["inventory"]
    assert inventory["paragraphs"] == 4
    assert inventory["headings"] == 1
    assert inventory["tables"] == 1
    assert inventory["style_ids"] == ["Heading1", "Normal"]
    assert inventory["images"] == [{
        "id": "rId4", "part": "word/media/image1.png",
        "sha256": hashlib.sha256(IMAGE).hexdigest(),
    }]


def test_broken_embed_reference_fails(tmp_path: Path) -> None:
    docx = tmp_path / "broken.docx"
    _make_docx(docx, embed="rId9")
    result = inspect_docx(docx)
    assert any(row["rule"] == "broken_relationship" and row["id"] == "rId9"
               for row in result["issues"])


def test_missing_document_part_fails(tmp_path: Path) -> None:
    docx = tmp_path / "nodoc.docx"
    _make_docx(docx, include_document=False)
    result = inspect_docx(docx)
    assert any(row["rule"] == "missing_required_part" for row in result["issues"])


def test_non_zip_is_invalid_package(tmp_path: Path) -> None:
    junk = tmp_path / "junk.docx"
    junk.write_text("not a zip", encoding="utf-8")
    result = inspect_docx(junk)
    assert any(row["rule"] == "invalid_package" for row in result["issues"])


def test_absolute_relationship_target_resolves(tmp_path: Path) -> None:
    """OPC absolute part names (``/word/media/...``) are valid targets."""
    docx = tmp_path / "absolute.docx"
    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("word/document.xml", DOCUMENT.format(embed="rId4"))
        archive.writestr("word/_rels/document.xml.rels",
                         RELS.replace('Target="media/image1.png"',
                                      'Target="/word/media/image1.png"'))
        archive.writestr("word/media/image1.png", IMAGE)
    result = inspect_docx(docx)
    assert result["issues"] == []
    assert result["inventory"]["images"][0]["part"] == "word/media/image1.png"


def test_external_target_cannot_satisfy_embed(tmp_path: Path) -> None:
    docx = tmp_path / "external.docx"
    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("word/document.xml", DOCUMENT.format(embed="rId4"))
        archive.writestr("word/_rels/document.xml.rels",
                         RELS.replace('Target="media/image1.png"',
                                      'Target="media/image1.png" TargetMode="External"'))
        archive.writestr("word/media/image1.png", IMAGE)
    result = inspect_docx(docx)
    assert any(row["rule"] == "broken_relationship" and row["id"] == "rId4"
               for row in result["issues"])


def test_corrupt_member_is_an_issue_not_a_crash(tmp_path: Path) -> None:
    docx = tmp_path / "crc.docx"
    _make_docx(docx)
    data = bytearray(docx.read_bytes())
    # Flip bytes inside the stored image payload so its CRC check fails.
    offset = data.find(b"word/media/image1.png") + len("word/media/image1.png")
    for index in range(offset, offset + 8):
        data[index] ^= 0xFF
    docx.write_bytes(bytes(data))
    result = inspect_docx(docx)
    assert any(row["rule"] in ("corrupt_part", "broken_relationship")
               for row in result["issues"])
