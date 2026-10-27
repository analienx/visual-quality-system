"""Current-source oracle: positive and adversarial Desktop/MCP guards."""
from __future__ import annotations

import json
import zipfile

import pytest

from scripts import contoso_p11_semantic_probe as historical
from scripts import contoso_p14_live_oracle as cli
from tests.test_contoso_p11_semantic_oracle import FakePort
from vqs.pbir import source_digest


def _project(tmp_path):
    with zipfile.ZipFile(historical.FIXTURE) as archive:
        archive.extractall(tmp_path)
    return tmp_path


def test_p14_current_source_actual_years_shared_model_and_os_pid(tmp_path, monkeypatch):
    project = _project(tmp_path)
    port = FakePort(desktop_pid=442)
    monkeypatch.setattr(cli, "StdioModelingClient", lambda **kw: port)
    actual = source_digest(project / "Contoso Retail.Report")
    result = cli.run(project, 442)
    assert result["contract"] == cli.SCHEMA
    assert result["semantic"] == "pass"
    assert result["interactive"] == "not_run"
    assert result["desktop_source_attested"] is False
    assert result["source_sha256"] == actual
    assert result["local_project_source_fingerprinted"] is True
    assert [s["year"] for s in result["states"]] == [None, 2023, 2024, 2025]
    assert all(s["semantic"] == "pass" and s["source_sha256"] == actual
               for s in result["states"])
    assert port.connect_calls == 1
    assert len(port.calls) == 13
    assert result["region_europe_2024"]["semantic"] == "pass"
    assert result["region_europe_2024"]["kpis"]["Sales"] == 80.
    assert result["region_scope_semantic"] == "pass"


def test_wrong_or_absent_pbip_blocks_before_any_model_connection(tmp_path, monkeypatch):
    class NoClient:
        def __init__(self, **kwargs):
            raise AssertionError("invalid source must not touch Desktop")

    monkeypatch.setattr(cli, "StdioModelingClient", NoClient)
    assert cli.run(tmp_path, 40)["semantic"] == "blocked"
    project = _project(tmp_path)
    wrapper = project / "Contoso Retail.pbip"
    wrapper.write_text(json.dumps({"artifacts": []}), encoding="utf-8")
    assert "wrapper" in cli.run(project, 40)["reason"]


def test_missing_or_mutated_model_reference_blocks(tmp_path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr(cli, "StdioModelingClient", lambda **kw: FakePort())
    definition = project / "Contoso Retail.Report/definition.pbir"
    definition.write_text(json.dumps({"datasetReference": {
        "byConnection": {"connectionString": "remote"}}}), encoding="utf-8")
    result = cli.run(project, 4242)
    assert result["semantic"] == "blocked"
    assert "unresolved" in result["reason"]


def test_cross_year_wrong_pid_blocks_even_if_dax_numbers_match(tmp_path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr(cli, "StdioModelingClient",
                        lambda **kw: FakePort(desktop_pid=10))
    result = cli.run(project, 12)
    assert len(result["states"]) == 4
    assert result["semantic"] == "blocked"
    assert "PID" in result["reason"]


def test_model_source_swap_during_live_query_fails_closed(tmp_path, monkeypatch):
    project = _project(tmp_path)
    target = next((project / "Contoso Retail.SemanticModel").rglob("*.tmdl"))

    class MutatingPort(FakePort):
        def query_scoped(self, *args, **kwargs):
            result = super().query_scoped(*args, **kwargs)
            if len(self.calls) == 4:
                target.write_bytes(target.read_bytes() + b"\n// changed mid-run")
            return result

    monkeypatch.setattr(cli, "StdioModelingClient",
                        lambda **kw: MutatingPort())
    result = cli.run(project, 4242)
    assert result["semantic"] == "blocked"
    assert "changed during" in result["reason"]


def test_symlinked_model_source_does_not_get_silently_omitted(tmp_path, monkeypatch):
    project = _project(tmp_path)
    target = next((project / "Contoso Retail.SemanticModel").rglob("*.tmdl"))
    shadow = tmp_path / "shadow.tmdl"
    shadow.write_bytes(target.read_bytes())
    target.unlink()
    try:
        target.symlink_to(shadow)
    except (OSError, NotImplementedError) as exc:
        # Windows without symlink privilege cannot construct this fixture.
        # Keep the negative control active on symlink-capable hosts.
        pytest.skip(f"filesystem symlinks unavailable: {exc}")
    monkeypatch.setattr(cli, "StdioModelingClient",
                        lambda **kw: (_ for _ in ()).throw(AssertionError("no MCP")))
    result = cli.run(project, 4242)
    assert result["semantic"] == "blocked"
    assert "symlink" in result["reason"]


def test_live_oracle_cli_persists_blocked_receipt_and_refuses_overwrite(
        tmp_path, capsys):
    output = tmp_path / "private-dax.json"
    argv = [str(tmp_path), "--desktop-pid", "342", "--output", str(output)]
    assert cli.main(argv) == 2
    assert json.loads(output.read_text(encoding="utf-8"))["semantic"] == "blocked"
    assert json.loads(capsys.readouterr().out)["interactive"] == "not_run"
    with pytest.raises(SystemExit, match="2"):
        cli.main(argv)


def test_current_source_cli_end_to_end_writes_four_year_receipt(
        tmp_path, monkeypatch, capsys):
    project = _project(tmp_path)
    monkeypatch.setattr(cli, "StdioModelingClient",
                        lambda **kwargs: FakePort(desktop_pid=213))
    output = tmp_path / "current-run-oracle.json"
    assert cli.main([str(project), "--desktop-pid", "213", "--output",
                     str(output)]) == 0
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["semantic"] == "pass"
    assert receipt["source_sha256"] == source_digest(project / "Contoso Retail.Report")
    assert len(receipt["states"]) == 4
    assert receipt["desktop_source_attested"] is False
    assert json.loads(capsys.readouterr().out)["semantic"] == "pass"
