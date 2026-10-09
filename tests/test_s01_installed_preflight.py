"""S01: version preflight through installed routes, before any port.

A malformed versionMetadata blocks `vqs inspect` and `vqs capture`
on the installed entry point; capture's source preflight runs
before the Bridge binary, so a blocked report never reaches the
external port and no renders are staged.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vqs import capture as capture_mod
from vqs.cli import main as vqs_main

VQS_BIN = shutil.which("vqs")
needs_vqs = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs entry point not on PATH")

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")
SCHEMA_INDEX = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.1.0/schema.json")
SCHEMA_VERSION = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                  "report/definition/versionMetadata/1.0.0/schema.json")


def _bad_version_report(root: Path) -> Path:
    report = root / "bad.Report"
    pages = report / "definition" / "pages"
    (pages / "P1").mkdir(parents=True)
    (pages / "pages.json").write_text(
        json.dumps({"$schema": SCHEMA_INDEX, "pageOrder": ["P1"]}),
        encoding="utf-8")
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1"]}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(
        json.dumps({"$schema": SCHEMA_VERSION, "version": "banana"}),
        encoding="utf-8")
    (report / "definition" / "report.json").write_text(json.dumps({
        "$schema": SCHEMA_REPORT, "layoutOptimization": "None",
        "themeCollection": {}}), encoding="utf-8")
    (pages / "P1" / "page.json").write_text(
        json.dumps({"displayName": "P1", "width": 1280, "height": 720}),
        encoding="utf-8")
    return report


def test_bridge_never_called_after_blocked_preflight(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys) -> None:
    """S01: capture preflight blocks before the Bridge binary."""
    report = _bad_version_report(tmp_path)

    def boom(args, timeout):
        raise AssertionError("bridge must not be reached")

    monkeypatch.setattr(capture_mod, "_bridge", boom)
    code = vqs_main(["capture", str(report), str(tmp_path / "renders")])
    out = capsys.readouterr().out
    assert code == 2, out
    assert "Cannot read report" in out
    assert not (tmp_path / "renders").exists()


@needs_vqs
def test_installed_inspect_blocks_bad_version(
        tmp_path: Path) -> None:
    """S01+C09: the installed inspect route rejects bad versions."""
    report = _bad_version_report(tmp_path)
    proc = subprocess.run([VQS_BIN, "inspect", str(report)],
                          capture_output=True, text=True, timeout=300,
                          check=False)
    assert proc.returncode == 2, proc.stdout
    assert json.loads(proc.stdout)["verdict"] == "blocked"


@needs_vqs
def test_installed_capture_blocks_before_bridge(
        tmp_path: Path) -> None:
    """S01+C09: installed capture stages nothing for bad versions."""
    report = _bad_version_report(tmp_path)
    renders = tmp_path / "renders"
    proc = subprocess.run([VQS_BIN, "capture", str(report), str(renders)],
                          capture_output=True, text=True, timeout=300,
                          check=False)
    assert proc.returncode == 2, proc.stdout
    assert "Cannot read report" in proc.stdout
    assert not renders.exists()
