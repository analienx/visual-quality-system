"""Corporate Spend exact-PID native Region G4, with independent live DAX.

Private-only evidence. Never asserts authorized human G2/G4/G6 approvals.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vqs.powerbi.desktop_native_provenance import snapshot
from vqs.powerbi.desktop_source import collect, project_artifacts, strict_local_model_attested
from vqs.powerbi.modeling import ModelingScope, StdioModelingClient
from vqs.powerbi.native_capture_provenance import _os_identity, _status

SCHEMA = "vqs.corporate-native-region-g4/1"
DAX = (
    "EVALUATE SUMMARIZECOLUMNS("
    "'Country Region'[Sales Region], "
    '"VarPct", [Var to Plan %])'
)
STEPS = ("Europe", "Latin America", "Europe")


def validate_step(
    receipt: Mapping[str, Any],
    values: Mapping[str, float],
    *,
    expected: str,
    prior: str | None,
    pid: int,
    pbip: Path,
) -> dict[str, Any]:
    """False-positive protection for actual native selection and rendered KPI."""
    if expected not in ("Europe", "Latin America"):
        raise ValueError("unapproved Region value")
    if (receipt.get("schema") != "vqs.native-corporate-region-uia/1"
            or receipt.get("pid") != pid
            or receipt.get("pbip") != str(pbip)
            or receipt.get("target") != expected
            or receipt.get("control_name") != "Sales Region"
            or receipt.get("action") != (
                "TogglePattern + ExpandCollapsePattern.Collapse")
            or receipt.get("selected_target") is not True
            or receipt.get("other_region_unselected") is not True):
        raise ValueError("native UIA receipt does not attest target selection")
    observed = receipt.get("observed")
    if not isinstance(observed, str) or not (
            observed == expected or observed.startswith(expected + " ")):
        raise ValueError("collapsed native Region label does not match")
    before = receipt.get("before")
    if prior is not None and (
            not isinstance(before, str) or not before.startswith(prior)):
        raise ValueError("region state progression differs from expected")
    if type(receipt.get("variance_pct_ui")) not in (int, float):
        raise ValueError("native rendered KPI is not numeric")
    current = float(receipt["variance_pct_ui"])
    oracle = values.get(expected)
    other = values.get("Europe" if expected == "Latin America" else "Latin America")
    if oracle is None or other is None or not (
            math.isfinite(current) and math.isfinite(oracle) and math.isfinite(other)):
        raise ValueError("complete independent DAX reference unavailable")
    if not math.isclose(current, oracle * 100, abs_tol=0.055, rel_tol=0):
        raise ValueError("rendered card does not match scoped live DAX")
    if math.isclose(current, other * 100, abs_tol=0.055, rel_tol=0):
        raise ValueError("different Region DAX indistinguishable; no proof of filter")
    return {
        "target": expected,
        "native_value_committed": True,
        "rendered_kpi_matches_independent_dax": True,
        "different_from_other_region": True,
    }


def run(project: Path, pid: int, save_receipt: Mapping[str, Any],
        *, adapter: Path) -> dict[str, Any]:
    """Execute bounded actions only after strict native saved-source attestation."""
    if type(pid) is not int or pid < 1:
        raise ValueError("invalid Power BI Desktop PID")
    project = project.resolve(strict=True)
    pbip = next(project.glob("*.pbip"))
    _os_identity(pid, pbip.resolve())
    prior_source = snapshot(project)
    if save_receipt.get("native_saved_source_verified") is not True or (
            prior_source != save_receipt.get("manifest_after")):
        raise ValueError("exact saved-source witness missing/stale")
    state = collect(project, pid, native_save_witness=save_receipt)
    if state.get("status") != "pass" or not strict_local_model_attested(state):
        raise ValueError("Desktop loaded model/source not strictly attested")
    if not adapter.is_file():
        raise ValueError("approved native UIA adapter missing")
    client = StdioModelingClient(target_pid=pid, timeout=50)
    try:
        model = client.connect()
        if model.get("desktopPid") != pid:
            raise ValueError("live DAX engine attached to wrong Desktop")
        reply = client.query_scoped(DAX, ModelingScope(), max_rows=20)
        values: dict[str, float] = {}
        for item in reply["rows"]:
            region = item["Country Region[Sales Region]"]
            pct = item["[VarPct]"]
            if region in values or not isinstance(pct, (int, float)):
                raise ValueError("missing or ambiguous DAX region reference")
            values[str(region)] = float(pct)
        if not all(k in values for k in ("Europe", "Latin America")):
            raise ValueError("unrelated DAX regional reference missing")
        steps: list[dict[str, Any]] = []
        prior: str | None = None
        for name in STEPS:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-File", str(adapter), "-DesktopProcessId", str(pid),
                 "-ExpectedPbip", str(pbip), "-TargetRegion", name],
                capture_output=True, text=True, encoding="utf-8-sig",
                errors="replace", timeout=55, check=False,
            )
            if result.returncode:
                raise ValueError("native UIA region action rejected: "
                                 + result.stderr[-240:])
            receipt = json.loads(result.stdout)
            steps.append(validate_step(
                receipt, values, expected=name, prior=prior, pid=pid,
                pbip=pbip.resolve()))
            prior = name
            if snapshot(project) != prior_source:
                raise ValueError("source changed during native interaction")
            _os_identity(pid, pbip.resolve())
        _, report = project_artifacts(project)
        bridge = shutil.which("powerbi-desktop")
        if not bridge:
            raise ValueError("native Desktop Bridge CLI unavailable")
        last = _status(bridge, pid, pbip.resolve(), report.resolve())
        if type(last.get("hasUnsavedChanges")) is not bool:
            raise ValueError("native interaction did not report Desktop dirty state")
        return {
            "schema": SCHEMA,
            "status": "pass_bounded_engineering",
            "source_unchanged": True,
            "desktop_pid": pid,
            "source_files": len(prior_source),
            "desktop_unsaved_after_actions": last["hasUnsavedChanges"],
            "steps": steps,
            "human_g2_g4_signed": False,
            "owner_g6_approved": False,
        }
    finally:
        client.close()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--native-save", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("refusing to overwrite private G4 evidence")
    script = Path(__file__).resolve().parent / "native_scripts" / "corporate_region_uia.ps1"
    try:
        receipt = run(args.project, args.pid,
                      json.loads(args.native_save.read_text("utf8")),
                      adapter=script)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        receipt = {"schema": SCHEMA, "status": "blocked", "reason": str(exc),
                   "owner_g6_approved": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as f:
        json.dump(receipt, f, indent=2)
        f.write("\n")
    print(json.dumps(receipt))
    return 0 if receipt["status"] == "pass_bounded_engineering" else 2


if __name__ == "__main__":
    raise SystemExit(main())
