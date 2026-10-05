"""R6-E05: whole-source completeness requires verified authority.

Oracle A05: a completed form with pages dropped from both lists
fails/blocks through the installed review-bundle route. Without a
verified transport or live report inventory, coverage is unbound
(blocked) and static conformance cannot imply a whole-source pass;
other diagnostics still run. A live inventory binds completeness;
a stale transport against a live report is refused.
"""
import hashlib
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from typing import Any

import pytest

from vqs.cli import main as vqs_main
from vqs.pbir import report_context, source_digest
from vqs.review.adjudicate import adjudicate_bundle
from vqs.review.bundle import pack

VQS_BIN = shutil.which("vqs")
needs_vqs = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs entry point not on PATH")

CALIBRATION = {"canvas_width": 500, "canvas_height": 500, "scale": 1,
               "viewport": "500x500@1x", "method": "bridge-screenshot-all"}
READINESS = {"populated": True, "method": "scoped-dax-probe",
             "checked_at": "2026-10-03T00:00:00Z"}
REASON = ("Inspected the correct fresh full-canvas image specifically "
          "for this criterion at the target scale.")
FAIR = "https://developer.microsoft.com/json-schemas/fabric/item/"


def _write_png(path: Path, width: int = 500, height: int = 500) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x20\x60\xc0" * width
                   for _ in range(height))
    comp = zlib.compress(raw)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def _report(root: Path, pages: tuple[str, ...] = ("P1", "P2")) -> Path:
    report = root / "R.Report"
    for page_id in pages:
        page_dir = report / "definition" / "pages" / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(json.dumps(
            {"displayName": page_id, "width": 500, "height": 500}),
            encoding="utf-8")
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": list(pages)}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(json.dumps(
        {"$schema": FAIR + "report/definition/versionMetadata/1.0.0/schema.json",
         "version": "2.0.0"}), encoding="utf-8")
    (report / "definition" / "report.json").write_text(json.dumps(
        {"$schema": FAIR + "report/definition/report/3.3.0/schema.json",
         "themeCollection": {}}), encoding="utf-8")
    return report


def _renders(report: Path, root: Path,
              pages: tuple[str, ...] = ("P1", "P2")) -> Path:
    renders = root / "renders"
    renders.mkdir(exist_ok=True)
    mapping, files = {}, {}
    for page_id in pages:
        _write_png(renders / f"{page_id}.png")
        files[f"{page_id}.png"] = hashlib.sha256(
            (renders / f"{page_id}.png").read_bytes()).hexdigest()
        mapping[page_id] = f"{page_id}.png"
    (renders / "capture-manifest.json").write_text(json.dumps(
        {"source_sha256": source_digest(report), "page_images": mapping,
         "files": files, "calibration": CALIBRATION,
         "data_readiness": READINESS}), encoding="utf-8")
    return renders


def _complete(template: dict[str, Any], source: str) -> dict[str, Any]:
    form = json.loads(json.dumps(template))
    form["reviewer"]["id"] = "reviewer-1"
    form["image_capability"] = {"available": True,
                                "provider": "synthetic-test"}
    for page in form["pages"]:
        page["pixels"] = [500, 500]
        for answer in page["observations"]:
            answer.update(status="pass", reason=REASON)
    assert form["source_sha256"] == source
    return form


def _form(tmp_path: Path, capsys: Any) -> tuple[Path, dict[str, Any]]:
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    assert vqs_main(["request-review", str(report), str(renders),
                     "--fixer-id", "fixer-1"]) == 0
    template = json.loads(capsys.readouterr().out)
    return report, _complete(template, source_digest(report))


def _live_authority(report: Path) -> dict[str, Any]:
    info = report_context(report)
    return {"authority": "live-report/1",
            "pages": [page["id"] for page in info["pages"]],
            "source_sha256": source_digest(report)}


def _rules(items: list[dict[str, Any]]) -> set[str]:
    return {row.get("rule", "?") for row in items}


def test_form_only_coverage_unbound(tmp_path: Path, capsys: Any) -> None:
    """A completed form alone cannot prove whole-source coverage."""
    _report, form = _form(tmp_path, capsys)
    decided = adjudicate_bundle(form)
    assert decided["verdict"] == "blocked"
    assert decided["static_conformance"] == "fail"
    assert "source_pages_unbound" in _rules(decided["findings"])


def test_form_only_diagnostics_preserved(tmp_path: Path, capsys: Any) -> None:
    """Unbound coverage still adjudicates every other diagnostic."""
    _report, form = _form(tmp_path, capsys)
    form["pages"] = form["pages"][:1]
    decided = adjudicate_bundle(form)
    assert decided["verdict"] == "blocked"
    assert "source_page_uncovered" in _rules(decided["findings"])
    assert "source_pages_unbound" in _rules(decided["findings"])


def test_live_report_inventory_binds_completeness(tmp_path: Path,
                                                  capsys: Any) -> None:
    """A current authoritative inventory establishes coverage."""
    report, form = _form(tmp_path, capsys)
    decided = adjudicate_bundle(form, _live_authority(report))
    assert decided["static_conformance"] == "pass"
    assert decided["verdict"] == "blocked"
    assert "source_pages_unbound" not in _rules(decided["findings"])
    assert "image_review_required" in _rules(decided["findings"])


def test_live_report_divergence_fails(tmp_path: Path, capsys: Any) -> None:
    """A trimmed form list fails against the live inventory."""
    report, form = _form(tmp_path, capsys)
    form["pages"] = form["pages"][:1]
    form["source_pages"] = ["P1"]
    decided = adjudicate_bundle(form, _live_authority(report))
    assert decided["verdict"] == "fail"
    assert "source_pages_unbound" in _rules(decided["findings"])


@needs_vqs
def test_installed_adjudicate_without_authority(tmp_path: Path,
                                                capsys: Any) -> None:
    """Installed: no transport/report leaves coverage unbound."""
    _report, form = _form(tmp_path, capsys)
    form_path = tmp_path / "form.json"
    form_path.write_text(json.dumps(form), encoding="utf-8")
    proc = subprocess.run(
        [VQS_BIN, "adjudicate-bundle", str(form_path),
         "--run-root", str(tmp_path / "runs"), "--run-id", "r6-e05-none"],
        capture_output=True, text=True, timeout=180, check=False)
    assert proc.returncode == 2, proc.stderr + proc.stdout
    assert "source_pages_unbound" in proc.stdout


@needs_vqs
def test_installed_adjudicate_with_report(tmp_path: Path,
                                          capsys: Any) -> None:
    """Installed: --report binds completeness; image review still blocks."""
    report, form = _form(tmp_path, capsys)
    form_path = tmp_path / "form.json"
    form_path.write_text(json.dumps(form), encoding="utf-8")
    proc = subprocess.run(
        [VQS_BIN, "adjudicate-bundle", str(form_path),
         "--report", str(report),
         "--run-root", str(tmp_path / "runs"), "--run-id", "r6-e05-live"],
        capture_output=True, text=True, timeout=180, check=False)
    assert proc.returncode == 2, proc.stderr + proc.stdout
    assert "source_pages_unbound" not in proc.stdout
    assert "image_review_required" in proc.stdout


@needs_vqs
def test_installed_transport_plus_report_agree(tmp_path: Path,
                                               capsys: Any) -> None:
    """Installed: transport + live report agree and bind together."""
    report, form = _form(tmp_path, capsys)
    renders = tmp_path / "renders"
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    form_path = tmp_path / "form.json"
    form_path.write_text(json.dumps(form), encoding="utf-8")
    proc = subprocess.run(
        [VQS_BIN, "adjudicate-bundle", str(form_path),
         "--transport-bundle", str(tmp_path / "b1"),
         "--report", str(report),
         "--run-root", str(tmp_path / "runs"), "--run-id", "r6-e05-both"],
        capture_output=True, text=True, timeout=180, check=False)
    assert proc.returncode == 2, proc.stderr + proc.stdout
    assert "source_pages_unbound" not in proc.stdout


@needs_vqs
def test_installed_stale_transport_refused(tmp_path: Path,
                                           capsys: Any) -> None:
    """Installed: a transport stale against the live report is refused."""
    report, form = _form(tmp_path, capsys)
    renders = tmp_path / "renders"
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    page = (report / "definition" / "pages" / "P2" / "page.json")
    doc = json.loads(page.read_text(encoding="utf-8"))
    doc["width"] = 640
    page.write_text(json.dumps(doc), encoding="utf-8")
    form_path = tmp_path / "form.json"
    form_path.write_text(json.dumps(form), encoding="utf-8")
    proc = subprocess.run(
        [VQS_BIN, "adjudicate-bundle", str(form_path),
         "--transport-bundle", str(tmp_path / "b1"),
         "--report", str(report),
         "--run-root", str(tmp_path / "runs"), "--run-id", "r6-e05-stale"],
        capture_output=True, text=True, timeout=180, check=False)
    assert proc.returncode == 2, proc.stderr + proc.stdout
    assert "Transport invalid" in proc.stdout
