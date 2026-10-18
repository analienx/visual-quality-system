"""P15: re-execute report pixel QA and expose unresolved acceptance gates.

This is a read-only pre-acceptance assessment. An untrusted JSON observation,
AI self-review or mathematically matching trace is never an independent G2/G4
or suite G6 approval. The canonical release oracle remains vqs.acceptance.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vqs.pbir import source_digest
from vqs.powerbi.interaction_audit import assess_recorded_trace, inspect_deep_dive_contract
from vqs.visual.pixel_quality import audit_regions
from vqs.visual.regions import RegionError, _inventory

SCHEMA = "vqs.visual-assurance-readiness/1"


def assess_report_readiness(
        bundle_dir: str, regions_dir: str, *, report: str,
        pages: list[str] | None = None,
        policy: Mapping[str, Any] | None = None,
        oracle: Mapping[str, Any] | None = None,
        trace: Mapping[str, Any] | None = None,
        captures_dir: str | None = None) -> dict[str, Any]:
    """Audit all selected page visuals and compare any supplied runtime trace.

    Mandatory acceptance gates stay blocked absent real external evidence.
    This function never consumes or trusts a caller's claimed release verdict.
    """
    pixel = audit_regions(bundle_dir, regions_dir, report=report, policy=policy)
    inventory = _inventory(Path(bundle_dir).resolve())
    all_pages = inventory["pages"]
    known = {page["id"] for page in all_pages}
    if not isinstance(pages, (list, type(None))) or (pages is not None and (
            not pages or any(not isinstance(p, str) or not p for p in pages)
            or len(set(pages)) != len(pages) or not set(pages) <= known)):
        raise RegionError("assurance page scope must select actual unique PBIR pages")
    selected = known if pages is None else set(pages)
    expected = {(p["id"], v["visual_id"]) for p in all_pages if p["id"] in selected
                for v in p["visuals"]}
    captured = {(r["page_id"], r["visual_id"]) for r in pixel["regions"]}
    missing = sorted(expected - captured)
    outside = sorted(captured - expected)
    measured = [row for row in pixel["regions"] if row["page_id"] in selected]
    pixel_findings = [
        {"page_id": row["page_id"], "visual_id": row["visual_id"],
         "findings": row["findings"]}
        for row in measured if row["findings"]]
    statuses = {row["status"] for row in measured}
    scoped_status = ("fail" if "fail" in statuses
                     else "unknown" if "unknown" in statuses
                     else "review_required" if "review_required" in statuses
                     else "no_pixel_issue_proven")
    # Never claim a measured page when its screenshot bundle lacked a visual;
    # extra regions outside a deliberately limited page scope are not proof.
    pixel_status = ("fail" if scoped_status == "fail"
                    else "blocked" if missing
                    else "blocked" if scoped_status in ("unknown", "review_required")
                    else "measured_no_pixel_issue_proven")
    source = pixel["source_sha256"]
    runtime = {"evidence_consistency": "blocked", "interactive": "blocked",
               "reason": "no current-source Desktop click/observation trace"}
    if oracle is not None or trace is not None or captures_dir is not None:
        if oracle is None or trace is None or captures_dir is None:
            runtime["reason"] = "incomplete runtime oracle/trace/screenshot triad"
        elif (source_digest(report) != source
              or not isinstance(oracle, Mapping) or not isinstance(trace, Mapping)
              or trace.get("source_sha256") != source
              or oracle.get("source_sha256") != source):
            runtime = {"evidence_consistency": "fail", "interactive": "blocked",
                       "reason": "runtime record does not match verified report source"}
        else:
            structure = inspect_deep_dive_contract(report)
            if structure["structural"] != "pass":
                runtime = {"evidence_consistency": structure["structural"],
                           "interactive": "blocked", "reason": "PBIR interaction contract changed"}
            else:
                runtime = assess_recorded_trace(oracle, trace, captures_dir)
                runtime["pbir_contract"] = structure
    failures = []
    if scoped_status == "fail":
        failures.append("verified_rendered_pixel_defect")
    if runtime["evidence_consistency"] == "fail":
        failures.append("semantic_or_screenshot_interaction_mismatch")
    return {
        "schema": SCHEMA, "source_sha256": source,
        "bundle_sha256": pixel["bundle_sha256"],
        "scope": {"pages": sorted(selected), "full_report": selected == known,
                  "expected_visuals": len(expected),
                  "covered_visuals": len(expected & captured),
                  "missing_visuals": [{"page_id": p, "visual_id": v} for p, v in missing],
                  "out_of_scope_crops": len(outside)},
        "pixel": {"status": pixel_status, "measured": len(measured),
                  "source_bound_audit": scoped_status,
                  "policy_targets": pixel["policy_targets"],
                  "findings": pixel_findings},
        "runtime": runtime,
        "gates": {
            "G0_verified_source_and_images": "pass",
            "G2_independent_visual_design_review": "blocked",
            "G4_live_interaction_parity": "blocked",
            "G6_independent_multi_artifact_release": "blocked",
        },
        "verdict": "fail" if failures else "blocked",
        "failures": failures,
        "blocked_reasons": (["visual_inventory_uninspected"] if missing else []),
        "required_next_evidence": [
            "independent review of current whole-page Desktop screenshots",
            "trusted actual Desktop year-selection/map/region click witness",
            "two unrelated PBIPs and generated DOCX with independent G6 verifier and owner approval",
        ],
    }
