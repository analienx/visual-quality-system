"""Repair lost per-category palette selectors in a disposable PBIR visual.

Usage: python -m scripts.restore_categorical_colors --reference visual.json
       --candidate <scratch-copy>/visual.json --receipt <private.json>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vqs.powerbi.category_color_repair import (
    CategoryColorRepairError,
    restore_from_reference,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--disposable-root", type=Path, required=True,
                        help="explicit root containing ONLY authorized disposable candidates")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.receipt.exists() or args.receipt.is_symlink():
        parser.error("refusing to overwrite prior evidence receipt")
    try:
        outcome = restore_from_reference(
            args.reference, args.candidate, disposable_root=args.disposable_root)
    except (OSError, CategoryColorRepairError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as dest:
        json.dump(outcome, dest, indent=2)
        dest.write("\n")
    print(json.dumps(outcome, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
