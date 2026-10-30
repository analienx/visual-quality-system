"""Exact-PID native Power BI Desktop page capture with source-bound receipts.

A capture with the expected filename is not proof of current source identity.
This producer checks OS ownership, Desktop Bridge, source snapshot before and
after and all generated native PNGs; it does not approve G2/G4/G6.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from vqs.powerbi.acceptance_subjects import _asset
from vqs.powerbi.desktop_native_provenance import snapshot
from vqs.powerbi.desktop_source import project_artifacts


def _status(cli: str, pid: int, pbip: Path, report: Path) -> dict[str, Any]:
    p = subprocess.run([cli, "status", "--pid", str(pid), "--wait-seconds", "15"],
                       capture_output=True, text=True, timeout=35, check=False)
    if p.returncode:
        raise ValueError("Power BI Bridge status failed: " + p.stderr[-250:])
    state = json.loads(p.stdout)
    instances = state.get("instances")
    if state.get("status") != "ready" or not isinstance(instances, list) or (
            len(instances) != 1):
        raise ValueError("expected exactly one ready Desktop Bridge instance")
    entry = instances[0]
    if entry.get("pid") != pid or entry.get("bridgeStatus") != "connected" or (
            Path(str(entry.get("currentFilePath"))).resolve() != pbip or
            Path(str(entry.get("reportDir"))).resolve() != report):
        raise ValueError("Desktop Bridge report/PID identity mismatched")
    if not isinstance(entry.get("pages"), list) or not entry["pages"]:
        raise ValueError("native page inventory missing")
    return entry


def capture(project: Path, pid: int, output_dir: Path, *,
            bridge_cli: str | None = None) -> dict[str, Any]:
    """Capture a private disposable report; never substitute stale screenshots."""
    if os.name != "nt" or type(pid) is not int or pid <= 0:
        raise ValueError("native capture requires an exact Windows Desktop PID")
    project = project.resolve(strict=True)
    pbip, report = project_artifacts(project)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ValueError("capture output directory already exists")
    if output_dir == project or output_dir in project.parents or (
            project in output_dir.parents):
        raise ValueError("native capture must not write inside PBIP")
    cli = bridge_cli or shutil.which("powerbi-desktop")
    if not cli:
        raise ValueError("Power BI Desktop Bridge executable unavailable")
    try:
        import psutil
    except ImportError as exc:
        raise ValueError("native PID ownership requires psutil") from exc
    proc = psutil.Process(pid)
    cmdline = proc.cmdline()
    if proc.name().lower() != "pbidesktop.exe" or (
            len(cmdline) < 2 or Path(cmdline[-1]).resolve() != pbip):
        raise ValueError("OS process does not own exact PBIP")
    birth = proc.create_time()
    before = snapshot(project)
    entry = _status(cli, pid, pbip, report)
    if entry.get("hasUnsavedChanges") is not False:
        raise ValueError("fresh native capture requires a clean saved source")
    output_dir.mkdir(parents=True, exist_ok=False)
    p = subprocess.run(
        [cli, "screenshot-all", "--pid", str(pid),
         "--output-dir", str(output_dir), "--scale", "2",
         "--settle", "1000", "--wait-seconds", "35"],
        capture_output=True, text=True, timeout=145, check=False,
    )
    if p.returncode:
        raise ValueError("native screenshot-all failed: " + p.stderr[-300:])
    receipt = json.loads(p.stdout)
    if receipt.get("status") != "ok" or receipt.get("pid") != pid or (
            Path(str(receipt.get("reportDir"))).resolve() != report):
        raise ValueError("native screenshot receipt had wrong report or PID")
    pages = entry["pages"]
    shots = receipt.get("screenshots")
    if not isinstance(shots, list) or len(shots) != len(pages):
        raise ValueError("native page capture incomplete")
    if {x.get("id") for x in pages} != {x.get("pageId") for x in shots}:
        raise ValueError("native page IDs differ from before-capture inventory")
    assets = []
    for shot in shots:
        image_path = Path(str(shot["outputPath"])).resolve(strict=True)
        if image_path.parent != output_dir:
            raise ValueError("native capture escaped destination directory")
        data = _asset(image_path)
        data["page_id"] = shot["pageId"]
        data["display_name"] = shot["pageDisplayName"]
        assets.append(data)
    if set(output_dir.iterdir()) != {Path(x["path"]) for x in assets}:
        raise ValueError("unexpected or extra files in native capture folder")
    after_entry = _status(cli, pid, pbip, report)
    if proc.create_time() != birth or snapshot(project) != before:
        raise ValueError("native PID/source changed during capture")
    if {x["id"] for x in after_entry["pages"]} != {x["id"] for x in pages}:
        raise ValueError("native page inventory changed during capture")
    return {
        "schema": "vqs.native-capture-identity/1",
        "project": str(project),
        "pbip": str(pbip),
        "report": str(report),
        "desktop_pid": pid,
        "os_process_created": birth,
        "native_pages": assets,
        "source_files": {
            key: {"sha256": value["sha256"], "size": value["size"]}
            for key, value in before.items()
        },
        "source_unchanged_during_capture": True,
        "post_capture_unsaved_flag": after_entry.get("hasUnsavedChanges"),
        "formal_g2_g4_g6": "blocked",
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists() or args.receipt.is_symlink():
        parser.error("refusing to replace existing evidence")
    proof = capture(args.project, args.pid, args.output_dir)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf8") as stream:
        json.dump(proof, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"native_source_bound": True,
                      "pages": len(proof["native_pages"]),
                      "formal_g2_g4_g6": "blocked",
                      "receipt": str(args.receipt)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
