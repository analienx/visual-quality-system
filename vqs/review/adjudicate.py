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
    check_policy_binding,
    check_reviewer,
)


_HEX64 = frozenset("0123456789abcdefABCDEF")


def _is_bound_image(value: object) -> bool:
    """A materialized image binding: 64-hex digest, not a bare label."""
    return (isinstance(value, str) and len(value) == 64
            and all(char in _HEX64 for char in value))


def _is_pixels(value: object) -> bool:
    """A concrete [width, height] pair of positive ints."""
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(dim, int) and not isinstance(dim, bool) and dim > 0
                    for dim in value))


def adjudicate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Adjudicate a review bundle; static checks never approve a release.

    R12: a bundle declaring whole-source coverage (``source_pages``)
    always blocks for capable image review even when statically
    conformant (``static_conformance`` labels the static half); pages
    need materialized image bindings, duplicated or uncovered pages
    block. Bundles without ``source_pages`` keep legacy semantics.
    """
    findings: list[dict[str, Any]] = []
    if not isinstance(bundle, dict):
        return {"verdict": "blocked", "findings": [{"rule": "bundle_not_an_object"}]}
    source = bundle.get("source_sha256", "")
    surface = bundle.get("surface", "")
    findings.extend(check_policy_binding(
        bundle, surface if isinstance(surface, str) else "", source))
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
        if (not _is_bound_image(page.get("image_sha256"))
                or not _is_pixels(page.get("pixels"))):
            findings.append({"rule": "page_image_unbound", "verdict": "blocked",
                             "page": page_id})
        if not shape_issues and page.get("pixels") is not None:
            for row in check_calibration(calibration, page.get("pixels")):
                findings.append({**row, "page": page_id})
        inventory = page.get("visual_inventory", [])
        if not isinstance(inventory, list):
            inventory = []
        valid_ids = {"page"} | {v.get("id") for v in inventory
                                if isinstance(v, dict) and isinstance(v.get("id"), str) and v.get("id")}
        findings.extend(check_observations(surface if isinstance(surface, str) else "",
                                           page.get("observations"), valid_ids,
                                           page_id))
    declared = bundle.get("source_pages")
    if declared is not None:
        page_ids = [page.get("id") for page in pages
                    if isinstance(page, dict) and isinstance(page.get("id"), str)]
        if (not isinstance(declared, list) or not declared
                or any(not isinstance(entry, str) or not entry for entry in declared)):
            findings.append({"rule": "source_pages_invalid", "verdict": "blocked"})
        else:
            seen: set[str] = set()
            for pid in page_ids:
                if pid in seen:
                    findings.append({"rule": "duplicate_page_evidence", "verdict": "blocked",
                                     "page": pid})
                seen.add(pid)
            for entry in declared:
                if entry not in seen:
                    findings.append({"rule": "source_page_uncovered", "verdict": "blocked",
                                     "page": entry})
            for pid in page_ids:
                if pid not in declared:
                    findings.append({"rule": "source_page_undeclared", "verdict": "blocked",
                                     "page": pid})
        static_ok = not any(row.get("verdict") in ("fail", "blocked") for row in findings)
        findings.append({"rule": "image_review_required", "verdict": "blocked",
                         "reason": "Static conformance never approves; release needs "
                                   "a capable image review of fresh full-canvas renders"})
        if any(row.get("verdict") == "fail" for row in findings):
            return {"verdict": "fail", "findings": findings,
                    "static_conformance": "pass" if static_ok else "fail"}
        return {"verdict": "blocked", "findings": findings,
                "static_conformance": "pass" if static_ok else "fail"}
    if not findings:
        return {"verdict": "pass", "findings": []}
    if any(row.get("verdict") == "fail" for row in findings):
        return {"verdict": "fail", "findings": findings}
    return {"verdict": "blocked", "findings": findings}
