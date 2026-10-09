"""R21 RED: strict scope validation before any model observation.

Explicit malformed scope fields (roles/model/period/source) must
block before dispatch: collect_answers returns blocked questions
and the transport log shows zero DAX calls. scope_from_dict
raises on malformed presence. Duplicate question IDs are
rejected, never silently overwritten. All red pre-R3.
"""
import json
import sys
from pathlib import Path

import pytest

from vqs.powerbi.modeling import ModelingError, scope_from_dict
from vqs.repair.answers import collect_answers

FAKE = (Path(__file__).resolve().parent / "helpers"
        / "fake_modeling_mcp.py")
ONE_INSTANCE = [{"server": "localhost:52383",
                 "database": "AdventureWorks"}]
ROWS = [{"Revenue": 1200}]


def _client(tmp_path: Path, responses: dict, **extra):
    from vqs.powerbi.modeling import StdioModelingClient

    script = tmp_path / "script.json"
    script.write_text(json.dumps({"responses": responses, **extra}),
                      encoding="utf-8")
    log = tmp_path / "requests.log"
    client = StdioModelingClient(
        command=[sys.executable, str(FAKE), str(script), str(log)])
    client._vqs_log = log
    return client


def _logged(client) -> list[dict]:
    log = client._vqs_log
    if not log.exists():
        return []
    return [json.loads(line) for line in
            log.read_text(encoding="utf-8").splitlines() if line.strip()]


def _connected(**extra: object) -> dict:
    return {"connection_operations/ListLocalInstances": ONE_INSTANCE,
            "connection_operations/Connect": {"connection": "ok"},
            "dax_query_operations/Execute": {"rows": ROWS}}


def test_malformed_roles_block_before_dax(tmp_path: Path) -> None:
    """RED R21: dict roles block with no DAX call on the wire."""
    client = _client(tmp_path, _connected())
    try:
        result = collect_answers(client, [{
            "id": "q1", "dax": "EVALUATE ROW(\"n\", 1)",
            "scope": {"model": "localhost:52383/AdventureWorks",
                      "roles": {"name": "RLS"}}}])
    finally:
        client.close()
    assert result["q1"]["verdict"] == "blocked"
    calls = [entry for entry in _logged(client)
             if entry["request"].get("operation") == "Execute"]
    assert calls == []


def test_malformed_model_and_period_block(tmp_path: Path) -> None:
    """RED R21: list model / numeric period block, never broaden."""
    with pytest.raises((ValueError, TypeError, ModelingError)):
        scope_from_dict({"model": []})
    with pytest.raises((ValueError, TypeError, ModelingError)):
        scope_from_dict({"period": 2024})
    with pytest.raises((ValueError, TypeError, ModelingError)):
        scope_from_dict({"roles": "admin"})
    with pytest.raises((ValueError, TypeError, ModelingError)):
        scope_from_dict(["not", "a", "mapping"])


def test_duplicate_question_ids_rejected(tmp_path: Path) -> None:
    """RED R21: a repeated question id never overwrites silently."""
    client = _client(tmp_path, _connected())
    try:
        result = collect_answers(client, [
            {"id": "q1", "dax": "EVALUATE ROW(\"n\", 1)",
             "scope": {"model": "localhost:52383/AdventureWorks"}},
            {"id": "q1", "dax": "EVALUATE ROW(\"n\", 2)",
             "scope": {"model": "localhost:52383/AdventureWorks"}}])
    finally:
        client.close()
    assert "duplicate_question_id" in json.dumps(result)


def test_well_formed_scope_still_observes(tmp_path: Path) -> None:
    """Control: a valid explicit scope still collects answers."""
    client = _client(tmp_path, _connected())
    try:
        result = collect_answers(client, [{
            "id": "q1", "dax": "EVALUATE ROW(\"n\", 1)",
            "scope": {"model": "localhost:52383/AdventureWorks",
                      "roles": ["admin"]}}])
    finally:
        client.close()
    assert result["q1"]["verdict"] == "observed"
    assert result["q1"]["rows"] == ROWS


def test_unbindable_period_blocks_before_dax(tmp_path: Path) -> None:
    """Control: a well-formed but unbindable period blocks, no DAX."""
    client = _client(tmp_path, _connected())
    try:
        result = collect_answers(client, [{
            "id": "q1", "dax": "EVALUATE ROW(\"n\", 1)",
            "scope": {"model": "localhost:52383/AdventureWorks",
                      "period": "2024"}}])
    finally:
        client.close()
    assert result["q1"]["verdict"] == "blocked"
    calls = [entry for entry in _logged(client)
             if entry["request"].get("operation") == "Execute"]
    assert calls == []
