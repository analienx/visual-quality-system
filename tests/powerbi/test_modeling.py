"""Modeling-port tests: stdio client against the fake MCP server.

Hermetic: the client spawns tests/helpers/fake_modeling_mcp.py with a
scripted JSON conversation. No live model, no Desktop, no network.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

from vqs.powerbi.modeling import (
    ModelingError,
    ModelingScope,
    StdioModelingClient,
    compare_scope,
    scope_from_dict,
)

FAKE = Path(__file__).resolve().parent.parent / "helpers" / "fake_modeling_mcp.py"

ONE_INSTANCE = [{"server": "localhost:52383", "database": "AdventureWorks"}]


def _script(tmp_path: Path, responses: dict, **extra) -> Path:
    script = tmp_path / "script.json"
    script.write_text(json.dumps({"responses": responses, **extra}),
                      encoding="utf-8")
    return script


def _client(tmp_path: Path, responses: dict, **extra) -> StdioModelingClient:
    script = _script(tmp_path, responses, **extra)
    log = tmp_path / "requests.log"
    client = StdioModelingClient(
        command=[sys.executable, str(FAKE), str(script), str(log)])
    client._vqs_log = log  # test-only handle, never read by vqs/*
    return client


def _logged(client: StdioModelingClient) -> list[dict]:
    log = client._vqs_log
    if not log.exists():
        return []
    return [json.loads(line) for line in
            log.read_text(encoding="utf-8").splitlines() if line.strip()]


def _connected(responses: dict | None = None) -> dict:
    scripted = {"connection_operations/ListLocalInstances": ONE_INSTANCE,
                "connection_operations/Connect": {"connection": "ok"}}
    scripted.update(responses or {})
    return scripted


def test_connect_binds_single_instance(tmp_path: Path) -> None:
    client = _client(tmp_path, _connected())
    try:
        bound = client.connect()
    finally:
        client.close()
    assert bound["model"] == "localhost:52383/AdventureWorks"
    assert bound["server"] == "localhost:52383"
    assert bound["database"] == "AdventureWorks"


def test_connect_accepts_instances_object_form(tmp_path: Path) -> None:
    scripted = _connected({"connection_operations/ListLocalInstances":
                           {"instances": ONE_INSTANCE}})
    client = _client(tmp_path, scripted)
    try:
        bound = client.connect()
    finally:
        client.close()
    assert bound["model"] == "localhost:52383/AdventureWorks"


def test_connect_refuses_zero_or_several(tmp_path: Path) -> None:
    client = _client(tmp_path, _connected(
        {"connection_operations/ListLocalInstances": []}))
    try:
        with pytest.raises(ModelingError, match="no local"):
            client.connect()
    finally:
        client.close()
    two = _connected({"connection_operations/ListLocalInstances":
                      ONE_INSTANCE + [{"server": "x", "database": "y"}]})
    client = _client(tmp_path, two)
    try:
        with pytest.raises(ModelingError, match="several local"):
            client.connect()
    finally:
        client.close()


def test_connect_refuses_missing_identity_and_failed_connect(
        tmp_path: Path) -> None:
    client = _client(tmp_path, _connected(
        {"connection_operations/ListLocalInstances": [{"server": "s"}]}))
    try:
        with pytest.raises(ModelingError, match="lacks server/database"):
            client.connect()
    finally:
        client.close()
    client = _client(tmp_path, _connected(
        {"connection_operations/Connect": {"isError": True}}))
    try:
        with pytest.raises(ModelingError, match="Connect failed"):
            client.connect()
    finally:
        client.close()


def test_readiness_proves_populated_and_repeatable(tmp_path: Path) -> None:
    rows = [{"ok": 1}]
    client = _client(tmp_path, _connected({
        "model_operations/GetStats": {"tables": 3},
        "dax_query_operations/Execute": {"rows": rows}}))
    try:
        scope = ModelingScope(source_sha256="abc")
        ready = client.readiness(scope)
    finally:
        client.close()
    assert ready["populated"] is True
    assert ready["rowcount"] == 1
    assert ready["query_hash"] == hashlib.sha256(
        json.dumps(rows, sort_keys=True, ensure_ascii=False,
                   default=str).encode("utf-8")).hexdigest()
    assert ready["scope_echo"]["model"] == "localhost:52383/AdventureWorks"
    assert ready["scope_echo"]["source_sha256"] == "abc"
    calls = [entry for entry in _logged(client)
             if entry["request"].get("operation") == "Execute"]
    assert len(calls) == 2  # the repeat-query contract: probed twice


def test_readiness_blocks_on_empty_or_unstable(tmp_path: Path) -> None:
    client = _client(tmp_path, _connected({
        "model_operations/GetStats": {"tables": 0},
        "dax_query_operations/Execute": {"rows": [{"ok": 1}]}}))
    try:
        ready = client.readiness(ModelingScope())
    finally:
        client.close()
    assert ready["populated"] is False
    assert "no tables" in ready["detail"]
    flapping = _connected({
        "model_operations/GetStats": {"tables": 2},
        "dax_query_operations/Execute": {
            "__sequence__": [{"rows": [{"ok": 1}]}, {"rows": [{"ok": 2}]}]}})
    client = _client(tmp_path, flapping)
    try:
        ready = client.readiness(ModelingScope())
    finally:
        client.close()
    assert ready["populated"] is False
    assert "unstable" in ready["detail"]


def test_readiness_countrows_first_named_table(tmp_path: Path) -> None:
    client = _client(tmp_path, _connected({
        "model_operations/GetStats": {"tables": ["Sales", "Costs"]},
        "dax_query_operations/Execute": {"rows": [{"n": 42}]}}))
    try:
        ready = client.readiness(ModelingScope())
    finally:
        client.close()
    assert ready["populated"] is True
    assert ready["probe_table"] == "Sales"
    assert ready["data_rows"] == 42
    queries = [entry["request"]["query"] for entry in _logged(client)
               if entry["request"].get("operation") == "Execute"]
    assert queries == ["EVALUATE ROW(\"n\", COUNTROWS('Sales'))"] * 2


def test_readiness_countrows_zero_or_nonnumeric_blocks(
        tmp_path: Path) -> None:
    stats = {"model_operations/GetStats": {"tables": ["Sales"]}}
    client = _client(tmp_path, _connected({
        **stats, "dax_query_operations/Execute": {"rows": [{"n": 0}]}}))
    try:
        ready = client.readiness(ModelingScope())
    finally:
        client.close()
    assert ready["populated"] is False
    assert "has no rows" in ready["detail"]
    client = _client(tmp_path, _connected({
        **stats, "dax_query_operations/Execute": {"rows": [{"n": "many"}]}}))
    try:
        ready = client.readiness(ModelingScope())
    finally:
        client.close()
    assert ready["populated"] is False
    assert "no number" in ready["detail"]


def test_readiness_accepts_stats_shapes_honestly(tmp_path: Path) -> None:
    listed = _connected({
        "model_operations/GetStats": {"tables": [{"name": "T"}]},
        "dax_query_operations/Execute": {"rows": [{"n": 7}]}})
    client = _client(tmp_path, listed)
    try:
        ready = client.readiness(ModelingScope())
    finally:
        client.close()
    assert ready["populated"] is True
    assert ready["probe_table"] == "T"
    declared = _connected({
        "model_operations/GetStats": {"tables": 2, "tableNames": ["A"]},
        "dax_query_operations/Execute": {"rows": [{"n": 1}]}})
    client = _client(tmp_path, declared)
    try:
        ready = client.readiness(ModelingScope())
    finally:
        client.close()
    assert ready["probe_table"] == "A"
    for raw, shape in ((True, "bool"), ("x", "str"), (None, "NoneType")):
        client = _client(tmp_path, _connected({
            "model_operations/GetStats": {"tables": raw},
            "dax_query_operations/Execute": {"rows": [{"ok": 1}]}}))
        try:
            ready = client.readiness(ModelingScope())
        finally:
            client.close()
        assert ready["populated"] is False
        assert ready["tables_shape"] == shape


def test_query_scoped_rejects_non_json_answer(tmp_path: Path) -> None:
    client = _client(tmp_path, _connected(
        {"dax_query_operations/Execute": {"__text__": "GARBAGE"}}))
    try:
        with pytest.raises(ModelingError, match="non-JSON"):
            client.query_scoped("EVALUATE T", ModelingScope())
    finally:
        client.close()


def test_query_scoped_echoes_bound_context(tmp_path: Path) -> None:
    rows = [{"city": "Paris"}, {"city": "Lima"}]
    client = _client(tmp_path, _connected({
        "dax_query_operations/Execute": {"rows": rows}}))
    try:
        scope = ModelingScope(roles=("Sales",), period="2024",
                              filters={"region": "EU"})
        answer = client.query_scoped("EVALUATE Cities", scope, max_rows=50)
    finally:
        client.close()
    assert answer["rows"] == rows
    assert answer["rowcount"] == 2
    assert answer["context"]["model"] == "localhost:52383/AdventureWorks"
    assert answer["context"]["roles"] == ["Sales"]
    assert answer["context"]["period"] == "2024"
    assert answer["context"]["query_sha256"] == hashlib.sha256(
        b"EVALUATE Cities").hexdigest()
    logged = [entry for entry in _logged(client)
              if entry["request"].get("operation") == "Execute"]
    assert logged[0]["request"]["impersonation"] == {"roles": ["Sales"]}
    assert logged[0]["request"]["maxRows"] == 50
    with pytest.raises(ModelingError, match="nonempty string"):
        client.query_scoped("  ", scope)


def test_server_error_nonjson_and_timeout_become_modeling_error(
        tmp_path: Path) -> None:
    client = _client(tmp_path, _connected(
        {"model_operations/GetStats": {"__error__": {"code": -1,
                                                    "message": "boom"}}}))
    try:
        with pytest.raises(ModelingError, match="boom"):
            client.readiness(ModelingScope())
    finally:
        client.close()
    client = _client(tmp_path, _connected(
        {"model_operations/GetStats": {"__raw__": "NOT JSON AT ALL"}}))
    try:
        with pytest.raises(ModelingError, match="not JSON"):
            client.readiness(ModelingScope())
    finally:
        client.close()
    slow = _script(tmp_path, _connected({
        "model_operations/GetStats": {"tables": 1},
        "dax_query_operations/Execute": {"rows": [{"ok": 1}]}}), sleep=30)
    client = StdioModelingClient(
        command=[sys.executable, str(FAKE), str(slow)], timeout=1)
    try:
        with pytest.raises(ModelingError, match="timed out or closed"):
            client.readiness(ModelingScope())
    finally:
        client.close()


def test_missing_launcher_blocks_without_spawn(tmp_path: Path) -> None:
    client = StdioModelingClient(command=["vqs-no-such-launcher-xyz"])
    try:
        with pytest.raises(ModelingError, match="not on PATH"):
            client.connect()
    finally:
        client.close()  # safe with no process


def test_close_is_idempotent_and_client_recovers(tmp_path: Path) -> None:
    client = _client(tmp_path, _connected({
        "model_operations/GetStats": {"tables": 1},
        "dax_query_operations/Execute": {"rows": [{"ok": 1}]}}))
    try:
        assert client.readiness(ModelingScope())["populated"] is True
        client.close()
        client.close()
        assert client.readiness(ModelingScope())["populated"] is True
    finally:
        client.close()


def test_scope_helpers_tolerate_malformed_input() -> None:
    assert scope_from_dict(None) == ModelingScope()
    assert scope_from_dict({"roles": "Solo"}) == ModelingScope(roles=("Solo",))
    assert scope_from_dict({"roles": 7}).roles == ()
    assert scope_from_dict({"model": 7}).model is None
    expected = ModelingScope(model="m", roles=("r",), period="p",
                             filters={"a": 1})
    assert compare_scope(expected, {"model": "m", "roles": ["r"],
                                   "period": "p",
                                   "filters": {"a": 1}}) == []
    assert compare_scope(expected, {"model": "other", "roles": ["r"],
                                   "period": "p",
                                   "filters": {"a": 1}}) == ["model"]
    assert compare_scope(expected, {"model": "m", "roles": ["x"],
                                   "period": "q",
                                   "filters": {}}) == ["roles", "filters",
                                                       "period"]
    assert compare_scope(ModelingScope(), {"model": "anything"}) == []
