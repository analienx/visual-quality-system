"""Collect current-source All/2023/2024/2025 Contoso DAX evidence.

Windows example, after opening the *same* disposable PBIP in Desktop:
  python -m scripts.contoso_p14_live_oracle <Contoso-project-dir> \
      --desktop-pid 12345 --output <new-private-oracle.json>

The Desktop PID binds the OS-owned local engine, not a loaded-PBIP file path.
There is currently no trusted Desktop-to-on-disk-source attestation; operators
must verify the opened file, and G4 remains blocked without real UI witness.
Never commit the private numeric oracle or claim that MCP metadata proves clicks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from vqs.powerbi.contoso_project import inventory as _inventory
from vqs.powerbi.contoso_runtime import CURRENT_SOURCE_CONTRACT, collect
from vqs.powerbi.modeling import StdioModelingClient

SCHEMA = CURRENT_SOURCE_CONTRACT
YEARS = (None, 2023, 2024, 2025)


def run(project: Path, pid: int) -> dict[str, Any]:
    """Run four actual DAX states, fail closed on local source/model drift.

    A caller's PID/source label is never proof Desktop opened those exact
    files. The connector OS-checks engine ownership; loaded project identity
    requires a separate trusted Desktop witness.
    """
    result: dict[str, Any] = {
        "contract": SCHEMA, "desktop_pid": pid, "semantic": "blocked",
        "interactive": "not_run", "desktop_source_attested": False,
    }
    if type(pid) is not int or pid <= 0:
        result["reason"] = "exact positive run-owned Desktop PID is mandatory"
        return result
    try:
        before, wrapper_hash = _inventory(project)
    except (OSError, ValueError) as exc:
        result["reason"] = f"current PBIP source could not be verified: {exc}"
        return result
    source = before["digest"]
    result["source_sha256"] = source
    result["local_project_source_fingerprinted"] = True
    client = StdioModelingClient(target_pid=pid)
    try:
        states = []
        connection = None
        for year in YEARS:
            state = collect(client, source, year, connection=connection)
            states.append(state)
            if connection is None and state["semantic"] == "pass":
                connection = {"model": state["model"],
                              "desktopPid": state["desktop_pid"]}
            if state["semantic"] != "pass":
                break
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result["reason"] = f"live model collection unavailable: {exc}"
        return result
    finally:
        client.close()
    result["states"] = states
    try:
        after, wrapper_after = _inventory(project)
    except (OSError, ValueError) as exc:
        result["reason"] = f"source became unreadable during DAX: {exc}"
        return result
    if before != after or wrapper_hash != wrapper_after:
        result["reason"] = "Contoso report/model/PBIP changed during DAX collection"
    elif (len(states) != 4 or any(s["semantic"] != "pass" for s in states)):
        result["reason"] = "one or more live DAX year states failed"
    elif len({s.get("model") for s in states}) != 1 or {
            s.get("desktop_pid") for s in states} != {pid}:
        result["reason"] = "model identity or OS-owned Desktop PID changed between states"
    else:
        result["semantic"] = "pass"
        result["reason"] = ("four source-labelled DAX states agree; "
                            "loaded Desktop file and clicks remain independently unverified")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--desktop-pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error("refusing to overwrite existing private runtime evidence")
    result = run(args.project, args.desktop_pid)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"semantic": result["semantic"],
                      "interactive": result["interactive"],
                      "receipt": str(args.output)}, indent=2))
    return 0 if result["semantic"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
