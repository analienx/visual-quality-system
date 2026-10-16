"""One-time evidence-only official Power BI Desktop Windows hosted smoke test.

Downloads only an official Microsoft binary, demands a valid Microsoft
Authenticode signature, runs in a disposable Windows VM, and opens a
synthetic Microsoft-CLI scaffold. It never uses customer data or credentials.
This diagnostic cannot be used as production report or DAX PASS evidence.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

INSTALL_URL = (
    "https://download.microsoft.com/download/8/8/0/"
    "880bca75-79dd-466a-927d-1abf1f5454b0/PBIDesktopSetup_x64.exe"
)


def _run(cmd: list[str], timeout: int = 60, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, check=False, **kwargs)


def _installer(temp: Path, evidence: dict[str, object]) -> Path:
    dest = temp / "PBIDesktopSetup_x64.exe"
    assert not dest.exists()
    digest = hashlib.sha256()
    total = 0
    req = urllib.request.Request(INSTALL_URL, headers={"User-Agent": "VQS-Hosted-Desktop-Probe/1"})
    with urllib.request.urlopen(req, timeout=90) as res, dest.open("xb") as target:
        final = res.geturl()
        if not final.lower().startswith("https://download.microsoft.com/"):
            raise ValueError("unexpected installer redirect host")
        while True:
            part = res.read(1024 * 1024)
            if not part:
                break
            total += len(part)
            if total > 950_000_000:
                raise ValueError("unexpected installer size")
            target.write(part)
            digest.update(part)
    if total < 300_000_000:
        raise ValueError("installer unexpectedly small")
    evidence["installer_bytes"] = total
    evidence["installer_sha256"] = digest.hexdigest()
    return dest


def _authenticode(path: Path) -> dict[str, object]:
    # Authenticode validation needs the Windows trust store, not just an
    # unauthenticated download checksum. Powershell is used only for this OS API.
    # Use a literal path within one PowerShell script. PowerShell -Command
    # does not reliably expose subsequent process argv via $args[0].
    quoted = "'" + str(path).replace("'", "''") + "'"
    script = (
        "$s=Get-AuthenticodeSignature -LiteralPath " + quoted + "; "
        "$o=[pscustomobject]@{Status=[string]$s.Status;"
        "Subject=[string]$s.SignerCertificate.Subject};"
        "$o | ConvertTo-Json -Compress"
    )
    cp = _run(["powershell.exe", "-NoProfile", "-NonInteractive",
               "-Command", script], timeout=90)
    if cp.returncode:
        raise RuntimeError("Authenticode OS validation failed: " + cp.stderr[-200:])
    data = json.loads(cp.stdout)
    if data.get("Status") != "Valid":
        raise ValueError("Power BI installer signature is not valid")
    if "Microsoft Corporation" not in data.get("Subject", ""):
        raise ValueError("Power BI installer not signed by Microsoft Corporation")
    return {"status": data["Status"],
            "subject_is_microsoft": True}


def _desktop_path() -> Path | None:
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    for path in (pf / "Microsoft Power BI Desktop" / "bin" / "PBIDesktop.exe",
                 pf86 / "Microsoft Power BI Desktop" / "bin" / "PBIDesktop.exe"):
        if path.is_file():
            return path
    return None


def _scaffold(temp: Path) -> Path:
    cli = shutil.which("powerbi-report-author")
    if cli is None:
        raise RuntimeError("official Microsoft authoring CLI missing")
    target = temp / "synthetic"
    target.mkdir(exist_ok=False)
    cp = _run([cli, "scaffold", str(target), "--name",
               "VQS Hosted Smoke", "--offline"], timeout=90, shell=False)
    if cp.returncode:
        raise RuntimeError("official synthetic scaffold failed: " + cp.stderr[-250:])
    result = json.loads(cp.stdout)["data"]
    pbip = Path(result["pbipPath"])
    if not pbip.is_file() or pbip.parent.resolve() != target.resolve():
        raise ValueError("Microsoft scaffold returned wrong local file")
    return pbip


def _visible_windows() -> list[dict[str, object]]:
    from ctypes import wintypes

    u = ctypes.windll.user32
    windows: list[dict[str, object]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd: int, _: int) -> bool:
        if not u.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        if u.GetWindowTextW(hwnd, buf, 511) > 0:
            title = buf.value
            if ("Power BI" in title or "VQS Hosted" in title):
                # Deliberately omit potentially sensitive window titles.
                windows.append({"powerbi_window_present": True,
                                "title_matches_synthetic": "VQS Hosted" in title,
                                "visible": True})
        return True

    u.EnumWindows(visit, 0)
    return windows


def _start_desktop(pbip: Path, evidence: dict[str, object], preview: Path) -> None:
    executable = _desktop_path()
    if executable is None:
        raise RuntimeError("Power BI Desktop executable absent after install")
    evidence["powerbi_executable"] = True
    process = subprocess.Popen([str(executable), str(pbip)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    evidence["desktop_process_created"] = True
    deadline = time.monotonic() + 125
    window: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        window = _visible_windows()
        if window:
            break
        if process.poll() is not None and process.returncode not in (0,):
            break
        time.sleep(3)
    evidence["visible_desktop_window"] = bool(window)
    evidence["synthetic_title_visible"] = any(
        item["title_matches_synthetic"] for item in window)
    active = _run(["tasklist", "/FO", "CSV"], timeout=25)
    evidence["local_analysis_services_process_seen"] = "msmdsrv.exe" in active.stdout.lower()
    if window:
        try:
            from PIL import ImageGrab
            image = ImageGrab.grab(all_screens=False)
            if image.width >= 1440 and image.height >= 900:
                image.save(preview)
                evidence["desktop_screen_captured"] = True
                evidence["screen_size"] = [image.width, image.height]
            else:
                evidence["desktop_screen_captured"] = False
                evidence["screen_size"] = [image.width, image.height]
        except (OSError, ValueError) as exc:
            evidence["screenshot_error_class"] = type(exc).__name__
    evidence["model_dax_query"] = "NOT_RUN"
    evidence["report_pixel_quality"] = "NOT_RUN"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists() or args.preview.exists():
        raise SystemExit("Refusing to overwrite evidence")
    evidence: dict[str, object] = {
        "contract": "vqs.hosted-powerbi-official-install-smoke/1",
        "platform": platform.system(),
        "official_source": "microsoft_download_center_58494",
        "powerbi_install": "NOT_ATTEMPTED",
        "powerbi_render_acceptance": "NOT_PROVEN",
        "customer_data": "NOT_USED",
        "credentials": "NOT_USED",
        "model_dax_query": "NOT_RUN",
        "error_class": None,
    }
    try:
        if os.name != "nt":
            raise RuntimeError("windows required")
        tmp = Path(os.environ.get("RUNNER_TEMP", ".")) / "vqs-pbi-install-spike"
        tmp.mkdir(parents=True, exist_ok=False)
        downloaded = _installer(tmp, evidence)
        evidence["authenticode"] = _authenticode(downloaded)
        setup = _run([str(downloaded), "-quiet", "-norestart",
                      "LANGUAGE=en-US", "ACCEPT_EULA=1"], timeout=720)
        evidence["installer_exit"] = setup.returncode
        evidence["powerbi_install"] = (
            "installed" if setup.returncode in (0, 3010) else "blocked"
        )
        if setup.returncode not in (0, 3010):
            raise RuntimeError("Microsoft installer exit was non-success")
        report = _scaffold(tmp)
        evidence["synthetic_pbip_scaffold"] = True
        _start_desktop(report, evidence, args.preview)
    except Exception as exc:  # noqa: BLE001 - evidence must survive external failures
        evidence["error_class"] = type(exc).__name__
        evidence["error_summary"] = str(exc)[:200]
    args.out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0  # Diagnostic is not a CI acceptance gate.


if __name__ == "__main__":
    sys.exit(main())
