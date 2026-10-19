"""Capture source-bound all-page PNG evidence from a P17 native Word PDF.

Example (private, disposable artifacts only):
  python -m scripts.word_p19_page_evidence candidate.docx \
    --pdf native.pdf --native-receipt native.json --pages-dir audit-pages

The output includes one numbered PNG for every page plus index.json, whose
independent visual review and report-image consistency statuses stay blocked.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vqs.document.page_evidence import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--native-receipt", type=Path, required=True)
    parser.add_argument("--pages-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.native_receipt.is_file() or args.native_receipt.is_symlink():
        parser.error("local P17 native Word JSON receipt required")
    try:
        with args.native_receipt.open("r", encoding="utf-8") as reader:
            receipt = json.load(reader)
    except (OSError, ValueError) as exc:
        parser.error(f"cannot parse P17 native receipt: {exc}")
    result = run(args.docx, args.pdf, receipt, args.pages_dir)
    print(json.dumps({
        "all_page_capture": result["all_page_capture"],
        "page_count": result.get("page_count"),
        "review_flags": result.get("review_flags"),
        "independent_paginated_review": result["independent_paginated_review"],
        "document_report_consistency": result["document_report_consistency"],
        "reason": result["reason"],
        "index": str(args.pages_dir / "index.json")
                 if result["all_page_capture"] == "pass" else None,
    }, indent=2))
    return 0 if result["all_page_capture"] == "pass" else (
        1 if result["all_page_capture"] == "fail" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
