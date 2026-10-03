"""Criterion-11 guard tests: missing targets, nesting, mismatch, links.

GOAL regression 11: missing write targets, original nested under
candidate, per-operation write mismatch and link escape must be
rejected. Link tests monkeypatch the link predicate (creating real
links needs privileges on some hosts); nesting uses real directories.
"""
import os
import subprocess
from pathlib import Path

import pytest

from vqs.repair import validate_materialized_roots, validate_plan

ORIGINAL = "/reports/original.Report"
CANDIDATE = "/candidate/worktree-1"


def _plan(**overrides):
    base = {
        "operations": [{"type": "theme.set", "target": "visual",
                        "value": "#0F2A44",
                        "writes": ["/candidate/worktree-1/report.Report"]}],
        "write_targets": ["/candidate/worktree-1/report.Report"],
        "rollback": "git checkout -- report.Report",
    }
    base.update(overrides)
    return base


def test_missing_write_targets_rejected() -> None:
    assert validate_plan(_plan(write_targets=[]),
                         ORIGINAL, CANDIDATE) == [
        {"rule": "plan_has_no_write_targets"}]
    for bad in (None, "definition/pages/P1", {"targets": []}, 7):
        assert validate_plan(_plan(write_targets=bad),
                             ORIGINAL, CANDIDATE) == [
            {"rule": "plan_write_targets_not_a_list"}], bad
    assert validate_plan(_plan(), ORIGINAL, CANDIDATE) == []


def test_model_match_requires_qualifiers() -> None:
    for target in ("measured", "models/x", "daxy", "tablespoon"):
        op = {"type": "theme.set", "target": target}
        assert validate_plan(_plan(operations=[op]),
                             ORIGINAL, CANDIDATE) == [], target
    for target in ("model", "dax", "dataset[col]", "measure.X", "rls"):
        op = {"type": "theme.set", "target": target}
        assert any(row["rule"] == "dax_rls_unapproved"
                   for row in validate_plan(_plan(operations=[op]),
                                             ORIGINAL, CANDIDATE)), target


def test_roots_overlap_rejected_both_directions() -> None:
    nested = _plan()
    assert any(row["rule"] == "roots_overlap" for row in validate_plan(
        nested, "/candidate/worktree-1/report.Report", CANDIDATE))
    assert any(row["rule"] == "roots_overlap" for row in validate_plan(
        nested, ORIGINAL, "/reports"))
    assert any(row["rule"] == "roots_overlap" for row in validate_plan(
        nested, CANDIDATE, CANDIDATE))
    assert validate_plan(nested, ORIGINAL, CANDIDATE) == []


def test_operation_write_mismatch_rejected() -> None:
    op = {"type": "theme.set", "target": "visual", "value": "#0F2A44",
          "writes": ["/candidate/worktree-1/other.Report"]}
    assert any(row["rule"] == "operation_write_mismatch"
               for row in validate_plan(_plan(operations=[op]),
                                         ORIGINAL, CANDIDATE))
    bad_shape = {"type": "theme.set", "target": "visual",
                 "writes": "not-a-list"}
    assert any(row["rule"] == "operation_write_mismatch"
               for row in validate_plan(_plan(operations=[bad_shape]),
                                         ORIGINAL, CANDIDATE))
    undeclared = {"type": "theme.set", "target": "visual"}
    assert validate_plan(_plan(operations=[undeclared]),
                         ORIGINAL, CANDIDATE) == []


def test_materialized_roots_require_real_dirs(tmp_path: Path) -> None:
    missing = validate_materialized_roots(str(tmp_path / "nope"),
                                          str(tmp_path / "alsono"))
    assert [row["rule"] for row in missing] == ["roots_not_materialized"] * 2
    original = tmp_path / "orig.Report"
    candidate = tmp_path / "cand"
    original.mkdir()
    candidate.mkdir()
    assert validate_materialized_roots(str(original), str(candidate)) == []


def test_materialized_overlap_and_links_rejected(
        tmp_path: Path, monkeypatch) -> None:
    candidate = tmp_path / "cand"
    nested = candidate / "orig.Report"
    nested.mkdir(parents=True)
    assert validate_materialized_roots(str(nested),
                                       str(candidate)) == [
        {"rule": "roots_overlap",
         "remediation": "Candidate and original roots must not overlap "
                        "after link resolution"}]
    original = tmp_path / "orig.Report"
    original.mkdir()
    (candidate / "page.json").write_text("{}", encoding="utf-8")
    assert validate_materialized_roots(str(original), str(candidate)) == []
    real_islink = os.path.islink

    def fake_islink(path):
        return str(path).endswith("page.json") or real_islink(path)

    monkeypatch.setattr(os.path, "islink", fake_islink)
    flagged = validate_materialized_roots(str(original), str(candidate))
    assert [row["rule"] for row in flagged] == ["link_escape"]
    assert flagged[0]["root"] == "candidate"


def test_realpath_escape_caught_without_link_flags(
        tmp_path: Path, monkeypatch) -> None:
    original = tmp_path / "orig.Report"
    candidate = tmp_path / "cand"
    original.mkdir()
    candidate.mkdir()
    (candidate / "page.json").write_text("{}", encoding="utf-8")
    real = os.path.realpath

    def fake(path):
        if str(path).endswith("page.json"):
            return os.path.join(str(tmp_path), "elsewhere", "page.json")
        return real(path)

    monkeypatch.setattr(os.path, "realpath", fake)
    monkeypatch.setattr(os.path, "islink", lambda path: False)
    monkeypatch.setattr(os.path, "isjunction", lambda path: False,
                        raising=False)
    flagged = validate_materialized_roots(str(original), str(candidate))
    assert [row["rule"] for row in flagged] == ["link_escape"]


def test_junction_branch_refuses_on_any_version(
        tmp_path: Path, monkeypatch) -> None:
    original = tmp_path / "orig.Report"
    candidate = tmp_path / "cand"
    original.mkdir()
    candidate.mkdir()
    (candidate / "page.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(os.path, "islink", lambda path: False)
    monkeypatch.setattr(os.path, "isjunction",
                        lambda path: str(path).endswith("page.json"),
                        raising=False)
    flagged = validate_materialized_roots(str(original), str(candidate))
    assert [row["rule"] for row in flagged] == ["link_escape"]


def test_walk_errors_fail_closed(tmp_path: Path, monkeypatch) -> None:
    original = tmp_path / "orig.Report"
    candidate = tmp_path / "cand"
    original.mkdir()
    candidate.mkdir()

    def failing_walk(top, followlinks=False, onerror=None):
        if onerror is not None:
            onerror(OSError("simulated EACCES"))
        return iter(())

    monkeypatch.setattr(os, "walk", failing_walk)
    flagged = validate_materialized_roots(str(original), str(candidate))
    assert [row["rule"] for row in flagged] == ["roots_unreadable"]


def test_real_symlink_escape_refused(tmp_path: Path) -> None:
    original = tmp_path / "orig.Report"
    candidate = tmp_path / "cand"
    original.mkdir()
    candidate.mkdir()
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    try:
        os.symlink(str(tmp_path / "outside.json"),
                   str(candidate / "evil.json"))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create links on this host: {exc}")
    flagged = validate_materialized_roots(str(original), str(candidate))
    assert [row["rule"] for row in flagged] == ["link_escape"]


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_real_junction_escape_refused(tmp_path: Path) -> None:
    original = tmp_path / "orig.Report"
    candidate = tmp_path / "cand"
    outside = tmp_path / "outside"
    original.mkdir()
    candidate.mkdir()
    outside.mkdir()
    (outside / "smuggled.json").write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(candidate / "jdir"), str(outside)],
        capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        pytest.skip(f"mklink /J unavailable: {completed.stderr[:200]}")
    flagged = validate_materialized_roots(str(original), str(candidate))
    assert [row["rule"] for row in flagged] == ["link_escape"]


def test_missing_isjunction_still_refuses_escape(
        tmp_path: Path, monkeypatch) -> None:
    original = tmp_path / "orig.Report"
    candidate = tmp_path / "cand"
    original.mkdir()
    candidate.mkdir()
    (candidate / "page.json").write_text("{}", encoding="utf-8")
    real = os.path.realpath

    def fake(path):
        if str(path).endswith("page.json"):
            return os.path.join(str(tmp_path), "elsewhere", "page.json")
        return real(path)

    monkeypatch.setattr(os.path, "realpath", fake)
    monkeypatch.setattr(os.path, "islink", lambda path: False)
    monkeypatch.delattr(os.path, "isjunction", raising=False)
    flagged = validate_materialized_roots(str(original), str(candidate))
    assert [row["rule"] for row in flagged] == ["link_escape"]
