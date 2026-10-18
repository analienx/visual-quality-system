"""R6-E06: verified transport binds every render, fixer, calibration.

Oracle A06: installed bundle verification -> adjudicate-bundle with
an untouched verified transport and an edited form hash, substituted
render, or mismatched resolution must fail. Spoofed fixers fail, and
reviewer separation binds the real transport fixer (renaming the form
fixer cannot launder self-review). Thin lookalike dicts are rejected
at the verified boundary; verification never relies on them.
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
from vqs.pbir import source_digest
from vqs.review.adjudicate import adjudicate_bundle
from vqs.review.bundle import pack, verify

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


def _write_png(path: Path, width: int = 500, height: int = 500,
               color: int = 2) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0)
    pixel = {0: b"\x80", 2: b"\x20\x60\xc0",
             6: b"\x20\x60\xc0\xff"}[color]
    raw = b"".join(b"\x00" + pixel * width for _ in range(height))
    comp = zlib.compress(raw)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def _report(root: Path) -> Path:
    report = root / "R.Report"
    for page_id in ("P1", "P2"):
        page_dir = report / "definition" / "pages" / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(json.dumps(
            {"displayName": page_id, "width": 500, "height": 500}),
            encoding="utf-8")
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1", "P2"]}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(json.dumps(
        {"$schema": FAIR + "report/definition/versionMetadata/1.0.0/schema.json",
         "version": "2.0.0"}), encoding="utf-8")
    (report / "definition" / "report.json").write_text(json.dumps(
        {"$schema": FAIR + "report/definition/report/3.3.0/schema.json",
         "themeCollection": {}}), encoding="utf-8")
    return report


def _renders(report: Path, root: Path) -> Path:
    renders = root / "renders"
    renders.mkdir(exist_ok=True)
    mapping, files = {}, {}
    # Distinct bytes per page (RGB vs RGBA): swapped digests must be a
    # real substitution, not an identical-bytes no-op.
    for page_id, color in (("P1", 2), ("P2", 6)):
        _write_png(renders / f"{page_id}.png", color=color)
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


def _chain(tmp_path: Path, capsys: Any
           ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pack + verify a bundle and complete its review form."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    assert vqs_main(["request-review", str(report), str(renders),
                     "--fixer-id", "fixer-1"]) == 0
    template = json.loads(capsys.readouterr().out)
    form = _complete(template, source_digest(report))
    bundle_dir = tmp_path / "b1"
    pack(str(report), str(renders), str(bundle_dir), "fixer-1")
    checked = verify(str(bundle_dir))
    assert checked["status"] == "valid"
    return form, checked


def _rules(items: list[dict[str, Any]]) -> set[str]:
    return {row.get("rule", "?") for row in items}


def test_verify_returns_render_authority(tmp_path: Path,
                                         capsys: Any) -> None:
    """Verify emits per-page bindings, calibration, bundle identity."""
    _form, checked = _chain(tmp_path, capsys)
    assert checked["authority"] == "vqs.bundle.verify/1"
    assert set(checked["renders"]) == {"P1", "P2"}
    for page_id, entry in checked["renders"].items():
        assert entry["image"] == f"{page_id}.png"
        assert len(entry["sha256"]) == 64
        assert entry["pixels"] == [500, 500]
        actual = hashlib.sha256(
            (tmp_path / "b1" / entry["image"]).read_bytes()).hexdigest()
        assert entry["sha256"] == actual
    assert checked["calibration"]["canvas_width"] == 500
    assert checked["calibration"]["scale"] == 1
    assert len(checked["bundle_sha256"]) == 64
    again = verify(str(tmp_path / "b1"))
    assert again["bundle_sha256"] == checked["bundle_sha256"]
    assert again["renders"] == checked["renders"]


def test_edited_form_hash_fails(tmp_path: Path, capsys: Any) -> None:
    """A valid transport plus an edited form digest fails."""
    form, checked = _chain(tmp_path, capsys)
    form["pages"][0]["image_sha256"] = "e" * 64
    decided = adjudicate_bundle(form, checked)
    assert decided["verdict"] == "fail"
    assert "page_render_substituted" in _rules(decided["findings"])


def test_substituted_render_fails(tmp_path: Path, capsys: Any) -> None:
    """Swapped page digests fail against the verified bindings."""
    form, checked = _chain(tmp_path, capsys)
    first = form["pages"][0]["image_sha256"]
    form["pages"][0]["image_sha256"] = form["pages"][1]["image_sha256"]
    form["pages"][1]["image_sha256"] = first
    decided = adjudicate_bundle(form, checked)
    assert decided["verdict"] == "fail"
    assert "page_render_substituted" in _rules(decided["findings"])


def test_mismatched_resolution_fails(tmp_path: Path, capsys: Any) -> None:
    """A form resolution outside the verified pixels fails."""
    form, checked = _chain(tmp_path, capsys)
    form["pages"][0]["pixels"] = [250, 250]
    decided = adjudicate_bundle(form, checked)
    assert decided["verdict"] == "fail"
    assert "render_pixels_mismatch" in _rules(decided["findings"])


def test_spoofed_fixer_fails(tmp_path: Path, capsys: Any) -> None:
    """A form fixer outside the verified fixer fails."""
    form, checked = _chain(tmp_path, capsys)
    form["fixer_id"] = "fixer-9"
    decided = adjudicate_bundle(form, checked)
    assert decided["verdict"] == "fail"
    assert "fixer_unbound" in _rules(decided["findings"])


def test_self_review_via_spoofed_fixer_fails(tmp_path: Path,
                                             capsys: Any) -> None:
    """Reviewer separation binds the real transport fixer, not the form."""
    form, checked = _chain(tmp_path, capsys)
    form["fixer_id"] = "spoofer"
    form["reviewer"]["id"] = "fixer-1"
    decided = adjudicate_bundle(form, checked)
    assert decided["verdict"] == "fail"
    assert "own_review_forbidden" in _rules(decided["findings"])
    assert "fixer_unbound" in _rules(decided["findings"])


def test_calibration_drift_fails(tmp_path: Path, capsys: Any) -> None:
    """A form calibration outside the verified capture fails."""
    form, checked = _chain(tmp_path, capsys)
    form["calibration"] = dict(CALIBRATION, scale=2)
    decided = adjudicate_bundle(form, checked)
    assert decided["verdict"] == "fail"
    assert "calibration_unbound" in _rules(decided["findings"])


def test_thin_lookalike_rejected(tmp_path: Path, capsys: Any) -> None:
    """A caller pages+source dict is not verified authority."""
    form, checked = _chain(tmp_path, capsys)
    lookalike = {"pages": checked["pages"],
                 "source_sha256": checked["source_sha256"]}
    decided = adjudicate_bundle(form, lookalike)
    assert decided["verdict"] == "fail"
    assert "transport_unverified" in _rules(decided["findings"])


def test_untouched_chain_conforms(tmp_path: Path, capsys: Any) -> None:
    """Untouched verified transport + honest form: static conformance."""
    form, checked = _chain(tmp_path, capsys)
    decided = adjudicate_bundle(form, checked)
    assert decided["static_conformance"] == "pass"
    assert decided["verdict"] == "blocked"
    assert not any(row.get("verdict") == "fail"
                   for row in decided["findings"])


@needs_vqs
@pytest.mark.parametrize("attack", ["hash", "pixels", "fixer"])
def test_installed_attack_chain_fails(tmp_path: Path, capsys: Any,
                                      attack: str) -> None:
    """Installed headline: verify -> adjudicate fails edited forms."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    assert vqs_main(["request-review", str(report), str(renders),
                     "--fixer-id", "fixer-1"]) == 0
    template = json.loads(capsys.readouterr().out)
    form = _complete(template, source_digest(report))
    bundle_dir = tmp_path / "b1"
    pack(str(report), str(renders), str(bundle_dir), "fixer-1")
    assert verify(str(bundle_dir))["status"] == "valid"
    if attack == "hash":
        form["pages"][0]["image_sha256"] = "e" * 64
        rule = "page_render_substituted"
    elif attack == "pixels":
        form["pages"][0]["pixels"] = [250, 250]
        rule = "render_pixels_mismatch"
    else:
        form["fixer_id"] = "fixer-9"
        rule = "fixer_unbound"
    form_path = tmp_path / "form.json"
    form_path.write_text(json.dumps(form), encoding="utf-8")
    proc = subprocess.run(
        [VQS_BIN, "adjudicate-bundle", str(form_path),
         "--transport-bundle", str(bundle_dir),
         "--run-root", str(tmp_path / "runs"),
         "--run-id", f"r6-e06-{attack}"],
        capture_output=True, text=True, timeout=180, check=False)
    assert proc.returncode == 1, proc.stderr + proc.stdout
    assert rule in proc.stdout
