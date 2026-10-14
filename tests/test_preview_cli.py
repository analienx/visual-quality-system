"""Public CLI parity with private complete-PBIP preview materializer."""
import json
from pathlib import Path

from tests.test_populated_preview import VISUAL, _project_pair
from vqs.cli import main


def test_prepare_preview_command_produces_project_not_just_report(tmp_path, capsys):
    wrapper, original, model, typed = _project_pair(tmp_path)
    dest = tmp_path / "private-preview"
    code = main([
        "prepare-preview", str(wrapper), str(typed), str(dest),
        "--visual", VISUAL,
    ])
    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "materialized"
    assert output["preview_cache_present"] is True
    assert output["semantic_runtime_readiness"] == "NOT_RUN"
    assert Path(output["preview_pbip"]).is_file()
    assert (dest / "Model.SemanticModel/.pbi/cache.abf").read_bytes() == (
        model / ".pbi/cache.abf").read_bytes()
    assert (dest / "original.Report" / VISUAL).read_bytes() == (
        typed / VISUAL).read_bytes()
    assert original.exists()


def test_prepare_preview_command_refuses_undeclared_diff(tmp_path, capsys):
    wrapper, _original, _model, typed = _project_pair(tmp_path)
    result = main([
        "prepare-preview", str(wrapper), str(typed),
        str(tmp_path / "private-preview"), "--visual",
        "definition/pages/P1/visuals/incorrect/visual.json",
    ])
    output = json.loads(capsys.readouterr().out)
    assert result == 2
    assert output["status"] == "blocked"
    assert not (tmp_path / "private-preview").exists()
