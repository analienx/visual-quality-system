"""Run P16 native Desktop UIA Year + Region witness against current Contoso.

Use a disposable, already-open Contoso PBIP. Requires the P14 live DAX oracle
generated against this exact project and Desktop PID. Writes one private JSON
receipt; country Shape Map and independent G4 acceptance remain blocked.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vqs.powerbi.desktop_uia import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--desktop-pid", type=int, required=True)
    parser.add_argument("--attest-loaded-file", action="store_true",
                        help="Require exact OS/Bridge PBIP identity before any UIA action")
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error("refusing to overwrite existing private native UIA evidence")
    try:
        oracle = json.loads(args.oracle.read_text(encoding="utf-8"))
        result = run(args.project, args.desktop_pid, oracle,
                     attest_source=args.attest_loaded_file)
    except (OSError, ValueError, TypeError) as exc:
        result = {"native_uia": "blocked", "interactive": "blocked",
                  "country_map": "blocked", "independent_acceptance": "blocked",
                  "reason": f"private DAX oracle unavailable: {exc}"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"native_uia": result["native_uia"],
                      "interactive": result["interactive"],
                      "events": len(result.get("events", [])),
                      "native_actions_verified": result.get("native_actions_verified", 0),
                      "read_only_baseline_verified": result.get(
                          "read_only_baseline_verified", False),
                      "reason": result.get("reason"),
                      "receipt": str(args.output)}, indent=2))
    return 0 if result["native_uia"] == "pass" else (
        1 if result["native_uia"] == "fail" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
