"""Generate private, read-only Desktop file identity evidence; no Desktop edits."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from vqs.pbir import source_digest
from vqs.powerbi.desktop_source import collect, project_artifacts


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
        wrapper, report = project_artifacts(args.project)
        result["report_source_sha256"] = source_digest(report)
        result["wrapper_sha256"] = hashlib.sha256(wrapper.read_bytes()).hexdigest()
        model = args.project / (wrapper.stem + ".SemanticModel")
        if model.is_dir() and not model.is_symlink():
            files = [f for f in model.rglob("*") if f.is_file()
                     and ".pbi" not in f.relative_to(model).parts
                     and f.name != ".platform"]
            if any(f.is_symlink() for f in model.rglob("*")):
                raise ValueError("symlinked semantic model is not an attested source")
            h = hashlib.sha256()
            for f in sorted(files):
                relative = f.relative_to(model).as_posix().encode("utf8")
                h.update(len(relative).to_bytes(4, "big"))
                h.update(relative)
                content = f.read_bytes()
                h.update(len(content).to_bytes(8, "big"))
                h.update(content)
            result["model_source_sha256"] = h.hexdigest() if files else None
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
