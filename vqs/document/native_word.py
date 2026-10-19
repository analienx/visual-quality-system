"""P17: native Microsoft Word pagination witness, never OOXML-only acceptance.

Runs Word itself on a read-only, source-fingerprinted, disposable DOCX,
exports all pages to a bounded, private PDF, and reads Word's measured pages,
sections, headings and table spans. Independent page-image review and report
claim consistency are *not* certified by this automated renderer.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from vqs.document.inspect import inspect_docx
from vqs.document.render import check_backend_equivalence

SCHEMA = "vqs.word-native-render-evidence/1"
WORD_SCHEMA = "vqs.native-word-pagination/1"
MAX_DOCX_BYTES = 64 * 1024 * 1024
MAX_PDF_BYTES = 256 * 1024 * 1024


class WordNativeError(ValueError):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)


def _require(condition: bool, status: str, message: str) -> None:
    if not condition:
        raise WordNativeError(status, message)


def _source(path: Path) -> tuple[str, dict[str, Any]]:
    _require(path.suffix.lower() == ".docx" and path.is_file()
             and not path.is_symlink() and not str(path).startswith("\\\\"),
             "blocked", "actual local, regular DOCX file required")
    size = path.stat().st_size
    _require(100 <= size <= MAX_DOCX_BYTES, "blocked", "DOCX is empty or exceeds size cap")
    raw = path.read_bytes()
    _require(len(raw) == size, "blocked", "DOCX changed while fingerprinted")
    structure = inspect_docx(path)
    _require(isinstance(structure, dict) and not structure.get("issues")
             and isinstance(structure.get("inventory"), dict),
             "blocked", "source DOCX OOXML package/relationships fail structural checks")
    return hashlib.sha256(raw).hexdigest(), structure["inventory"]


def _pdf(path: Path) -> tuple[str, int]:
    _require(path.is_file() and not path.is_symlink(), "blocked",
             "Word did not materialize a private PDF")
    size = path.stat().st_size
    _require(1024 <= size <= MAX_PDF_BYTES, "blocked", "PDF is empty or exceeds size cap")
    with path.open("rb") as stream:
        signature = stream.read(8)
        stream.seek(max(0, size - 2048))
        trailer = stream.read()
    _require(signature.startswith(b"%PDF-") and b"%%EOF" in trailer,
             "blocked", "Word export lacks a complete PDF signature/trailer")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    _require(path.stat().st_size == size, "fail", "PDF changed during hashing")
    return digest.hexdigest(), size


def _finite_point(value: Any, *, minimum: float = 0, maximum: float = 3000) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and minimum <= value <= maximum)


def _word_receipt(payload: Any, source: Path, inventory: Mapping[str, Any]) -> dict:
    _require(isinstance(payload, dict) and payload.get("schema") == WORD_SCHEMA
             and payload.get("renderer") == "Microsoft Word"
             and type(payload.get("native_word_pid")) is int
             and payload["native_word_pid"] > 0
             and payload.get("read_only") is True
             and isinstance(payload.get("source_full_name"), str)
             and Path(payload["source_full_name"]).resolve() == source.resolve()
             and isinstance(payload.get("word_version"), str)
             and bool(payload["word_version"])
             and isinstance(payload.get("utc"), str),
             "fail", "native Word renderer/process/source/read-only attestation contradicted")
    pages, paragraphs, table_count = (
        payload.get("page_count"), payload.get("paragraphs"), payload.get("tables"))
    _require(type(pages) is int and 1 <= pages <= 2000
             and type(paragraphs) is int and 1 <= paragraphs <= 15000
             and type(table_count) is int and 0 <= table_count <= 1000,
             "blocked", "native Word page/paragraph/table statistics unavailable")
    expected_groups = inventory.get("word_main_story_table_groups")
    _require(type(expected_groups) is int and 0 <= expected_groups <= inventory.get("tables", 0),
             "blocked", "Word table parity requires a supported flat OOXML body")
    _require(paragraphs >= inventory.get("paragraphs", 0),
             "fail", "Word rendered fewer paragraphs than the OOXML source")
    _require(table_count == expected_groups,
             "fail", "Word logical table count contradicts OOXML adjacent table groups")
    sections = payload.get("sections")
    _require(isinstance(sections, list) and bool(sections),
             "blocked", "native Word section/page margins not reported")
    for index, section in enumerate(sections, 1):
        _require(isinstance(section, dict) and section.get("index") == index,
                 "blocked", "Word section order is incomplete")
        fields = ("width_points", "height_points", "top_points", "bottom_points",
                  "left_points", "right_points")
        _require(all(_finite_point(section.get(key)) for key in fields),
                 "blocked", "Word page/margin measurements missing or nonfinite")
        _require(section["width_points"] >= 200 and section["height_points"] >= 200
                 and section["left_points"] + section["right_points"]
                 < section["width_points"]
                 and section["top_points"] + section["bottom_points"]
                 < section["height_points"],
                 "fail", "Word section margins leave no usable page area")
    headings = payload.get("headings")
    _require(isinstance(headings, list)
             and len(headings) == inventory.get("headings"),
             "blocked", "native Word heading position inventory incomplete")
    positions = []
    last_para = 0
    for heading in headings:
        _require(isinstance(heading, dict)
                 and type(heading.get("paragraph")) is int
                 and last_para < heading["paragraph"] <= paragraphs
                 and type(heading.get("page")) is int
                 and 1 <= heading["page"] <= pages
                 and isinstance(heading.get("style"), str)
                 and bool(heading["style"]),
                 "blocked", "Word heading lacks its page/paragraph/style identity")
        last_para = heading["paragraph"]
        y = heading.get("y_points")
        # Microsoft Word can return -1 for unavailable positions. Keep a
        # partial geometry axis instead of inventing a pixel coordinate.
        _require(_finite_point(y, minimum=-1), "blocked",
                 "Word heading position is not a numeric point measurement")
        positions.append(y >= 0)
    tables = payload.get("table_pages")
    _require(isinstance(tables, list) and len(tables) == table_count,
             "blocked", "native Word table pagination inventory incomplete")
    split = []
    for index, table in enumerate(tables, 1):
        _require(isinstance(table, dict) and table.get("index") == index
                 and type(table.get("start_page")) is int
                 and type(table.get("end_page")) is int
                 and 1 <= table["start_page"] <= table["end_page"] <= pages,
                 "blocked", "native Word table spans contradict page count")
        if table["start_page"] != table["end_page"]:
            split.append(index)
    return {
        "page_count": pages, "paragraphs": paragraphs, "tables": table_count,
        "ooxml_table_elements": inventory["tables"],
        "ooxml_adjacent_table_groups": expected_groups,
        "headings": headings, "sections": sections, "table_pages": tables,
        "split_table_indices": split,
        "heading_position_coverage": "complete" if all(positions) else "partial",
        "native_word_pid": payload["native_word_pid"],
        "word_version": payload["word_version"], "utc": payload["utc"],
    }


def _invoke_native(source: Path, private_pdf: Path) -> dict:
    if os.name != "nt":
        raise WordNativeError("blocked", "native Word COM pagination requires Windows")
    shell = shutil.which("powershell.exe")
    if not shell:
        raise WordNativeError("blocked", "Windows PowerShell is unavailable")
    script = (Path(__file__).resolve().parents[2] /
              "scripts" / "windows" / "native_word_export.ps1")
    if not script.is_file():
        raise WordNativeError("blocked", "native Word script unavailable")
    cmd = [shell, "-NoProfile", "-NonInteractive", "-File", str(script),
           "-DocumentPath", str(source), "-PdfPath", str(private_pdf)]
    try:
        finished = subprocess.run(cmd, capture_output=True, text=True,
                                  check=False, timeout=120, encoding="utf-8-sig")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WordNativeError("blocked", f"native Word automation unavailable: {exc}") from exc
    if finished.returncode != 0:
        raise WordNativeError(
            "blocked", f"native Word refused isolated read-only export: {finished.stderr[-800:]}")
    try:
        return json.loads(finished.stdout.strip())
    except (TypeError, ValueError) as exc:
        raise WordNativeError("blocked", "native Word did not return sole JSON") from exc


def run(source_docx: Path, pdf_output: Path,
        *, invoke: Callable[[Path, Path], dict] = _invoke_native) -> dict:
    """Render exact DOCX in Word; persist no partial PDF on blocked status.

    The native renderer reports *its own* pagination, not pixel completeness
    or an independent verdict on document truth. All pages still require
    visible PDF image review and source-to-report claim verification.
    """
    owned_pdf_created = False
    result: dict[str, Any] = {
        "schema": SCHEMA, "native_word_render": "blocked",
        "independent_paginated_review": "blocked",
        "document_report_consistency": "blocked",
        "independent_acceptance": "blocked",
        "reason": "Word rendering has not been verified",
    }
    try:
        _require(isinstance(source_docx, Path) and isinstance(pdf_output, Path),
                 "blocked", "source and PDF output must be exact filesystem paths")
        _require(pdf_output.suffix.lower() == ".pdf"
                 and pdf_output.resolve() != source_docx.resolve()
                 and not pdf_output.exists() and not pdf_output.is_symlink()
                 and pdf_output.parent.is_dir(),
                 "blocked", "new local private PDF path required; never overwrite")
        source_sha, inventory = _source(source_docx)
        result["source_sha256"] = source_sha
        with tempfile.TemporaryDirectory(
                prefix="vqs-word-private-render-", dir=pdf_output.parent) as temp:
            pending = Path(temp) / "rendered.pdf"
            payload = invoke(source_docx.resolve(), pending)
            numeric = _word_receipt(payload, source_docx, inventory)
            pdf_sha, size = _pdf(pending)
            after_sha, after_inventory = _source(source_docx)
            _require(source_sha == after_sha and inventory == after_inventory,
                     "fail", "read-only native Word render changed DOCX source")
            # Exclusive create, never replace a user-owned PDF even under race.
            with pending.open("rb") as reader, pdf_output.open("xb") as writer:
                owned_pdf_created = True
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
            copied_sha, copied_size = _pdf(pdf_output)
            if copied_sha != pdf_sha or copied_size != size:
                raise WordNativeError("fail", "exported PDF changed while copied")
            final_source, final_inventory = _source(source_docx)
            _require(final_source == source_sha and final_inventory == inventory,
                     "fail", "physical DOCX changed during PDF publication")
            result.update(numeric)
            result.update({
                "native_word_render": "pass", "pdf_sha256": pdf_sha,
                "pdf_bytes": size, "pdf_path": str(pdf_output),
                "backend_equivalence": check_backend_equivalence(
                    "Microsoft Word", payload["renderer"]),
                "reason": ("native Microsoft Word exported an unchanged source as a "
                           "bounded PDF with header/trailer and Word-reported "
                           "pagination; independent PDF visual/claim review blocked"),
            })
    except WordNativeError as exc:
        result["native_word_render"] = exc.status
        result["reason"] = str(exc)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result["reason"] = f"native Word render unavailable: {exc}"
    finally:
        if owned_pdf_created and result["native_word_render"] != "pass":
            try:
                pdf_output.unlink(missing_ok=True)
            except OSError as exc:
                result["reason"] += f"; private partial PDF cleanup failed: {exc}"
    return result
