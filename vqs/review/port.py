"""Structured reviewer provider boundary (P0-U6 items 24-26).

``request-review``/form/bundle stay as debugging/portable escape hatches.
The primary UX is a ReviewPort: it consumes an exact source-bound
bundle (verified renders, never bare pixels) and returns typed
observations. The coordinator calls the port when configured and seals
the reviewer evidence; fixer/reviewer separation is enforced
(reviewer id must differ from the fixer id). A missing reviewer
capability blocks visual acceptance; a port failure or malformed
observation blocks the handoff loudly. Tests use explicit fakes with
synthetic labels — never a faked vision result.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

REVIEWER_VERSION = "vqs.reviewer/1"
OBSERVATION_VERDICTS = ("pass", "fail", "blocked")


class ReviewError(OSError):
    """Reviewer refusal; the message names the exact contract breach."""


class ReviewPort:
    """Reviewer capability contract (duck-typed).

    ``reviewer_id`` is a non-empty reviewer identity string.
    ``review(bundle_dir)`` consumes a verified vqs review bundle
    directory and returns ``{"observations": [...]}`` where each
    observation is ``{"page_id": str, "check": str,
    "verdict": "pass" | "fail" | "blocked"}`` with optional
    JSON-native detail. Anything else raises ReviewError upstream —
    the port never returns free-form vision prose.
    """

    reviewer_id: str = ""

    def review(self, bundle_dir: str) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


def _dotted(path: str) -> Any:
    """Import ``module:attr`` or ``module.attr``; ReviewError on failure."""
    target = path.strip()
    module_name, _, attr = (target.rpartition(":") if ":" in target
                            else target.rpartition("."))
    if not module_name or not attr:
        raise ReviewError(f"reviewer must be an object or dotted path, "
                          f"got {path!r}")
    try:
        module = importlib.import_module(module_name)
    except (ImportError, ValueError) as exc:
        raise ReviewError(
            f"reviewer import failed for {path!r}: {exc}") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ReviewError(
            f"reviewer {path!r} has no attribute {attr!r}") from exc


def resolve_reviewer(spec: Any) -> tuple[Any | None, str | None]:
    """Resolve a reviewer spec to (port, reviewer_id); None stays None.

    Objects are duck-checked (callable ``review`` + non-empty
    ``reviewer_id``); strings resolve as dotted paths. Anything else
    raises ReviewError instead of degrading into manual review.
    """
    if spec is None:
        return None, None
    port = _dotted(spec) if isinstance(spec, str) else spec
    reviewer_id = getattr(port, "reviewer_id", None)
    review = getattr(port, "review", None)
    if (not isinstance(reviewer_id, str) or not reviewer_id.strip()
            or not callable(review)):
        raise ReviewError("reviewer must expose a non-empty reviewer_id "
                          "and a callable review(bundle_dir)")
    return port, reviewer_id


def _check_observations(payload: Any, pages: list[str]) -> list[dict]:
    """Validate typed observations; ReviewError on any contract breach."""
    if not isinstance(payload, dict):
        raise ReviewError("reviewer must return an observations object")
    observations = payload.get("observations")
    if not isinstance(observations, list):
        raise ReviewError("reviewer observations must be a list")
    seen: set[tuple[str, str]] = set()
    clean: list[dict] = []
    for position, item in enumerate(observations):
        where = f"observation {position}"
        if not isinstance(item, dict):
            raise ReviewError(f"{where} is not an object")
        page_id, check, verdict = (item.get("page_id"), item.get("check"),
                                   item.get("verdict"))
        if not isinstance(page_id, str) or page_id not in pages:
            raise ReviewError(f"{where} names an unknown page: "
                              f"{page_id!r}")
        if not isinstance(check, str) or not check.strip():
            raise ReviewError(f"{where} needs a non-empty check name")
        if verdict not in OBSERVATION_VERDICTS:
            raise ReviewError(f"{where} has an untyped verdict: "
                              f"{verdict!r}")
        key = (page_id, check)
        if key in seen:
            raise ReviewError(f"duplicate observation for {page_id}/{check}")
        seen.add(key)
        clean.append({"page_id": page_id, "check": check,
                      "verdict": verdict,
                      "detail": item.get("detail")})
    try:
        json.dumps(clean, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ReviewError(
            f"reviewer observations are not JSON-sealable: {exc}") from exc
    return clean


def review_bundle(*, bundle_dir: str, reviewer: Any, reviewer_id: str,
                  fixer_id: str) -> dict[str, Any]:
    """Run the reviewer over a verified bundle; return the sealed record.

    The bundle is re-verified first (tampered renders never reach the
    reviewer); the reviewer/fixer separation is enforced; observations
    are validated and bound to the verified render hashes. Raises
    ReviewError with a precise reason on any breach.
    """
    from .bundle import verify as verify_bundle

    if not isinstance(fixer_id, str) or not fixer_id.strip():
        raise ReviewError("review needs a non-empty fixer id")
    if reviewer_id == fixer_id:
        raise ReviewError("fixer/reviewer separation violated: reviewer "
                          f"{reviewer_id!r} is the fixer")
    try:
        authority = verify_bundle(bundle_dir)
    except (ValueError, OSError, TypeError) as exc:
        raise ReviewError(f"review bundle invalid: {exc}") from exc
    pages = authority.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ReviewError("verified bundle carries no pages")
    try:
        payload = reviewer.review(bundle_dir)
    except ReviewError:
        raise
    except Exception as exc:  # noqa: BLE001 - reviewer crash is a refusal
        raise ReviewError(f"reviewer failed: {type(exc).__name__}: "
                          f"{exc}") from exc
    observations = _check_observations(payload, [
        page for page in pages if isinstance(page, str)])
    tally = {verdict: sum(1 for item in observations
                          if item["verdict"] == verdict)
             for verdict in OBSERVATION_VERDICTS}
    visual = ("blocked" if tally["blocked"]
              else "fail" if tally["fail"] else "pass")
    verified = authority.get("renders")
    verified = verified if isinstance(verified, dict) else {}
    renders = {binding.get("image"): binding.get("sha256")
               for binding in verified.values()
               if isinstance(binding, dict)}
    return {"reviewer": reviewer_id, "fixer": fixer_id,
            "source_sha256": authority.get("source_sha256"),
            "bundle_sha256": authority.get("bundle_sha256"),
            "renders": renders, "pages": pages,
            "observations": observations, "tally": tally,
            "visual": visual, "version": REVIEWER_VERSION}
