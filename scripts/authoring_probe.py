"""Real Microsoft PBIR authoring lane (no mocks, no Desktop, no user reports).

Create an official pinned-schema PBIP scaffold with the installed Microsoft
CLI, then prove that its exact PBIR is accepted and a deliberately corrupted
copy is rejected with structured diagnostics. Environment-dependent CLI
presence or a synthetic unit-test fixture cannot satisfy these oracles.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.report_skill import PINNED_CLI_VERSION, check, cli_check
from vqs.powerbi.author import mscli


def _scaffold(target: Path, tool: str) -> dict[str, Any]:
    cmd = [tool, "scaffold", str(target), "--name", "VQS CLI Contract",
           "--offline"]
    cp = subprocess.run(cmd, capture_output=True, text=True,
                        timeout=90, check=False)
    if cp.returncode != 0:
        raise RuntimeError(f"Microsoft scaffold failed (exit={cp.returncode}): "
                           f"{cp.stderr[-500:]}")
    try:
        obj = json.loads(cp.stdout)
        data = obj["data"]
        pbip = Path(data["pbipPath"])
        report = Path(data["reportDir"])
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError("Microsoft scaffold returned an invalid envelope") from exc
    if (not pbip.is_file() or not report.is_dir()
            or pbip.parent.resolve() != target.resolve()
            or report.parent.resolve() != target.resolve()):
        raise RuntimeError("scaffold paths do not match isolated target")
    if data.get("validation", {}).get("result") != "succeeded":
        raise RuntimeError("scaffold did not validate its own source")
    return {"command": cmd, "pbip": str(pbip), "report": str(report),
            "initial_validation": data["validation"]}


def main(argv: list[str]) -> int:
    output = Path(argv[1]) if len(argv) > 1 else Path("authoring-real-cli.json")
    report: dict[str, Any] = {
        "lane": "real-microsoft-cli",
        "oracle": "A07-positive-negative",
        "skill": check(),
        "cli": cli_check(),
        "valid": None, "invalid": None,
    }
    verdict = False
    try:
        if report["skill"]["status"] != "pass" or report["cli"]["status"] != "pass":
            raise RuntimeError("reviewed skill or pinned CLI unavailable")
        if report["cli"]["version"] != PINNED_CLI_VERSION:
            raise RuntimeError("unexpected Microsoft CLI version")
        with tempfile.TemporaryDirectory(prefix="vqs-microsoft-valid-") as directory:
            root = Path(directory)
            scaffold = _scaffold(root / "project", report["cli"]["path"])
            pbip = Path(scaffold["pbip"])
            genuine = mscli.validate(pbip)
            report["valid"] = genuine
            if genuine["status"] != "valid" or genuine["warnings"]:
                raise RuntimeError("positive control: official PBIP scaffold rejected")
            # Corrupt the isolated project, not the original or the valid result.
            definition = Path(scaffold["report"]) / "definition.pbir"
            definition.write_text("{ invalid json", encoding="utf-8")
            rejected = mscli.validate(pbip)
            report["invalid"] = rejected
            if rejected["status"] != "invalid" or not rejected["errors"]:
                raise RuntimeError("negative control: corrupted PBIR was not rejected")
            verdict = True
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        report["failure"] = str(exc)
    report["verdict"] = "pass" if verdict else "fail"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
                      encoding="utf-8")
    print("Microsoft real PBIR fixture:",
          report["verdict"],
          "valid=", (report["valid"] or {}).get("status"),
          "invalid=", (report["invalid"] or {}).get("status"),
          "reason=", report.get("failure", ""))
    return 0 if verdict else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
