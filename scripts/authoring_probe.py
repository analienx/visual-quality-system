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
from vqs.powerbi.author import compile as metadata_compile
from vqs.powerbi.author import metadata, mscli, preflight


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
        toolchain = preflight.check("microsoft")
        if toolchain["status"] != "pass":
            raise RuntimeError("Microsoft skill/CLI preflight failed for metadata")
        report["metadata"] = {
            "catalog": metadata.query(toolchain, "catalog.describe", "barChart"),
            "property": metadata.query(toolchain, "formatting.describe_property",
                                       "barChart", "categoryAxis", "labelPrecision"),
            "object": metadata.query(toolchain, "formatting.describe_object",
                                     "barChart", "categoryAxis"),
            "effective": metadata.query(toolchain, "formatting.effective_properties",
                                        "barChart"),
            "unsupported": metadata.query(
                toolchain, "formatting.describe_property",
                "barChart", "categoryAxis", "vqsNotARealProperty"),
        }
        catalog = report["metadata"]["catalog"]
        prop = report["metadata"]["property"]
        refused = report["metadata"]["unsupported"]
        obj = report["metadata"]["object"]
        effective = report["metadata"]["effective"]
        if (catalog["status"] != "pass"
                or not {"Category", "Y"}.issubset(
                    set(catalog["data"].get("requiredRoles", [])))):
            raise RuntimeError("real Microsoft visual role catalog failed")
        if (prop["status"] != "pass"
                or prop["data"]["property"]["type"] != "integer"):
            raise RuntimeError("real Microsoft formatting-property metadata failed")
        if (obj["status"] != "pass"
                or obj["data"].get("labelPrecision", {}).get("type") != "integer"):
            raise RuntimeError("real Microsoft describe-object metadata failed")
        if (effective["status"] != "pass"
                or "categoryAxis" not in effective["data"]["visualObjects"]
                or "title" not in effective["data"]["visualContainerObjects"]):
            raise RuntimeError("real Microsoft effective-properties metadata failed")
        if refused["status"] != "blocked":
            raise RuntimeError("unknown formatting property was accepted")
        with tempfile.TemporaryDirectory(prefix="vqs-microsoft-valid-") as directory:
            root = Path(directory)
            scaffold = _scaffold(root / "project", report["cli"]["path"])
            # Source+metadata binding on a separate disposable, synthetic
            # visual. This is a metadata gate oracle, not a complete report.
            sample = root / "metadata-fixture.Report"
            target = sample / "definition/pages/P1/visuals/v1/visual.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps({
                "name": "v1",
                "visual": {"visualType": "barChart",
                           "objects": {"categoryAxis": [{
                               "properties": {"labelPrecision": {
                                   "expr": {"Literal": {"Value": "2"}}}}}]}}
            }), encoding="utf-8")
            operation = {"type": "axis.tick_format",
                         "target": "visual",
                         "selector": {"page": "P1", "visual": "v1"},
                         "path": ["visual", "objects", "categoryAxis", 0,
                                  "properties", "labelPrecision", "expr",
                                  "Literal", "Value"],
                         "value": "3",
                         "writes": ["definition/pages/P1/visuals/v1/visual.json"]}
            plan = {"operations": [operation]}
            receipt = metadata_compile.evaluate(plan, str(sample), toolchain)
            report["source_metadata_gate"] = receipt
            if receipt["status"] != "pass" or not receipt["operations"]:
                raise RuntimeError("real Microsoft metadata-bound source gate refused")
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
