"""F06 RED: engine responsiveness is not populated model data.

When GetStats reports only a table count (no names), readiness probes
a constant query and returns populated=True. Empty/unloaded data can
then enter a ready capture manifest. Count-only metadata plus
constants must remain data-unknown/blocked through the real
readiness/capture entry points; only source-bound positive population
evidence passes.

M2 flip: test_readiness_proves_populated_and_repeatable encodes the
defect (count-only expects populated); the flapping case in
test_readiness_blocks_on_empty_or_unstable must move to a named-table
fixture to keep its unstable-control.
"""
import json
import sys
from pathlib import Path

from vqs.evidence import check_data_readiness
from vqs.powerbi.modeling import ModelingScope, StdioModelingClient

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


def test_f06_count_only_stats_stay_unpopulated(tmp_path: Path) -> None:
    """RED: count-only metadata + constant probe must not be populated."""
    client = _client(tmp_path, _connected({
        "model_operations/GetStats": {"tables": 3},
        "dax_query_operations/Execute": {"rows": [{"ok": 1}]}}))
    try:
        ready = client.readiness(ModelingScope(source_sha256="abc"))
    finally:
        client.close()
    assert ready["populated"] is False
    assert "detail" in ready or "detail" in ready


def test_f06_count_only_readiness_blocks_data_gate(tmp_path: Path) -> None:
    """RED: readiness output must fail the capture data-readiness check."""
    client = _client(tmp_path, _connected({
        "model_operations/GetStats": {"tables": 3},
        "dax_query_operations/Execute": {"rows": [{"ok": 1}]}}))
    try:
        ready = client.readiness(ModelingScope(source_sha256="abc"))
    finally:
        client.close()
    assert check_data_readiness(ready) != []
