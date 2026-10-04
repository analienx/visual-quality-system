"""F08 RED: answer collection must speak the typed ModelingScope contract.

collect_answers currently passes raw dict scopes to a client whose
protocol requires ModelingScope, so real scoped queries collapse to
blocked with AttributeError. Production entry: collect_answers with a
live StdioModelingClient against the scripted fixture.
"""
import json
import sys
from pathlib import Path

from vqs.powerbi.modeling import StdioModelingClient
from vqs.repair.answers import collect_answers

FAKE = (Path(__file__).resolve().parent / "helpers"
        / "fake_modeling_mcp.py")
ONE_INSTANCE = [{"server": "localhost:52383",
                 "database": "AdventureWorks"}]
ROWS = [{"Revenue": 1200}, {"Revenue": 875}]


def _client(tmp_path: Path) -> StdioModelingClient:
    script = tmp_path / "script.json"
    script.write_text(json.dumps({"responses": {
        "connection_operations/ListLocalInstances": ONE_INSTANCE,
        "connection_operations/Connect": {"connection": "ok"},
        "dax_query_operations/Execute": {"rows": ROWS}}}),
        encoding="utf-8")
    log = tmp_path / "requests.log"
    return StdioModelingClient(
        command=[sys.executable, str(FAKE), str(script), str(log)])


def test_f08_collect_answers_uses_typed_scope(tmp_path: Path) -> None:
    client = _client(tmp_path)
    try:
        answers = collect_answers(client, [{
            "id": "q1", "dax": "EVALUATE ROW(\"n\", 1)",
            "scope": {"model": "localhost:52383/AdventureWorks"}}])
    finally:
        client.close()
    assert answers["q1"]["verdict"] == "observed"
    assert answers["q1"]["rows"] == ROWS
    context = answers["q1"]["context"]
    assert context["model"] == "localhost:52383/AdventureWorks"
