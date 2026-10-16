"""Integration: real verified bundle/sidecar -> specialist ReviewPort observations."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.test_visual_regions import _scene_bundle
from vqs.pbir import source_digest
from vqs.review.adaptive_port import AdaptiveVisualReviewPort
from vqs.review.bundle import verify
from vqs.review.port import ReviewError, review_bundle
from vqs.visual.regions import build_regions


def _pass(task):
    return {name: {
        "verdict": "pass", "observed_symptom": False,
        "observation": "Visible card is contained in the render",
        "visible_evidence": "No visibly cut off text at the lower edge",
        "location_hint": "lower edge of card", "severity_proposal": "none",
        "repair_hypothesis": None, "cannot_establish": [],
    } for name in task.checks}


class FakeVerifiedProvider:
    def __init__(self):
        self.seen = []

    def review_task(self, task, page: Path, crop: Path):
        self.seen.append((task, page, crop))
        assert hashlib.sha256(page.read_bytes()).hexdigest() == task.page_image_sha256
        assert hashlib.sha256(crop.read_bytes()).hexdigest() == task.crop_image_sha256
        return {
            "answer": _pass(task),
            "receipt": {
                "task_id": task.task_id, "provider": "test-double",
                "actual_model": "fixture-only", "model_provenance": "provider_runtime_event",
                "effort": "high",
            },
        }


def test_reviewport_verifies_real_bundle_region_and_does_not_self_certify(tmp_path):
    report, bundle = _scene_bundle(tmp_path)
    before = source_digest(report)
    regions_dir = tmp_path / "regions"
    build_regions(str(bundle), str(regions_dir), report=str(report))
    provider = FakeVerifiedProvider()
    adapter = AdaptiveVisualReviewPort(
        regions_dir=str(regions_dir), provider=provider)
    output = review_bundle(
        bundle_dir=str(bundle), reviewer=adapter,
        reviewer_id=adapter.reviewer_id, fixer_id=verify(str(bundle))["fixer_id"])
    assert len(provider.seen) == 1
    assert output["source_sha256"] == before
    assert source_digest(report) == before
    assert output["tally"]["pass"] == 3
    assert output["tally"]["blocked"] == 1
    assert output["visual"] == "blocked"
    evidence = adapter.last_specialist_evidence
    assert evidence["executed_tasks"] == 1
    assert evidence["reviews"][0]["visual_id"] == "v1"
    assert evidence["reviews"][0]["page_id"] == "p1"
    assert evidence["reviews"][0]["crop_sha256"]


def test_budget_is_explicit_not_equated_with_pass(tmp_path):
    report, bundle = _scene_bundle(
        tmp_path, extra={
            "v2": {"x": 110, "y": 40, "width": 42, "height": 35, "z": 7}})
    regions_dir = tmp_path / "regions"
    build_regions(str(bundle), str(regions_dir), report=str(report))
    adapter = AdaptiveVisualReviewPort(
        regions_dir=str(regions_dir), provider=FakeVerifiedProvider(),
        max_tasks=1)
    result = adapter.review(str(bundle))
    assert adapter.last_specialist_evidence["executed_tasks"] == 1
    assert adapter.last_specialist_evidence["skipped_by_budget"] == 1
    assert any(row["detail"].get("status") == "not_run_budget"
               for row in result["observations"])


def test_tampered_crop_refused_before_any_model_call(tmp_path):
    report, bundle = _scene_bundle(tmp_path)
    regions_dir = tmp_path / "regions"
    record = build_regions(str(bundle), str(regions_dir), report=str(report))
    (regions_dir / record["regions"][0]["crop_image"]).write_bytes(b"tampered")
    provider = FakeVerifiedProvider()
    with pytest.raises(ReviewError, match="source evidence invalid"):
        AdaptiveVisualReviewPort(
            regions_dir=str(regions_dir), provider=provider).review(str(bundle))
    assert not provider.seen


def test_provider_model_receipt_is_required(tmp_path):
    report, bundle = _scene_bundle(tmp_path)
    regions_dir = tmp_path / "regions"
    build_regions(str(bundle), str(regions_dir), report=str(report))
    class MissingReceipt:
        def review_task(self, task, page, crop):
            return {"answer": _pass(task), "receipt": {"task_id": task.task_id}}
    with pytest.raises(ReviewError, match="not attested"):
        AdaptiveVisualReviewPort(
            regions_dir=str(regions_dir), provider=MissingReceipt()).review(str(bundle))


def test_second_provider_failure_preserves_first_real_task_evidence(tmp_path):
    report, bundle = _scene_bundle(
        tmp_path, extra={
            "v2": {"x": 110, "y": 40, "width": 42, "height": 35, "z": 7}})
    region_dir = tmp_path / "regions"
    build_regions(str(bundle), str(region_dir), report=str(report))
    class IntermittentProvider(FakeVerifiedProvider):
        def review_task(self, task, page, crop):
            if self.seen:
                raise ReviewError("provider returned no usable fixed-key image answer")
            return super().review_task(task, page, crop)

    adapter = AdaptiveVisualReviewPort(
        regions_dir=str(region_dir), provider=IntermittentProvider())
    reviewed = review_bundle(
        bundle_dir=str(bundle), reviewer=adapter,
        reviewer_id=adapter.reviewer_id, fixer_id=verify(str(bundle))["fixer_id"])
    assert reviewed["visual"] == "blocked"
    assert adapter.last_specialist_evidence["executed_tasks"] == 2
    assert adapter.last_specialist_evidence["blocked_tasks"] == 1
    assert adapter.last_specialist_evidence["reviews"][0]["receipt"]["actual_model"] == "fixture-only"
    assert any(item["detail"].get("status") == "provider_blocked"
               for item in reviewed["observations"])


def test_exact_source_selectors_refuse_unknown_target(tmp_path):
    report, bundle = _scene_bundle(tmp_path)
    region_dir = tmp_path / "regions"
    build_regions(str(bundle), str(region_dir), report=str(report))
    provider = FakeVerifiedProvider()
    with pytest.raises(ReviewError, match="absent or unsupported"):
        AdaptiveVisualReviewPort(
            regions_dir=str(region_dir), provider=provider,
            selectors=[("p1", "invented-visual")]).review(str(bundle))
    assert not provider.seen


def test_static_matrix_scroll_pass_does_not_certify_unexercised_interaction(
        tmp_path, monkeypatch):
    """A screenshot PASS cannot prove the user can reach hidden rows."""
    from vqs.review.specialists import TABLE

    report, bundle = _scene_bundle(tmp_path)
    region_dir = tmp_path / "regions"
    build_regions(str(bundle), str(region_dir), report=str(report))
    # Synthetic PBIR visual uses a card container; force a matrix rubric
    # solely to exercise the adapter's conditional scroll-coverage policy.
    monkeypatch.setattr(
        "vqs.review.adaptive_port.specialist_for_type",
        lambda _visual_type: TABLE)
    adapter = AdaptiveVisualReviewPort(
        regions_dir=str(region_dir), provider=FakeVerifiedProvider())
    review = review_bundle(
        bundle_dir=str(bundle), reviewer=adapter,
        reviewer_id=adapter.reviewer_id, fixer_id=verify(str(bundle))["fixer_id"])
    scroll = next(row for row in review["observations"]
                  if row["check"].endswith(".scroll_access"))
    assert scroll["verdict"] == "blocked"
    assert scroll["detail"]["interactive_scroll_test"] == "not_run"
    assert scroll["detail"]["evidence"]["verdict"] == "pass"
    assert review["visual"] == "blocked"
    assert adapter.last_specialist_evidence["reviews"][0]["response"][
        "scroll_access"]["verdict"] == "pass"
    row_visibility = next(row for row in review["observations"]
                          if row["check"].endswith(".row_total_visibility"))
    assert row_visibility["verdict"] == "blocked"
    assert row_visibility["detail"]["row_visibility_confirmation"] == (
        "not_run_pilot_false_clear")
    assert row_visibility["detail"]["evidence"]["verdict"] == "pass"
