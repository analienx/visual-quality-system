"""Desktop capture: Bridge screenshots bound to an exact source revision.

``capture`` selects the Desktop instance that has the given report
open (exact PID + canonical path — never "whichever is open"), runs
Bridge ``screenshot-all``, and writes the ``capture-manifest.json``
that ``vqs request-review`` consumes. Anything unproven blocks with
the exact missing piece: no binary, no instance, wrong report,
unsaved changes, several instances without ``--pid``, missing or
corrupt page PNGs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


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

def capture(report: str, renders: str, pid: int | None = None,
            scale: int = 2, wait_seconds: int = 60) -> dict:
    """Capture every page and write the manifest; raise on any gap."""
    from .evidence import png_size
    from .pbir import report_context, source_digest

    report_path = Path(report)
    try:
        info = report_context(report_path)
        expected = [page["id"] for page in info["pages"]]
        source_before = source_digest(report_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise OSError(f"Cannot read report: {exc}") from exc
    instance = select_instance(str(report_path), pid, wait_seconds)
    renders_path = Path(renders)
    renders_path.mkdir(parents=True, exist_ok=True)
    code, output = _bridge(
        ["screenshot-all", "--pid", str(instance["pid"]),
         "--output-dir", str(renders_path), "--scale", str(scale),
         "--wait-seconds", str(wait_seconds)],
        timeout=wait_seconds + 300)
    if code != 0:
        raise OSError(f"screenshot-all failed: {output[:500]}")
    mapping = _screenshot_map(output)
    page_images = {}
    files = {}
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
        except (ValueError, OSError) as exc:
            raise OSError(f"Corrupt capture for {page_id}: {exc}") from exc
        page_images[page_id] = target.name
        files[target.name] = _sha256(target)
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
    manifest = {"source_sha256": source_after,
                "page_images": page_images,
                "files": files,
                "desktop": {"pid": instance["pid"],
                            "report": instance.get("currentFilePath"),
                            "scale": scale}}
    (renders_path / "capture-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
