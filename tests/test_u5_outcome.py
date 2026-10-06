"""P0-U5: execution success separated from report quality.

Stage passes describe execution; the sealed summary exposes
quality_before/after, resolved/remaining/new findings, candidate and
promotion status, and an outcome. Envelope pass requires the requested
acceptance scope to pass. Hosted CI only (no live Desktop).
"""
from pathlib import Path

from vqs.coordinator import (_acceptance, _candidate_status,
                              _decide_outcome, _reconcile_quality,
                              run_workflow)


def _checks(states: dict[str, str]) -> list[dict[str, str]]:
    return [{"check": name, "status": status}
            for name, status in states.items()]


def test_reconcile_resolved_remaining_new() -> None:
    """Finding deltas follow proven pass/fail transitions only."""
    result = _reconcile_quality(
        _checks({"a": "fail", "b": "fail", "c": "pass"}),
        _checks({"a": "pass", "b": "fail", "c": "fail"}))
    assert result == {"resolved": ["a"], "remaining": ["b", "c"],
                      "new": ["c"], "complete": True}


def test_reconcile_ignores_unevaluated_checks() -> None:
    """Blocked/absent checks never count as resolved or new."""
    result = _reconcile_quality(
        _checks({"a": "fail", "b": "blocked"}),
        _checks({"b": "fail", "c": "blocked"}))
    assert result == {"resolved": [], "remaining": ["b"], "new": [],
                      "complete": True}


def test_reconcile_unknown_stays_unknown() -> None:
    """Missing, malformed, or vanished findings never report as zero."""
    for before, after in ((None, []), ([], None),
                          ([{"check": "a"}], [{"check": "a",
                                               "status": "pass"}]),
                          (_checks({"a": "fail"}), []),
                          ("nope", _checks({"a": "fail"}))):
        result = _reconcile_quality(before, after)
        assert result == {"resolved": [], "remaining": [], "new": [],
                          "complete": False}, (before, after)


def test_decide_outcome_table() -> None:
    """Every outcome follows execution, acceptance, and the delta."""
    decide = _decide_outcome
    assert decide(mode="repair", execution="blocked", acceptance=False,
                  resolved=[], new=[], candidates=0) == "blocked"
    assert decide(mode="repair", execution="fail", acceptance=False,
                  resolved=[], new=[], candidates=1) == "failed"
    assert decide(mode="repair", execution="pass", acceptance=True,
                  resolved=["a"], new=[], candidates=1) == "accepted"
    assert decide(mode="repair", execution="pass", acceptance=False,
                  resolved=[], new=["b"], candidates=1) == "regressed"
    assert decide(mode="repair", execution="pass", acceptance=False,
                  resolved=["a"], new=[], candidates=1
                  ) == "improved_not_accepted"
    assert decide(mode="propose", execution="pass", acceptance=False,
                  resolved=[], new=[], candidates=0) == "no_safe_fix"
    assert decide(mode="review", execution="pass", acceptance=False,
                  resolved=[], new=[], candidates=0) == "not_accepted"
    assert decide(mode="repair", execution="pass", acceptance=False,
                  resolved=[], new=[], candidates=1) == "not_accepted"


def test_acceptance_scope_by_mode() -> None:
    """Each mode's acceptance scope matches what the mode was asked."""
    assert _acceptance("review", review_verdict="pass", quality_after=None,
                       candidates=0, regression_failed=False) is True
    assert _acceptance("review", review_verdict="fail", quality_after=None,
                       candidates=0, regression_failed=False) is False
    assert _acceptance("propose", review_verdict="fail", quality_after=None,
                       candidates=2, regression_failed=False) is True
    assert _acceptance("propose", review_verdict="pass", quality_after=None,
                       candidates=0, regression_failed=False) is True
    assert _acceptance("propose", review_verdict="fail", quality_after=None,
                       candidates=0, regression_failed=False) is False
    assert _acceptance("repair", review_verdict="fail", quality_after="pass",
                       candidates=1, regression_failed=False) is True
    assert _acceptance("repair", review_verdict="fail", quality_after="pass",
                       candidates=1, regression_failed=True) is False
    assert _acceptance("repair", review_verdict="fail", quality_after="fail",
                       candidates=1, regression_failed=False) is False


def test_candidate_status_shapes() -> None:
    """Candidate lifecycle derives from the stage ledger alone."""

    def _entry(stage: str, status: str, **extra: object) -> dict:
        record: dict = {"stage": stage, "status": status}
        record.update(extra)
        return record

    assert _candidate_status([])["status"] == "none"
    assert _candidate_status(
        [_entry("repair", "not_run")])["status"] == "none"
    assert _candidate_status(
        [_entry("repair", "blocked", run_id="r")])["status"] == "blocked"
    assert _candidate_status(
        [_entry("repair", "fail", run_id="r")])["status"] == "failed"
    assert _candidate_status(
        [_entry("repair", "pass", run_id="r",
                evidence={"candidate": "c"}),
         _entry("verify", "pass")]) == {
             "status": "verified", "run_id": "r", "candidate": "c"}
    assert _candidate_status(
        [_entry("repair", "pass", run_id="r",
                evidence={"candidate": "c"}),
         _entry("verify", "fail")])["status"] == "failed-verification"
    assert _candidate_status(
        [_entry("repair", "pass", run_id="r",
                evidence={"candidate": "c"}),
         _entry("verify", "blocked")])["status"] == "applied-unverified"
    assert _candidate_status(
        [_entry("repair", "pass", run_id="r",
                evidence={"candidate": "c"})])["status"] == (
                    "applied-unverified")


def _overlap_facts(offset: int = 100) -> dict:
    visuals = [
        {"page": "P1", "visual": "A", "bound": True,
         "x": 0, "y": 0, "width": 200, "height": 200, "z": 0.0},
        {"page": "P1", "visual": "B", "bound": True,
         "x": offset, "y": offset, "width": 200, "height": 200, "z": 1.0}]
    pages = [{"page": "P1", "width": 1280, "height": 720,
              "visuals": [{"visual": "A", "x": 0, "y": 0,
                           "width": 200, "height": 200},
                          {"visual": "B", "x": offset, "y": offset,
                           "width": 200, "height": 200}]}]
    return {"rules": {"layout.no_visual_overlap": {"visuals": visuals},
                      "layout.visuals_within_page": {"pages": pages}}}


def test_review_failing_report_not_accepted(tmp_path: Path) -> None:
    """Review mode on a failing report: execution pass, acceptance fail."""
    envelope = run_workflow(facts=_overlap_facts(), mode="review",
                            scope="static", run_root=str(tmp_path),
                            run_id="u5-review-fail")
    assert envelope["verdict"] == "fail"
    summary = envelope["summary"]
    assert summary["outcome"] == "not_accepted"
    assert summary["acceptance"] is False
    assert summary["quality_before"] == "fail"
    assert summary["quality_after"] is None
    assert summary["remaining_findings"] != []
    assert summary["resolved_findings"] == []
    assert summary["new_regressions"] == []
    assert summary["findings_complete"] is True
    assert summary["candidate_status"] == {"status": "none", "run_id": None,
                                           "candidate": None}
    assert summary["promotion_status"]["status"] == "not-performed"
    assert "never" in summary["note"] or "acceptance" in summary["note"]
    by_check = {item["check"]: item for item in envelope["findings"]}
    assert by_check["outcome"]["detail"]["outcome"] == "not_accepted"


def test_review_passing_report_accepted(tmp_path: Path) -> None:
    """Review mode on a clean report: the acceptance scope passes."""
    envelope = run_workflow(facts=_overlap_facts(offset=500), mode="review",
                            scope="static", run_root=str(tmp_path),
                            run_id="u5-review-pass")
    assert envelope["review_verdict"] == "pass"
    assert envelope["verdict"] == "pass"
    assert envelope["summary"]["outcome"] == "accepted"
    assert envelope["summary"]["acceptance"] is True
    assert envelope["summary"]["remaining_findings"] == []


def test_propose_without_safe_fix(tmp_path: Path) -> None:
    """A >50% overlap admits no verified move: execution pass, no_safe_fix."""
    envelope = run_workflow(facts=_overlap_facts(offset=50), mode="propose",
                            scope="static", run_root=str(tmp_path),
                            run_id="u5-no-fix")
    assert envelope["verdict"] == "fail"
    summary = envelope["summary"]
    assert summary["outcome"] == "no_safe_fix"
    assert summary["candidates_proposed"] == 0
    assert "no finding admits" in " ".join(envelope["next_actions"])
