"""Exercise the documented consumer gate with fictional, separate checkouts."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "contoso-retail"
WORKFLOW = ROOT / "examples" / "ci" / "powerbi-quality.yml"


@pytest.mark.parametrize(
    ("scenario", "code", "verdict"),
    [("unchanged", 0, "pass"), ("new", 1, "fail"), ("missing-base", 2, "blocked")],
)
def test_installed_gate_on_fictional_revisions(
    tmp_path: Path, scenario: str, code: int, verdict: str,
) -> None:
    workspace = tmp_path / "řešení with spaces"
    base, head = workspace / "base", workspace / "head"
    shutil.copytree(EXAMPLE, base)
    shutil.copytree(EXAMPLE, head)
    if scenario == "new":
        visual = next(head.rglob("visuals/card-096ca6e7/visual.json"))
        doc = json.loads(visual.read_text(encoding="utf-8-sig"))
        doc["visual"]["objects"]["labels"][0]["properties"]["fontSize"]["expr"][
            "Literal"]["Value"] = "30D"
        visual.write_text(json.dumps(doc), encoding="utf-8")
    baseline = base / ("missing.pbip" if scenario == "missing-base" else "Contoso Retail.pbip")
    sarif, result = tmp_path / "gate.sarif", tmp_path / "gate.json"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "-m", "vqs", "gate", str(head / "Contoso Retail.pbip"),
         "--baseline", str(baseline), "--sarif", str(sarif), "--sarif-root", str(head),
         "--out", str(result), "--github"],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False,
    )
    assert completed.returncode == code, completed.stdout + completed.stderr
    assert json.loads(result.read_text(encoding="utf-8"))["verdict"] == verdict
    log = json.loads(sarif.read_text(encoding="utf-8"))
    assert log["version"] == "2.1.0"
    results = log["runs"][0]["results"]
    if scenario == "new":
        introduced = next(item for item in results if item.get("baselineState") == "new")
        location = introduced["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        # Repository-relative, as in the consumer's repo: the checkout's
        # `head/` directory exists only on the runner, so a `head/...` path
        # could never be placed on the pull request's changed files.
        assert location == "Contoso Retail.Report/definition/report.json"
        assert "file=Contoso Retail.Report/definition/report.json" in completed.stdout
        assert "::error" in completed.stdout
    elif scenario == "missing-base":
        assert results[0]["ruleId"] == "vqs.gate.blocked"
        assert "::error" in completed.stdout


def _workflow_script(step: str) -> str:
    content = WORKFLOW.read_text(encoding="utf-8")
    section = content.split(f"      - name: {step}\n", 1)[1].split("\n      - name:", 1)[0]
    return textwrap.dedent(section.split("        run: |\n", 1)[1])


@pytest.mark.skipif(os.name == "nt", reason="workflow uses Linux bash")
def test_workflow_validation_and_quoting(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(VQS_REVISION="f" * 40, HEAD_REPORT="a/Sales.pbip", BASE_REPORT="b/Sales.pbip")
    validation = _workflow_script("Validate configuration")

    def run(script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", script], cwd=tmp_path, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )

    assert run(validation).returncode == 0
    env["VQS_REVISION"] = "REPLACE_WITH_REVIEWED_40_HEX_COMMIT"
    assert run(validation).returncode == 2
    env["VQS_REVISION"] = "f" * 40
    env["BASE_REPORT"] = "../outside.pbip"
    assert run(validation).returncode == 2
    env["BASE_REPORT"] = "b/Sales.pbip"

    # A hostile-looking report filename must remain one literal argument.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "vqs"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$ARGS_FILE"\n', encoding="utf-8")
    fake.chmod(0o755)
    env.update(
        PATH=str(bin_dir) + os.pathsep + env.get("PATH", ""),
        GITHUB_WORKSPACE=str(tmp_path), RUNNER_TEMP=str(tmp_path), ARGS_FILE=str(tmp_path / "args"),
        HEAD_REPORT="report ' $(touch injected) & å.pbip",
    )
    assert run(_workflow_script("Compare static findings")).returncode == 0
    args = (tmp_path / "args").read_text(encoding="utf-8").splitlines()
    assert args[1] == f"{tmp_path}/head/{env['HEAD_REPORT']}"
    assert args[args.index("--sarif-root") + 1] == f"{tmp_path}/head"
    assert not (tmp_path / "injected").exists()


def test_workflow_is_bounded_and_annotates_repository_paths() -> None:
    """Platform-independent checks of the copyable sample itself."""
    content = WORKFLOW.read_text(encoding="utf-8")
    # A hung gate must not hold a hosted runner for the 6-hour default.
    assert "    timeout-minutes: 20\n" in content
    # Annotations must name repository paths, not the runner's checkout dir.
    assert '--sarif-root "$GITHUB_WORKSPACE/head"' in content
    assert '--sarif-root "$GITHUB_WORKSPACE" ' not in content
