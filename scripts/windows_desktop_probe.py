"""Disposable-runner probe of real Power BI Desktop behaviour VQS depends on.

Runs only on an ephemeral Windows CI machine against a *copy* of the
fictional Contoso demo PBIP. It answers questions that unit tests cannot:

* Does ``screenshot-all`` flip Desktop's ``hasUnsavedChanges`` flag?
* What path casing does the OS command line report versus ``Path.resolve``?
* Does the real ``vqs.powerbi.native_capture_provenance.capture`` pass?

Output is a JSON summary of booleans, counts and digests only: no
screenshots, credentials or personal paths are published. This is
engineering evidence, never G2/G4/G6 acceptance.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples" / "contoso-retail-verified"


def _run(argv: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, "", f"{type(exc).__name__}: {exc}"
    return done.returncode, done.stdout, done.stderr


def _bridge() -> str | None:
    return shutil.which("powerbi-desktop")


def _status(cli: str, pid: int | None = None) -> dict[str, Any]:
    argv = [cli, "status", "--wait-seconds", "10"]
    if pid is not None:
        argv[2:2] = ["--pid", str(pid)]
    code, out, err = _run(argv, timeout=60)
    try:
        data = json.loads(out)
    except ValueError:
        return {"error": f"rc={code} {err[-300:]} {out[-300:]}"}
    return data if isinstance(data, dict) else {"error": "non-object status"}


def _instance_summary(entry: dict[str, Any]) -> dict[str, Any]:
    pages = entry.get("pages")
    return {"pid": entry.get("pid"),
            "bridgeStatus": entry.get("bridgeStatus"),
            "hasUnsavedChanges": entry.get("hasUnsavedChanges"),
            "page_count": len(pages) if isinstance(pages, list) else None,
            "currentFilePath_name": Path(str(entry.get("currentFilePath"))).name}


def _snapshot(project: Path) -> dict[str, str]:
    return {p.relative_to(project).as_posix():
            hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(project.rglob("*"))
            if p.is_file() and ".pbi" not in p.relative_to(project).parts}


def _command_line(pid: int) -> str | None:
    script = (f'(Get-CimInstance Win32_Process -Filter "ProcessId = {pid}")'
              '.CommandLine')
    code, out, _ = _run(["powershell.exe", "-NoProfile", "-NonInteractive",
                         "-Command", script], timeout=40)
    return out.strip() if code == 0 else None


def main() -> int:
    summary: dict[str, Any] = {"schema": "vqs.windows-desktop-probe/1",
                               "platform": sys.platform,
                               "vqs_revision": os.environ.get("GITHUB_SHA"),
                               "steps": {}}
    steps = summary["steps"]
    out_path = Path(os.environ.get("PROBE_OUT", "desktop-probe.json"))

    def finish() -> int:
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0

    if os.name != "nt":
        steps["platform"] = "skipped: not Windows"
        return finish()
    import importlib.util

    # VQS must attest Desktop without optional third-party modules.
    steps["psutil_installed"] = importlib.util.find_spec("psutil") is not None
    cli = _bridge()
    steps["bridge_cli"] = bool(cli)
    if cli:
        steps["bridge_version"] = _run([cli, "--version"])[1].strip()[:80]
    work = Path(os.environ.get("RUNNER_TEMP", os.getcwd())) / "vqs-probe"
    if work.exists():
        shutil.rmtree(work)
    # Deliberately mixed casing: the OS keeps what was typed on the command
    # line, while Path.resolve() returns the on-disk casing.
    project = work / "ContosoProbe"
    shutil.copytree(SOURCE, project)
    pbip = next(project.glob("*.pbip"))
    typed = str(pbip).replace("ContosoProbe", "contosoprobe")
    steps["resolve_normalizes_case"] = str(Path(typed).resolve()) == str(pbip.resolve())
    before_source = _snapshot(project)
    if not cli:
        return finish()
    code, out, err = _run([cli, "open", typed], timeout=600)
    steps["open"] = {"rc": code, "stdout_tail": out[-400:], "stderr_tail": err[-400:]}
    entry: dict[str, Any] | None = None
    deadline = time.monotonic() + 900
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _status(cli)
        instances = last.get("instances")
        if isinstance(instances, list):
            ready = [i for i in instances if isinstance(i, dict)
                     and i.get("bridgeStatus") == "connected"
                     and isinstance(i.get("pages"), list) and i["pages"]]
            if ready:
                entry = ready[0]
                break
        time.sleep(15)
    steps["status_wait_seconds"] = round(900 - max(0, deadline - time.monotonic()))
    if entry is None:
        steps["ready"] = False
        steps["last_status"] = {k: last.get(k) for k in ("status", "error")}
        return finish()
    pid = int(entry["pid"])
    steps["ready"] = True
    steps["before_capture"] = _instance_summary(entry)
    command = _command_line(pid)
    if command is not None:
        steps["os_command_line_has_typed_case"] = "contosoprobe" in command
        steps["os_command_line_has_disk_case"] = "ContosoProbe" in command
    # A freshly opened PBIP reports unsaved changes (observed on 2.159), so
    # the capture-flag question needs a clean baseline: perform the repo's
    # own witnessed native UIA Save on this disposable copy first.
    sys.path.insert(0, str(ROOT))
    try:
        from vqs.powerbi.desktop_native_save import save_and_witness

        witness = save_and_witness(project, pid, disposable_root=work)
        steps["native_save"] = {
            "verified": witness.get("native_saved_source_verified"),
            "unsaved_before": witness.get("unsaved_before"),
            "unsaved_after": witness.get("unsaved_after"),
            "reason": str(witness.get("reason", ""))[:300]}
    except Exception as exc:  # noqa: BLE001 - report every refusal
        steps["native_save"] = {"verified": False,
                                "reason": f"{type(exc).__name__}: {exc}"[:400]}
    time.sleep(5)
    saved = _status(cli, pid)
    inst = saved.get("instances")
    if isinstance(inst, list) and inst:
        steps["after_native_save"] = _instance_summary(inst[0])
    before_source = _snapshot(project)
    shots = work / "bridge-shots"
    code, out, err = _run([cli, "screenshot-all", "--pid", str(pid),
                           "--output-dir", str(shots), "--scale", "2",
                           "--settle", "1000", "--wait-seconds", "35"],
                          timeout=300)
    steps["screenshot_all_rc"] = code
    if code != 0:
        steps["screenshot_all_stderr"] = err[-400:]
    pngs = sorted(shots.glob("*.png")) if shots.exists() else []
    steps["png_count"] = len(pngs)
    after = _status(cli, pid)
    inst = after.get("instances")
    if isinstance(inst, list) and inst:
        steps["after_capture"] = _instance_summary(inst[0])
    steps["source_changed_by_capture"] = _snapshot(project) != before_source
    # The real VQS producer, unchanged: it must refuse or pass honestly.
    try:
        from vqs.powerbi.native_capture_provenance import capture

        receipt = capture(project, pid, work / "vqs-capture")
        steps["vqs_capture"] = {
            "status": "pass", "pages": len(receipt["native_pages"]),
            "post_capture_unsaved_flag": receipt["post_capture_unsaved_flag"]}
    except Exception as exc:  # noqa: BLE001 - report every refusal
        steps["vqs_capture"] = {"status": "refused",
                                "reason": f"{type(exc).__name__}: {exc}"[:400]}
    # Second capture in the same session: was the first one sticky?
    second = _status(cli, pid)
    inst = second.get("instances")
    if isinstance(inst, list) and inst:
        steps["after_vqs_capture"] = _instance_summary(inst[0])
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
