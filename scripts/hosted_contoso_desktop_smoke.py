"""Windows GitHub hosted *real* complete Contoso Power BI Desktop smoke.

Runs only on the disposable hosted VM. Uses the already installed official
Power BI Desktop, opens the owner-authorized exact Contoso fixture and captures
native screenshots after bounded settling periods. Model DAX parity remains
UNPROVEN until a DAX probe executes successfully.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import time
import zipfile
from ctypes import wintypes
from pathlib import Path


def _pbi_exe() -> Path:
    pf = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    exe = pf / "Microsoft Power BI Desktop" / "bin" / "PBIDesktop.exe"
    if not exe.is_file():
        raise RuntimeError("official Power BI Desktop executable not installed")
    return exe


def _windows() -> dict[str, bool | int]:
    u = ctypes.windll.user32
    result = {"powerbi_visible": False, "contoso_title_visible": False,
              "powerbi_window_count": 0}
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback
    def visit(hwnd: int, _: int) -> bool:
        if not u.IsWindowVisible(hwnd):
            return True
        name = ctypes.create_unicode_buffer(510)
        if u.GetWindowTextW(hwnd, name, 509) > 0:
            title = name.value
            if "Power BI" in title or "Contoso Retail" in title:
                result["powerbi_visible"] = True
                result["powerbi_window_count"] += 1
                if "Contoso Retail" in title:
                    result["contoso_title_visible"] = True
        return True

    u.EnumWindows(visit, 0)
    return result


def _extract(archive: Path, dest: Path) -> tuple[Path, int]:
    if dest.exists():
        raise RuntimeError("refuse reuse")
    dest.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        members = z.infolist()
        if len(members) != 86 or any(
            ".." in Path(info.filename).parts or
            Path(info.filename).is_absolute() or info.file_size > 1_000_000
            for info in members
        ):
            raise RuntimeError("unexpected Contoso archive membership")
        z.extractall(dest)
    pbip = dest / "Contoso Retail.pbip"
    cache = dest / "Contoso Retail.SemanticModel" / ".pbi" / "cache.abf"
    if not pbip.is_file() or not cache.is_file():
        raise RuntimeError("complete Contoso project is not present")
    return pbip, cache.stat().st_size


def evaluate(out: Path, screen_prefix: Path) -> dict[str, object]:
    from PIL import ImageGrab

    base = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    archive = base / "contoso-retail-complete-p7.zip"
    reference = json.loads((base / "contoso-retail-complete-p7.manifest.json").read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != reference["zip_sha256"]:
        raise RuntimeError("Contoso archive hash mismatch")
    target = Path(os.environ.get("RUNNER_TEMP", ".")) / "vqs-real-contoso-desktop"
    pbip, cache_bytes = _extract(archive, target)
    exe = _pbi_exe()
    process = subprocess.Popen([str(exe), str(pbip)],
                               stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    record: dict[str, object] = {
        "contract": "vqs.github-hosted-contoso-desktop/1",
        "fixture_sha256": reference["zip_sha256"],
        "model_cache_bytes": cache_bytes,
        "powerbi_desktop_installed": True,
        "process_created": True,
        "model_dax_query": "NOT_RUN",
        "render_acceptance": "NOT_PROVEN",
        "screenshots": [],
    }
    # Wait and sample; real GUI title and actual screenshot contents
    # are independently reviewed, not inferred from process launch.
    start = time.monotonic()
    for seconds in (25, 75, 140):
        remaining = seconds - (time.monotonic() - start)
        if remaining > 0:
            time.sleep(remaining)
        windows = _windows()
        result = subprocess.run(["tasklist", "/FO", "CSV"], check=False,
                                capture_output=True, text=True, timeout=30)
        filename = screen_prefix.with_name(f"{screen_prefix.name}-{seconds}s.png")
        shot = ImageGrab.grab(all_screens=False)
        shot.save(filename)
        evidence = {
            "elapsed_target_seconds": seconds,
            "screen_sha256": hashlib.sha256(filename.read_bytes()).hexdigest(),
            "screen_resolution": [shot.width, shot.height],
            "screenshot_bytes": filename.stat().st_size,
            "windows": windows,
            "analysis_services_process_seen": "msmdsrv.exe" in result.stdout.lower(),
            "powerbi_process_running": process.poll() is None,
        }
        record["screenshots"].append(evidence)
        print("CONTOSO_HOSTED_SAMPLE", json.dumps(evidence), flush=True)
    record["contoso_title_seen"] = any(
        x["windows"]["contoso_title_visible"] for x in record["screenshots"]
    )
    record["model_dax_query"] = "NOT_RUN"
    record["render_acceptance"] = "AWAITING_INDEPENDENT_IMAGE_REVIEW"
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--screens", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing existing evidence")
    try:
        result = evaluate(args.out, args.screens)
    except Exception as exc:  # noqa: BLE001 - external GUI needs a persistent receipt
        result = {
            "contract": "vqs.github-hosted-contoso-desktop/1",
            "status": "blocked",
            "error_class": type(exc).__name__,
            "error": str(exc)[:200],
            "model_dax_query": "NOT_RUN",
            "render_acceptance": "NOT_PROVEN",
        }
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
