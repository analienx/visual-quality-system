"""Spike-harness tests (WP-03/WP-04 offline subset): probe honesty.

PBI-04 (exact PID/path), DOC-06 (no Word-exact claims from another backend),
and the acceptance negatives: missing backends yield ``blocked`` with the
exact missing piece. No Desktop run, render, or model query is performed.
Capability probes are stubbed, so these tests are hermetic on any host.
"""
import vqs.powerbi.desktop as spike
from vqs.adapters.ports import Capability
from vqs.document import check_backend_equivalence, render, word_spike_readiness
from vqs.powerbi import check_target_match, desktop_spike_readiness


def _available(component: str) -> Capability:
    return Capability(component, "available", f"stubbed {component}")


def _unavailable(component: str) -> Capability:
    return Capability(component, "unavailable", f"stubbed missing {component}")


def test_desktop_spike_ready_when_probes_available(monkeypatch) -> None:
    monkeypatch.setattr(spike, "probe_file",
                        lambda component, path: _available(component))
    monkeypatch.setattr(spike, "probe_executable",
                        lambda component, *names: _available(component))
    report = desktop_spike_readiness()
    assert report["gate"] == "G1-desktop-spike"
    assert report["verdict"] == "ready"
    assert report.get("missing", []) == []
    assert any("desktop-bridge-cli" in cap["component"]
               for cap in report["capabilities"])


def test_desktop_spike_blocked_names_missing_piece(monkeypatch) -> None:
    monkeypatch.setattr(spike, "probe_file",
                        lambda component, path: _unavailable(component))
    monkeypatch.setattr(spike, "probe_executable",
                        lambda component, *names: _unavailable(component))
    report = desktop_spike_readiness()
    assert report["verdict"] == "blocked"
    assert sorted(report["missing"]) == ["desktop-bridge-cli",
                                         "powerbi-desktop-binary"]


def test_wrong_pid_or_path_fails_before_pixels() -> None:
    assert check_target_match(1, "a.pbip", 1, "a.pbip")["verdict"] == "pass"
    assert check_target_match(1, "x/../a.pbip", 1, "a.pbip")["verdict"] == "pass"
    assert check_target_match(2, "a.pbip", 1, "a.pbip")["verdict"] == "fail"
    assert check_target_match(1, "b.pbip", 1, "a.pbip")["verdict"] == "fail"
    assert check_target_match(1, "", 1, "a.pbip")["verdict"] == "blocked"


def test_word_spike_ready_with_interactive_word(monkeypatch) -> None:
    monkeypatch.setattr(render, "probe_executable",
                        lambda component, *names: _unavailable(component))
    monkeypatch.setattr(render, "_probe_word",
                        lambda: _available("interactive-word"))
    report = word_spike_readiness()
    assert report["gate"] == "G1-word-spike"
    assert report["verdict"] == "ready"
    assert "interactive-word" in report["backends"]


def test_word_spike_blocked_without_backends(monkeypatch) -> None:
    monkeypatch.setattr(render, "probe_executable",
                        lambda component, *names: _unavailable(component))
    monkeypatch.setattr(render, "_probe_word",
                        lambda: _unavailable("interactive-word"))
    report = word_spike_readiness()
    assert report["verdict"] == "blocked"
    assert "interactive-word" in report["missing"]


def test_renderer_mismatch_cannot_pass() -> None:
    assert check_backend_equivalence("word", "word")["verdict"] == "pass"
    failed = check_backend_equivalence("word", "libreoffice")
    assert failed["verdict"] == "fail"
    assert "Word-exact" in failed["reason"]
    assert check_backend_equivalence("", "word")["verdict"] == "blocked"
