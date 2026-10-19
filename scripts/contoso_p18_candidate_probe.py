"""Reproduce P18 detection → typed repair on the pinned P10 Contoso fixture.

This is a **private, disposable validation probe**, not a way to overwrite or
publish customer reports. The caller supplies a fresh workspace; the script
refuses any existing destination. It prints a small, source-safe receipt.
Desktop screenshot and live DAX acceptance are separate explicit gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from scripts.contoso_p12_layout_repair import FIXTURE, MANIFEST
from vqs.design_rules import layout_composition
from vqs.powerbi.measure import measure_report
from vqs.repair.execute import apply_plan, tree_digest
from vqs.repair.regress import verify_candidate
from vqs.repair.synthesize import synthesize_plan


def _checked_unpack(destination: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if hashlib.sha256(FIXTURE.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("archived source checksum mismatch")
    with zipfile.ZipFile(FIXTURE) as archive:
        paths = archive.namelist()
        if len(paths) != manifest["files"]:
            raise ValueError("archived source inventory mismatch")
        for name in paths:
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                raise ValueError(f"unsafe archived path: {name!r}")
        destination.mkdir(parents=True)
        archive.extractall(destination)


def run(workspace: Path) -> dict:
    """Produce one source-bound, atomically applied candidate in a fresh root."""
    if workspace.exists():
        raise FileExistsError(f"refusing to reuse candidate workspace: {workspace}")
    source_project = workspace / "source"
    candidate = workspace / "candidate" / "Contoso Retail.Report"
    _checked_unpack(source_project)
    source = source_project / "Contoso Retail.Report"
    before = tree_digest(source)
    measured = measure_report(str(source))
    verdict = layout_composition(measured["rules"]["layout.composition"]["pages"])
    if verdict["status"] != "fail":
        raise ValueError("pinned pre-repair source did not reproduce failure")
    proposed = synthesize_plan([
        {"check": "layout.composition", "status": "fail", "detail": verdict}],
        measured, source_run_id="p18-pinned-contoso")
    plan = proposed["plan"]
    if plan is None or proposed["decisions"]:
        raise ValueError(f"the pre-repair source is not solvable: {proposed['decisions']}")
    applied = apply_plan(plan, str(source), str(candidate))
    if applied["verdict"] != "applied":
        return {"verdict": "blocked", "stage": applied.get("stage"),
                "reason": applied.get("reason"),
                "original_unchanged": tree_digest(source) == before}
    after = measure_report(str(candidate))
    composition = layout_composition(after["rules"]["layout.composition"]["pages"])
    confined = verify_candidate(source, candidate, applied["edits"])
    unchanged = tree_digest(source) == before
    return {
        "verdict": ("candidate_only" if composition["status"] == "pass"
                    and confined["verdict"] == "pass" and unchanged else "fail"),
        "source_sha256": before,
        "candidate_sha256": tree_digest(candidate),
        "source_unchanged": unchanged,
        "composition_before": verdict["status"],
        "composition_after": composition["status"],
        "repair_confinement": confined["verdict"],
        "operations": len(plan["operations"]),
        "changed_visual_files": len(plan["write_targets"]),
        "candidate_report": str(candidate),
        "affected_pages": applied["affected_pages"],
        "microsoft_validation": "not_run",
        "native_render_and_data": "blocked_pending_probe",
        "independent_acceptance": "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path,
                        help="A fresh disposable project workspace")
    args = parser.parse_args()
    receipt = run(args.workspace.resolve())
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if receipt["verdict"] == "candidate_only" else 2


if __name__ == "__main__":
    raise SystemExit(main())
