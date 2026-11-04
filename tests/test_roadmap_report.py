"""Negative and positive validation tests for Git-tracked implementation status.

These checks do not count as Desktop/Word/product acceptance.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from scripts.roadmap_report import DEFAULT_LEDGER, summarize, validate


def _ledger() -> dict:
    return json.loads(Path(DEFAULT_LEDGER).read_text(encoding="utf-8"))


def test_published_ledger_is_acyclic_and_has_valid_status_claims() -> None:
    data = _ledger()
    assert validate(data) == []
    result = summarize(data)
    assert result["independently_verified"] == 0
    assert result["initial_release_packages"] == 14
    v020 = next(item for item in data["packages"] if item["id"] == "WP-30")
    assert v020["issue"] == 130
    assert v020["stage"] == "S10"
    assert {"WP-05", "WP-07"} == set(v020["depends_on"])
    assert v020["state"] == "planned"
    assert v020["verification"] == "not_run"
    answers = next(item for item in data["packages"] if item["id"] == "WP-31")
    assert answers["issue"] == 133
    assert {"WP-30", "WP-10"} == set(answers["depends_on"])
    assert answers["state"] == "planned"
    assert answers["verification"] == "not_run"
    guided = next(item for item in data["packages"] if item["id"] == "WP-32")
    assert guided["issue"] == 135
    assert guided["depends_on"] == ["WP-31"]
    assert guided["state"] == "planned"
    assert guided["verification"] == "not_run"
    quote_safety = next(item for item in data["packages"] if item["id"] == "WP-34")
    assert quote_safety["issue"] == 139
    assert quote_safety["depends_on"] == ["WP-32"]
    assert quote_safety["state"] == "planned"
    assert quote_safety["verification"] == "not_run"
    adoption = next(item for item in data["packages"] if item["id"] == "WP-33")
    assert adoption["issue"] == 137
    assert adoption["depends_on"] == ["WP-34"]
    assert adoption["state"] == "planned"
    assert adoption["verification"] == "not_run"
    intent = next(item for item in data["packages"] if item["id"] == "WP-35")
    assert intent["issue"] == 143
    assert intent["depends_on"] == ["WP-33"]
    assert intent["state"] == "planned"
    assert intent["verification"] == "not_run"
    assert result["deferred"] == 1
    assert result["next_runnable"] == ["WP-00"]


def test_future_package_does_not_inflate_initial_or_deferred_counts() -> None:
    data = deepcopy(_ledger())
    future = next(item for item in data["packages"] if item["id"] == "WP-30")
    future["depends_on"] = []
    result = summarize(data)
    assert result["initial_release_packages"] == 14
    assert result["deferred"] == 1
    assert "WP-30" in result["next_runnable"]


def test_issue_closure_or_invented_verified_status_cannot_replace_evidence() -> None:
    data = deepcopy(_ledger())
    data["packages"][0]["state"] = "verified"
    data["packages"][0]["verification"] = "verified"
    assert any("lacks independent evidence" in problem for problem in validate(data))


def test_unverified_dependency_prevents_premature_work_status() -> None:
    data = deepcopy(_ledger())
    data["packages"][1]["state"] = "ready"
    assert any("prerequisite WP-00 not independently verified" in problem for problem in validate(data))


def test_unknown_dependency_and_self_cycle_fail() -> None:
    data = deepcopy(_ledger())
    data["packages"][0]["depends_on"] = ["WP-NOPE", "WP-00"]
    errors = validate(data)
    assert any("missing dependency WP-NOPE" in problem for problem in errors)
    assert any("self dependency" in problem for problem in errors)


def test_blocked_claim_requires_a_reason() -> None:
    data = deepcopy(_ledger())
    data["packages"][0]["state"] = "blocked"
    assert any("must include a blocker" in problem for problem in validate(data))
