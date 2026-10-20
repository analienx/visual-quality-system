"""Power BI and DOCX must be independently gated without weakening authority."""
from __future__ import annotations

from vqs.acceptance import (
    COVERAGE_PAIRS,
    REQUIRED_NEGATIVES,
    run_acceptance,
)
from vqs.components import (
    COMBINED_LEGACY,
    POWERBI_CORE,
    RELEASE_SCOPES,
    WORD_DOCX,
    suite_subject_digest,
)
from vqs.evidence import canonical_json_sha256


def _subjects(*kinds: str) -> list[dict]:
    return [
        {
            "id": f"s{index}",
            "kind": kind,
            "source_sha256": f"{index + 1:x}" * 64,
            **({"layout_digest": f"{index + 1:x}" * 16}
               if kind == "pbip" else {}),
        }
        for index, kind in enumerate(kinds)
    ]


def _rules(result: dict) -> set[str]:
    return {finding["rule"] for finding in result["findings"]}


def _incomplete(result: dict) -> list[str]:
    return next(finding["missing"] for finding in result["findings"]
                if finding["rule"] == "gate_set_incomplete")


def test_legacy_default_keeps_original_contract() -> None:
    assert COMBINED_LEGACY.coverage_pairs == COVERAGE_PAIRS
    assert COMBINED_LEGACY.required_negatives == REQUIRED_NEGATIVES
    result = run_acceptance({"subjects": _subjects("pbip", "pbip"), "gates": []})
    assert "partial_suite" in _rules(result)
    assert any(finding.get("reason") == "Two unrelated PBIPs plus a DOCX are required"
               for finding in result["findings"])


def test_powerbi_core_requires_two_unrelated_reports_but_no_docx() -> None:
    result = run_acceptance({
        "release_scope": "powerbi-core",
        "subjects": _subjects("pbip", "pbip"),
        "gates": [],
    })
    assert result["verdict"] == "blocked"
    assert "partial_suite" not in _rules(result)
    assert "release_scope_subject_mismatch" not in _rules(result)
    assert "G2:s0" in _incomplete(result)
    assert "G4:s1" in _incomplete(result)
    assert "G6:suite" in _incomplete(result)
    assert not any(pair.startswith("G5:") for pair in _incomplete(result))
    missing = next(finding["missing"] for finding in result["findings"]
                   if finding["rule"] == "negative_controls_missing")
    assert set(missing) == POWERBI_CORE.required_negatives
    assert "missing_word_font" not in missing


def test_word_docx_requires_its_own_pages_and_prose() -> None:
    result = run_acceptance({
        "release_scope": "word-docx",
        "subjects": _subjects("docx"),
        "gates": [],
    })
    assert result["verdict"] == "blocked"
    assert "partial_suite" not in _rules(result)
    assert "G5:s0" in _incomplete(result)
    assert "G0:s0" in _incomplete(result)
    assert "G6:suite" in _incomplete(result)
    assert not any(pair.startswith(("G2:", "G3:", "G4:"))
                   for pair in _incomplete(result))
    missing = next(finding["missing"] for finding in result["findings"]
                   if finding["rule"] == "negative_controls_missing")
    assert set(missing) == WORD_DOCX.required_negatives
    assert "wrong_pid" not in missing


def test_each_scope_refuses_mixed_subjects_instead_of_ignoring_them() -> None:
    for release_scope, kinds in (
        ("powerbi-core", ("pbip", "pbip", "docx")),
        ("word-docx", ("docx", "pbip")),
    ):
        result = run_acceptance({
            "release_scope": release_scope,
            "subjects": _subjects(*kinds),
            "gates": [],
        })
        assert result["verdict"] == "fail"
        assert "release_scope_subject_mismatch" in _rules(result)


def test_invalid_release_scope_never_downgrades_to_easier_requirements() -> None:
    for bad in ("unknown", "", None, 4, [], {}):
        result = run_acceptance({
            "release_scope": bad,
            "subjects": _subjects("pbip", "pbip"),
            "gates": [],
        })
        assert result["verdict"] == "blocked"
        assert "release_scope_invalid" in _rules(result)
        assert "partial_suite" in _rules(result)


def test_scoped_suite_digest_prevents_cross_component_replay() -> None:
    triples = [
        {"id": "p", "kind": "pbip", "source_sha256": "a" * 64},
    ]
    pbip_digest = canonical_json_sha256(suite_subject_digest(triples, POWERBI_CORE))
    docx_digest = canonical_json_sha256(suite_subject_digest(triples, WORD_DOCX))
    combined_digest = canonical_json_sha256(suite_subject_digest(triples, COMBINED_LEGACY))
    assert len({pbip_digest, docx_digest, combined_digest}) == 3
    assert combined_digest == canonical_json_sha256(triples)


def test_scoped_suite_record_requires_its_scope_bound_digest() -> None:
    subjects = _subjects("pbip", "pbip")
    triples = [{"id": s["id"], "kind": s["kind"],
                "source_sha256": s["source_sha256"]} for s in subjects]
    correct = canonical_json_sha256(suite_subject_digest(triples, POWERBI_CORE))
    record = {"release_scope": "powerbi-core", "subjects": subjects,
              "gates": [], "suite": {"subjects": triples, "suite_digest": correct}}
    accepted_structure = run_acceptance(record)
    assert "suite_digest_mismatch" not in _rules(accepted_structure)
    assert accepted_structure["verdict"] == "blocked"  # no G6 producer/authority

    wrong = {**record, "suite": {"subjects": triples, "suite_digest":
                                canonical_json_sha256(triples)}}
    replay_attempt = run_acceptance(wrong)
    assert replay_attempt["verdict"] == "fail"
    assert "suite_digest_mismatch" in _rules(replay_attempt)


def test_powerbi_core_rejects_two_copies_of_one_layout() -> None:
    subjects = _subjects("pbip", "pbip")
    subjects[1]["layout_digest"] = subjects[0]["layout_digest"]
    verdict = run_acceptance({"release_scope": "powerbi-core",
                              "subjects": subjects, "gates": []})
    assert "partial_suite" in _rules(verdict)


def test_public_profiles_are_exact_and_require_independent_g6() -> None:
    assert set(RELEASE_SCOPES) == {"powerbi-core", "word-docx", "combined"}
    assert all(("G5", "pbip") not in scope.coverage_pairs
               and ("G4", "docx") not in scope.coverage_pairs
               for scope in RELEASE_SCOPES.values())
    # Scope definitions are structural requirements, not producer capability:
    # a source-only G0 seal cannot satisfy the release's independent G6.
    assert all(scope.required_negatives and scope.coverage_pairs
               for scope in RELEASE_SCOPES.values())
