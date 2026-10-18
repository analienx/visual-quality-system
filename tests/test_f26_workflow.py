"""F26: one integrated six-tool workflow on installed entry points.

The engine chain (inspect/review/propose/repair/verify/status) runs on
synthetic report projects, and the installed ``vqs`` CLI plus ``vqs-mcp``
stdio server drive the same engine from outside-checkout working
directories against two independently shaped synthetic projects, with
negative controls and resume-after-change. Synthetic fixtures prove
contract handling, never live visual/data approval.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "powerbi" / "fixtures"
VQS_BIN = shutil.which("vqs")
MCP_BIN = shutil.which("vqs-mcp")

needs_vqs = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs entry point not on PATH")
needs_mcp = pytest.mark.skipif(MCP_BIN is None,
                               reason="installed vqs-mcp entry point missing")

EXIT_BY_VERDICT = {"pass": 0, "fail": 1, "blocked": 2}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _copy_project(root: Path, name: str) -> tuple[Path, Path]:
    """Copy the miniature fixtures into an isolated synthetic project."""
    report = root / f"{name}.Report"
    model = root / f"{name}.SemanticModel"
    shutil.copytree(FIX / "mini_report", report)
    shutil.copytree(FIX / "mini_model", model)
    return report, model


def _shape_alpha(report: Path) -> None:
    """Value-level reshape: same structure, own display values."""
    page_path = report / "definition" / "pages" / "P1" / "page.json"
    page = _read_json(page_path)
    page["displayName"] = "Alpha overview"
    _write_json(page_path, page)
    card = _read_json(report / "definition" / "pages" / "P1" / "visuals"
                      / "cardx" / "visual.json")
    title = card["visual"]["visualContainerObjects"]["title"][0]
    title["properties"]["text"]["expr"]["Literal"]["Value"] = "'Alpha revenue'"
    _write_json(report / "definition" / "pages" / "P1" / "visuals"
                / "cardx" / "visual.json", card)


def _shape_beta(report: Path) -> None:
    """Structural reshape: a second page with renamed visuals."""
    pages = report / "definition" / "pages"
    page_path = pages / "P1" / "page.json"
    page = _read_json(page_path)
    page["displayName"] = "Beta overview"
    _write_json(page_path, page)
    shutil.copytree(pages / "P1", pages / "P2")
    grown = _read_json(pages / "P2" / "page.json")
    grown["name"] = "P2"
    grown["displayName"] = "Beta detail"
    _write_json(pages / "P2" / "page.json", grown)
    index = _read_json(report / "definition" / "pages.json")
    index["pageOrder"] = ["P1", "P2"]
    _write_json(report / "definition" / "pages.json", index)
    renames = {"cardx": "cardy", "slicera": "slicerd", "slicerb": "slicere",
               "slicerc": "slicerf", "titlebox": "titleb"}
    for old, new in renames.items():
        (pages / "P2" / "visuals" / old).rename(
            pages / "P2" / "visuals" / new)
        visual = _read_json(pages / "P2" / "visuals" / new / "visual.json")
        visual["name"] = new
        _write_json(pages / "P2" / "visuals" / new / "visual.json", visual)
    card_path = pages / "P2" / "visuals" / "cardy" / "visual.json"
    card = _read_json(card_path)
    labels = card["visual"]["objects"]["labels"][0]["properties"]
    labels["fontSize"]["expr"]["Literal"]["Value"] = "20D"
    title = card["visual"]["visualContainerObjects"]["title"][0]
    title["properties"]["text"]["expr"]["Literal"]["Value"] = "'Beta cost'"
    _write_json(card_path, card)


def _size_plan(page: str, visual: str, value: str) -> dict:
    target = f"definition/pages/{page}/visuals/{visual}/visual.json"
    return {
        "operations": [{
            "type": "typography.size", "target": "visual",
            "selector": {"page": page, "visual": visual},
            "path": ["visual", "objects", "labels", 0, "properties",
                     "fontSize", "expr", "Literal", "Value"],
            "value": value, "writes": [target]}],
        "write_targets": [target],
        "rollback": "re-materialize from original",
    }


def _vqs(*argv: str, cwd: Path) -> tuple[int, dict]:
    # Synthetic fixtures intentionally omit mandatory Microsoft PBIR details.
    # Make direct/static fixture validation explicit for *subprocess* tests;
    # ambient global CLI installation must never alter their oracle.
    if argv and argv[0] == "repair" and "--authoring-backend" not in argv:
        argv = (*argv, "--authoring-backend", "direct")
    proc = subprocess.run([VQS_BIN, *argv], cwd=cwd, capture_output=True,
                          text=True, timeout=300, check=False)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except ValueError:
        raise AssertionError(
            f"vqs {' '.join(argv)} rc={proc.returncode} "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}")


def test_f26_engine_chain_seals_and_verifies(tmp_path: Path) -> None:
    from vqs.pipeline import (
        inspect_report,
        propose_candidates,
        repair_candidate,
        review_report,
        run_status_report,
        verify_candidate,
    )

    report, model = _copy_project(tmp_path, "Alpha")
    _shape_alpha(report)
    model_def = str(model / "definition")
    runs = str(tmp_path / "runs")
    inspected = inspect_report(str(report), model_def)
    assert inspected["verdict"] == "pass"
    reviewed = review_report(report_dir=str(report), model_dir=model_def,
                             run_root=runs, run_id="rev-a")
    assert reviewed["run_dir"] is not None
    triage = propose_candidates(runs, "rev-a")
    assert triage["verdict"] == "pass"
    assert triage["work_items"]
    assert triage["candidates"] == []
    plan_path = tmp_path / "plan-a.json"
    _write_json(plan_path, _size_plan("P1", "cardx", "26D"))
    candidate = str(tmp_path / "cand-a")
    repaired = repair_candidate(str(plan_path), str(report), candidate,
                                run_root=runs, run_id="rep-a")
    assert repaired["verdict"] == "pass"
    assert repaired["run_dir"] is not None
    assert Path(candidate).is_dir()
    assert verify_candidate(run_root=runs, run_id="rep-a")[
        "verdict"] == "pass"
    assert run_status_report(runs, "rep-a")["verdict"] == "pass"
    assert run_status_report(runs, "rev-a")["verdict"] == reviewed["verdict"]
    # Cross-type guards: runs only feed their own downstream tool.
    assert "not a sealed review run" in " ".join(
        propose_candidates(runs, "rep-a")["blocked_reasons"])
    assert "not a sealed repair run" in " ".join(
        verify_candidate(run_root=runs, run_id="rev-a")["blocked_reasons"])
    # Negative control: an undeclared post-repair edit fails verification.
    stray = Path(candidate) / "definition" / "pages" / "P1" / "visuals" \
        / "titlebox" / "visual.json"
    stray_doc = _read_json(stray)
    stray_doc["displayName"] = "tampered"
    _write_json(stray, stray_doc)
    assert verify_candidate(run_root=runs, run_id="rep-a")[
        "verdict"] == "fail"


@needs_vqs
def test_f26_installed_cli_two_projects(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    alpha, alpha_model = _copy_project(tmp_path, "Alpha")
    _shape_alpha(alpha)
    beta, beta_model = _copy_project(tmp_path, "Beta")
    _shape_beta(beta)
    alpha_pages = _read_json(
        alpha / "definition" / "pages.json")["pageOrder"]
    beta_pages = _read_json(beta / "definition" / "pages.json")["pageOrder"]
    assert alpha_pages == ["P1"]
    assert beta_pages == ["P1", "P2"]
    projects = (
        ("a", alpha, alpha_model, "P1", "cardx", "26D"),
        ("b", beta, beta_model, "P2", "cardy", "22D"),
    )
    for tag, report, model, page, visual, size in projects:
        runs = tmp_path / f"runs-{tag}"
        code, reviewed = _vqs(
            "review", str(report), "--model", str(model / "definition"),
            "--run-root", str(runs), "--run-id", f"rev-{tag}", cwd=work)
        assert code == EXIT_BY_VERDICT[reviewed["verdict"]]
        assert reviewed["run_dir"] is not None
        code, triage = _vqs("propose", "--run-root", str(runs),
                            "--run-id", f"rev-{tag}", cwd=work)
        assert code == 0
        assert triage["work_items"]
        plan_path = tmp_path / f"plan-{tag}.json"
        _write_json(plan_path, _size_plan(page, visual, size))
        candidate = tmp_path / f"cand-{tag}"
        code, repaired = _vqs(
            "repair", str(plan_path), "--original", str(report),
            "--candidate-root", str(candidate), "--run-root", str(runs),
            "--run-id", f"rep-{tag}", cwd=work)
        assert code == 0
        assert repaired["verdict"] == "pass"
        assert candidate.is_dir()
        code, verified = _vqs("verify", "--run-root", str(runs),
                              "--run-id", f"rep-{tag}", cwd=work)
        assert code == 0
        assert verified["verdict"] == "pass"
        assert verified["evidence"][0]["kind"] == "verification"
        code, status = _vqs("run-status", str(runs), f"rep-{tag}", cwd=work)
        assert code == 0
        assert status["verdict"] == "pass"
    # Negative controls through the installed CLI.
    runs_a = tmp_path / "runs-a"
    bad_plan = tmp_path / "bad-plan.json"
    ghost = _size_plan("P1", "cardx", "26D")
    ghost["operations"][0]["selector"] = {"page": "P1", "visual": "ghost"}
    _write_json(bad_plan, ghost)
    code, bad = _vqs("repair", str(bad_plan), "--original", str(alpha),
                     "--candidate-root", str(tmp_path / "cand-bad"),
                     "--run-root", str(runs_a), "--run-id", "rep-bad",
                     cwd=work)
    assert code == 2
    assert bad["verdict"] == "blocked"
    stray = tmp_path / "cand-a" / "definition" / "pages" / "P1" / "visuals" \
        / "titlebox" / "visual.json"
    stray_doc = _read_json(stray)
    stray_doc["displayName"] = "tampered"
    _write_json(stray, stray_doc)
    code, tampered = _vqs("verify", "--run-root", str(runs_a),
                          "--run-id", "rep-a", cwd=work)
    assert code == 1
    assert tampered["verdict"] == "fail"
    code, _ = _vqs("propose", "--run-root", str(runs_a),
                   "--run-id", "nope", cwd=work)
    assert code == 2
    code, _ = _vqs("run-status", str(runs_a), "../..", cwd=work)
    assert code == 2
    # Resume-after-change through the installed CLI.
    facts_path = tmp_path / "facts.json"
    _write_json(facts_path, {"rules": {}})
    code, first = _vqs("review", "--facts", str(facts_path),
                       "--run-root", str(runs_a), "--run-id", "res-1",
                       cwd=work)
    assert code == EXIT_BY_VERDICT[first["verdict"]]
    assert first["run_dir"] is not None
    code, same = _vqs("review", "--facts", str(facts_path),
                      "--run-root", str(runs_a), "--run-id", "res-2",
                      "--resume-from", "res-1", cwd=work)
    assert code == EXIT_BY_VERDICT[same["verdict"]]
    assert same["run_dir"] is not None
    facts_path.write_text(json.dumps({"rules": {"nope.rule": {}}}),
                          encoding="utf-8")
    code, changed = _vqs("review", "--facts", str(facts_path),
                         "--run-root", str(runs_a), "--run-id", "res-3",
                         "--resume-from", "res-1", cwd=work)
    assert code == 2
    assert changed["verdict"] == "blocked"


@needs_mcp
def test_f26_installed_mcp_matches_engine(tmp_path: Path) -> None:
    from vqs.pipeline import review_report

    report, model = _copy_project(tmp_path, "Gamma")
    model_def = str(model / "definition")
    runs = str(tmp_path / "runs")
    engine = review_report(report_dir=str(report), model_dir=model_def,
                           run_root=runs, run_id="eng-1")
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "f26", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "vqs_review",
                    "arguments": {"report_dir": str(report),
                                  "model_dir": model_def,
                                  "run_root": runs, "run_id": "mcp-1"}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "vqs_run_status",
                    "arguments": {"run_root": runs, "run_id": "../.."}}},
    ]
    proc = subprocess.run(
        [MCP_BIN], cwd=tmp_path, capture_output=True, text=True,
        input="".join(json.dumps(req) + "\n" for req in requests),
        timeout=300, check=False)
    assert proc.returncode == 0
    responses = [json.loads(line) for line in proc.stdout.splitlines()
                 if line.strip()]
    assert [resp.get("id") for resp in responses] == [1, 2, 3]
    mcp = json.loads(responses[1]["result"]["content"][0]["text"])
    assert mcp["verdict"] == engine["verdict"]
    assert mcp["findings"] == engine["findings"]
    assert mcp["coverage"] == engine["coverage"]
    assert mcp["run_dir"] is not None
    traversal = json.loads(responses[2]["result"]["content"][0]["text"])
    assert traversal["verdict"] == "blocked"
