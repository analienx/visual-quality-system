"""OOXML structure inspection (WP-08 static half, issue #13).

Stdlib only (`zipfile` + `xml`). Reports part inventory — paragraphs,
headings, tables, style ids, relationships, embedded-image hashes — and
structural issues (missing required parts, unresolvable rel targets).

DOC-01 boundary, stated plainly: a structure-only pass is NOT pagination
acceptance. Orphaned headings, split tables, and page geometry need a real
paginated render in the declared backend (spike #9); this module only proves
the package is well-formed and its references resolve.
"""
from __future__ import annotations

import hashlib
import posixpath
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
RELS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

REQUIRED_PARTS = ("[Content_Types].xml", "word/document.xml")


def _parse(xml_bytes: bytes) -> ET.Element | None:
    try:
        return ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None


def inspect_docx(path: Path) -> dict:
    """Inventory a DOCX package; corrupt content yields issues, never raises."""
    path = Path(path)
    try:
        archive = zipfile.ZipFile(path)
        names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError) as exc:
        if not path.is_file():
            raise
        return {"inventory": {}, "issues": [{"rule": "invalid_package",
                                             "detail": f"{type(exc).__name__}"}]}
    with archive:
        issues: list[dict] = []
        for required in REQUIRED_PARTS:
            if required not in names:
                issues.append({"rule": "missing_required_part", "part": required})
        if issues:
            return {"inventory": {"parts": sorted(names)}, "issues": issues}
        document = _parse(archive.read("word/document.xml"))
        if document is None:
            return {"inventory": {"parts": sorted(names)},
                    "issues": [{"rule": "unparseable_document"}]}
        paragraphs = document.findall(f".//{W}p")
        headings = [p for p in paragraphs
                    if p.find(f"{W}pPr/{W}pStyle") is not None
                    and str(p.find(f"{W}pPr/{W}pStyle").get(f"{W}val", "")).startswith("Heading")]
        tables = document.findall(f".//{W}tbl")
        # Document.Tables.Count is a *logical main-story* inventory, not a
        # literal count of every OOXML <w:tbl>. Word joins adjacent body table
        # elements without an intervening paragraph (observed 50 -> 42 on a
        # real generated 30-page Contoso DOCX). It also need not include
        # nested tables. Derive a conservative flat-body grouping and refuse
        # parity claims for unsupported wrappers or nested table shapes.
        body = document.find(f"{W}body")
        word_table_groups: int | None = 0 if body is not None else None
        if body is not None:
            prior_was_table = False
            for child in body:
                if child.tag == f"{W}tbl":
                    if not prior_was_table:
                        word_table_groups += 1
                    prior_was_table = True
                    if child.findall(f".//{W}tbl"):
                        word_table_groups = None
                        break
                else:
                    prior_was_table = False
                    if child.findall(f".//{W}tbl"):
                        word_table_groups = None
                        break
        if body is None:
            issues.append({"rule": "missing_body"})
        embeds = [blip.get(f"{R}embed") for blip in document.findall(f".//{A}blip")
                  if blip.get(f"{R}embed")]
        bookmarks = {item.get(f"{W}name") for item in
                     document.findall(f".//{W}bookmarkStart")
                     if item.get(f"{W}name")}
        internal_links = [item.get(f"{W}anchor") for item in
                          document.findall(f".//{W}hyperlink")
                          if item.get(f"{W}anchor")]
        unresolved_links = sum(anchor not in bookmarks for anchor in internal_links)
        rels_name = "word/_rels/document.xml.rels"
        targets: dict[str, str] = {}
        if rels_name in names:
            rels = _parse(archive.read(rels_name))
            if rels is None:
                issues.append({"rule": "unparseable_relationships"})
            else:
                for rel in rels.findall(f"{RELS}Relationship"):
                    rid, target = rel.get("Id"), rel.get("Target")
                    if rid and target:
                        resolved = posixpath.normpath(posixpath.join("word", target))
                        targets[rid] = resolved
        images: list[dict] = []
        for rid in embeds:
            target = targets.get(rid)
            if target is None or target not in names:
                issues.append({"rule": "broken_relationship", "id": rid, "target": target})
                continue
            digest = hashlib.sha256(archive.read(target)).hexdigest()
            images.append({"id": rid, "part": target, "sha256": digest})
        styles: list[str] = []
        if "word/styles.xml" in names:
            root = _parse(archive.read("word/styles.xml"))
            if root is not None:
                styles = sorted({s.get(f"{W}styleId", "") for s in root.findall(f"{W}style")})
        inventory = {"parts": sorted(names), "paragraphs": len(paragraphs),
                     "headings": len(headings), "tables": len(tables),
                     "word_main_story_table_groups": word_table_groups,
                     "bookmark_definitions": len(bookmarks),
                     "internal_bookmark_links": len(internal_links),
                     "unresolved_internal_bookmark_links": unresolved_links,
                     "style_ids": styles, "images": images}
        return {"inventory": inventory, "issues": issues}
