"""Production scope must refuse native-only validation before writing."""
from __future__ import annotations

from test_r6_e07_authoring import _project

from vqs.pipeline import repair_candidate
from vqs.powerbi.author.policy import authorize


def test_strict_policy_blocks_direct_and_blanket_waivers(tmp_path):
    native = {"status": "pass", "validation_provider": "direct",
              "assurance": "native_static_only"}
    ms = {"status": "pass", "validation_provider": "microsoft",
          "assurance": "microsoft_structural_only"}
    assert authorize("production", native)["status"] == "blocked"
    assert authorize("production", ms)["status"] == "pass"
    assert authorize("production", ms, allow_warnings=True)["status"] == "blocked"
    proj, original = _project(tmp_path)
    candidate = proj / "no-candidate"
    runs = tmp_path / "no-runs"
    outcome = repair_candidate(str(proj / "plan.json"), str(original),
        str(candidate), run_root=str(runs), authoring_backend="direct",
        authoring_assurance="production")
    assert outcome["verdict"] == "blocked"
    assert not candidate.exists() and not runs.exists()
