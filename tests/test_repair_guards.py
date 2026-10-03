"""Criterion-11 guard tests: missing targets, nesting, mismatch, links.

GOAL regression 11: missing write targets, original nested under
candidate, per-operation write mismatch and link escape must be
rejected. Link tests monkeypatch the link predicate (creating real
links needs privileges on some hosts); nesting uses real directories.
"""
import os
from pathlib import Path

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
    assert validate_plan(_plan(write_targets=None),
                         ORIGINAL, CANDIDATE) == [
        {"rule": "plan_has_no_write_targets"}]
    assert validate_plan(_plan(), ORIGINAL, CANDIDATE) == []


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
