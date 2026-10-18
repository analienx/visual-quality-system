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


def _clean_str_list(value: object) -> list[str] | None:
    """A non-empty string inventory, or None when malformed."""
    if (not isinstance(value, list) or not value
            or any(not isinstance(entry, str) or not entry
                   for entry in value)):
        return None
    return list(value)


def _check_verified_transport(transport: dict[str, Any], bundle: dict[str, Any],
                              source: object, declared: object,
                              pages: list[Any], calibration: object,
                              shape_issues: list[dict[str, Any]],
                              findings: list[dict[str, Any]]) -> str | None:
    """Corroborate the form against verified transport authority.

    Returns the authority fixer id for reviewer separation, or None
    when the authority itself is malformed (lookalikes fail closed).
    """
    t_pages = _clean_str_list(transport.get("pages"))
    t_source = transport.get("source_sha256")
    t_fixer = transport.get("fixer_id")
    renders = transport.get("renders")
    t_calibration = transport.get("calibration")
    bundle_id = transport.get("bundle_sha256")
    if (t_pages is None or not _is_bound_image(t_source)
            or not isinstance(t_fixer, str) or not t_fixer.strip()
            or not isinstance(renders, dict)
            or not isinstance(t_calibration, dict)
            or not _is_bound_image(bundle_id)):
        findings.append({"rule": "transport_unverified", "verdict": "fail",
                         "reason": "Verified-transport authority is "
                                   "malformed; caller lookalikes are rejected"})
        return None
    clean_form = _clean_str_list(declared)
    if (t_source != source or not source or clean_form is None
            or sorted(t_pages) != sorted(clean_form)):
        findings.append({"rule": "source_pages_unbound", "verdict": "fail",
                         "reason": "Completed form diverges from the "
                                   "verified transport inventory"})
    if bundle.get("fixer_id", "") != t_fixer:
        findings.append({"rule": "fixer_unbound", "verdict": "fail",
                         "reason": "Form fixer differs from the verified "
                                   "transport fixer"})
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("id", "?")
        entry = renders.get(page.get("id"))
        if (not isinstance(entry, dict)
                or not _is_bound_image(entry.get("sha256"))
                or not _is_pixels(entry.get("pixels"))):
            findings.append({"rule": "transport_unverified", "verdict": "fail",
                             "page": page_id,
                             "reason": "Verified authority lacks a render "
                                       "binding for this page"})
            continue
        form_hash = page.get("image_sha256")
        if _is_bound_image(form_hash) and form_hash != entry["sha256"]:
            findings.append({"rule": "page_render_substituted", "verdict": "fail",
                             "page": page_id,
                             "reason": "Form render digest differs from the "
                                       "verified transport render"})
        form_pixels = page.get("pixels")
        if (_is_pixels(form_pixels)
                and list(form_pixels) != list(entry["pixels"])):
            findings.append({"rule": "render_pixels_mismatch", "verdict": "fail",
                             "page": page_id,
                             "reason": "Form render resolution differs from "
                                       "the verified transport render"})
    # Resolution-binding dims only: canvas/scale pin the capture the
    # form claims; viewport/method describe setup. A malformed form
    # calibration is already flagged by check_calibration above.
    if not shape_issues and isinstance(calibration, dict):
        for dim in ("canvas_width", "canvas_height", "scale"):
            if calibration.get(dim) != t_calibration.get(dim):
                findings.append({"rule": "calibration_unbound",
                                 "verdict": "fail",
                                 "reason": "Form capture calibration differs "
                                           "from the verified transport"})
                break
    return t_fixer


def _check_live_inventory(transport: dict[str, Any], source: object,
                          declared: object,
                          findings: list[dict[str, Any]]) -> None:
    """Completeness-only corroboration against a live report inventory."""
    t_pages = _clean_str_list(transport.get("pages"))
    t_source = transport.get("source_sha256")
    if t_pages is None or not _is_bound_image(t_source):
        findings.append({"rule": "transport_unverified", "verdict": "fail",
                         "reason": "Live-report authority is malformed"})
        return
    clean_form = _clean_str_list(declared)
    if (t_source != source or not source or clean_form is None
            or sorted(t_pages) != sorted(clean_form)):
        findings.append({"rule": "source_pages_unbound", "verdict": "fail",
                         "reason": "Completed form diverges from the live "
                                   "report inventory"})


def adjudicate_bundle(bundle: dict[str, Any],
                      transport: dict[str, Any] | None = None
                      ) -> dict[str, Any]:
    """Adjudicate a review bundle; static checks never approve a release.

    R12: a bundle declaring whole-source coverage (``source_pages``)
    always blocks for capable image review even when statically
    conformant (``static_conformance`` labels the static half); pages
    need materialized image bindings, duplicated or uncovered pages
    block. S10: the inventory itself is required — an omitted or null
    ``source_pages`` blocks as ``source_pages_missing``. Static
    adjudication never passes; there is no metadata-only pass route.
    T09: with ``transport`` (verified bundle header pages + source),
    the form's ``source_pages`` must match the authoritative
    inventory exactly — a caller-edited list fails as
    ``source_pages_unbound`` instead of certifying completeness.
    R6-DEC-05: without a verified transport or live report
    inventory, whole-source coverage is unbound (blocked) — the
    form's own list can never certify its own completeness, and
    static conformance cannot imply a whole-source pass. R6-DEC-06:
    a verified transport is the full authority object returned by
    :func:`vqs.review.bundle.verify` (per-page render digests +
    pixels, calibration, fixer, bundle identity); thin lookalike
    dicts fail as ``transport_unverified``. Each form render digest,
    resolution, calibration, and fixer is corroborated against the
    verified material, and reviewer separation is checked against
    the authority fixer. A live report inventory binds completeness
    only, not fixer/reviewer identity: without a verified
    transport, separation is checked against the form-declared
    fixer. Direct API callers must obtain the
    authority from :func:`vqs.review.bundle.verify` (or a live
    report read for inventory-only binding); the verified path is
    in-process verify -> CLI -> adjudicate.
    """
    findings: list[dict[str, Any]] = []
    if not isinstance(bundle, dict):
        return {"verdict": "blocked", "findings": [{"rule": "bundle_not_an_object"}]}
    source = bundle.get("source_sha256", "")
    surface = bundle.get("surface", "")
    findings.extend(check_policy_binding(
        bundle, surface if isinstance(surface, str) else "", source))
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
    if declared is None:
        findings.append({"rule": "source_pages_missing", "verdict": "blocked",
                         "reason": "Whole-source inventory is required; static "
                                   "adjudication never passes without it"})
    else:
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
    # R6-DEC-05/06: completeness needs verified authority; reviewer
    # separation binds the authority fixer when one is established.
    authority_fixer: str | None = None
    if transport is None:
        findings.append({"rule": "source_pages_unbound", "verdict": "blocked",
                         "reason": "No verified transport or live report "
                                   "inventory; whole-source coverage cannot "
                                   "be proven"})
    else:
        marker = (transport.get("authority")
                  if isinstance(transport, dict) else None)
        if marker == "vqs.bundle.verify/1" and isinstance(transport, dict):
            authority_fixer = _check_verified_transport(
                transport, bundle, source, declared, pages, calibration,
                shape_issues, findings)
        elif marker == "live-report/1" and isinstance(transport, dict):
            _check_live_inventory(transport, source, declared, findings)
        else:
            findings.append({"rule": "transport_unverified", "verdict": "fail",
                             "reason": "Transport is not a verified "
                                       "authority object; caller lookalikes "
                                       "are rejected"})
    if authority_fixer is None:
        authority_fixer = bundle.get("fixer_id", "")
    findings.extend(check_reviewer(bundle.get("reviewer", {}),
                                   authority_fixer))
    static_ok = not any(row.get("verdict") in ("fail", "blocked") for row in findings)
    findings.append({"rule": "image_review_required", "verdict": "blocked",
                     "reason": "Static conformance never approves; release needs "
                               "a capable image review of fresh full-canvas renders"})
    if any(row.get("verdict") == "fail" for row in findings):
        return {"verdict": "fail", "findings": findings,
                "static_conformance": "pass" if static_ok else "fail"}
    return {"verdict": "blocked", "findings": findings,
            "static_conformance": "pass" if static_ok else "fail"}
