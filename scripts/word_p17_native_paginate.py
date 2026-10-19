"""Render a private DOCX in actual Microsoft Word and record page geometry.

Windows, with an exclusive Word session and a disposable DOCX:
  python -m scripts.word_p17_native_paginate C:\\private\\candidate.docx \
    --pdf C:\\private\\candidate-word.pdf \
    --output C:\\private\\candidate-word-evidence.json

Exit 0 proves read-only Word->PDF render only. Independent page visual and
Power BI report consistency remain BLOCKED until separately reviewed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vqs.document.native_word import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if (args.output.exists() or args.output.is_symlink()
            or args.pdf.exists() or args.pdf.is_symlink()):
        parser.error("refusing to replace an existing private PDF or audit")
    if args.pdf.resolve() == args.output.resolve():
        parser.error("PDF and JSON output must be distinct")
    result = run(args.docx, args.pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, ensure_ascii=False)
        output.write("\n")
    print(json.dumps({
        "native_word_render": result["native_word_render"],
        "independent_paginated_review": result["independent_paginated_review"],
        "page_count": result.get("page_count"),
        "reason": result.get("reason"),
        "receipt": str(args.output),
    }, indent=2))
    return 0 if result["native_word_render"] == "pass" else (
        1 if result["native_word_render"] == "fail" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
