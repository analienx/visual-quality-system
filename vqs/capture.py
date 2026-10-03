"""Desktop capture: Bridge screenshots bound to an exact source revision.

``capture`` selects the Desktop instance that has the given report
open (exact PID + canonical path — never "whichever is open"), runs
Bridge ``screenshot-all``, and writes the ``capture-manifest.json``
that ``vqs request-review`` consumes. Anything unproven blocks with
the exact missing piece: no binary, no instance, wrong report,
unsaved changes, several instances without ``--pid``, missing or
corrupt page PNGs.

Manifest v2 additionally binds measured full-canvas calibration
(PBIR canvas cross-checked against PNG pixels at the requested
scale) and scoped data readiness (modeling-port row evidence queried
twice). Capture refuses to manifest blank captures, partial canvas,
below-minimum pixels, unproven data, pre/post drift (source, target,
or readiness), stale staging, unsupported interactions, non-default
saved states, and mixed-size page sets. An exclusive per-PID lease
serializes captures on one host. Set VQS_MODELING_AUTO=1 to attempt
a live modeling connection; otherwise pass a modeling port explicitly
or accept a manifest without data readiness (downstream blocks it).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path
from typing import Any

MIN_REVIEWABLE_PIXELS = 450


def _bridge(args: list[str], timeout: int) -> tuple[int, str]:
    """Run the Bridge CLI; (returncode, combined output)."""
    binary = shutil.which("powerbi-desktop")
    if binary is None:
        raise FileNotFoundError("powerbi-desktop not on PATH")
    try:
        try:
            completed = subprocess.run(
                [binary, *args], capture_output=True, text=True,
                timeout=timeout, check=False)
        except OSError as exc:
            # Fallback for .bat/.cmd shims un-runnable without a shell.
            # list2cmdline quotes whitespace, not metachars: refuse the
            # shell when hostile output could have smuggled one in.
            command = subprocess.list2cmdline([binary, *args])
            if re.search(r'[&|^<>%!`$;\r\n]', command):
                raise OSError("Refusing shell fallback on metacharacters: "
                              f"{' '.join(args)}") from exc
            completed = subprocess.run(
                command, capture_output=True, text=True,
                timeout=timeout, check=False, shell=True)
    except subprocess.TimeoutExpired as exc:
        raise OSError(f"Bridge timed out: {' '.join(args)}") from exc
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
        os.path.abspath(right))


def select_instance(report_dir: str, pid: int | None,
                    wait_seconds: int) -> dict:
    """Pick the instance showing this report; raise blocked errors."""
    try:
        code, output = _bridge(
            ["status"], timeout=max(wait_seconds, 30) + 30)
    except FileNotFoundError as exc:
        raise LookupError(str(exc)) from exc
    if code != 0:
        raise LookupError(f"Bridge status failed: {output[:300]}")
    try:
        payload = json.loads(output)
    except ValueError as exc:
        raise LookupError(f"Bridge status is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise TypeError("Bridge status is not a JSON object")
    instances = payload.get("instances", [])
    if not isinstance(instances, list):
        raise TypeError("Bridge status has no instances list")
    instances = [i for i in instances if isinstance(i, dict)]
    if not instances:
        raise LookupError("No running Power BI Desktop instance found")
    if pid is not None:
        matches = [i for i in instances
                   if str(i.get("pid")) == str(pid)]
        if not matches:
            raise LookupError(f"No Desktop instance with PID {pid}")
        instance = matches[0]
    else:
        if len(instances) > 1:
            open_files = ", ".join(
                f"PID {i.get('pid')}: {i.get('currentFilePath')}"
                for i in instances)
            raise LookupError("Several Desktop instances open; pass --pid. "
                              f"Open: {open_files}")
        instance = instances[0]
    if not _same_path(str(instance.get("reportDir", "")), report_dir):
        raise LookupError(
            f"Desktop PID {instance.get('pid')} has "
            f"{instance.get('currentFilePath')} open, not {report_dir}")
    if "hasUnsavedChanges" not in instance:
        raise LookupError("Bridge did not report a save state; refusing "
                          "to capture against unknown staleness")
    if instance.get("hasUnsavedChanges"):
        raise LookupError("Desktop has unsaved changes; save or revert, "
                          "then capture again")
    return instance


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_bridge() -> list[int]:
    """Gate on a proven Bridge version; LookupError names the gap."""
    from .powerbi.desktop import gate_bridge_version

    try:
        code, output = _bridge(["--version"], timeout=30)
    except FileNotFoundError as exc:
        raise LookupError(str(exc)) from exc
    if code != 0:
        raise LookupError(f"Bridge --version failed: {output[:300]}")
    gate = gate_bridge_version(output)
    if gate["verdict"] != "pass":
        raise LookupError(gate["reason"])
    return gate["version"]


def _require_fresh_staging(renders_path: Path) -> None:
    """Refuse a staging dir with stale files that could mix into evidence."""
    if not renders_path.exists():
        return
    stale = sorted(p.name for p in renders_path.iterdir())
    if stale:
        raise OSError("Staging is not fresh; refusing to mix evidence: "
                      + ", ".join(stale[:8]))


def _safe_page_id(page_id: str) -> str:
    """Reject page ids that escape the renders dir as filenames."""
    if (not isinstance(page_id, str) or not page_id or page_id != page_id.strip()
            or "/" in page_id or "\\" in page_id or page_id in (".", "..")):
        raise OSError(f"Unsafe page id for evidence filename: {page_id!r}")
    return page_id


def _png_pixels(path: Path) -> tuple[int, int, bool]:
    """Decode PNG pixels; (width, height, uniform). Raise when unverifiable.

    Supports 8-bit gray/RGB/RGBA, non-interlaced — the screenshot shape.
    Anything else (or truncated data) raises: unverifiable pixels never
    pass as proven captures.
    """
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, width, height, depth, color, interlace = 8, 0, 0, 0, 0, 0
    raw_idat = b""
    while pos + 8 <= len(data):
        (size,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + size]
        if len(body) != size:
            raise ValueError("truncated PNG chunk")
        if kind == b"IHDR":
            (width, height, depth, color, _comp, _filt,
             interlace) = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            raw_idat += body
        elif kind == b"IEND":
            break
        pos += 12 + size
    channels = {0: 1, 2: 3, 6: 4}.get(color)
    if not width or not height or depth != 8 or channels is None:
        raise ValueError("unsupported PNG pixel format for blank detection")
    if interlace != 0:
        raise ValueError("interlaced PNG is unsupported for blank detection")
    try:
        inflated = zlib.decompress(raw_idat)
    except zlib.error as exc:
        raise ValueError(f"corrupt PNG data: {exc}") from exc
    stride = width * channels
    if len(inflated) != height * (stride + 1):
        raise ValueError("PNG data size mismatches dimensions")
    first_pixel: bytes | None = None
    uniform = True
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        kind = inflated[offset]
        offset += 1
        if kind > 4:
            raise ValueError("unknown PNG filter type")
        row = bytearray(inflated[offset:offset + stride])
        offset += stride
        for index in range(stride):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if kind == 1:
                row[index] = (row[index] + left) & 0xFF
            elif kind == 2:
                row[index] = (row[index] + up) & 0xFF
            elif kind == 3:
                row[index] = (row[index] + ((left + up) >> 1)) & 0xFF
            elif kind == 4:
                pick = left + up - upper_left
                dist_left = abs(pick - left)
                dist_up = abs(pick - up)
                dist_corner = abs(pick - upper_left)
                if dist_left <= dist_up and dist_left <= dist_corner:
                    row[index] = (row[index] + left) & 0xFF
                elif dist_up <= dist_corner:
                    row[index] = (row[index] + up) & 0xFF
                else:
                    row[index] = (row[index] + upper_left) & 0xFF
        for start in range(0, stride, channels):
            pixel = bytes(row[start:start + channels])
            if first_pixel is None:
                first_pixel = pixel
            elif pixel != first_pixel:
                uniform = False
                break
        if not uniform:
            break
        previous = row
    return width, height, uniform


def _screenshot_map(output: str) -> dict[str, str]:
    """Map pageId to PNG path from screenshot-all JSON output."""
    try:
        start = output.index('{')
        payload, _ = json.JSONDecoder().raw_decode(output[start:])
    except (ValueError, IndexError) as exc:
        raise OSError("Cannot parse screenshot-all output") from exc
    if not isinstance(payload, dict):
        raise OSError("screenshot-all returned no screenshots list")
    shots = payload.get("screenshots", [])
    if not isinstance(shots, list):
        raise OSError("screenshot-all returned no screenshots list")
    mapping = {}
    for shot in shots:
        if isinstance(shot, dict) and shot.get("pageId"):
            mapping[str(shot["pageId"])] = str(shot.get("outputPath", ""))
    return mapping

def _resolve_modeling(modeling: Any) -> tuple[Any, bool]:
    """Resolve the modeling port: explicit, auto (env opt-in), or skipped.

    Returns (port_or_None, owned). Owned ports are closed by capture;
    injected ones belong to the caller.
    """
    if modeling is not None:
        return modeling, False
    if os.environ.get("VQS_MODELING_AUTO") != "1":
        return None, False
    from .powerbi.modeling import StdioModelingClient

    return StdioModelingClient(), True


def capture(report: str, renders: str, pid: int | None = None,
            scale: int = 2, wait_seconds: int = 60,
            state: str = "default",
            interactions: list[str] | None = None,
            expected_scope: dict[str, Any] | None = None,
            modeling: Any = None,
            lease_dir: str | None = None) -> dict:
    """Capture every page and write the manifest; raise on any gap.

    New gates (all default-safe for existing callers): proven Bridge
    version, default saved state only, no requested interactions, fresh
    staging, per-PID exclusive lease, pre/post readiness with
    expected-scope verification and drift refusal, post-capture target
    recheck, exact canvas x scale pixels per page, minimum reviewable
    size, and blank-capture refusal. The manifest carries measured
    ``calibration`` always and ``data_readiness`` when a modeling port
    proves it.
    """
    from .evidence import png_size
    from .pbir import report_context, source_digest
    from .powerbi.modeling import ModelingScope, compare_scope

    if state != "default":
        raise OSError(f"Saved-state {state!r} verification is unsupported; "
                      "capture the default state")
    if interactions:
        raise OSError("Unsupported interactions for static capture: "
                      + ", ".join(sorted(str(i) for i in interactions)))
    bridge_version = _require_bridge()
    report_path = Path(report)
    try:
        info = report_context(report_path)
        expected = [page["id"] for page in info["pages"]]
        sizes = {page["id"]: ((page.get("canvas") or [None, None])[0],
                              (page.get("canvas") or [None, None])[1])
                 for page in info["pages"]}
        source_before = source_digest(report_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise OSError(f"Cannot read report: {exc}") from exc
    for page_id in expected:
        _safe_page_id(page_id)
    canvas = set(sizes.values())
    if len(canvas) != 1:
        raise OSError("Pages have differing canvas sizes; single "
                      "calibration cannot hold")
    canvas_width, canvas_height = canvas.pop()
    if (not isinstance(canvas_width, int) or not isinstance(canvas_height, int)
            or canvas_width <= 0 or canvas_height <= 0):
        raise OSError("Page canvas size is not a positive integer pair")
    if scale not in (1, 2):
        raise OSError(f"Capture scale must be 1 or 2, not {scale!r}")
    instance = select_instance(str(report_path), pid, wait_seconds)
    renders_path = Path(renders)
    _require_fresh_staging(renders_path)
    renders_path.mkdir(parents=True, exist_ok=True)
    from .run_store import claim_artifact, release_artifact

    locks = Path(lease_dir) if lease_dir else (
        Path(tempfile.gettempdir()) / "vqs-desktop-leases")
    lease_id = f"desktop-pid-{instance['pid']}"
    owner = f"vqs-capture-pid-{os.getpid()}"
    if not claim_artifact(locks, lease_id, owner):
        raise OSError(f"Exclusive lease held for Desktop PID "
                      f"{instance['pid']}; another capture holds it")
    port, owned = _resolve_modeling(modeling)
    scope = ModelingScope(source_sha256=source_before)
    readiness_before: dict[str, Any] | None = None
    try:
        if port is not None:
            readiness_before = port.readiness(scope)
            if not readiness_before.get("populated"):
                raise OSError("Data not populated: "
                              f"{readiness_before.get('detail', 'no rows')}")
            if expected_scope is not None:
                wanted = ModelingScope(
                    model=expected_scope.get("model"),
                    roles=tuple(expected_scope.get("roles", []) or []),
                    filters=expected_scope.get("filters"),
                    period=expected_scope.get("period"))
                mismatched = compare_scope(
                    wanted, readiness_before.get("scope_echo", {}))
                if mismatched:
                    raise OSError("Live scope differs from expected: "
                                  + ", ".join(mismatched))
        code, output = _bridge(
            ["screenshot-all", "--pid", str(instance["pid"]),
             "--output-dir", str(renders_path), "--scale", str(scale),
             "--wait-seconds", str(wait_seconds)],
            timeout=wait_seconds + 300)
        if code != 0:
            raise OSError(f"screenshot-all failed: {output[:500]}")
        mapping = _screenshot_map(output)
        if port is not None:
            readiness_after = port.readiness(scope)
            if not readiness_after.get("populated"):
                raise OSError("Data not populated after capture: "
                              f"{readiness_after.get('detail', 'no rows')}")
            assert readiness_before is not None
            if (readiness_after.get("rowcount")
                    != readiness_before.get("rowcount")
                    or readiness_after.get("query_hash")
                    != readiness_before.get("query_hash")):
                raise OSError("Data changed during capture; no manifest written")
        recheck = select_instance(str(report_path), instance["pid"],
                                  wait_seconds)
        if str(recheck.get("pid")) != str(instance["pid"]):
            raise OSError("Capture target PID changed during capture; "
                          "no manifest written")
        page_images = {}
        files = {}
        pixels: dict[str, list[int]] = {}
        missing = []
        for page_id in expected:
            raw = mapping.get(page_id, "")
            target = renders_path / f"{page_id}.png"
            if not raw or not Path(raw).is_file():
                missing.append(page_id)
                continue
            source = Path(raw)
            if source.resolve() != target.resolve():
                os.replace(source, target)
            try:
                png_size(target)
                width, height, uniform = _png_pixels(target)
            except (ValueError, OSError) as exc:
                raise OSError(f"Corrupt capture for {page_id}: {exc}") from exc
            if (width, height) != (canvas_width * scale, canvas_height * scale):
                raise OSError(f"Partial canvas for {page_id}: expected "
                              f"{canvas_width * scale}x{canvas_height * scale}, "
                              f"got {width}x{height}")
            if min(width, height) < MIN_REVIEWABLE_PIXELS:
                raise OSError(f"Capture for {page_id} below reviewable "
                              f"minimum {MIN_REVIEWABLE_PIXELS}px")
            if uniform:
                raise OSError(f"Blank capture for {page_id}: uniform pixels")
            page_images[page_id] = target.name
            files[target.name] = _sha256(target)
            pixels[page_id] = [width, height]
        if missing:
            raise OSError("Bridge did not capture pages: "
                          + ", ".join(sorted(missing)))
        try:
            source_after = source_digest(report_path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise OSError(f"Cannot re-read report: {exc}") from exc
        # Digest comparison cannot see A->B->A flaps or post-digest edits;
        # no manifest is written here, so unmanifested renders can never
        # pass evidence binding later.
        if source_after != source_before:
            raise OSError("Report changed during capture; no manifest written")
        first_pixels = pixels[expected[0]] if expected else [0, 0]
        manifest: dict[str, Any] = {
            "source_sha256": source_after,
            "page_images": page_images,
            "files": files,
            "desktop": {"pid": instance["pid"],
                        "report": instance.get("currentFilePath"),
                        "scale": scale,
                        "bridge_version": bridge_version,
                        "desktop_version": instance.get("desktopVersion")},
            "state": state,
            "interactions_applied": [],
            "calibration": {
                "canvas_width": canvas_width, "canvas_height": canvas_height,
                "scale": scale,
                "viewport": f"{first_pixels[0]}x{first_pixels[1]}",
                "method": "pbir-canvas-png-pixels-crosscheck"},
        }
        if port is not None:
            assert readiness_before is not None
            manifest["data_readiness"] = {
                "populated": True,
                "method": readiness_before.get(
                    "method", "modeling-mcp:repeat-query"),
                "scope": readiness_before.get("scope_echo", {})}
            manifest["modeling"] = {"status": "ready"}
        else:
            manifest["modeling"] = {
                "status": "skipped",
                "reason": "no modeling port supplied (pass one or set "
                          "VQS_MODELING_AUTO=1)"}
        (renders_path / "capture-manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    finally:
        if owned and port is not None:
            try:
                port.close()
            except OSError:
                pass
        release_artifact(locks, lease_id, owner)
