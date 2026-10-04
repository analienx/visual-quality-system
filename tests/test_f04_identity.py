"""F04 RED: one source/model identity across apply/capture/verify.

apply_plan exposes only tree_digest content hashes (report-root
relative), while capture manifests bind pbir.source_digest (report +
referenced-model source). The two domains cannot compose: no field of
an applied result verifies a capture manifest through real consumers.

M2 fix shape: apply_plan additionally exposes the capture-domain
source_sha256 of the candidate, keeping before/after as the byte-exact
rollback digests; verify routes through the production verifier.
"""
import json
import shutil
from pathlib import Path

from vqs.pbir import source_digest
from vqs.repair.execute import apply_plan, tree_digest
from vqs.repair.regress import verify_renders

FIXTURES = (Path(__file__).resolve().parent / "fixtures"
            / "vqs_agent_first" / "repair")


def _load(scenario):
    root = FIXTURES / scenario
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    return root / "original.Report", plan


def _applied(tmp_path):
    fixture_report, plan = _load("scenario_tick")
    original = tmp_path / "original.Report"
    shutil.copytree(fixture_report, original)
    applied = apply_plan(plan, str(original), str(tmp_path / "cand"))
    assert applied["verdict"] == "applied"
    return applied


def test_f04_apply_exposes_capture_domain_source(tmp_path) -> None:
    """RED: applied result must carry the capture-domain source identity."""
    applied = _applied(tmp_path)
    candidate = Path(applied["candidate"])
    assert applied["source_sha256"] == source_digest(candidate)


def test_f04_rollback_digests_stay_byte_exact(tmp_path) -> None:
    """Byte-exact rollback digests keep their own names (passes now)."""
    applied = _applied(tmp_path)
    candidate = Path(applied["candidate"])
    assert applied["after"] == tree_digest(candidate)


def test_f04_apply_to_verify_composes(tmp_path) -> None:
    """RED: producer-to-consumer wiring apply -> manifest -> verify."""
    applied = _applied(tmp_path)
    candidate = Path(applied["candidate"])
    manifest = {"source_sha256": source_digest(candidate),
                "page_images": {"P1": "P1.png"}}
    # M2: the verify call gains the materialized renders dir; the
    # identity asserted here must be the one that verifies.
    verdict = verify_renders(["P1"], [manifest],
                             applied["source_sha256"])
    assert verdict["verdict"] in ("pass", "blocked")
    assert manifest["source_sha256"] == applied["source_sha256"]
