"""R10 RED: seal binds the canonical actual input, not the summary.

seal_verdict accepts the actual input document plus applicable
identities, persists input.json as a tamper-checked artifact,
and binds its digest; changing any material input while holding
the summary constant changes the binding. Both red pre-R3
(seal_verdict takes no actual input), green after.
"""
import hashlib
import json
from pathlib import Path

from vqs.pipeline import seal_verdict
from vqs.run_store import verify_seal

SUMMARY = [{"check": "plan", "status": "pass", "detail": {}}]


def _seal(run_root: Path, run_id: str, actual: dict,
          identities: dict) -> dict:
    return seal_verdict(run_root, run_id, "vqs.validate-plan/1", "pass",
                        SUMMARY, inputs={"actual": actual,
                                         "identities": identities})


def test_actual_input_persisted_and_bound(tmp_path: Path) -> None:
    """RED R10: input.json persists and its digest binds the seal."""
    actual = {"operations": [{"op": "text.set", "value": "A"}]}
    identities = {"config": "c" * 64, "tool": "vqs.validate-plan/1"}
    result = _seal(tmp_path, "run-input-1", actual, identities)
    run_dir = Path(result["run_dir"])
    assert verify_seal(run_dir) == []
    stored = json.loads((run_dir / "input.json").read_text(encoding="utf-8"))
    assert stored["actual"] == actual
    assert stored["identities"] == identities
    want = hashlib.sha256(json.dumps(
        stored, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert result["manifest"]["bindings"]["input_sha256"] == want


def test_changed_input_changes_binding(tmp_path: Path) -> None:
    """RED R10: same summary, different actual input: different binding."""
    first = _seal(tmp_path, "run-input-a",
                  {"operations": [{"op": "text.set", "value": "A"}]},
                  {"config": "c" * 64})
    second = _seal(tmp_path, "run-input-b",
                   {"operations": [{"op": "text.set", "value": "B"}]},
                   {"config": "c" * 64})
    assert (first["manifest"]["bindings"]["input_sha256"]
            != second["manifest"]["bindings"]["input_sha256"])
