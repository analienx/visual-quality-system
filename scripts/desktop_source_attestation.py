"""Generate private, read-only Desktop file identity evidence; no Desktop edits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vqs.powerbi.contoso_project import inventory
from vqs.powerbi.desktop_source import collect


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--desktop-pid", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error("refusing overwrite of existing private identity receipt")
    result = collect(args.project, args.desktop_pid)
    try:
        project, wrapper = inventory(args.project)
        result["source_sha256"] = project["digest"]
        result["wrapper_sha256"] = wrapper
    except (OSError, ValueError, TypeError) as exc:
        result["status"] = "blocked"
        result["loaded_file_attested"] = False
        result["reason"] = f"source inventory unavailable: {type(exc).__name__}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"],
                      "loaded_file_attested": result["loaded_file_attested"],
                      "desktop_pid": args.desktop_pid,
                      "reason": result["reason"], "receipt": str(args.output)}))
    return 0 if result["loaded_file_attested"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
