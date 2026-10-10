"""Pre-mutation authoring capability and sealed evidence negative controls."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vqs.pipeline import repair_candidate
from vqs.powerbi.author import preflight


def _probe(version: str = "0.5.0", path: str = "/approved/report-author") -> dict:
    return {"available": True, "version": version, "path": path}


def _pinned(version: str = "0.5.0", path: str = "/approved/report-author"):
    return (
        {"status": "pass", "snapshot": {"sha256": "a" * 64},
         "commit": "b" * 40},
        {"status": "pass", "version": version, "path": path},
    )


def test_preflight_proves_mutation_and_validation_are_different_concepts():
    direct = preflight.check("direct", prober=lambda: _probe())
    assert direct["status"] == "pass"
    assert direct["mutation_engine"] == "vqs_typed"
    assert direct["validation_provider"] == "direct"
    assert direct["assurance"] == "native_static_only"
    verified = preflight.check("microsoft", prober=_probe,
                               approved_checker=_pinned)
    assert verified["status"] == "pass"
    assert verified["validation_provider"] == "microsoft"
    assert verified["assurance"] == "microsoft_structural_only"
    json.dumps(verified, allow_nan=False)


@pytest.mark.parametrize("issue,prober,checker", [
    ("stale skill", lambda: _probe(),
     lambda: ({"status": "blocked"}, {"status": "pass"})),
    ("missing executable", lambda: _probe(),
     lambda: ({"status": "pass"}, {"status": "blocked"})),
    ("version drift", lambda: _probe(version="0.6.0"), _pinned),
    ("path shadowing", lambda: _probe(path="/different/tool"), _pinned),
    ("missing snapshot", lambda: _probe(),
     lambda: ({"status": "pass", "snapshot": {}},
              {"status": "pass", "version": "0.5.0",
               "path": "/approved/report-author"})),
])
def test_preflight_blocks_unsafe_microsoft_toolchains(issue, prober, checker):
    result = preflight.check("microsoft", prober=prober,
                             approved_checker=checker)
    assert result["status"] == "blocked", issue
    assert result["assurance"] == "none", issue


def test_missing_cli_does_not_claim_microsoft():
    unavailable = preflight.check("auto", prober=lambda: {
        "available": False, "version": None, "path": None,
    })
    assert unavailable["status"] == "pass"  # legacy compatibility only
    assert unavailable["assurance"] == "native_static_only"
    assert unavailable["validation_provider"] == "direct"


def test_failed_preflight_prevents_candidate_and_run_creation(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    original = tmp_path / "original.Report"
    original.mkdir()
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "operations": [{"type": "axis.tick_format", "target": "visual",
                        "selector": {"page": "P1", "visual": "v1"},
                        "path": ["visual", "objects", "categoryAxis", 0,
                                 "properties", "labelPrecision", "expr",
                                 "Literal", "Value"],
                        "value": "3",
                        "writes": ["definition/pages/P1/visuals/v1/visual.json"]}],
        "write_targets": ["definition/pages/P1/visuals/v1/visual.json"],
        "rollback": "re-materialize from original"
    }), encoding="utf-8")
    # Use the established valid synthetic source fixture to reach the gate.
    source = Path(__file__).parent / "powerbi" / "fixtures" / "mini_report"
    shutil.rmtree(original)
    shutil.copytree(source, original)
    # Independent of the real CLI/skill, simulate a failed identity gate.
    monkeypatch.setattr(preflight, "check", lambda policy: {
        "status": "blocked", "policy": policy,
        "reason": "deliberately stale reviewed Microsoft skill",
    })
    candidate = tmp_path / "candidate.Report"
    runs = tmp_path / "runs"
    result = repair_candidate(str(plan), str(original), str(candidate),
                              run_root=str(runs), run_id="preflight-refusal",
                              authoring_backend="microsoft")
    assert result["verdict"] == "blocked"
    assert not candidate.exists()
    assert not runs.exists()


def test_real_microsoft_preflight_if_approved_local_checkout_present():
    # This is a real local capability probe; CI's separate authoring lane
    # exercises actual scaffold/validation and detects platform differences.
    from vqs.powerbi.author import mscli

    actual = mscli.probe()
    if not actual["available"]:
        pytest.skip("real Microsoft CLI unavailable in portable test lane")
    result = preflight.check("microsoft", prober=lambda: actual)
    assert result["status"] == "pass", result.get("reason")


def test_preflight_checker_crash_and_malformed_result_block():
    for checker in (
        lambda: (_ for _ in ()).throw(RuntimeError("probe crashed")),
        lambda: (None, None),
    ):
        result = preflight.check("microsoft", prober=_probe,
                                 approved_checker=checker)
        assert result["status"] == "blocked"
        assert "approved toolchain" in result["reason"]


def test_source_worktree_approved_toolchain_attested_in_full():
    from vqs.powerbi.author import mscli

    probe = mscli.probe()
    if not probe["available"]:
        pytest.skip("real CLI unavailable")
    attested = preflight.check("microsoft", prober=lambda: probe)
    assert attested["status"] == "pass", attested.get("reason")
    assert attested["skill"]["snapshot"]["file_count"] == 88
    assert attested["cli"]["version"] == "0.5.0"


def test_desktop_repair_cannot_use_native_only_assurance(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from vqs.coordinator import run_workflow

    monkeypatch.setattr(preflight, "check", lambda policy: {
        "contract": "vqs.authoring-preflight/1",
        "policy": policy, "status": "pass",
        "validation_provider": "direct",
        "mutation_engine": "vqs_typed",
        "assurance": "native_static_only",
    })
    root = tmp_path / "no-creation"
    result = run_workflow(
        facts={"rules": {}}, mode="repair", scope="desktop",
        run_root=str(root), run_id="unsafe-desktop")
    assert result["verdict"] == "blocked"
    assert "requires verified Microsoft" in result["blocked_reasons"][0]
    assert not root.exists()


def test_desktop_repair_blocks_failed_skill_without_creating_run(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from vqs.coordinator import run_workflow

    monkeypatch.setattr(preflight, "check", lambda policy: {
        "status": "blocked", "reason": "vendor digest mismatch",
        "policy": policy,
    })
    root = tmp_path / "no-run"
    result = run_workflow(
        facts={"rules": {}}, mode="repair", scope="desktop",
        authoring_backend="microsoft",
        run_root=str(root), run_id="stale-vendor")
    assert result["verdict"] == "blocked"
    assert "vendor digest mismatch" in result["blocked_reasons"][0]
    assert not root.exists()


def test_coordinator_resume_rejects_toolchain_attestation_drift(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from vqs.coordinator import run_workflow

    version = {"value": "fixture-1"}

    def fake_attestation(policy):
        return {"contract": "vqs.authoring-preflight/1",
                "policy": policy, "status": "pass",
                "validation_provider": "direct",
                "mutation_engine": "vqs_typed",
                "assurance": "native_static_only",
                "probe": {"fixture_version": version["value"]}}

    monkeypatch.setattr(preflight, "check", fake_attestation)
    run_root = tmp_path / "runs"
    first = run_workflow(facts={"rules": {}}, mode="repair", scope="static",
                         run_root=str(run_root), run_id="first")
    assert (run_root / "first" / "manifest.json").is_file(), first
    version["value"] = "fixture-2"
    second = run_workflow(facts={"rules": {}}, mode="repair", scope="static",
                          run_root=str(run_root), run_id="second",
                          resume_from="first")
    assert second["verdict"] == "blocked"
    assert "authoring_attestation_sha256" in second["blocked_reasons"][0]
    assert not (run_root / "second").exists()


def test_compiled_vqs_skill_pin_matches_source_checkout():
    from vqs.powerbi.author import skill_attest

    skill, _cli = skill_attest.check()
    assert skill["status"] == "pass", skill.get("reason")
    assert skill["commit"] == skill_attest.APPROVED_COMMIT
    assert skill["snapshot"]["sha256"] == skill_attest.APPROVED_TREE_SHA256


def test_explicit_wheel_skill_checkout_and_tamper_detection(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from vqs.powerbi.author import skill_attest

    checkout = tmp_path / "skill-checkout"
    source = Path(__file__).resolve().parents[1] / ".agents" / "skills"
    dest = checkout / ".agents" / "skills"
    dest.mkdir(parents=True)
    shutil.copytree(source / "powerbi-report-cli", dest / "powerbi-report-cli")
    shutil.copy2(source / "powerbi-report-cli-upstream.json", dest)
    monkeypatch.setenv("VQS_APPROVED_SKILL_ROOT", str(checkout))
    verified, _ = skill_attest.check()
    assert verified["status"] == "pass"
    vendor = dest / "powerbi-report-cli" / "SKILL.md"
    vendor.write_bytes(vendor.read_bytes() + b"\nUnauthorized guidance\n")
    tampered, _ = skill_attest.check()
    assert tampered["status"] == "blocked"
    assert "approved release digest" in tampered["reason"]
