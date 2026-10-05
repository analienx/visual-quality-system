"""T15/D09: advertised flows work outside the checkout, installed.

Two canonical projects (mini + insight) copied out of the checkout
run through the installed CLI (inspect/measure/cycles) and through
installed `vqs-mcp serve` using the documented handshake shape.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

VQS_BIN = shutil.which("vqs")
MCP_BIN = shutil.which("vqs-mcp")
needs_cli = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs not on PATH")
needs_mcp = pytest.mark.skipif(MCP_BIN is None,
                               reason="installed vqs-mcp not on PATH")

FIXTURES = Path(__file__).resolve().parent / "powerbi" / "fixtures"
PROJECTS = [("mini_report", "mini_model"), ("insight_report", "mini_model")]
CYCLE_CASES = [("clean_model", 0), ("cycle_model", 1)]


def _stage(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    assert not str(target.resolve()).startswith(str(Path.cwd()))
    return target


@needs_cli
@pytest.mark.parametrize("report,model", PROJECTS)
def test_installed_inspect_measure_outside_checkout(
        tmp_path: Path, report: str, model: str) -> None:
    """D09: installed inspect/measure run on out-of-checkout projects."""
    staged_report = shutil.copytree(FIXTURES / report,
                                    _stage(tmp_path, report))
    staged_model = shutil.copytree(FIXTURES / model,
                                   _stage(tmp_path, model))
    completed = subprocess.run(
        [VQS_BIN, "inspect", str(staged_report), "--model",
         str(staged_model)], capture_output=True, text=True, timeout=120,
        check=False)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["source_sha256"]
    completed = subprocess.run(
        [VQS_BIN, "measure", str(staged_report), "--model",
         str(staged_model)], capture_output=True, text=True, timeout=120,
        check=False)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["rules"]


@needs_cli
@pytest.mark.parametrize("model,code", CYCLE_CASES)
def test_installed_cycles_outside_checkout(tmp_path: Path, model: str,
                                            code: int) -> None:
    """D09: installed cycles judges out-of-checkout models."""
    staged = shutil.copytree(FIXTURES / model, _stage(tmp_path, model))
    completed = subprocess.run([VQS_BIN, "cycles", str(staged)],
                               capture_output=True, text=True, timeout=120,
                               check=False)
    assert completed.returncode == code, completed.stderr
    assert "acyclic" in completed.stdout


@needs_mcp
def test_installed_mcp_documented_handshake_flow(tmp_path: Path) -> None:
    """D09/T15: the documented MCP handshake drives a real inspect call."""
    staged_report = shutil.copytree(FIXTURES / "mini_report",
                                    _stage(tmp_path, "mini_report"))
    staged_model = shutil.copytree(FIXTURES / "mini_model",
                                   _stage(tmp_path, "mini_model"))
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "example-client",
                                   "version": "1.0.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "vqs_inspect",
                    "arguments": {"report_dir": str(staged_report),
                                  "model_dir": str(staged_model)}}},
    ]
    completed = subprocess.run(
        [MCP_BIN], input="\n".join(json.dumps(line) for line in lines),
        capture_output=True, text=True, timeout=180, check=False)
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in
                 completed.stdout.splitlines() if line.strip()]
    by_id = {row.get("id"): row for row in responses}
    assert "error" not in by_id[1]
    assert "vqs_inspect" in json.dumps(by_id[2])
    assert "error" not in by_id[3]
    assert "source_sha256" in json.dumps(by_id[3])
