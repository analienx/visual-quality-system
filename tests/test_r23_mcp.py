"""R23 RED: MCP session lifecycle and argument validation.

tools/call and tools/list before initialize (or without the
initialized notification) are rejected with -32002 and create
no files; mismatched protocol versions are negotiated, not
ignored; array arguments are element-validated. The correct
initialize->initialized->tools flow keeps working throughout.
"""
import io
import json
from pathlib import Path

import pytest

from vqs.mcp.server import PROTOCOL_VERSION, handle_message, serve

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")


def _report(root: Path) -> str:
    report = root / "R.Report"
    page_dir = report / "definition" / "pages" / "P1"
    page_dir.mkdir(parents=True)
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1"]}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(
        json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}), encoding="utf-8")
    (report / "definition" / "report.json").write_text(json.dumps({
        "$schema": SCHEMA_REPORT, "layoutOptimization": "None",
        "themeCollection": {}}), encoding="utf-8")
    (page_dir / "page.json").write_text(json.dumps({
        "displayName": "P1", "width": 1280, "height": 720}),
        encoding="utf-8")
    return str(report)


def _run(lines: list[dict]) -> list[dict]:
    reader = io.StringIO("\n".join(json.dumps(line) for line in lines))
    writer = io.StringIO()
    assert serve(reader, writer) == 0
    return [json.loads(line) for line in
            writer.getvalue().splitlines() if line.strip()]


def _init(version: str = PROTOCOL_VERSION) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": version,
                       "capabilities": {},
                       "clientInfo": {"name": "r3-red", "version": "0"}}}


def _initialized() -> dict:
    return {"jsonrpc": "2.0", "method": "notifications/initialized"}


def test_pre_init_call_rejected_without_side_effects(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RED R23: a pre-init repair/review call does nothing on disk."""
    monkeypatch.chdir(tmp_path)
    report = _report(tmp_path)
    responses = _run([{
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": "vqs_review",
                   "arguments": {"report_dir": report}}}])
    assert len(responses) == 1
    assert responses[0].get("error", {}).get("code") == -32002
    assert not (tmp_path / ".vqs-runs").exists()


def test_pre_init_list_rejected() -> None:
    """RED R23: tools/list also waits for the initialized session."""
    responses = _run([{"jsonrpc": "2.0", "id": 2,
                       "method": "tools/list"}])
    assert responses[0].get("error", {}).get("code") == -32002


def test_version_mismatch_negotiated() -> None:
    """RED R23: an unsupported client protocol version is refused."""
    responses = _run([_init("1999-01-01")])
    assert "error" in responses[0]


def test_array_element_types_rejected(tmp_path: Path) -> None:
    """RED R23: wrong-typed array elements fail schema validation."""
    responses = _run([
        _init(), _initialized(),
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "vqs_verify",
                    "arguments": {"original": str(tmp_path),
                                  "candidate": str(tmp_path),
                                  "edits": "not-a-list",
                                  "approved_removals": [123]}}}])
    assert responses[-1].get("error", {}).get("code") == -32602


def test_lifecycle_flow_keeps_working(tmp_path: Path) -> None:
    """Control: initialize->initialized->list->call stays green."""
    responses = _run([
        _init(), _initialized(),
        {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "vqs_run_status",
                    "arguments": {"run_root": str(tmp_path),
                                  "run_id": "no-such-run"}}},
    ])
    assert responses[0]["result"]["protocolVersion"] == PROTOCOL_VERSION
    listed = responses[1]["result"]["tools"]
    assert {spec["name"] for spec in listed} == {
        "vqs_inspect", "vqs_review", "vqs_propose",
        "vqs_repair", "vqs_verify", "vqs_run_status", "vqs_run"}
    assert "error" not in responses[2]
    envelope = json.loads(responses[2]["result"]["content"][0]["text"])
    assert envelope["verdict"] == "blocked"
    assert envelope["tool"] == "vqs.run_status"


def test_handle_message_pure_without_session_state() -> None:
    """RED R23: session state rides the call, never a module global."""
    import vqs.mcp.server as server_module

    assert not any(name.lower().startswith(("session", "_session",
                                            "client", "_client"))
                   and not name.startswith("__")
                   for name in vars(server_module))
    response = handle_message({"jsonrpc": "2.0", "id": 9,
                               "method": "tools/call",
                               "params": {"name": "vqs_run_status",
                                          "arguments": {"run_root": "x",
                                                        "run_id": "y"}}})
    assert response.get("error", {}).get("code") == -32002
