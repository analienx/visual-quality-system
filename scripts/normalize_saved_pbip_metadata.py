"""Source-grounded, metadata-only fix for disposable saved Desktop PBIPs.

The result is never evidence of Desktop saved-source, G2, G4 or G6 acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vqs.powerbi.desktop_saved_metadata import normalize_saved_metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--disposable-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error("refusing overwrite of existing private receipt")
    try:
        result = normalize_saved_metadata(
            args.project, disposable_root=args.disposable_root,
            apply=args.apply,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        result = {
            "schema": "vqs.saved-pbip-metadata-normalization/1",
            "status": "blocked", "reason": str(exc),
            "desktop_loaded_file_attested": False,
            "independent_g2_g4_g6": "blocked",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
