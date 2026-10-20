"""P22: native-Word, source-safe TOC repair into a disposable DOCX candidate.

Proof is deliberately scoped to one TOC, internal bookmarks, ordered heading
strings and table-cell strings. Word may rewrite field-result and ordinary
paragraph OOXML; the latter requires independent prose and visual review.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from vqs.document.inspect import W
from vqs.document.native_word import _source

SCHEMA = "vqs.word-toc-candidate-evidence/1"
NATIVE_SCHEMA = "vqs.native-word-toc-candidate/1"


class TocCandidateError(ValueError):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)


def _require(condition: bool, status: str, reason: str) -> None:
    if not condition:
        raise TocCandidateError(status, reason)


def _document(path: Path) -> ET.Element:
    with zipfile.ZipFile(path) as archive:
        return ET.fromstring(archive.read("word/document.xml"))


def _texts(root: ET.Element) -> tuple[dict, int]:
    """Keep exact ordered heading/table-cell strings without leaking content."""
    def heading(paragraph: ET.Element) -> bool:
        style = paragraph.find(f"{W}pPr/{W}pStyle")
        return style is not None and (style.get(f"{W}val") or "").startswith("Heading")

    headings = ["".join(t.text or "" for t in p.findall(f".//{W}t"))
                for p in root.findall(f".//{W}p")
                if heading(p)]
    cells = ["".join(t.text or "" for t in cell.findall(f".//{W}t"))
             for cell in root.findall(f".//{W}tc")]
    inventory = {}
    for name, values in (("heading_texts", headings), ("table_cell_texts", cells)):
        inventory[name] = len(values)
        inventory[name + "_sha256"] = hashlib.sha256(
            json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()
    fields = " ".join(t.text or "" for t in root.findall(f".//{W}instrText"))
    return inventory, len(re.findall(r"\bTOC\b", fields, flags=re.IGNORECASE))


def _body_paragraphs(root: ET.Element) -> list[str]:
    return ["".join(t.text or "" for t in p.findall(f".//{W}t"))
            for p in root.findall(f"./{W}body/{W}p")]


def _body_delta(before: ET.Element, after: ET.Element) -> dict:
    left, right = _body_paragraphs(before), _body_paragraphs(after)
    changes = [op for op in difflib.SequenceMatcher(
        None, left, right, autojunk=False).get_opcodes() if op[0] != "equal"]
    return {"source_paragraphs": len(left), "candidate_paragraphs": len(right),
            "changed_hunks": len(changes),
            "independent_prose_review": "required" if changes else "not_triggered"}


def _native_receipt(raw: Any, source: Path, pending: Path) -> dict:
    _require(isinstance(raw, Mapping) and raw.get("schema") == NATIVE_SCHEMA
             and raw.get("renderer") == "Microsoft Word"
             and type(raw.get("native_word_pid")) is int
             and raw["native_word_pid"] > 0
             and isinstance(raw.get("word_version"), str) and bool(raw["word_version"])
             and isinstance(raw.get("utc"), str)
             and raw.get("source_opened_read_only") is True
             and raw.get("toc_count_before") == 1
             and raw.get("toc_count_after") == 1
             and isinstance(raw.get("source_full_name"), str)
             and isinstance(raw.get("candidate_full_name"), str)
             and Path(raw["source_full_name"]).resolve() == source.resolve()
             and Path(raw["candidate_full_name"]).resolve() == pending.resolve(),
             "fail", "native Word source/read-only/one-TOC attestation contradicted")
    return {"native_word_pid": raw["native_word_pid"],
            "word_version": raw["word_version"], "utc": raw["utc"]}


def _invoke_native(source: Path, pending: Path) -> dict:
    if os.name != "nt":
        raise TocCandidateError("blocked", "native Word TOC update requires Windows")
    shell = shutil.which("powershell.exe")
    if not shell:
        raise TocCandidateError("blocked", "Windows PowerShell unavailable")
    script = (Path(__file__).resolve().parents[2] /
              "scripts/windows/native_word_toc_candidate.ps1")
    _require(script.is_file(), "blocked", "native Word TOC script missing")
    try:
        proc = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-File", str(script),
             "-DocumentPath", str(source), "-CandidatePath", str(pending)],
            capture_output=True, text=True, timeout=180, check=False,
            encoding="utf-8-sig")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TocCandidateError("blocked", f"Word TOC update unavailable: {exc}") from exc
    if proc.returncode:
        raise TocCandidateError("blocked", "Word refused isolated TOC update: "
                                + proc.stderr[-500:])
    try:
        return json.loads(proc.stdout.strip())
    except ValueError as exc:
        raise TocCandidateError("blocked", "Word TOC script did not return JSON") from exc


def run(source_docx: Path, candidate_docx: Path,
        *, invoke: Callable[[Path, Path], dict] = _invoke_native) -> dict:
    """Candidate-only operation, with unchanged source and exclusive publication."""
    result: dict[str, Any] = {
        "schema": SCHEMA, "toc_candidate_update": "blocked",
        "native_paginated_review": "blocked", "rendered_field_integrity": "blocked",
        "document_report_consistency": "blocked", "independent_acceptance": "blocked",
        "reason": "one-TOC native Word candidate has not been verified",
    }
    owned_candidate = False
    try:
        _require(isinstance(source_docx, Path) and isinstance(candidate_docx, Path),
                 "blocked", "explicit DOCX source and candidate paths required")
        _require(candidate_docx.suffix.lower() == ".docx"
                 and candidate_docx.resolve() != source_docx.resolve()
                 and candidate_docx.parent.is_dir()
                 and not candidate_docx.parent.is_symlink()
                 and not candidate_docx.exists() and not candidate_docx.is_symlink()
                 and not str(candidate_docx).startswith("\\\\"),
                 "blocked", "new local disposable DOCX target required; no overwrite")
        before_hash, before = _source(source_docx)
        before_root = _document(source_docx)
        before_text, toc_count = _texts(before_root)
        _require(toc_count == 1, "blocked", "exactly one OOXML TOC field required")
        _require(before.get("unresolved_internal_bookmark_links", 0) > 0,
                 "blocked", "source has no demonstrably broken bookmark target")
        _require(type(before.get("word_main_story_table_groups")) is int,
                 "blocked", "unsupported source table topology")
        with tempfile.TemporaryDirectory(
                prefix="vqs-word-toc-private-", dir=candidate_docx.parent) as temp:
            pending = Path(temp) / "candidate.docx"
            native = _native_receipt(invoke(source_docx.resolve(), pending),
                                     source_docx, pending)
            after_hash, after = _source(pending)
            after_root = _document(pending)
            after_text, after_tocs = _texts(after_root)
            _require(after_hash != before_hash and after_tocs == 1,
                     "fail", "Word did not regenerate exactly one TOC")
            _require(after.get("unresolved_internal_bookmark_links") == 0
                     and after.get("internal_bookmark_links", 0)
                     >= before["internal_bookmark_links"]
                     and after.get("bookmark_definitions", 0) > 0,
                     "fail", "Word left missing TOC bookmark targets")
            _require(after.get("word_main_story_table_groups")
                     == before["word_main_story_table_groups"],
                     "fail", "Word changed logical body table inventory")
            _require(after_text == before_text,
                     "fail", "Word changed ordered heading or table-cell text")
            body_delta = _body_delta(before_root, after_root)
            unchanged_hash, unchanged_inventory = _source(source_docx)
            _require(unchanged_hash == before_hash and unchanged_inventory == before,
                     "fail", "original DOCX changed during TOC update")
            with pending.open("rb") as reader, candidate_docx.open("xb") as writer:
                owned_candidate = True
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
            published_hash, published_inv = _source(candidate_docx)
            final_hash, final_inv = _source(source_docx)
            _require(published_hash == after_hash and published_inv == after
                     and final_hash == before_hash and final_inv == before,
                     "fail", "published candidate or original source was changed")
            result.update({
                "toc_candidate_update": "pass", "source_sha256": before_hash,
                "candidate_sha256": after_hash,
                "candidate_path": str(candidate_docx),
                "source_bookmark_links_unresolved": before["unresolved_internal_bookmark_links"],
                "candidate_bookmark_links_unresolved": after["unresolved_internal_bookmark_links"],
                "candidate_bookmark_definitions": after["bookmark_definitions"],
                "logical_table_groups": before["word_main_story_table_groups"],
                "preserved_content": before_text,
                "non_table_body_delta": body_delta, "native_word": native,
                "reason": "one native TOC updated in new source-safe DOCX; independent prose, "
                          "actual PDF pagination and document/report review remain blocked",
            })
    except TocCandidateError as exc:
        result["toc_candidate_update"] = exc.status
        result["reason"] = str(exc)
    except (OSError, ValueError, TypeError, KeyError, AttributeError,
            ET.ParseError, zipfile.BadZipFile) as exc:
        result["reason"] = f"TOC candidate unavailable: {type(exc).__name__}: {exc}"
    finally:
        if owned_candidate and result["toc_candidate_update"] != "pass":
            try:
                candidate_docx.unlink(missing_ok=True)
            except OSError as exc:
                result["reason"] += f"; candidate cleanup failed: {exc}"
    return result
