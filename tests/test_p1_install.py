"""P1 items 32-34: install/version hygiene with focused tests.

`vqs --version` and `python -m vqs` work; doctor reports package
version, import root, engine/tool schemas, and git SHA when
discoverable; stale editable installs are reported obvious (never
modified).
"""
import importlib.metadata as md
import json
import runpy
import sys
from pathlib import Path

import pytest

import vqs
from vqs.cli import main as vqs_main
from vqs.install import (
    git_sha,
    installation_report,
    package_version,
)


class _FakeDist:
    def __init__(self, location, version="9.9.9", direct_url=None):
        self._location = str(location)
        self.version = version
        self._direct_url = direct_url

    def locate_file(self, name):
        return f"{self._location}/{name}" if name else self._location

    def read_text(self, name):
        if name == "direct_url.json" and self._direct_url is not None:
            return json.dumps(self._direct_url)
        return None


def test_version_flag_prints_package(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        vqs_main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip().startswith("vqs ")


def test_module_main_supports_dash_m(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["vqs", "--version"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("vqs", run_name="__main__", alter_sys=True)
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip().startswith("vqs ")


def test_package_version_absent_is_none(monkeypatch) -> None:
    def absent(name):
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "version", absent)
    assert package_version() is None


def test_installation_report_shape() -> None:
    report = installation_report()
    assert report["distribution"] == "visual-quality-system"
    assert report["import_root"].endswith("vqs")
    assert set(report["schemas"]) == {"config", "tool", "plan",
                                      "reviewer", "policy", "ledger",
                                      "contracts", "mcp_protocol"}
    assert isinstance(report["stale"], bool)
    assert "never modifies installs" in report["note"]


def test_stale_install_is_obvious(tmp_path, monkeypatch) -> None:
    foreign = tmp_path / "sitepkgs" / "vqs"
    foreign.mkdir(parents=True)
    monkeypatch.setattr(md, "distribution",
                        lambda name: _FakeDist(tmp_path / "sitepkgs"))
    report = installation_report()
    assert report["installed"] is True
    assert report["stale"] is True
    assert "reinstall" in report["stale_reason"]


def test_matching_editable_is_not_stale(monkeypatch) -> None:
    project = str(Path(vqs.__file__).resolve().parent.parent)
    monkeypatch.setattr(md, "distribution",
                        lambda name: _FakeDist(project, direct_url={
                            "url": "file:///elsewhere",
                            "dir_info": {"editable": True}}))
    report = installation_report()
    assert report["editable"] is True
    assert report["project_dir"] == "/elsewhere"
    assert report["stale"] is False


def test_missing_distribution_reports_source_run(monkeypatch) -> None:
    def absent(name):
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "distribution", absent)
    report = installation_report()
    assert report["installed"] is False
    assert report["version"] is None
    assert report["stale"] is False


def test_git_sha_absent_without_checkout(tmp_path) -> None:
    assert git_sha(tmp_path) is None
