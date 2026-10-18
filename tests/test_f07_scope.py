"""F07 RED: requested scope must not be mislabeled as observed scope.

The client applies roles but merely echoes filters/period, and retains
a requested model ID even when it differs from the connection. An
unfiltered answer can be labeled EU/2024 and compare equal to another
caller-labeled scope. M3 fix: bind observed model identity, actually
apply/verify each supported dimension, and block unsupported
dimensions at the affected gate.

M3 flip: test_query_scoped_echoes_bound_context encodes the defect
(filtered scope echoes period); it becomes a blocked-control.
"""
import json
import sys
from pathlib import Path

import pytest

from vqs.powerbi.modeling import (
    ModelingError,
    ModelingScope,
    StdioModelingClient,
)
from vqs.repair.answers import collect_answers

FAKE = Path(__file__).resolve().parent / "helpers" / "fake_modeling_mcp.py"

ONE_INSTANCE = [{"server": "localhost:52383", "database": "AdventureWorks"}]


def _client(tmp_path: Path, responses: dict, **extra) -> StdioModelingClient:
    script = tmp_path / "script.json"
    script.write_text(json.dumps({"responses": responses, **extra}),
                      encoding="utf-8")
    log = tmp_path / "requests.log"
    return StdioModelingClient(
        command=[sys.executable, str(FAKE), str(script), str(log)])


def _connected(responses: dict | None = None) -> dict:
    scripted = {"connection_operations/ListLocalInstances": ONE_INSTANCE,
                "connection_operations/Connect": {"connection": "ok"}}
    scripted.update(responses or {})
    return scripted


def _query_client(tmp_path: Path) -> StdioModelingClient:
    return _client(tmp_path, _connected({
        "dax_query_operations/Execute": {"rows": [{"n": 1}]}}))


def test_f07_filtered_query_blocks(tmp_path: Path) -> None:
    """RED: a filters-carrying scope must block, never echo unfiltered."""
    client = _query_client(tmp_path)
    try:
        with pytest.raises(ModelingError, match="filter|supported"):
            client.query_scoped(
                "EVALUATE Cities",
                ModelingScope(filters={"region": "EU"}))
    finally:
        client.close()


def test_f07_period_query_blocks(tmp_path: Path) -> None:
    """RED: a period-carrying scope must block, never echo unapplied."""
    client = _query_client(tmp_path)
    try:
        with pytest.raises(ModelingError, match="period|supported"):
            client.query_scoped(
                "EVALUATE Cities", ModelingScope(period="2024"))
    finally:
        client.close()


def test_f07_model_mismatch_blocks(tmp_path: Path) -> None:
    """RED: requested model differing from the connection must block."""
    client = _query_client(tmp_path)
    try:
        with pytest.raises(ModelingError, match="model"):
            client.query_scoped(
                "EVALUATE Cities", ModelingScope(model="other-db"))
    finally:
        client.close()


def test_f07_filtered_readiness_blocks(tmp_path: Path) -> None:
    """RED: readiness must not label an unfiltered probe as filtered."""
    client = _client(tmp_path, _connected({
        "model_operations/GetStats": {"tables": ["Sales"]},
        "dax_query_operations/Execute": {"rows": [{"n": 5}]}}))
    try:
        with pytest.raises(ModelingError, match="filter|supported"):
            client.readiness(ModelingScope(filters={"region": "EU"}))
    finally:
        client.close()


def test_f07_filtered_answer_collection_blocks(tmp_path: Path) -> None:
    """RED: filtered oracle questions block with an explicit reason."""
    client = _query_client(tmp_path)
    try:
        answers = collect_answers(client, [{
            "id": "q-eu", "dax": "EVALUATE Cities",
            "scope": {"filters": {"region": "EU"}}}])
    finally:
        client.close()
    assert answers["q-eu"]["verdict"] == "blocked"
    assert ("filter" in answers["q-eu"]["reason"].lower()
            or "supported" in answers["q-eu"]["reason"].lower())
