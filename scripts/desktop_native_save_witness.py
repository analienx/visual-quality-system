"""Create a private, run-owned, source-hashed native Desktop Save witness.

Invokes Save ONLY on explicitly authorized disposable scratch Desktop sessions.
This never self-approves independent G2/G4/G6 or publishes files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vqs.powerbi.desktop_native_save import save_and_witness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--desktop-pid", type=int, required=True)
    parser.add_argument("--disposable-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--invoke-native-save", action="store_true",
                        help="Required to act; absence is safe dry-run denial")
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error("refusing to overwrite existing private native Save witness")
    if not args.invoke_native_save:
        parser.error("no native Save invoked without --invoke-native-save")
    try:
        receipt = save_and_witness(
            args.project, args.desktop_pid, disposable_root=args.disposable_root,
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        receipt = {
            "schema": "vqs.native-desktop-saved-source/1",
            "native_saved_source_verified": False,
            "reason": f"native Save witness failed closed: {exc}",
            "desktop_pid": args.desktop_pid,
            "independent_g2_g4_g6": "blocked",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(receipt, target, indent=2, ensure_ascii=False)
        target.write("\n")
    ok = receipt["native_saved_source_verified"] is True
    print(json.dumps({
        "native_saved_source_verified": ok,
        "reason": receipt.get("verification_reason", receipt.get("reason")),
        "private_receipt": str(args.output),
        "independent_g2_g4_g6": "blocked",
    }))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
