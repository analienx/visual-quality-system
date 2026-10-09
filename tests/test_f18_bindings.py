"""F18 RED: verdict producers must populate seal bindings.

run_check/seal_verdict never supply bindings, so sealed check/plan/
adjudication outputs lack input/source/model/data, policy/profile, and
tool identities. M3 wires them through production entry points:
bindings carry at least input_sha256 (canonical input bytes),
policy_version, and tool. Changed input/policy must change sealed
outputs. Effective profile/state binding lands with F25 (M4).
"""
from pathlib import Path

from vqs.pipeline import run_check, seal_verdict
from vqs.policy import POLICY_VERSION


def test_f18_check_seals_input_policy_tool_bindings(tmp_path: Path) -> None:
    """RED: sealed check manifest must bind input, policy, and tool."""
    result = run_check({"rules": {}}, tmp_path / "runs", run_id="check-1")
    bindings = result["manifest"]["bindings"]
    assert bindings["input_sha256"]
    assert bindings["policy_version"] == POLICY_VERSION
    assert bindings["tool"] == "vqs.check/1"


def test_f18_changed_input_changes_sealed_bindings(tmp_path: Path) -> None:
    """RED: different facts must seal different input bindings."""
    first = run_check({"rules": {}}, tmp_path / "runs", run_id="check-1")
    second = run_check({"rules": {"r": {}}}, tmp_path / "runs", run_id="check-2")
    assert (first["manifest"]["bindings"]["input_sha256"]
            != second["manifest"]["bindings"]["input_sha256"])


def test_f18_adjudication_seals_tool_and_policy(tmp_path: Path) -> None:
    """RED: sealed adjudication manifest must bind tool and policy."""
    result = seal_verdict(tmp_path / "runs", "adj-1", "vqs.adjudicate-bundle/1",
                          "blocked", [{"check": "x", "status": "blocked"}])
    bindings = result["manifest"]["bindings"]
    assert bindings["tool"] == "vqs.adjudicate-bundle/1"
    assert bindings["policy_version"] == POLICY_VERSION
