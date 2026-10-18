"""CLI tests (WP-19): vqs measure emits pipeline-shaped facts."""
import json
from pathlib import Path

from vqs.cli import main as vqs_main

FIXTURES = Path(__file__).parent / "fixtures"
REPORT = str(FIXTURES / "mini_report")
MODEL = str(FIXTURES / "mini_model" / "definition")


def test_measure_emits_facts_to_stdout(capsys) -> None:
    code = vqs_main(["measure", REPORT, "--model", MODEL])
    captured = capsys.readouterr()
    assert code == 0
    facts = json.loads(captured.out)
    assert facts["rules"]["typography.text_contrast"] == {"readings": [
        {"foreground": "#52617A", "background": "#FFFFFF", "page": "P1",
         "visual": "titlebox", "paragraph": 1, "role": "subtitle", "count": 1},
        {"foreground": "#101828", "background": "#FFFFFF", "page": "P1",
         "visual": "titlebox", "paragraph": 0, "role": "title", "count": 1}]}
    assert facts["models"][0]["model_dir"] == MODEL


def test_measure_writes_out_file(tmp_path: Path) -> None:
    out = tmp_path / "facts.json"
    code = vqs_main(["measure", REPORT, "--out", str(out)])
    assert code == 0
    facts = json.loads(out.read_text(encoding="utf-8"))
    assert "typography.format_declaration_consistency" in facts["rules"]
    assert "models" not in facts


def test_measure_missing_report_blocks(capsys) -> None:
    code = vqs_main(["measure", str(FIXTURES / "absent")])
    captured = capsys.readouterr()
    assert code == 2
    assert json.loads(captured.out)["status"] == "blocked"
