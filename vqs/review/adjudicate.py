"""Review-bundle adjudication (WP-07 static half, issue #12).

Decides a structured review bundle without looking at pixels: reviewer
separation (CORE-06), image-capability presence (DES-10), capture calibration
(full-canvas at target scale), per-page source binding (stale images fail),
data readiness (unproven data blocks), and observation completeness (every
verdict carries its reason, located failures carry theirs). Reviewer and
observation checks reuse the canonical validators in :mod:`vqs.evidence` so
static adjudication cannot drift from interactive review verification.
Verdict aggregation never coerces ``unknown`` into ``pass``. Model
disagreement, hallucination detection, and perceptual judgment itself need a
capable image reviewer plus real renders — explicitly out of scope here.
"""
from __future__ import annotations

from typing import Any

from vqs.evidence import (
    check_calibration,
    check_data_readiness,
    check_observations,
    check_reviewer,
)


def adjudicate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Adjudicate a review bundle; empty findings means release-pass."""
    findings: list[dict[str, Any]] = []
    if not isinstance(bundle, dict):
        return {"verdict": "blocked", "findings": [{"rule": "bundle_not_an_object"}]}
    source = bundle.get("source_sha256", "")
    surface = bundle.get("surface", "")
    findings.extend(check_reviewer(bundle.get("reviewer", {}),
                                   bundle.get("fixer_id", "")))
    capability = bundle.get("image_capability", {})
    if not isinstance(capability, dict) or capability.get("available") is not True:
        findings.append({"rule": "missing_image_capability", "verdict": "blocked",
                         "reason": "A capable image reviewer is required; text-only cannot assess pixels"})
    calibration = bundle.get("calibration")
    shape_issues = check_calibration(calibration)
    findings.extend(shape_issues)
    findings.extend(check_data_readiness(bundle.get("data_readiness")))
    pages = bundle.get("pages")
    if not isinstance(pages, list) or not pages:
        findings.append({"rule": "no_pages_evidence", "verdict": "blocked"})
        pages = []
    for page in pages:
        if not isinstance(page, dict):
            findings.append({"rule": "page_not_an_object", "verdict": "blocked"})
            continue
        page_id = page.get("id", "?")
        if page.get("image_source_sha256", "") != source or not source:
            findings.append({"rule": "stale_image", "verdict": "fail", "page": page_id})
        if not shape_issues and page.get("pixels") is not None:
            for row in check_calibration(calibration, page.get("pixels")):
                findings.append({**row, "page": page_id})
        valid_ids = {"page"} | {v.get("id") for v in page.get("visual_inventory", [])
                                if isinstance(v, dict) and v.get("id")}
        findings.extend(check_observations(surface if isinstance(surface, str) else "",
                                           page.get("observations"), valid_ids,
                                           page_id))
    if not findings:
        return {"verdict": "pass", "findings": []}
    if any(row.get("verdict") == "fail" for row in findings):
        return {"verdict": "fail", "findings": findings}
    return {"verdict": "blocked", "findings": findings}
