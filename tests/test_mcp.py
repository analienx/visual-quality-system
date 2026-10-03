"""MCP lane tests (WP-02): schemas, validation, stdio transport.

The server is transport-only: every tools/call result must equal the
shared engine's envelope for the same inputs. Blocked verdicts are
normal results, never transport errors; only malformed calls and
unknown methods produce JSON-RPC errors. There is no shell tool.
"""
import io
import json
from pathlib import Path

POWERBI_FIX = Path(__file__).parent / "powerbi" / "fixtures"
REPORT = str(POWERBI_FIX / "mini_report")

EXPECTED_TOOLS = {"vqs_inspect", "vqs_review", "vqs_propose", "vqs_repair",
                  "vqs_verify", "vqs_run_status"}


def _session(lines: list[str]) -> list[dict]:
    from vqs.mcp.server import serve

    reader = io.StringIO("".join(line + "\n" for line in lines))
    writer = io.StringIO()
    assert serve(reader, writer) == 0
    return [json.loads(line) for line in writer.getvalue().splitlines()
            if line.strip()]


def test_tools_list_is_exactly_the_six() -> None:
    responses = _session([json.dumps({"jsonrpc": "2.0", "id": 1,
                                      "method": "tools/list"})])
    assert len(responses) == 1
    names = {t["name"] for t in responses[0]["result"]["tools"]}
    assert names == EXPECTED_TOOLS
    assert not (names & {"shell", "exec", "run", "run_shell", "bash"})
    for tool in responses[0]["result"]["tools"]:
        assert tool["inputSchema"]["additionalProperties"] is False


def test_initialize_handshake() -> None:
    from vqs import __version__

    responses = _session([json.dumps({"jsonrpc": "2.0", "id": 1,
                                      "method": "initialize"})])
    result = responses[0]["result"]
    assert result["serverInfo"] == {"name": "vqs-mcp",
                                   "version": __version__}
    assert result["capabilities"] == {"tools": {}}


def test_call_validation_errors() -> None:
    from vqs.mcp.schemas import validate_call

    assert validate_call("nope", {})[1] is not None
    assert validate_call("vqs_inspect", [])[1] is not None
    assert validate_call("vqs_inspect", {})[1] is not None  # missing arg
    assert validate_call("vqs_inspect", {"report_dir": "r",
                                         "bogus": 1})[1] is not None
    assert validate_call("vqs_inspect", {"report_dir": 7})[1] is not None
    assert validate_call("vqs_review", {"scope": "nope"})[1] is not None
    spec, error = validate_call("vqs_inspect", {"report_dir": "r"})
    assert error is None and spec["tool"] == "vqs.inspect"


def test_transport_errors_and_notification_silence() -> None:
    responses = _session([
        "{oops",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "nope/method"}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "vqs_inspect", "arguments": {}}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
    ])
    assert [r.get("error", {}).get("code") for r in responses] == [
        -32700, -32601, -32602]
    assert len(responses) == 3  # the notification answered nothing


def test_inspect_call_matches_engine() -> None:
    from vqs.pipeline import inspect_report

    responses = _session([json.dumps(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
         "params": {"name": "vqs_inspect",
                    "arguments": {"report_dir": REPORT}}})])
    assert "error" not in responses[0]
    text = responses[0]["result"]["content"][0]["text"]
    assert json.loads(text) == inspect_report(REPORT)


def test_blocked_verdict_is_a_result_not_an_error(tmp_path: Path) -> None:
    responses = _session([json.dumps(
        {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
         "params": {"name": "vqs_run_status",
                    "arguments": {"run_root": str(tmp_path),
                                  "run_id": "nope"}}})])
    assert "error" not in responses[0]
    assert "isError" not in responses[0]["result"]
    envelope = json.loads(responses[0]["result"]["content"][0]["text"])
    assert envelope["verdict"] == "blocked"
    assert envelope["tool"] == "vqs.run_status"


def test_review_call_parity_with_cli(tmp_path: Path, capsys) -> None:
    from vqs.cli import main as vqs_main

    run_root = str(tmp_path / "runs")
    responses = _session([json.dumps(
        {"jsonrpc": "2.0", "id": 11, "method": "tools/call",
         "params": {"name": "vqs_review",
                    "arguments": {"report_dir": REPORT,
                                  "run_root": run_root,
                                  "run_id": "mcp1"}}})])
    mcp = json.loads(responses[0]["result"]["content"][0]["text"])
    code = vqs_main(["review", REPORT, "--run-root", run_root,
                     "--run-id", "cli1"])
    cli = json.loads(capsys.readouterr().out)
    assert mcp["verdict"] == cli["verdict"]
    assert mcp["findings"] == cli["findings"]
    assert mcp["coverage"] == cli["coverage"]
    assert code == {"pass": 0, "fail": 1, "blocked": 2}[cli["verdict"]]


def test_server_main_rejects_argv(capsys) -> None:
    from vqs.mcp.server import main

    assert main(["--shell"]) == 2
    assert "no arguments" in capsys.readouterr().err
