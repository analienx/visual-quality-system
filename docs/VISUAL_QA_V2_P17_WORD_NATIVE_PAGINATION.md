# P17 — Actual Microsoft Word DOCX pagination and page-position witness

**Capability, not independent acceptance.** This feature establishes what
Microsoft Word actually paginated; it does not infer that the content is
visually beautiful or that numbers are correct relative to Power BI.

## Problem and implementation

VQS previously inspected OOXML relationships, style declarations and
renderer *availability*. Those checks cannot show whether a page has a
widowed heading, split table, unexpected blank space, truncated paragraph or
stale embedded chart. A renderer readiness probe is not the document being
rendered. Issue #13 requires real paginated evidence.

P17 adds:

- `scripts/windows/native_word_export.ps1`: opens **only** the supplied
  local DOCX using an exclusive, newly launched Microsoft Word COM session.
  Existing user Word processes force a block. The source is read-only;
  macros are disabled, alerts suppressed, Word remains invisible, and
  Word is closed in `finally`. The renderer is exactly **Microsoft Word**,
  not LibreOffice labeled as Word.
- `vqs/document/native_word.py`: verifies real OOXML structure, source
  SHA-256 before/after, renderer/process/source/read-only receipt, PDF
  signature/trailer/hash/size, Word page count, source paragraph/heading/
  table counts, section page dimensions and margins, headings' physical
  page/Y coordinates, and each table's beginning/end page. Private temp
  export is copied only to a **new** PDF path, never overwriting a user file.
- `scripts/word_p17_native_paginate.py`: one command producing a fresh,
  private PDF and a JSON evidence receipt; blocked or mismatched runs return
  a nonzero exit and do not publish a partial PDF.
- Adversarial tests reject forged renderer/PID, ignored headings,
  fictitious pages, bad margins, changed source, malformed PDF, existing
  output and corrupted DOCX.

## Run on the Windows machine that has licensed Word installed

```powershell
python -m scripts.word_p17_native_paginate "C:\\private\\candidate.docx" --pdf "C:\\private\\candidate-word.pdf" --output "C:\\private\\candidate-word-evidence.json"
```

Inputs should be isolated copies, not canonical customer documents. The
Word automation requires an exclusive Office session and appropriate local
license. It never silently downgrades to LibreOffice or HTML rendering.

The source/output locations are intentionally distinct; PDF and receipt
must not already exist. Keep PDF/receipt private; they contain potentially
sensitive document content and source metadata. `native_word_render: pass`
means the actual Word document opened, paginated and exported a bounded PDF
whose source digest did not change. It is **not** document acceptance:
`independent_paginated_review: blocked`,
`document_report_consistency: blocked` and
`independent_acceptance: blocked` remain explicit.

If Word cannot report heading Y coordinates (some hidden/remote sessions
return -1 points), `heading_position_coverage: partial` prevents treating
them as measured. Page-spanning tables are reported as candidates for
review; deliberate long tables are not automatically condemned.

## Real Windows test results (2026-10-19)

Against wholly synthetic, isolated DOCX files, real Word 16.0:
- One-page text/heading report: Word exported a valid-signature PDF and
  located three heading Y coordinates (72, 189 and 287.5 points).
- Two-page report with a deliberate page break: 2/2 rendered pages,
  headings measured at page 1 (96 pt) and page 2 (72 pt).
- Long synthetic table: 4 rendered pages and one source table reported as
  spanning pages 1–4; flagged as a split-table review candidate.
All three sources were re-fingerprinted unchanged after export. These
private PDFs/receipts remain outside the repository. No customer DOCX or
independent reviewer was involved.

## Follow-up algorithms with strongest leverage

1. **Widowed headings and split tables:** consume actual heading page/Y
   and table page-span evidence; combine with OOXML `keepWithNext`,
   `cantSplit` and section semantics. Generate typed, allowlisted style
   candidates in disposable DOCX copies; re-render with Word after each
   candidate. Avoid adding arbitrary page breaks without checking every
   resulting page.
2. **Truncation/blank pages:** rasterize each native Word-exported PDF page,
   compare accessible/OCR text bounding boxes, ink occupancy, margins and
   paragraph-to-page coverage against DOCX source. Word statistics alone
   cannot prove glyph visibility. Independent image-capable review remains.
3. **Report consistency:** bind DOCX embedded chart hashes/metrics/units
   to the exact Power BI report source and live DAX oracle; stale chart
   images and disagreeing numbers block. Do not infer that an attractive
   PDF has the correct business answer.
4. **G6 release:** repeat the entire Power BI+Word loop on two independent
   PBIPs and their expected DOCX output with external review/signoff.

Official Microsoft references:
- Word `Document.ExportAsFixedFormat`:
  https://learn.microsoft.com/en-us/dotnet/api/microsoft.office.interop.word._document.exportasfixedformat?view=word-pia
- Word `Document.ComputeStatistics`:
  https://learn.microsoft.com/en-us/office/vba/api/word.document.computestatistics
- Word `Range.Information` and `WdInformation` page/coordinate fields:
  https://learn.microsoft.com/en-us/office/vba/api/word.wdinformation
