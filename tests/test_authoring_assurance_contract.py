"""W03: frozen validator selection, typed-writer separation, assurance truth."""
from __future__ import annotations

from vqs.powerbi.author import adapter
from vqs.powerbi.author.assurance import CONTRACT, compose


def _attestation(provider: str = "microsoft", path: str = "/approved/cli") -> dict:
    return {
        "contract": "vqs.authoring-preflight/1",
        "status": "pass",
        "policy": "microsoft" if provider == "microsoft" else "direct",
        "mutation_engine": "vqs_typed",
        "validation_provider": provider,
        "assurance": ("microsoft_structural_only" if provider == "microsoft"
                      else "native_static_only"),
        "cli": {"path": path, "version": "0.5.0"},
        "probe": {"path": path, "version": "0.5.0", "available": True},
    }


def test_frozen_cli_selection_uses_approved_binary_and_never_reprobes():
    seen = []
    attestation = _attestation()

    def forbidden_probe():
        raise AssertionError("PATH was probed after preflight")

    def runner(candidate, *, timeout, tool):
        seen.append((candidate, timeout, tool))
        return {"status": "valid", "errors": [], "warnings": [],
                "command": [tool, "validate", candidate], "returncode": 0}

    result = adapter.run_backend("candidate.Report", policy="microsoft",
                                 timeout=37, attestation=attestation,
                                 prober=forbidden_probe, runner=runner)
    assert result["verdict"] == "pass"
    assert seen == [("candidate.Report", 37, "/approved/cli")]
    proof = compose(attestation, result)
    assert proof["contract"] == CONTRACT
    assert proof["mutation_engine"] == "vqs_typed"
    assert proof["validation_provider"] == "microsoft_cli"
    assert proof["structural_validation"] == "pass"
    assert proof["rendered_desktop"] == "not_run"
    assert proof["data_semantics"] == "not_run"
    assert proof["release_acceptance"] == "not_run"


def test_mismatched_pinned_tool_blocks_without_executing_validator():
    attestation = _attestation()
    attestation["cli"]["path"] = "/different/cli"
    calls = []
    result = adapter.run_backend(
        "candidate", policy="microsoft", attestation=attestation,
        runner=lambda *a, **kw: calls.append(kw))
    assert result["verdict"] == "blocked"
    assert calls == []
    assert "path/version" in result["reason"]


def test_attested_microsoft_outage_never_falls_back_to_direct():
    attestation = _attestation()
    seen = []
    result = adapter.run_backend(
        "candidate", policy="microsoft", attestation=attestation,
        runner=lambda *_a, **_kw: (seen.append("validate") or
                                    {"status": "missing", "errors": [],
                                     "warnings": [], "note": "tool removed"}))
    assert seen == ["validate"]
    assert result["verdict"] == "blocked"
    assert result["backend"] == "microsoft"
    proof = compose(attestation, result)
    assert proof["structural_validation"] == "blocked"


def test_explicit_native_writer_never_claims_structural_acceptance():
    attestation = _attestation("direct")
    result = adapter.run_backend(
        "candidate", policy="direct", attestation=attestation,
        prober=lambda: 1 / 0, runner=lambda *a, **k: 1 / 0)
    assert result["verdict"] == "pass"
    proof = compose(attestation, result)
    assert proof["validation_provider"] == "native_static"
    assert proof["structural_validation"] == "not_run"
    assert proof["independent_visual_review"] == "not_run"


def test_invalid_or_forged_attestation_refuses_before_validation():
    called = []
    for patch in (
        {"mutation_engine": "unbounded_editor"},
        {"status": "blocked"},
        {"policy": "auto"},
        {"validation_provider": "unreviewed"},
        {"probe": None},
    ):
        attestation = {**_attestation(), **patch}
        result = adapter.run_backend(
            "candidate", policy="microsoft", attestation=attestation,
            runner=lambda *a, **k: called.append("called"))
        assert result["verdict"] == "blocked", patch
    assert called == []


def test_invalid_microsoft_structural_result_does_not_claim_data():
    attestation = _attestation()
    result = adapter.run_backend(
        "candidate", policy="microsoft", attestation=attestation,
        runner=lambda *a, **k: {"status": "invalid", "errors": ["bad role"],
                                "warnings": []})
    proof = compose(attestation, result)
    assert result["verdict"] == "fail"
    assert proof["structural_validation"] == "fail"
    assert proof["data_semantics"] == "not_run"
