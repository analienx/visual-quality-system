"""F25 RED: named states and effective config are review identity.

review_report accepts any configured supported state but never resolves
it, and seals only source/model/facts hashes. A configured nondefault
state can run default facts, and effective profile/recipe/state changes
are absent from invalidation. M4: apply supported state semantics or
explicitly block nondefault state; bind canonical effective
config/profile/policy and invalidate affected dependencies. Never
report a named-state review from default facts.
"""
import json
from pathlib import Path

from vqs.config import default_config
from vqs.pipeline import review_report


def test_f25_nondefault_state_blocks(tmp_path: Path) -> None:
    """RED: a configured nondefault state must not run default facts."""
    config = default_config()
    config["supported_states"] = ["default", "filtered"]
    result = review_report(facts={"rules": {}}, state="filtered",
                           config=config, run_root=str(tmp_path / "runs"))
    assert result["verdict"] == "blocked"
    assert "state" in " ".join(result["blocked_reasons"]).lower()


def test_f25_sealed_review_binds_effective_config(tmp_path: Path) -> None:
    """RED: the sealed manifest must bind the canonical effective config."""
    result = review_report(facts={"rules": {}}, config=default_config(),
                           run_root=str(tmp_path / "runs"),
                           run_id="review-1")
    manifest = json.loads((Path(result["run_dir"]) / "manifest.json")
                         .read_text(encoding="utf-8"))
    assert manifest["bindings"]["config_sha256"]


def test_f25_changed_profile_invalidates_resume(tmp_path: Path) -> None:
    """RED: resume across a profile change must block, not re-seal."""
    run_root = str(tmp_path / "runs")
    first_config = default_config()
    first = review_report(facts={"rules": {}}, config=first_config,
                          run_root=run_root, run_id="run-1")
    assert first["run_id"] == "run-1"
    second_config = default_config()
    second_config["design_profile"] = {"text_contrast": "strict"}
    resumed = review_report(facts={"rules": {}}, config=second_config,
                            run_root=run_root, run_id="run-2",
                            resume_from="run-1")
    assert resumed["run_id"] is None
    assert ("config" in json.dumps(resumed).lower()
            or "profile" in json.dumps(resumed).lower())
    assert not (Path(run_root) / "run-2").exists()
