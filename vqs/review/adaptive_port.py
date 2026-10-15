"""Backward-compatible ReviewPort over verified P1 crop sidecars.

This initial P2 port targets cards and matrices. Every page also receives
an explicit BLOCKED coverage observation because generic page-sweep, map,
interactive and semantic audits have not run; no specialist-only review
can accidentally certify an entire report as PASS.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ..visual.regions import RegionError, verify_regions
from .bundle import verify as verify_bundle
from .contracts import SpecialistTask, validate_answer
from .port import ReviewError, review_bundle
from .specialists import specialist_for_type


class AdaptiveVisualReviewPort:
    reviewer_id = "vqs-independent-muse-specialists-p2"

    def __init__(self, *, regions_dir: str, provider: Any,
                 max_tasks: int = 12,
                 selectors: list[tuple[str, str]] | None = None) -> None:
        if type(max_tasks) is not int or not 1 <= max_tasks <= 64:
            raise ValueError("invalid specialist call budget")
        self.regions_dir = Path(regions_dir)
        self.provider = provider
        self.max_tasks = max_tasks
        self.selectors = None if selectors is None else frozenset(selectors)
        if self.selectors is not None and not self.selectors:
            raise ValueError("empty specialist target selection")
        self.last_specialist_evidence: dict[str, Any] | None = None

    def review(self, bundle_dir: str) -> dict[str, Any]:
        try:
            authority = verify_bundle(bundle_dir)
            proof = verify_regions(bundle_dir, str(self.regions_dir))
        except (RegionError, OSError, ValueError, KeyError, TypeError) as exc:
            raise ReviewError(f"specialist source evidence invalid: {exc}") from exc
        if authority["review_image_basis"] != "verified_canvas":
            raise ReviewError("specialist requires actual verified report-only pixels")
        regions = json.loads((self.regions_dir / "regions.json").read_text(
            encoding="utf-8"))["regions"]
        tasks: list[tuple[SpecialistTask, dict]] = []
        for region in regions:
            if (self.selectors is not None and
                    (region["page_id"], region["visual_id"]) not in self.selectors):
                continue
            specialist = specialist_for_type(region["visual_type"])
            if specialist is None:
                continue
            task = SpecialistTask.from_verified(
                authority=authority, region=region, specialist=specialist.code,
                checks=specialist.checks, prompt_version=specialist.version)
            tasks.append((task, region))
        if self.selectors is not None:
            selected = {(task.page_id, task.visual_id) for task, _ in tasks}
            if selected != self.selectors:
                raise ReviewError("requested specialist target absent or unsupported")
        if not tasks:
            raise ReviewError("region sidecar has no eligible card or matrix review")
        # Preserve source order, not model-generated ranking or arbitrary filesystem order.
        original_root = Path(bundle_dir).resolve()
        region_root = self.regions_dir.resolve()
        observations: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        for task, region in tasks[:self.max_tasks]:
            image = original_root / authority["review_images"][task.page_id]["image"]
            crop = region_root / region["crop_image"]
            if (image.is_symlink() or crop.is_symlink()
                    or image.resolve().parent != original_root
                    or crop.resolve().parent != region_root):
                raise ReviewError("specialist image path escapes sealed evidence")
            try:
                delivered = self.provider.review_task(task, image, crop)
            except ReviewError as exc:
                # A failed isolated task must not erase earlier valid evidence.
                observations.append({
                    "page_id": task.page_id,
                    "check": f"specialist.{task.specialist}.{task.visual_id}.execution",
                    "verdict": "blocked",
                    "detail": {"task_id": task.task_id, "status": "provider_blocked",
                               "reason": str(exc)},
                })
                evidence.append({
                    "task_id": task.task_id, "page_id": task.page_id,
                    "visual_id": task.visual_id, "specialist": task.specialist,
                    "status": "blocked_provider", "page_sha256": task.page_image_sha256,
                    "crop_sha256": task.crop_image_sha256,
                })
                continue
            if not isinstance(delivered, dict) or set(delivered) != {"answer", "receipt"}:
                raise ReviewError("specialist provider omitted answer or runtime receipt")
            answer = validate_answer(task, delivered["answer"])
            receipt = delivered["receipt"]
            if (not isinstance(receipt, dict)
                    or receipt.get("task_id") != task.task_id
                    or receipt.get("model_provenance") != "provider_runtime_event"
                    or receipt.get("effort") != "high"
                    or not isinstance(receipt.get("actual_model"), str)):
                raise ReviewError("specialist actual model/effort identity not attested")
            evidence.append({
                "task_id": task.task_id, "page_id": task.page_id,
                "visual_id": task.visual_id, "source_sha256": task.source_sha256,
                "page_sha256": task.page_image_sha256,
                "crop_sha256": task.crop_image_sha256,
                "specialist": task.specialist, "prompt_version": task.prompt_version,
                "response": answer, "receipt": receipt,
            })
            for check, decision in answer.items():
                observations.append({
                    "page_id": task.page_id,
                    "check": f"specialist.{task.specialist}.{task.visual_id}.{check}",
                    "verdict": decision["verdict"],
                    "detail": {
                        "visual_id": task.visual_id, "task_id": task.task_id,
                        "page_sha256": task.page_image_sha256,
                        "crop_sha256": task.crop_image_sha256,
                        "evidence": decision,
                        "actual_model": receipt["actual_model"],
                        "prompt_version": task.prompt_version,
                    },
                })
        for task, _ in tasks[self.max_tasks:]:
            observations.append({
                "page_id": task.page_id,
                "check": f"specialist.{task.specialist}.{task.visual_id}.coverage",
                "verdict": "blocked",
                "detail": {"status": "not_run_budget", "task_id": task.task_id},
            })
        # Narrow pilot does NOT satisfy mandatory broad page-sweep coverage.
        for page in authority["pages"]:
            observations.append({
                "page_id": page,
                "check": "specialist_review_coverage",
                "verdict": "blocked",
                "detail": {
                    "status": "not_run_full_page_sweep_or_other_specialists",
                    "executed_tasks": sum(x["page_id"] == page for x in evidence),
                },
            })
        self.last_specialist_evidence = {
            "schema": "vqs.specialist-evidence/1",
            "source_sha256": authority["source_sha256"],
            "bundle_sha256": proof["bundle_sha256"],
            "executed_tasks": len(evidence),
            "blocked_tasks": sum(x.get("status") == "blocked_provider" for x in evidence),
            "skipped_by_budget": max(0, len(tasks) - self.max_tasks),
            "reviews": evidence,
        }
        return {"observations": observations}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Advisory P2 card/matrix review; never certifies release")
    parser.add_argument("bundle")
    parser.add_argument("regions")
    parser.add_argument("--model", required=True)
    parser.add_argument("--target", action="append", default=[],
                        help="Exact PBIR PAGE_ID/VISUAL_ID; repeat for pilot targets")
    parser.add_argument("--max-tasks", type=int, default=12)
    parser.add_argument("--allow-remote-images", action="store_true")
    parser.add_argument("--allow-contributor", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.allow_remote_images:
        parser.error("explicit --allow-remote-images consent required")
    from .providers.muse import MuseHighSpecialist
    previous = {key: os.environ.get(key)
                for key in ("VQS_ALLOW_VISION_UPLOAD", "VQS_ALLOW_MUSE_CONTRIBUTOR")}
    try:
        os.environ["VQS_ALLOW_VISION_UPLOAD"] = "1"
        if args.allow_contributor:
            os.environ["VQS_ALLOW_MUSE_CONTRIBUTOR"] = "1"
        provider = MuseHighSpecialist(model=args.model)
        selectors = []
        for value in args.target:
            if "/" not in value or not all(value.split("/", 1)):
                parser.error("--target requires exact PAGE_ID/VISUAL_ID")
            selectors.append(tuple(value.split("/", 1)))
        port = AdaptiveVisualReviewPort(
            regions_dir=args.regions, provider=provider,
            max_tasks=args.max_tasks, selectors=selectors or None)
        authority = verify_bundle(args.bundle)
        result = review_bundle(
            bundle_dir=args.bundle, reviewer=port,
            reviewer_id=port.reviewer_id, fixer_id=authority["fixer_id"])
        output = {"advisory": True, "release_authority": False,
                  "review": result, "specialist_evidence": port.last_specialist_evidence}
        # Never overwrite private evidence from a different run.
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(output, stream, ensure_ascii=False, indent=2)
        print(json.dumps({
            "status": "advisory_review",
            "visual": result["visual"], "tally": result["tally"],
            "executed_tasks": port.last_specialist_evidence["executed_tasks"],
            "output": str(args.out),
        }))
        return 1 if result["visual"] != "pass" else 0
    except (ReviewError, ValueError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


if __name__ == "__main__":
    raise SystemExit(main())
