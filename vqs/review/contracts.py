"""Versioned, evidence-first specialist task and answer contracts.

LLM text is never source authority. All identifiers and hashes come from
the independently verified VQS bundle / derived-region manifests.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .port import ReviewError

TASK_SCHEMA = "vqs.specialist-task/1"
ANSWER_SCHEMA = "vqs.specialist-answer/1"
VERDICTS = frozenset({"pass", "fail", "blocked"})
SEVERITIES = frozenset({"none", "low", "medium", "high"})
CHECK_FIELDS = frozenset({
    "verdict", "observed_symptom", "observation", "visible_evidence",
    "location_hint", "severity_proposal", "repair_hypothesis", "cannot_establish",
})


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SpecialistTask:
    task_id: str
    source_sha256: str
    bundle_sha256: str
    page_id: str
    visual_id: str
    visual_type: str
    specialist: str
    checks: tuple[str, ...]
    prompt_version: str
    page_image_sha256: str
    crop_image_sha256: str

    @classmethod
    def from_verified(cls, *, authority: dict[str, Any], region: dict[str, Any],
                      specialist: str, checks: tuple[str, ...],
                      prompt_version: str) -> "SpecialistTask":
        page = region["page_id"]
        page_binding = authority["review_images"].get(page)
        if (authority.get("review_image_basis") != "verified_canvas"
                or not isinstance(page_binding, dict)
                or region.get("source_canvas_sha256") != page_binding.get("sha256")
                or not isinstance(region.get("crop_sha256"), str)
                or len(region["crop_sha256"]) != 64):
            raise ReviewError("specialist task lacks verified page/crop binding")
        if not checks or len(set(checks)) != len(checks):
            raise ReviewError("specialist contract has duplicate or missing checks")
        facts = {
            "schema": TASK_SCHEMA, "source_sha256": authority["source_sha256"],
            "bundle_sha256": authority["bundle_sha256"],
            "page_id": page, "visual_id": region["visual_id"],
            "visual_type": region["visual_type"], "specialist": specialist,
            "checks": list(checks), "prompt_version": prompt_version,
            "page_image_sha256": page_binding["sha256"],
            "crop_image_sha256": region["crop_sha256"],
        }
        if not all(isinstance(facts[k], str) and facts[k] for k in (
                "source_sha256", "bundle_sha256", "page_id", "visual_id",
                "visual_type", "specialist", "prompt_version")):
            raise ReviewError("specialist task has unsupported PBIR identity")
        return cls(task_id=_digest(facts), source_sha256=facts["source_sha256"],
                   bundle_sha256=facts["bundle_sha256"], page_id=page,
                   visual_id=region["visual_id"], visual_type=region["visual_type"],
                   specialist=specialist, checks=checks,
                   prompt_version=prompt_version,
                   page_image_sha256=facts["page_image_sha256"],
                   crop_image_sha256=facts["crop_image_sha256"])


def answer_schema(checks: tuple[str, ...]) -> dict[str, Any]:
    """Fixed named keys prevent duplicate/omitted array checks."""
    entry = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "verdict": {"type": "string", "enum": sorted(VERDICTS)},
            "observed_symptom": {"type": "boolean"},
            "observation": {"type": "string"},
            "visible_evidence": {"type": "string"},
            "location_hint": {"type": "string"},
            "severity_proposal": {"type": "string", "enum": sorted(SEVERITIES)},
            "repair_hypothesis": {"type": ["string", "null"]},
            "cannot_establish": {
                "type": "array", "items": {"type": "string"}, "maxItems": 6,
            },
        },
        "required": sorted(CHECK_FIELDS),
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {check: entry for check in checks},
        "required": list(checks),
    }


def validate_answer(task: SpecialistTask, answer: Any) -> dict[str, dict[str, Any]]:
    """Fail closed on hallucinated identity, ambiguous verdicts or weak evidence."""
    if not isinstance(answer, dict) or set(answer) != set(task.checks):
        raise ReviewError("specialist response omitted/added fixed-key checks")
    clean: dict[str, dict[str, Any]] = {}
    for name in task.checks:
        entry = answer[name]
        if not isinstance(entry, dict) or set(entry) != CHECK_FIELDS:
            raise ReviewError(f"specialist check {name} has an invalid shape")
        if (not isinstance(entry["verdict"], str) or entry["verdict"] not in VERDICTS\n                or type(entry["observed_symptom"]) is not bool):
            raise ReviewError(f"specialist check {name} has invalid verdict/symptom")
        if (not isinstance(entry["severity_proposal"], str)\n                or entry["severity_proposal"] not in SEVERITIES):
            raise ReviewError(f"specialist check {name} has invalid severity")
        for field in ("observation", "visible_evidence", "location_hint"):
            value = entry[field]
            if not isinstance(value, str) or len(value) > 600 or len(value.strip()) < 8:
                raise ReviewError(f"specialist check {name} has invalid {field}")
        for field in ("repair_hypothesis",):
            value = entry[field]
            if value is not None and (not isinstance(value, str) or len(value) > 240):
                raise ReviewError("specialist supplied invalid repair hypothesis")
        unknowns = entry["cannot_establish"]
        if (not isinstance(unknowns, list) or len(unknowns) > 6
                or any(not isinstance(x, str) or not 1 <= len(x) <= 180
                       for x in unknowns)):
            raise ReviewError("specialist supplied invalid uncertainties")
        if (entry["verdict"] == "fail" and
                (not entry["observed_symptom"]
                 or len(entry["visible_evidence"].strip()) < 12
                 or len(entry["location_hint"].strip()) < 5)):
            raise ReviewError("specialist FAIL lacks visible symptom/location proof")
        if entry["verdict"] == "pass" and entry["observed_symptom"]:
            raise ReviewError("specialist PASS contradicts observed defect")
        clean[name] = {
            **entry,
            # A BLOCKED verdict cannot erase a reported visible symptom.
            "needs_confirmation": (entry["observed_symptom"]
                                   and entry["verdict"] == "blocked"),
        }
    return clean
