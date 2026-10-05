"""Capture v2 gate tests: every manifest-v2 refusal, then the full shape.

Stubbed Bridge, synthetic PBIR reports, injected fake modeling ports.
No Desktop, no live model, no network.
"""
import json
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest

from vqs import capture as capture_mod
from vqs.pbir import source_digest
from vqs.run_store import claim_artifact


def _forward_filter(rows: list[bytes], channels: int, filt: int) -> bytes:
    """Apply PNG forward filtering (Sub/Up/Average/Paeth) to raw rows."""
    if filt == 0:
        return b"".join(b"\x00" + row for row in rows)
    out = b""
    prev = bytes(len(rows[0]))
    for row in rows:
        out += bytes([filt])
        filtered = bytearray(row)
        for i in range(len(filtered)):
            left = row[i - channels] if i >= channels else 0
            up = prev[i]
            upper_left = prev[i - channels] if i >= channels else 0
            if filt == 1:
                sub = left
            elif filt == 2:
                sub = up
            elif filt == 3:
                sub = (left + up) >> 1
            elif filt == 4:
                pick = left + up - upper_left
                dist_left = abs(pick - left)
                dist_up = abs(pick - up)
                dist_corner = abs(pick - upper_left)
                if dist_left <= dist_up and dist_left <= dist_corner:
                    sub = left
                elif dist_up <= dist_corner:
                    sub = up
                else:
                    sub = upper_left
            else:
                sub = 0
            filtered[i] = (filtered[i] - sub) & 0xFF
        out += bytes(filtered)
        prev = bytes(row)
    return out


def _chunk(tag: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + tag + body
            + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))


def _broken_png(kind: str) -> bytes:
    if kind == "short-ihdr":
        return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", b"\x00" * 10)
                + _chunk(b"IDAT", b"") + _chunk(b"IEND", b""))
    raise AssertionError(kind)


def _write_png(path: Path, width: int, height: int,
               blank: bool = False, filt: int = 0, interlace: int = 0,
               color: int = 2, bare: bool = False) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, interlace)
    if bare:
        raw = b""
    else:
        first = b"\x20\x60\xc0" if blank else b"\x00\x00\x00"
        plain = [first + b"\x20\x60\xc0" * (width - 1)]
        plain += [b"\x20\x60\xc0" * width for _ in range(height - 1)]
        raw = _forward_filter(plain, 3, filt)
    payload = (b"\x89PNG\r\n\x1a\n"
               + struct.pack(">I", 13) + b"IHDR" + ihdr
               + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
               + struct.pack(">I", len(zlib.compress(raw))) + b"IDAT"
               + zlib.compress(raw)
               + struct.pack(">I", zlib.crc32(b"IDAT" + zlib.compress(raw))
                             & 0xFFFFFFFF)
               + struct.pack(">I", 0) + b"IEND"
               + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF))
    path.write_bytes(payload)


def _make_report(root: Path, pages: dict[str, tuple[int, int]] | None = None,
                 name: str = "Example.Report") -> Path:
    pages = pages or {"p1": (1280, 720)}
    report = root / name
    (report / "definition" / "pages").mkdir(parents=True)
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": sorted(pages)}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(
        json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}), encoding="utf-8")
    (report / "definition" / "report.json").write_text(json.dumps({
        "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                    "report/definition/report/3.3.0/schema.json"),
        "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")
    for page_id, (width, height) in pages.items():
        page_dir = report / "definition" / "pages" / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(
            json.dumps({"displayName": page_id, "width": width,
                        "height": height}), encoding="utf-8")
    return report


def _instance(report: Path, pid: int = 111) -> dict:
    return {"pid": pid, "bridgeStatus": "connected",
            "currentFilePath": str(report.with_suffix(".pbip")),
            "hasUnsavedChanges": False, "reportDir": str(report),
            "pages": [{"id": "p1"}], "desktopVersion": "2.0-test"}


class FakePort:
    """Injectable modeling port with scripted readiness answers."""

    def __init__(self, readies: list[dict[str, Any]]) -> None:
        self._readies = readies
        self.calls: list[dict] = []
        self.closed = False

    def connect(self) -> dict[str, Any]:
        return {"model": "fake/model"}

    def readiness(self, scope: Any) -> dict[str, Any]:
        self.calls.append(scope.as_dict())
        index = min(len(self.calls) - 1, len(self._readies) - 1)
        return dict(self._readies[index])

    def query_scoped(self, dax: str, scope: Any,
                     max_rows: int = 100) -> dict[str, Any]:
        raise AssertionError("capture never runs scoped queries")

    def close(self) -> None:
        self.closed = True


def _ready(populated: bool = True, rowcount: int = 5,
           query_hash: str = "h", model: str = "fake/model",
           **extra: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {"populated": populated,
                           "method": "modeling-mcp:repeat-query",
                           "scope_echo": {"model": model},
                           "rowcount": rowcount, "query_hash": query_hash}
    doc.update(extra)
    return doc


def _stub(monkeypatch: pytest.MonkeyPatch, report: Path,
          statuses: list[list[dict]] | None = None,
          version: str = "powerbi-desktop 1.0.0",
          actions: dict[str, str] | None = None,
          mutate: Any = None) -> None:
    """Stub the Bridge: scripted status sequence + per-page PNG actions.

    Actions per page: ok (exact canvas x scale, non-uniform), blank,
    wrong-size, corrupt, missing, escape (outputPath outside the output
    dir), short-ihdr, huge-dims, interlaced, palette.
    """
    queue = list(statuses) if statuses else [[_instance(report)]]
    actions = actions or {}
    monkeypatch.setattr(capture_mod.tempfile, "gettempdir",
                        lambda: str(report.parent / "vqs-leases"))

    def fake_bridge(args: list[str], timeout: int) -> tuple[int, str]:
        if args[0] == "--version":
            return 0, version
        if args[0] == "status":
            instances = queue.pop(0) if len(queue) > 1 else queue[0]
            return 0, json.dumps({"status": "ready",
                                  "instances": instances})
        assert args[0] == "screenshot-all"
        scale = int(args[args.index("--scale") + 1])
        out = Path(args[args.index("--output-dir") + 1])
        shots = []
        for page_id, action in actions.items():
            if action == "missing":
                continue
            raw = out / f"Display {page_id}.png"
            if action == "escape":
                raw = out.parent / "escaped.png"
            dims = json.loads((report / "definition" / "pages" / page_id
                               / "page.json").read_text(encoding="utf-8"))
            width, height = dims["width"] * scale, dims["height"] * scale
            if action == "wrong-size":
                width, height = 500, 500
            if action == "corrupt":
                raw.write_bytes(b"this is not a png")
            elif action == "short-ihdr":
                raw.write_bytes(_broken_png("short-ihdr"))
            elif action == "huge-dims":
                _write_png(raw, 20000, 20000, bare=True)
            elif action == "interlaced":
                _write_png(raw, width, height, interlace=1)
            elif action == "palette":
                _write_png(raw, width, height, color=3)
            else:
                _write_png(raw, width, height, blank=(action == "blank"))
            shots.append({"pageId": page_id, "outputPath": str(raw)})
        if mutate is not None:
            mutate()
        return 0, json.dumps({"status": "ok", "screenshots": shots})

    monkeypatch.setattr(capture_mod, "_bridge", fake_bridge)


def test_bridge_version_gate_blocks_old_and_unparseable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, version="powerbi-desktop 0.9.0",
          actions={"p1": "ok"})
    with pytest.raises(LookupError, match="below"):
        capture_mod.capture(str(report), str(tmp_path / "r"))
    _stub(monkeypatch, report, version="no version here",
          actions={"p1": "ok"})
    with pytest.raises(LookupError, match="unparseable"):
        capture_mod.capture(str(report), str(tmp_path / "r2"))


def test_nondefault_state_and_interactions_block(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, actions={"p1": "ok"})
    with pytest.raises(OSError, match="unsupported"):
        capture_mod.capture(str(report), str(tmp_path / "r"),
                            state="bookmarked")
    with pytest.raises(OSError, match="slicer-click"):
        capture_mod.capture(str(report), str(tmp_path / "r2"),
                            interactions=["slicer-click"])


def test_blank_partial_corrupt_and_tiny_block(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, actions={"p1": "blank"})
    with pytest.raises(OSError, match="Blank capture"):
        capture_mod.capture(str(report), str(tmp_path / "r1"))
    _stub(monkeypatch, report, actions={"p1": "wrong-size"})
    with pytest.raises(OSError, match=r"Canvas size mismatch.*2560x1440.*500x500"):
        capture_mod.capture(str(report), str(tmp_path / "r2"))
    _stub(monkeypatch, report, actions={"p1": "corrupt"})
    with pytest.raises(OSError, match="Corrupt capture"):
        capture_mod.capture(str(report), str(tmp_path / "r3"))
    tiny = _make_report(tmp_path / "tiny", {"p1": (100, 100)})
    _stub(monkeypatch, tiny, actions={"p1": "ok"})
    with pytest.raises(OSError, match="minimum"):
        capture_mod.capture(str(tiny), str(tmp_path / "r4"), scale=1)


def test_stale_staging_mixed_canvas_and_scale_block(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "old.png").write_bytes(b"stale")
    _stub(monkeypatch, report, actions={"p1": "ok"})
    with pytest.raises(OSError, match="not fresh"):
        capture_mod.capture(str(report), str(stale))
    mixed = _make_report(tmp_path / "mixed",
                         {"p1": (1280, 720), "p2": (1920, 1080)})
    _stub(monkeypatch, mixed, actions={"p1": "ok", "p2": "ok"})
    with pytest.raises(OSError, match="differing"):
        capture_mod.capture(str(mixed), str(tmp_path / "r"))
    with pytest.raises(OSError, match="must be 1 or 2"):
        capture_mod.capture(str(report), str(tmp_path / "r2"), scale=3)


def test_unsafe_page_id_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path, {"p1": (1280, 720)})
    evil = report / "definition" / "evil"
    evil.mkdir(parents=True)
    (evil / "page.json").write_text(
        json.dumps({"displayName": "evil", "width": 1280, "height": 720}),
        encoding="utf-8")
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["../evil"]}), encoding="utf-8")
    _stub(monkeypatch, report, actions={})
    # The inventory refuses the unsafe id before capture's own
    # filename gate ever runs (page_order_unsafe names it; capture
    # surfaces inventory failures as OSError).
    with pytest.raises(OSError, match="page_order_unsafe"):
        capture_mod.capture(str(report), str(tmp_path / "r"))


def test_held_lease_blocks(tmp_path: Path,
                           monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    leases = tmp_path / "leases"
    assert claim_artifact(leases, "desktop-pid-111", "another-capture")
    _stub(monkeypatch, report, actions={"p1": "ok"})
    with pytest.raises(OSError, match="Exclusive lease"):
        capture_mod.capture(str(report), str(tmp_path / "r"),
                            lease_dir=str(leases))


def test_target_recheck_blocks_on_report_drift(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    other = _make_report(tmp_path / "other")
    _stub(monkeypatch, report, actions={"p1": "ok"},
          statuses=[[_instance(report)], [_instance(other)]])
    with pytest.raises(LookupError, match="not "):
        capture_mod.capture(str(report), str(tmp_path / "r"))


def test_unpopulated_and_drifted_readiness_block(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, actions={"p1": "ok"})
    port = FakePort([_ready(populated=False, detail="empty model")])
    with pytest.raises(OSError, match="not populated"):
        capture_mod.capture(str(report), str(tmp_path / "r1"),
                            modeling=port)
    assert port.closed is False  # injected ports belong to the caller
    drifting = FakePort([_ready(rowcount=5), _ready(rowcount=6)])
    with pytest.raises(OSError, match="changed during capture"):
        capture_mod.capture(str(report), str(tmp_path / "r2"),
                            modeling=drifting)


def test_expected_scope_mismatch_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, actions={"p1": "ok"})
    port = FakePort([_ready(model="fake/model")])
    with pytest.raises(OSError, match="differs from expected"):
        capture_mod.capture(str(report), str(tmp_path / "r"),
                            modeling=port,
                            expected_scope={"model": "other/model"})
    port = FakePort([_ready(model="fake/model")])
    manifest = capture_mod.capture(str(report), str(tmp_path / "r2"),
                                   modeling=port,
                                   expected_scope={"model": "fake/model"})
    assert manifest["data_readiness"]["scope"]["model"] == "fake/model"


def test_source_drift_during_capture_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    page_file = report / "definition" / "pages" / "p1" / "page.json"

    def mutate() -> None:
        doc = json.loads(page_file.read_text(encoding="utf-8"))
        doc["displayName"] = "changed mid-capture"
        page_file.write_text(json.dumps(doc), encoding="utf-8")

    _stub(monkeypatch, report, actions={"p1": "ok"}, mutate=mutate)
    with pytest.raises(OSError, match="changed during capture"):
        capture_mod.capture(str(report), str(tmp_path / "r"))


def test_modeling_auto_without_launcher_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil as _shutil

    report = _make_report(tmp_path)
    _stub(monkeypatch, report, actions={"p1": "ok"})
    monkeypatch.setenv("VQS_MODELING_AUTO", "1")
    monkeypatch.setattr(_shutil, "which", lambda _name: None)
    with pytest.raises(OSError, match="not on PATH"):
        capture_mod.capture(str(report), str(tmp_path / "r"))


def test_multipage_success_manifest_shape(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path, {"p1": (1280, 720), "p2": (1280, 720)})
    _stub(monkeypatch, report, actions={"p1": "ok", "p2": "ok"})
    port = FakePort([_ready(probe_table="Sales", data_rows=42)])
    renders = tmp_path / "renders"
    manifest = capture_mod.capture(str(report), str(renders),
                                   modeling=port)
    assert manifest["source_sha256"] == source_digest(report)
    assert manifest["page_images"] == {"p1": "p1.png", "p2": "p2.png"}
    assert set(manifest["files"]) == {"p1.png", "p2.png"}
    assert manifest["desktop"]["pid"] == 111
    assert manifest["desktop"]["scale"] == 2
    assert manifest["desktop"]["bridge_version"] == [1, 0, 0]
    assert manifest["state"] == "default"
    assert manifest["interactions_applied"] == []
    assert manifest["calibration"] == {
        "canvas_width": 1280, "canvas_height": 720, "scale": 2,
        "png_pixels": "2560x1440",
        "method": "pbir-canvas-png-size-crosscheck"}
    assert manifest["data_readiness"] == {
        "populated": True, "method": "modeling-mcp:repeat-query",
        "scope": {"model": "fake/model"}, "rowcount": 5, "query_hash": "h",
        "probe_table": "Sales", "data_rows": 42}
    assert manifest["modeling"] == {"status": "ready"}
    assert len(port.calls) == 2  # pre + post readiness probes
    on_disk = json.loads((renders / "capture-manifest.json")
                         .read_text(encoding="utf-8"))
    assert on_disk == manifest


def test_short_ihdr_blocks_without_crash(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, actions={"p1": "short-ihdr"})
    with pytest.raises(OSError, match="Corrupt capture"):
        capture_mod.capture(str(report), str(tmp_path / "r"))
    broken = tmp_path / "broken.png"
    broken.write_bytes(_broken_png("short-ihdr"))
    with pytest.raises(ValueError, match="Invalid PNG header"):
        capture_mod._png_pixels(broken)


def test_corrupt_label_ignores_directory_name(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, actions={"p1": "corrupt"})
    renders = tmp_path / "unsupported-case" / "r"
    with pytest.raises(OSError, match="Corrupt capture"):
        capture_mod.capture(str(report), str(renders))


def test_huge_dimensions_refuse_before_inflate(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path, {"p1": (20000, 20000)})
    _stub(monkeypatch, report, actions={"p1": "huge-dims"})
    with pytest.raises(OSError, match="exceeds decode cap"):
        capture_mod.capture(str(report), str(tmp_path / "r"), scale=1)


def test_unsupported_pixel_kinds_are_not_corruption(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, actions={"p1": "interlaced"})
    with pytest.raises(OSError, match="Unsupported capture"):
        capture_mod.capture(str(report), str(tmp_path / "r1"))
    _stub(monkeypatch, report, actions={"p1": "palette"})
    with pytest.raises(OSError, match="Unsupported capture"):
        capture_mod.capture(str(report), str(tmp_path / "r2"))


def test_bridge_path_escape_blocks_without_move(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, actions={"p1": "escape"})
    with pytest.raises(OSError, match="outside output dir"):
        capture_mod.capture(str(report), str(tmp_path / "r"))
    assert not (tmp_path / "r" / "p1.png").exists()
    assert (tmp_path / "escaped.png").is_file()  # source untouched


def test_missing_pid_blocks_not_crashes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    bad = _instance(report)
    del bad["pid"]
    _stub(monkeypatch, report, actions={"p1": "ok"}, statuses=[[bad]])
    with pytest.raises(TypeError, match="numeric PID"):
        capture_mod.capture(str(report), str(tmp_path / "r"))


def test_incomplete_readiness_blocks_drift_check(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, actions={"p1": "ok"})
    thin = FakePort([{"populated": True, "scope_echo": {}}])
    with pytest.raises(OSError, match="incomplete"):
        capture_mod.capture(str(report), str(tmp_path / "r"),
                            modeling=thin)


def test_colon_and_leading_dot_page_ids_block(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _make_report(tmp_path)
    pages_file = report / "definition" / "pages.json"
    for bad_id in ("p1:a", ".hidden"):
        pages_file.write_text(json.dumps({"pageOrder": [bad_id]}),
                              encoding="utf-8")
        _stub(monkeypatch, report, actions={})
        # Refused at inventory preflight with the unsafe-specific
        # rule, before capture's filename gate (surfaced as OSError).
        with pytest.raises(OSError, match="page_order_unsafe"):
            capture_mod.capture(str(report), str(tmp_path / f"r-{bad_id}"))


def test_shell_fallback_blocks_parens_allows_spaces(
        monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess as sp

    monkeypatch.setattr(capture_mod.shutil, "which",
                        lambda _cmd: "C:\\fake\\bridge.cmd")

    def flaky(cmd: Any, **kwargs: Any) -> sp.CompletedProcess[str]:
        if not kwargs.get("shell"):
            raise OSError("needs a shell")
        return sp.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(capture_mod.subprocess, "run", flaky)
    for hostile in ("foo(bar)", 'quo"te', "line\nbreak"):
        with pytest.raises(OSError, match="Refusing shell fallback"):
            capture_mod._bridge(["status", hostile], 5)
    code, out = capture_mod._bridge(["status", "C:\\My Renders\\x"], 5)
    assert (code, out) == (0, "ok")


@pytest.mark.parametrize("filt", [0, 1, 2, 3, 4])
def test_png_filters_decode_uniform_and_varied(
        tmp_path: Path, filt: int) -> None:
    varied = tmp_path / f"varied{filt}.png"
    _write_png(varied, 16, 8, filt=filt)
    assert capture_mod._png_pixels(varied) == (16, 8, False)
    blank = tmp_path / f"blank{filt}.png"
    _write_png(blank, 16, 8, blank=True, filt=filt)
    assert capture_mod._png_pixels(blank) == (16, 8, True)


def test_paeth_filtered_bytes_match_hand_derivation(tmp_path: Path) -> None:
    # Hand-derived Paeth forward filter for row1 (all base color) against
    # row0 (dark first pixel, base rest), 4px RGB: i<3 has no left/upper
    # neighbors against dark up bytes, so bytes pass through; i=3..5
    # cancel against equal left bytes; the rest cancel fully.
    shot = tmp_path / "paeth.png"
    _write_png(shot, 4, 2, filt=4)
    data = shot.read_bytes()
    pos, idat = 8, b""
    while pos + 8 <= len(data):
        (size,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + size]
        if kind == b"IDAT":
            idat += body
        if kind == b"IEND":
            break
        pos += 12 + size
    rows = zlib.decompress(idat)
    assert rows[13:26] == bytes([4, 0x20, 0x60, 0xC0] + [0] * 9)
