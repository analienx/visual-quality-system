"""Doctor tests: shape-only; presence values depend on the machine."""
import json

from vqs.cli import main as vqs_main
from vqs.doctor import report


def test_report_shape() -> None:
    data = report()
    assert data["status"] in ("ok", "needs_setup")
    checks = data["checks"]
    assert set(checks) == {"report_author", "desktop_bridge", "modeling_mcp",
                           "desktop_process", "installation",
                           "authoring_preflight", "mcp_protocols"}
    assert "2026-07-28" in checks["mcp_protocols"]
    assert checks["authoring_preflight"]["status"] in ("pass", "blocked")
    for name in ("report_author", "desktop_bridge", "modeling_mcp"):
        assert checks[name]["status"] in ("present", "missing")
    assert checks["report_author"]["name"] == "powerbi-report-author"
    assert (checks["report_author"]["package"]
            == "@microsoft/powerbi-report-authoring-cli")
    install = checks["installation"]
    assert install["distribution"] == "visual-quality-system"
    assert install["import_root"].endswith("vqs")
    assert set(install["schemas"]) == {"config", "tool", "plan",
                                       "reviewer", "policy", "ledger",
                                       "contracts", "mcp_protocol"}
    assert isinstance(install["stale"], bool)


def test_modeling_mcp_version_is_probed(monkeypatch) -> None:
    """Zephyrus 2 Nov 2026: 0.5.0-beta.16 answers ``--version`` but doctor
    never asked, so it reported ``unknown`` for an installed tool."""
    from vqs import doctor

    asked: dict[str, tuple[str, ...]] = {}

    def fake_version(executable: str, *args: str, timeout: int = 30) -> str:
        asked[executable] = args
        return "0.5.0-beta.16"

    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(doctor, "_version", fake_version)
    mcp = doctor._modeling_mcp()
    assert asked["/bin/powerbi-modeling-mcp"] == ("--version",)
    assert mcp["version"] == "0.5.0-beta.16"
    assert mcp["status"] == "present"


def test_version_probe_never_inherits_stdin(monkeypatch) -> None:
    """A stdio MCP server that ignores ``--version`` must see EOF and exit,
    never block doctor on the caller's terminal."""
    import subprocess

    from vqs import doctor

    seen: list[object] = []

    def fake_run(*args, **kwargs):
        seen.append(kwargs.get("stdin", "inherited"))
        return subprocess.CompletedProcess(args, 0, "1.0.0\n", "")

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)
    assert doctor._version("tool", "--version") == "1.0.0"
    assert seen == [subprocess.DEVNULL]


def test_doctor_command_exits_zero(capsys) -> None:
    assert vqs_main(["doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] in ("ok", "needs_setup")
