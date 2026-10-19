"""P19: source-bound, every-page raster witness for native Word PDF output.

This is an *evidence producer*, not an independent visual reviewer. It binds
the exact DOCX and PDF to the P17 native-Word receipt, decodes the entire PDF,
and exports immutable per-page PNGs and conservative geometry/ink diagnostics.
Image judgment, text semantics, report figure identity and G5/G6 acceptance
remain blocked until independently inspected.

PDFium is an optional, versioned capability: a missing parser blocks this
stage without weakening the package's stdlib-only core dependencies.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vqs.document.field_quality import scan_text
from vqs.document.inspect import inspect_docx
from vqs.document.native_word import MAX_PDF_BYTES
from vqs.document.native_word import SCHEMA as NATIVE_SCHEMA

SCHEMA = "vqs.word-all-page-evidence/1"
MAX_DOCX_BYTES = 64 * 1024 * 1024
MAX_PAGES = 250
MAX_PIXELS_PER_PAGE = 12_000_000
MAX_PAGE_PNG_BYTES = 32 * 1024 * 1024
MAX_TOTAL_PNG_BYTES = 512 * 1024 * 1024
RENDER_DPI = 120
PDF_POINTS_TOLERANCE = 2.0


class PageEvidenceError(ValueError):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)


def _require(condition: bool, status: str, message: str) -> None:
    if not condition:
        raise PageEvidenceError(status, message)


def _file_hash(path: Path, *, cap: int, kind: str) -> str:
    _require(path.is_file() and not path.is_symlink() and not str(path).startswith("\\\\"),
             "blocked", f"regular local {kind} file required")
    size = path.stat().st_size
    _require(100 <= size <= cap, "blocked", f"{kind} empty or exceeds size cap")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    _require(path.stat().st_size == size, "fail", f"{kind} changed during hashing")
    return digest.hexdigest()


def _page_size_matches(width: float, height: float, sections: list[dict]) -> bool:
    for section in sections:
        w, h = section.get("width_points"), section.get("height_points")
        if (type(w) in (float, int) and type(h) in (float, int)
                and math.isfinite(w) and math.isfinite(h)
                and ((abs(width - w) <= PDF_POINTS_TOLERANCE
                      and abs(height - h) <= PDF_POINTS_TOLERANCE)
                     or (abs(width - h) <= PDF_POINTS_TOLERANCE
                         and abs(height - w) <= PDF_POINTS_TOLERANCE))):
            return True
    return False


def _ink_sample(image: Any) -> float:
    """Small bounded pixel sample, used only to flag *possible* sparse pages.

    It must never turn a source-authenticated image into an independent visual
    pass. Using 64 evenly spaced columns/rows samples body and outer margins.
    """
    _require(image.mode == "RGB", "blocked", "unsupported PDF raster color layout")
    rows = min(image.height, 64)
    cols = min(image.width, 64)
    occupied = 0
    for yi in range(rows):
        y = min(image.height - 1, (yi * image.height + image.height // 2) // rows)
        for xi in range(cols):
            x = min(image.width - 1, (xi * image.width + image.width // 2) // cols)
            if min(image.getpixel((x, y))) < 245:
                occupied += 1
    return round(occupied / (rows * cols), 5)


def _receipt(source: Path, pdf: Path, raw: Any) -> tuple[str, str, int, list[dict]]:
    _require(isinstance(raw, dict) and raw.get("schema") == NATIVE_SCHEMA
             and raw.get("native_word_render") == "pass"
             and raw.get("backend_equivalence") == {
                 "verdict": "pass", "backend": "Microsoft Word"}
             and raw.get("independent_acceptance") == "blocked"
             and raw.get("independent_paginated_review") == "blocked"
             and raw.get("document_report_consistency") == "blocked"
             and type(raw.get("native_word_pid")) is int
             and raw["native_word_pid"] > 0
             and isinstance(raw.get("word_version"), str)
             and bool(raw["word_version"]),
             "blocked", "P17 native Word pass receipt with pending independent gates required")
    pages = raw.get("page_count")
    _require(type(pages) is int and 1 <= pages <= MAX_PAGES,
             "blocked", f"native Word pages missing or exceed {MAX_PAGES}-page cap")
    _require(isinstance(raw.get("pdf_path"), str) and raw["pdf_path"]
             and Path(raw["pdf_path"]).resolve() == pdf.resolve(),
             "fail", "PDF path does not match native Word receipt")
    source_sha = _file_hash(source, cap=MAX_DOCX_BYTES, kind="DOCX")
    pdf_sha = _file_hash(pdf, cap=MAX_PDF_BYTES, kind="PDF")
    _require(source_sha == raw.get("source_sha256"), "fail",
             "DOCX digest no longer matches native Word source")
    _require(pdf_sha == raw.get("pdf_sha256"), "fail",
             "PDF digest no longer matches native Word export")
    sections = raw.get("sections")
    _require(isinstance(sections, list) and bool(sections)
             and all(isinstance(item, dict) for item in sections),
             "blocked", "native Word section geometry absent")
    return source_sha, pdf_sha, pages, sections


def run(source_docx: Path, native_pdf: Path, native_receipt: Mapping[str, Any],
        output_dir: Path) -> dict:
    """Render all PDF pages as numbered PNGs, refusing stale inputs/outputs.

    Only our own newly created output directory is cleaned after an error.
    No source DOCX, PDF, P17 receipt or user-owned artifact is ever modified.
    """
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "all_page_capture": "blocked",
        "rendered_field_integrity": "blocked",
        "document_bookmark_integrity": "blocked",
        "independent_paginated_review": "blocked",
        "document_report_consistency": "blocked",
        "independent_acceptance": "blocked",
        "reason": "all-page Word evidence not yet captured",
    }
    created_dir = False
    created_files: list[Path] = []
    try:
        _require(all(isinstance(item, Path) for item in
                     (source_docx, native_pdf, output_dir)),
                 "blocked", "explicit filesystem paths required")
        _require(source_docx.suffix.lower() == ".docx"
                 and native_pdf.suffix.lower() == ".pdf"
                 and len({source_docx.resolve(), native_pdf.resolve(),
                          output_dir.resolve()}) == 3,
                 "blocked", "distinct DOCX, PDF and output directory required")
        _require(output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
                 and not output_dir.exists() and not output_dir.is_symlink()
                 and not str(output_dir).startswith("\\\\"),
                 "blocked", "new local output directory required; no overwrite")
        source_sha, pdf_sha, page_count, sections = _receipt(
            source_docx, native_pdf, native_receipt)
        document = inspect_docx(source_docx)
        _require(not document.get("issues") and isinstance(document.get("inventory"), dict),
                 "blocked", "source OOXML structure invalid")
        try:
            import pypdfium2 as pdfium  # type: ignore[import-not-found]
        except ImportError as exc:
            raise PageEvidenceError("blocked", "optional PDFium PDF renderer unavailable") from exc
        # Decode all pages and inspect the complete object graph before opening
        # an output directory. Truncated-but-header-shaped PDFs must not pass.
        try:
            reader = pdfium.PdfDocument(str(native_pdf))
        except Exception as exc:
            raise PageEvidenceError("fail", f"native PDF cannot be decoded: {type(exc).__name__}") from exc
        try:
            _require(len(reader) == page_count, "fail",
                     "decoded PDF page count contradicts native Word pagination")
            for index in range(page_count):
                page = reader[index]
                width, height = page.get_size()
                _require(_page_size_matches(width, height, sections),
                         "fail", "PDF page geometry contradicts native Word section size")
                # At selected DPI, no page is permitted to exceed renderer cap.
                w = math.ceil(width * RENDER_DPI / 72)
                h = math.ceil(height * RENDER_DPI / 72)
                _require(w > 0 and h > 0 and w * h <= MAX_PIXELS_PER_PAGE,
                         "blocked", "PDF page raster exceeds bounded resolution")

            output_dir.mkdir(exist_ok=False)
            created_dir = True
            pages: list[dict[str, Any]] = []
            total_png_bytes = 0
            field_errors: dict[str, int] = {}
            placeholders: dict[str, int] = {}
            for index in range(1, page_count + 1):
                page = reader[index - 1]
                bitmap = page.render(scale=RENDER_DPI / 72, draw_annots=True)
                image = bitmap.to_pil().convert("RGB")
                _require(image.width * image.height <= MAX_PIXELS_PER_PAGE,
                         "blocked", "actual PDF raster exceeds bounded resolution")
                ink_ratio = _ink_sample(image)
                textpage = page.get_textpage()
                count_chars = textpage.count_chars()
                _require(count_chars <= 100_000, "blocked",
                         "PDF page text exceeds bounded geometry scan")
                page_text = textpage.get_text_bounded()
                word_count = len(page_text.split())
                field_scan = scan_text(page_text)
                for key, value in field_scan["errors"].items():
                    field_errors[key] = field_errors.get(key, 0) + value
                for key, value in field_scan["placeholders"].items():
                    placeholders[key] = placeholders.get(key, 0) + value
                image_count = sum(1 for _ in page.get_objects(
                    filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]))
                width, height = page.get_size()
                overflow = 0
                for char_index in range(count_chars):
                    box = textpage.get_charbox(char_index)
                    if (box[0] < -1 or box[1] < -1 or box[2] > width + 1
                            or box[3] > height + 1):
                        overflow += 1
                flags = []
                if not word_count and not image_count and ink_ratio < 0.001:
                    flags.append("possibly_blank_page")
                if overflow:
                    flags.append("text_outside_page_bounds")
                if word_count == 0 and image_count:
                    flags.append("image_only_review_required")
                flags.extend(f"field_error:{key}" for key in field_scan["errors"])
                flags.extend(f"placeholder:{key}" for key in field_scan["placeholders"])
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                png = buffer.getvalue()
                _require(len(png) <= MAX_PAGE_PNG_BYTES,
                         "blocked", "individual PNG exceeds bounded output cap")
                total_png_bytes += len(png)
                _require(total_png_bytes <= MAX_TOTAL_PNG_BYTES,
                         "blocked", "page images exceed bounded output cap")
                name = f"page-{index:04d}.png"
                path = output_dir / name
                with path.open("xb") as stream:
                    created_files.append(path)
                    stream.write(png)
                pages.append({
                    "page": index, "png": name,
                    "sha256": hashlib.sha256(png).hexdigest(),
                    "bytes": len(png), "pixel_width": image.width,
                    "pixel_height": image.height,
                    "width_points": round(width, 3),
                    "height_points": round(height, 3),
                    "text_word_count": word_count,
                    "pdf_image_count": image_count,
                    "sampled_nonwhite_fraction": ink_ratio,
                    "field_error_counts": field_scan["errors"],
                    "placeholder_counts": field_scan["placeholders"],
                    "flags": flags,
                })
            _require(_file_hash(source_docx, cap=MAX_DOCX_BYTES, kind="DOCX") == source_sha
                     and _file_hash(native_pdf, cap=MAX_PDF_BYTES, kind="PDF") == pdf_sha,
                     "fail", "source or native PDF changed during page capture")
            # Validate every PNG after writing. A complete, ordered index is the
            # only success marker and is written last using exclusive create.
            for page in pages:
                _require(_file_hash(output_dir / page["png"],
                                    cap=MAX_PAGE_PNG_BYTES, kind="page PNG")
                         == page["sha256"],
                         "fail", "page PNG changed during publication")
            result.update({
                "all_page_capture": "pass",
                "rendered_field_integrity": "fail" if field_errors else "not_detected",
                "document_bookmark_integrity": "fail" if document["inventory"].get(
                    "unresolved_internal_bookmark_links", 0) else "not_detected",
                "source_sha256": source_sha, "pdf_sha256": pdf_sha,
                "native_word_version": native_receipt.get("word_version"),
                "raster_backend": "PDFium", "raster_backend_version": pdfium.PDFIUM_INFO.version,
                "raster_binding_version": pdfium.PYPDFIUM_INFO.version,
                "dpi": RENDER_DPI, "page_count": page_count,
                "captured_pages": pages,
                "field_error_counts": field_errors,
                "placeholder_counts": placeholders,
                "internal_bookmark_links": document["inventory"].get(
                    "internal_bookmark_links", 0),
                "unresolved_internal_bookmark_links": document["inventory"].get(
                    "unresolved_internal_bookmark_links", 0),
                "docx_images": document["inventory"].get("images", []),
                "review_flags": sum(len(page["flags"]) for page in pages),
                "reason": ("every native Word PDF page captured and hash-bound; "
                           + ("rendered Word field errors detected; " if field_errors else "")
                           + "independent visual and report-claim verification still blocked"),
            })
            index_file = output_dir / "index.json"
            with index_file.open("x", encoding="utf-8") as stream:
                created_files.append(index_file)
                json.dump(result, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
        finally:
            reader.close()
    except PageEvidenceError as exc:
        result["all_page_capture"] = exc.status
        result["reason"] = str(exc)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
        result["all_page_capture"] = "blocked"
        result["reason"] = f"PDF page capture unavailable: {type(exc).__name__}: {exc}"
    finally:
        if created_dir and result["all_page_capture"] != "pass":
            # Cleanup is limited to files this call exclusively created and
            # the exact directory it created. No broad recursive deletion.
            try:
                for path in reversed(created_files):
                    path.unlink()
                output_dir.rmdir()
            except OSError as exc:
                result["reason"] += f"; partial private evidence cleanup failed: {exc}"
    return result
