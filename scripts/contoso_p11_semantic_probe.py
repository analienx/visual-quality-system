"""Run source-bound P11 live Contoso DAX checks on the owned Desktop model.

Example (Windows, in a run-owned disposable Contoso P10 project):
  python -m scripts.contoso_p11_semantic_probe <P10-project> --desktop-pid 12345 \
      --year all --year 2024 --year 2025 --output <private-receipt.json>

This command does not manipulate Power BI Desktop, reports, or the model.
Run evidence contains Contoso aggregated numbers: keep it private, not in Git.
It intentionally cannot proclaim screenshot or interaction acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from vqs.pbir import IMAGE_EXTENSIONS, SOURCE_EXTENSIONS, source_digest
from vqs.powerbi.contoso_runtime import SOURCE_CONTRACT, collect
from vqs.powerbi.modeling import StdioModelingClient

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests/fixtures/contoso-retail-polished-insights-p10.manifest.json"
FIXTURE = ROOT / "tests/fixtures/contoso-retail-polished-insights-p10.zip"


def _year(value: str) -> int | None:
    if value.lower() == "all":
        return None
    try:
        year = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("year must be numeric or 'all'") from exc
    if year not in (2023, 2024, 2025):
        raise argparse.ArgumentTypeError("supported Contoso year: all, 2023, 2024, 2025")
    return year


def _source_name(name: str) -> bool:
    path = Path(name)
    if (not path.parts or path.parts[0] not in (
            "Contoso Retail.Report", "Contoso Retail.SemanticModel")
            or ".pbi" in path.parts):
        return False
    return (path.suffix.lower() in SOURCE_EXTENSIONS or
            ("StaticResources" in path.parts
             and path.suffix.lower() in IMAGE_EXTENSIONS))


def _fixture_matches(project: Path, manifest: dict) -> str | None:
    """Compare actual report/model bytes to the archived screenshot-bound P10.

    ``vqs.pbir.source_digest`` has yielded different values for identical
    archived files on Linux and Windows. Exact filename+bytes parity is the
    portable authority; the manifest carries the stable P10 source identity.
    """
    if hashlib.sha256(FIXTURE.read_bytes()).hexdigest() != manifest["sha256"]:
        return "committed P10 fixture SHA differs from its manifest"
    with zipfile.ZipFile(FIXTURE) as archive:
        expected = {n for n in archive.namelist() if _source_name(n)}
        if not expected:
            return "P10 fixture has no source files"
        for name in expected:
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts:
                return "P10 fixture has unsafe source path"
            path = project / rel
            if path.is_symlink() or not path.is_file() or path.read_bytes() != archive.read(name):
                return f"P10 source/model drift: {name}"
    actual = {p.relative_to(project).as_posix() for top in (
        "Contoso Retail.Report", "Contoso Retail.SemanticModel")
        for p in (project / top).rglob("*") if p.is_file() and _source_name(
            p.relative_to(project).as_posix())}
    if actual != expected:
        return "extra or missing report/model source files"
    return None


def run(project: Path, pid: int, years: list[int | None]) -> dict:
    """Refuse wrong sources before making *any* live MCP query."""
    report = project / "Contoso Retail.Report"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    desired = manifest["report_model_source_sha256"]
    receipt: dict = {"contract": SOURCE_CONTRACT,
                     "p10_historical_fingerprint": desired, "desktop_pid": pid,
                     "semantic": "blocked", "interactive": "not_run"}
    if not report.is_dir():
        receipt["reason"] = "P10 report directory absent"
        return receipt
    try:
        mismatch = _fixture_matches(project, manifest)
        if mismatch:
            receipt["reason"] = mismatch
            return receipt
        actual = source_digest(report)
    except (OSError, ValueError) as exc:
        receipt["reason"] = f"could not fingerprint project: {exc}"
        return receipt
    # Use the screenshot-bound manifest identity only after byte-for-byte
    # verification. The local source_digest is diagnostic until cross-platform
    # inventory ordering is normalized elsewhere.
    receipt["source_sha256"] = desired
    receipt["vqs_runtime_source_digest"] = actual
    receipt["source_verified_against_p10_fixture"] = True
    if type(pid) is not int or pid <= 0:
        receipt["reason"] = "an exact run-owned Desktop PID is mandatory"
        return receipt
    client = StdioModelingClient(target_pid=pid)
    try:
        results = []
        bound_connection = None
        for year in years:
            state = collect(client, desired, year, connection=bound_connection)
            results.append(state)
            if bound_connection is None and state["semantic"] == "pass":
                bound_connection = {"model": state["model"],
                                    "desktopPid": state["desktop_pid"]}
    finally:
        client.close()
    receipt["states"] = results
    all_pass = bool(results) and all(row["semantic"] == "pass" for row in results)
    stable_model = len({row.get("model") for row in results}) == 1
    stable_pid = {row.get("desktop_pid") for row in results} == {pid}
    receipt["semantic"] = "pass" if all_pass and stable_model and stable_pid else "blocked"
    if all_pass and not (stable_model and stable_pid):
        receipt["reason"] = "cross-year model identity or Desktop PID changed"
    elif receipt["semantic"] == "blocked":
        receipt["reason"] = "one or more year states lack executed DAX parity"
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--desktop-pid", type=int, required=True)
    parser.add_argument("--year", action="append", type=_year, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(set(args.year)) != len(args.year):
        parser.error("year states must be unique")
    if args.output.exists():
        parser.error("refusing to overwrite existing runtime evidence")
    evidence = run(args.project, args.desktop_pid, args.year)
    # Private run-owned output, never a fixture or repo-wide artifact.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"semantic": evidence["semantic"],
                      "interactive": evidence["interactive"],
                      "receipt": str(args.output)}, indent=2))
    return 0 if evidence["semantic"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
