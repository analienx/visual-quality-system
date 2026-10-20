"""Generate a disposable source-safe Word TOC candidate and scoped receipt.

Windows native Microsoft Word is required, with no other Word process alive.
Never substitute the candidate result for P17/P19/G5 independent acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vqs.document.toc_candidate import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if (args.candidate.exists() or args.candidate.is_symlink()
            or args.output.exists() or args.output.is_symlink()
            or args.candidate.resolve() == args.output.resolve()
            or not args.output.parent.is_dir()):
        parser.error("distinct fresh candidate DOCX and evidence JSON paths required")
    result = run(args.docx, args.candidate)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({
        "toc_candidate_update": result["toc_candidate_update"],
        "source_sha256": result.get("source_sha256"),
        "candidate_sha256": result.get("candidate_sha256"),
        "native_paginated_review": result["native_paginated_review"],
        "independent_acceptance": result["independent_acceptance"],
        "reason": result["reason"], "evidence": str(args.output),
    }, indent=2))
    return (0 if result["toc_candidate_update"] == "pass" else
            1 if result["toc_candidate_update"] == "fail" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
