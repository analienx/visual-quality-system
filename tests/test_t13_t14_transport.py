"""T13/T14: strict response frames and whole-trip deadlines.

Routes: StdioModelingClient against the scripted fake subprocess
(frame validity, kept notifications, stop-reading write deadline)
and vqs-mcp serve (typed initialize, no invalid-init effects).
"""
import io
import json
import sys
import threading
import time
from pathlib import Path

import pytest

from vqs.mcp.server import handle_message, serve
from vqs.powerbi.modeling import ModelingError, StdioModelingClient

FAKE = (Path(__file__).resolve().parent / "helpers" /
        "fake_modeling_mcp.py")
ONE_INSTANCE = [{"server": "localhost:52383",
                 "database": "AdventureWorks"}]


def _client(tmp_path: Path, responses: dict, name: str = "script.json",
            timeout: int = 60, **extra) -> StdioModelingClient:
    script = tmp_path / name
    script.write_text(json.dumps({"responses": responses, **extra}),
                      encoding="utf-8")
    log = tmp_path / f"{name}.log"
    client = StdioModelingClient(
        command=[sys.executable, str(FAKE), str(script), str(log)],
        timeout=timeout)
    client._vqs_log = log  # test-only handle, never read by vqs/*
    return client


def _connected(responses: dict | None = None) -> dict:
    scripted = {"connection_operations/ListLocalInstances": ONE_INSTANCE,
                "connection_operations/Connect": {"connection": "ok"}}
    scripted.update(responses or {})
    return scripted


MALFORMED = {
    "missing-version": '{"id": {RID}, "result": {"ok": true}}',
    "version-1.0": ('{"jsonrpc": "1.0", "id": {RID}, '
                    '"result": {"ok": true}}'),
    "request-shaped": ('{"jsonrpc": "2.0", "id": {RID}, '
                       '"method": "tools/call", "params": {}}'),
    "dual-result-error": ('{"jsonrpc": "2.0", "id": {RID}, '
                          '"result": {"ok": true}, '
                          '"error": {"code": -1}}'),
    "neither": '{"jsonrpc": "2.0", "id": {RID}}',
    "non-dict": '[{"jsonrpc": "2.0", "id": {RID}}]',
}


@pytest.mark.parametrize("raw", MALFORMED.values(), ids=list(MALFORMED))
def test_malformed_matching_frame_rejected(tmp_path: Path, raw: str) -> None:
    """T13: a matching id never validates a malformed response frame."""
    scripted = _connected({"connection_operations/ListLocalInstances":
                           {"__raw__": raw}})
    client = _client(tmp_path, scripted)
    try:
        with pytest.raises(ModelingError, match="malformed"):
            client.connect()
    finally:
        client.close()


def test_valid_notifications_kept_under_deadline(tmp_path: Path) -> None:
    """T13 positive: legal logging/progress frames precede the answer."""
    scripted = _connected()
    client = _client(
        tmp_path, scripted, notify_before={
            "connection_operations/ListLocalInstances": [
                '{"jsonrpc": "2.0", "method": "notifications/message", '
                '"params": {"level": "info"}}',
                '{"jsonrpc": "2.0", "method": "notifications/progress", '
                '"params": {"progressToken": 1}}']})
    try:
        bound = client.connect()
    finally:
        client.close()
    assert bound["model"] == "localhost:52383/AdventureWorks"


@pytest.mark.parametrize("client_info", [
    {"name": {"nested": True}, "version": "0"},
    {"name": "typed", "version": ["0"]},
    {"name": "  ", "version": "0"},
    "not-a-dict",
])
def test_untyped_client_info_rejected(client_info) -> None:
    """T13: initialize needs typed nonempty clientInfo name/version."""
    message = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2024-11-05",
                          "capabilities": {},
                          "clientInfo": client_info}}
    response = handle_message(message, {})
    assert response["error"]["code"] == -32602


def test_invalid_init_has_no_tool_effects(tmp_path: Path,
                                          monkeypatch) -> None:
    """T13 installed serve: invalid init buys no session and writes nothing."""
    monkeypatch.chdir(tmp_path)
    bad_init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05",
                           "capabilities": {},
                           "clientInfo": {"name": {"x": 1},
                                          "version": "0"}}}
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "connection_operations",
                       "arguments": {"request": {"operation": "List"}}}}
    reader = io.StringIO(json.dumps(bad_init) + "\n" +
                         json.dumps(call) + "\n")
    writer = io.StringIO()
    assert serve(reader, writer) == 0
    lines = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert [row.get("error", {}).get("code") for row in lines] == [
        -32602, -32002]
    assert list(tmp_path.iterdir()) == []


def test_write_deadline_when_server_stops_reading(tmp_path: Path) -> None:
    """T14: an over-pipe-capacity request fails finite with cleanup."""
    client = _client(tmp_path, _connected(), timeout=3,
                     stop_reading=True)
    baseline = len(threading.enumerate())
    started = time.monotonic()
    try:
        with pytest.raises(ModelingError, match="timed out"):
            client._call("dax_query_operations",
                         {"operation": "Execute",
                          "query": "X" * 2_000_000})
    finally:
        client.close()
    elapsed = time.monotonic() - started
    assert elapsed < 30
    assert client._process is None
    assert len(threading.enumerate()) == baseline
    logged = [json.loads(line) for line in
              client._vqs_log.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    assert [entry["tool"] for entry in logged] == [
        "handshake/initialize"]
