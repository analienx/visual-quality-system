"""Strict opt-in Desktop attestation must prevent unauthenticated live actions."""
from __future__ import annotations

import zipfile

from scripts import contoso_p11_semantic_probe as historical
from scripts import contoso_p14_live_oracle as dax
from tests.test_contoso_p11_semantic_oracle import FakePort
from vqs.powerbi import desktop_uia
from vqs.powerbi.contoso_project import inventory


def _project(tmp_path):
    with zipfile.ZipFile(historical.FIXTURE) as bundle:
        bundle.extractall(tmp_path)
    return tmp_path


def test_strict_dax_blocks_before_connecting_when_host_unattested(tmp_path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr(dax, "attest_desktop_source",
                        lambda *args: {"loaded_file_attested": False,
                                       "reason": "unsaved native state"})
    def unsafe_connector(**_kwargs):
        raise AssertionError("blocked attestation may not open modeling connector")
    monkeypatch.setattr(dax, "StdioModelingClient", unsafe_connector)
    result = dax.run(project, 48552, attest_source=True)
    assert result["semantic"] == "blocked"
    assert result["desktop_source_attested"] is False
    assert "unsaved" in result["reason"]


def test_strict_dax_with_attested_source_reuses_existing_oracles(tmp_path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr(dax, "attest_desktop_source",
                        lambda *args: {"loaded_file_attested": True,
                                       "status": "pass"})
    monkeypatch.setattr(dax, "StdioModelingClient",
                        lambda **kwargs: FakePort(desktop_pid=48552))
    result = dax.run(project, 48552, attest_source=True)
    assert result["semantic"] == "pass"
    assert result["desktop_source_attested"] is True
    assert len(result["states"]) == 4
    assert "OS/Bridge" in result["reason"]


def test_strict_uia_never_invokes_controls_on_unattested_host(tmp_path, monkeypatch):
    project = _project(tmp_path)
    source = inventory(project)[0]["digest"]
    monkeypatch.setattr(desktop_uia, "attest_desktop_source",
                        lambda *args: {"loaded_file_attested": False,
                                       "reason": "wrong PBIP"})
    def unsafe_action(*args):
        raise AssertionError("UIA must not target unverified report")
    result = desktop_uia.run(project, 48552, {"source_sha256": source},
                             invoke=unsafe_action, attest_source=True)
    assert result["native_uia"] == "blocked"
    assert "wrong PBIP" in result["reason"]
    assert "desktop_loaded_file_attestation" in result


def test_strict_uia_carries_live_host_attestation_without_self_approving(
        tmp_path, monkeypatch):
    project = _project(tmp_path)
    source = inventory(project)[0]["digest"]
    monkeypatch.setattr(desktop_uia, "attest_desktop_source",
                        lambda *args: {"loaded_file_attested": True,
                                       "status": "pass"})
    monkeypatch.setattr(desktop_uia, "assess_native_sequence",
                        lambda *args, **kwargs: {"native_uia": "pass",
                                                 "interactive": "blocked",
                                                 "independent_acceptance": "blocked"})
    result = desktop_uia.run(project, 48552, {"source_sha256": source},
                             attest_source=True)
    assert result["native_uia"] == "pass"
    assert result["desktop_loaded_file_attested"] is True
    assert result["independent_acceptance"] == "blocked"


def test_strict_dax_revokes_attestation_if_model_source_drifts(
        tmp_path, monkeypatch):
    project = _project(tmp_path)
    target = next((project / "Contoso Retail.SemanticModel").rglob("*.tmdl"))

    class MutatingPort(FakePort):
        def query_scoped(self, *args, **kwargs):
            answer = super().query_scoped(*args, **kwargs)
            if len(self.calls) == 4:
                target.write_bytes(target.read_bytes() + b"\n// changed mid-run")
            return answer

    monkeypatch.setattr(dax, "attest_desktop_source",
                        lambda *args: {"loaded_file_attested": True,
                                       "status": "pass"})
    monkeypatch.setattr(dax, "StdioModelingClient",
                        lambda **kwargs: MutatingPort(desktop_pid=48552))
    result = dax.run(project, 48552, attest_source=True)
    assert result["semantic"] == "blocked"
    assert result["desktop_source_attested"] is False
    assert "changed during" in result["reason"]
