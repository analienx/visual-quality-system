"""T08/T09: bounded PNG paths and authoritative inventory roundtrip.

T08 routes: image_evidence, request-review CLI, bundle verify/unpack,
repair verify_renders, production capture (stubbed Bridge only) — all
must refuse oversized/lying inputs before unbounded work.
T09 route: request-review -> completed form -> pack/verify ->
adjudicate with transport binding.
"""
import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest

import vqs.evidence as evidence_mod
from vqs.cli import main as vqs_main
from vqs.evidence import digest, image_evidence
from vqs.pbir import report_context, source_digest
from vqs.repair.regress import verify_renders
from vqs.review.adjudicate import adjudicate_bundle
from vqs.review.bundle import pack, unpack, verify

CALIBRATION = {"canvas_width": 500, "canvas_height": 500, "scale": 1,
               "viewport": "500x500@1x", "method": "bridge-screenshot-all"}
READINESS = {"populated": True, "method": "scoped-dax-probe",
             "checked_at": "2026-10-03T00:00:00Z"}
REASON = ("Inspected the correct fresh full-canvas image specifically "
          "for this criterion at the target scale.")
FAIR = "https://developer.microsoft.com/json-schemas/fabric/item/"


def _write_png(path: Path, width: int = 500, height: int = 500,
               color: int = 2, rows: int | None = None) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0)

    pixel = {0: b"\x80", 2: b"\x20\x60\xc0", 6: b"\x20\x60\xc0\xff"}[color]
    count = height if rows is None else rows
    raw = b"".join(b"\x00" + pixel * width for _ in range(count))
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


def _canvases(report: Path) -> dict[str, list[int]]:
    info = report_context(report)
    return {page["id"]: page["canvas"] for page in info["pages"]}


def _complete(template: dict, source: str) -> dict:
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


def _rules(items: list[dict]) -> set[str]:
    return {row.get("rule", "?") for row in items}


# T08 ------------------------------------------------------------------


def test_oversize_capped_before_hash_in_image_evidence(
        tmp_path: Path, monkeypatch) -> None:
    """T08: the encoded cap fires before hashing in the actual caller."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    monkeypatch.setattr(evidence_mod, "_PNG_FILE_CAP", 64)
    with pytest.raises(ValueError, match="exceeds size cap"):
        digest(renders / "P1.png")
    _pages, issues = image_evidence(renders, source_digest(report),
                                    ["P1", "P2"], _canvases(report))
    assert "page_render_invalid" in _rules(issues)


def test_lying_inflation_rejected_in_image_evidence(tmp_path: Path) -> None:
    """T08: small-IHDR/oversized-inflation fails decode, never allocates."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    _write_png(renders / "P1.png", rows=700)
    (renders / "capture-manifest.json").write_text(json.dumps({
        **json.loads((renders / "capture-manifest.json").read_text()),
        "files": {name: hashlib.sha256((renders / name).read_bytes()
                                       ).hexdigest()
                  for name in ("P1.png", "P2.png")}}), encoding="utf-8")
    _pages, issues = image_evidence(renders, source_digest(report),
                                    ["P1", "P2"], _canvases(report))
    assert "page_render_undecodable" in _rules(issues)


def test_request_review_blocks_oversized(tmp_path: Path, monkeypatch,
                                         capsys) -> None:
    """T08: installed request-review refuses oversized renders (exit 2)."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    monkeypatch.setattr(evidence_mod, "_PNG_FILE_CAP", 64)
    code = vqs_main(["request-review", str(report), str(renders),
                     "--fixer-id", "fixer-1"])
    assert code == 2
    assert "page_render_invalid" in capsys.readouterr().out


def test_verify_and_unpack_reject_oversized(tmp_path: Path,
                                            monkeypatch) -> None:
    """T08: bundle verify/unpack cap before re-hash (never hash first)."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    monkeypatch.setattr(evidence_mod, "_PNG_FILE_CAP", 64)
    with pytest.raises(ValueError, match="oversized"):
        verify(str(tmp_path / "b1"))
    with pytest.raises(OSError, match="oversized"):
        unpack(str(tmp_path / "b1"), str(tmp_path / "b2"))


def test_verify_renders_blocks_oversized(tmp_path: Path,
                                         monkeypatch) -> None:
    """T08: repair-render verification blocks oversized renders."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    monkeypatch.setattr(evidence_mod, "_PNG_FILE_CAP", 64)
    result = verify_renders(["P1", "P2"], [renders],
                            source_digest(report), _canvases(report))
    assert result["verdict"] == "blocked"
    assert result["missing_pages"] == ["P1", "P2"]


def test_capture_rejects_lying_inflation(tmp_path: Path, monkeypatch,
                                         capsys) -> None:
    """T08: production capture (stubbed Bridge) refuses lying inflation."""
    import vqs.capture as capture_mod

    report = tmp_path / "C.Report"
    (report / "definition" / "pages" / "p1").mkdir(parents=True)
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["p1"]}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(json.dumps(
        {"$schema": FAIR + "report/definition/versionMetadata/1.0.0/schema.json",
         "version": "2.0.0"}), encoding="utf-8")
    (report / "definition" / "report.json").write_text(json.dumps(
        {"$schema": FAIR + "report/definition/report/3.3.0/schema.json",
         "themeCollection": {}}), encoding="utf-8")
    (report / "definition" / "pages" / "p1" / "page.json").write_text(
        json.dumps({"displayName": "P", "width": 1280, "height": 720}),
        encoding="utf-8")

    def fake_bridge(args, timeout):
        if args[0] == "--version":
            return 0, "1.0.0\n"
        if args[0] == "status":
            return 0, json.dumps({"status": "ready", "instances": [{
                "pid": 111, "bridgeStatus": "connected",
                "currentFilePath": str(report.with_suffix(".pbip")),
                "hasUnsavedChanges": False, "reportDir": str(report),
                "pages": [{"id": "p1"}]}]})
        assert args[0] == "screenshot-all"
        out = Path(args[args.index("--output-dir") + 1])
        raw = out / "Display p1.png"
        _write_png(raw, 1280, 720, rows=900)
        return 0, json.dumps({"status": "ok", "screenshots": [
            {"pageId": "p1", "outputPath": str(raw)}]})

    monkeypatch.setattr(capture_mod, "_bridge", fake_bridge)
    code = vqs_main(["capture", str(report), str(tmp_path / "renders")])
    assert code == 2
    refused = json.loads(capsys.readouterr().out)
    assert refused["status"] == "blocked"
    assert "Corrupt capture for p1" in refused["reason"]
    assert "IDAT pixels exceed expected" in refused["reason"]


def test_valid_rgb_rgba_accepted(tmp_path: Path) -> None:
    """T08 positive: valid RGB/RGBA still decode through the shared path."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    _write_png(renders / "P2.png", color=6)
    (renders / "capture-manifest.json").write_text(json.dumps({
        **json.loads((renders / "capture-manifest.json").read_text()),
        "files": {name: hashlib.sha256((renders / name).read_bytes()
                                       ).hexdigest()
                  for name in ("P1.png", "P2.png")}}), encoding="utf-8")
    pages, issues = image_evidence(renders, source_digest(report),
                                   ["P1", "P2"], _canvases(report))
    assert issues == []
    assert [page["id"] for page in pages] == ["P1", "P2"]
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    assert verify(str(tmp_path / "b1"))["status"] == "valid"


# T09 ------------------------------------------------------------------


def test_request_review_emits_authoritative_inventory(
        tmp_path: Path, capsys) -> None:
    """T09: the template carries producer inventory, not a caller list."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    code = vqs_main(["request-review", str(report), str(renders),
                     "--fixer-id", "fixer-1"])
    assert code == 0
    template = json.loads(capsys.readouterr().out)
    assert template["source_pages"] == ["P1", "P2"]
    assert template["source_sha256"] == source_digest(report)


def test_full_chain_static_pass_visual_blocked(tmp_path: Path,
                                               capsys) -> None:
    """T09: template -> completed form -> bundle/adjudicate; static can
    pass while visual approval stays blocked for image review."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    assert vqs_main(["request-review", str(report), str(renders),
                     "--fixer-id", "fixer-1"]) == 0
    template = json.loads(capsys.readouterr().out)
    form = _complete(template, source_digest(report))
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    checked = verify(str(tmp_path / "b1"), str(report))
    assert checked["status"] == "valid"
    # R6-E06: forward the whole verified authority (render bindings,
    # calibration, fixer); thin lookalikes fail as unverified.
    decided = adjudicate_bundle(form, checked)
    assert decided["static_conformance"] == "pass"
    assert decided["verdict"] == "blocked"
    assert "image_review_required" in _rules(decided["findings"])
    assert not any(row.get("verdict") == "fail"
                   for row in decided["findings"])


def test_dropped_page_fails_inventory(tmp_path: Path, capsys) -> None:
    """T09: a form covering P1 of P1+P2 fails the inventory contract."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    assert vqs_main(["request-review", str(report), str(renders),
                     "--fixer-id", "fixer-1"]) == 0
    template = json.loads(capsys.readouterr().out)
    form = _complete(template, source_digest(report))
    form["pages"] = form["pages"][:1]
    decided = adjudicate_bundle(form)
    assert decided["verdict"] == "blocked"
    assert "source_page_uncovered" in _rules(decided["findings"])


def test_edited_list_unbound_vs_transport(tmp_path: Path, capsys) -> None:
    """T09: a caller-trimmed source_pages fails against the transport."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    assert vqs_main(["request-review", str(report), str(renders),
                     "--fixer-id", "fixer-1"]) == 0
    template = json.loads(capsys.readouterr().out)
    form = _complete(template, source_digest(report))
    form["pages"] = form["pages"][:1]
    form["source_pages"] = ["P1"]
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    checked = verify(str(tmp_path / "b1"))
    # R6-E06: the verified authority object, not a thin lookalike.
    decided = adjudicate_bundle(form, checked)
    assert decided["verdict"] == "fail"
    assert "source_pages_unbound" in _rules(decided["findings"])


def test_cli_adjudicate_with_transport(tmp_path: Path, capsys) -> None:
    """T09 installed: --transport-bundle binds (2 blocked) or fails (1)."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    assert vqs_main(["request-review", str(report), str(renders),
                     "--fixer-id", "fixer-1"]) == 0
    template = json.loads(capsys.readouterr().out)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    good = _complete(template, source_digest(report))
    good_path = tmp_path / "good.json"
    good_path.write_text(json.dumps(good), encoding="utf-8")
    code = vqs_main(["adjudicate-bundle", str(good_path),
                     "--transport-bundle", str(tmp_path / "b1"),
                     "--run-root", str(tmp_path / "runs"),
                     "--run-id", "adj-good"])
    assert code == 2
    bad = _complete(template, source_digest(report))
    bad["pages"] = bad["pages"][:1]
    bad["source_pages"] = ["P1"]
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    code = vqs_main(["adjudicate-bundle", str(bad_path),
                     "--transport-bundle", str(tmp_path / "b1"),
                     "--run-root", str(tmp_path / "runs"),
                     "--run-id", "adj-bad"])
    assert code == 1
