"""GOAL 17: installed CLI and MCP parity outside the checkout.

Installs the built package into an isolated target (--no-deps, so
the package itself installs offline; only build tooling may come from
the index), then drives the installed CLI entry point and the
installed MCP server from a foreign working directory. Also pins that
unavailable optional tools degrade honestly while offline review keeps
working.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
POWERBI_FIX = Path(__file__).parent / "powerbi" / "fixtures"
REPORT = str(POWERBI_FIX / "mini_report")


def _install(target: Path) -> None:
    command = [sys.executable, "-m", "pip", "install", "--quiet",
               "--target", str(target), "--no-deps", str(REPO)]
    subprocess.run(command, check=True, capture_output=True, text=True,
                   timeout=300)


def test_installed_cli_mcp_parity_outside_checkout(tmp_path: Path) -> None:
    target = tmp_path / "site"
    _install(target)
    work = tmp_path / "work"
    work.mkdir()
    env = {"PATH": "", "PYTHONPATH": str(target),
           "PYTHONIOENCODING": "utf-8"}
    import os
    full_env = dict(os.environ)
    full_env.update(env)

    cli = subprocess.run(
        [sys.executable, "-c",
         ("import json,sys; from vqs.cli import main; "
          "sys.exit(main(['review', sys.argv[1], '--run-root', sys.argv[2], "
          "'--run-id', 'pkg-cli']))"), REPORT, str(work / "runs")],
        capture_output=True, text=True, check=False, timeout=120, cwd=work,
        env=full_env)
    assert cli.returncode in (0, 1, 2), cli.stderr
    cli_envelope = json.loads(cli.stdout)

    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "vqs_review",
                          "arguments": {"report_dir": REPORT,
                                        "run_root": str(work / "runs"),
                                        "run_id": "pkg-mcp"}}}
    # R23 session: initialize + initialized notification precede tools.
    messages = [{"jsonrpc": "2.0", "id": 0, "method": "initialize",
                 "params": {"protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "pkg", "version": "0"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                request]
    mcp = subprocess.run(
        [sys.executable, "-m", "vqs.mcp"],
        input="".join(json.dumps(message) + "\n" for message in messages),
        capture_output=True, text=True, check=False, timeout=120, cwd=work,
        env=full_env)
    assert mcp.returncode == 0, mcp.stderr
    replies = [json.loads(line) for line in mcp.stdout.splitlines()
               if line.strip()]
    call = next(reply for reply in replies if reply.get("id") == 1)
    mcp_envelope = json.loads(
        call["result"]["content"][0]["text"])
    assert mcp_envelope["verdict"] == cli_envelope["verdict"]
    assert mcp_envelope["findings"] == cli_envelope["findings"]

    probe = subprocess.run(
        [sys.executable, "-c",
         ("import os; from importlib.metadata import distribution; "
          "import vqs; "
          "d = distribution('visual-quality-system'); "
          "print(sorted(f'{e.name}={e.value}' for e in d.entry_points)); "
          "print(os.path.realpath(vqs.__file__))")],
        capture_output=True, text=True, check=False, timeout=60, cwd=work,
        env=full_env)
    assert probe.returncode == 0, probe.stderr
    assert "vqs=vqs.cli:main" in probe.stdout
    assert "vqs-mcp=vqs.mcp.server:main" in probe.stdout
    import os
    assert os.path.realpath(str(target)) in probe.stdout


def test_offline_review_without_optional_tools(tmp_path: Path,
                                               monkeypatch) -> None:
    from vqs.doctor import report
    from vqs.pipeline import review_report

    monkeypatch.setenv("PATH", "")
    capabilities = report()
    assert capabilities["status"] == "ok"
    assert capabilities["checks"]["pbir"]["status"] == "missing"
    assert capabilities["checks"]["desktop_bridge"]["status"] == "missing"
    envelope = review_report(report_dir=REPORT,
                             run_root=str(tmp_path / "runs"),
                             run_id="offline1")
    assert envelope["verdict"] in ("pass", "fail")
    assert envelope["provenance"]["source_sha256"]
