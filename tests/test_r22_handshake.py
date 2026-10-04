"""R22 RED: tool errors honored, versions/capabilities negotiated.

An isError tool result with plausible rows must raise, never
become observed evidence; unknown-major protocol versions and
mal-typed capabilities must refuse; the initialized
notification is part of the faithful lifecycle. All red pre-R3.
"""
import json
import sys
from pathlib import Path

import pytest

from vqs.powerbi.modeling import ModelingError, ModelingScope

FAKE = (Path(__file__).resolve().parent / "helpers"
        / "fake_modeling_mcp.py")
ONE_INSTANCE = [{"server": "localhost:52383",
                 "database": "AdventureWorks"}]
ROWS = [{"Revenue": 1200}]


def _client(tmp_path: Path, responses: dict, name: str = "script.json",
            **extra):
    from vqs.powerbi.modeling import StdioModelingClient

    script = tmp_path / name
    script.write_text(json.dumps({"responses": responses, **extra}),
                      encoding="utf-8")
    log = tmp_path / f"{name}.log"
    client = StdioModelingClient(
        command=[sys.executable, str(FAKE), str(script), str(log)])
    client._vqs_log = log
    return client


def _connected(**extra: object) -> dict:
    return {"connection_operations/ListLocalInstances": ONE_INSTANCE,
            "connection_operations/Connect": {"connection": "ok"},
            "dax_query_operations/Execute": {"rows": ROWS}}


def test_is_error_rows_rejected(tmp_path: Path) -> None:
    """RED R22: isError=true with valid rows raises, never observes."""
    client = _client(tmp_path, _connected(
        **{"dax_query_operations/Execute":
           {"__isError__": {"rows": ROWS}}}))
    try:
        with pytest.raises(ModelingError, match="[Ii]sError|tool error"):
            client.query_scoped("EVALUATE ROW(\"n\", 1)",
                                ModelingScope(
                                    model="localhost:52383/AdventureWorks"))
    finally:
        client.close()


def test_unknown_major_version_rejected(tmp_path: Path) -> None:
    """RED R22: an unsupported negotiated version refuses to connect."""
    client = _client(tmp_path, _connected(), protocolVersion="1999-01-01")
    try:
        with pytest.raises(ModelingError, match="[Vv]ersion|protocol"):
            client.connect()
    finally:
        client.close()


def test_malformed_capabilities_rejected(tmp_path: Path) -> None:
    """RED R22: a wrong-typed tools capability refuses to connect."""
    client = _client(tmp_path, _connected(),
                     capabilities={"tools": "yes-please"})
    try:
        with pytest.raises(ModelingError, match="[Cc]apabilit"):
            client.connect()
    finally:
        client.close()


def test_initialized_notification_logged(tmp_path: Path) -> None:
    """Control: the faithful fixture tracks the initialized notification."""
    client = _client(tmp_path, _connected())
    try:
        client.connect()
    finally:
        client.close()
    kinds = [entry["request"].get("operation")
             for entry in (json.loads(line) for line in
                           client._vqs_log.read_text(
                               encoding="utf-8").splitlines()
                           if line.strip())]
    assert "initialize" in kinds
    assert "initialized" in kinds
    assert kinds.index("initialize") < kinds.index("initialized")
