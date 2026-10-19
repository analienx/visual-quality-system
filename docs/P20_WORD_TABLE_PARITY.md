# P20 — reconcile adjacent OOXML tables with native Word pagination

## Why the P17 all-page proof refused the fuller Contoso DOCX

P17's native Microsoft Word receipt originally required
`document.Tables.Count == len(document.xml.findall('.//w:tbl'))`.
This works for basic isolated tables but is incorrect for contiguous Word tables.

The real, private **30-page Contoso document** produced these source-bound
observations (copied to a SHA-identical private disposable DOCX; original
untouched):

| Count | Value | Evidence producer |
| --- | ---: | --- |
| Raw OOXML `<w:tbl>` elements | 50 | Static `word/document.xml` parse |
| Contiguous main-body table groups | 42 | Body child order; eight adjacent table elements join prior groups |
| Native Word `Document.Tables.Count` | 42 | Exclusive read-only Word COM inspection |
| Raw OOXML `<w:p>` descendants | 2,360 | Static parse |
| Native Word paragraphs | 2,428 | Word COM (passes the conservative ≥ source check) |
| Headings in both views | 45 | OOXML and Word COM |
| Native Word page count | 30 | Actual Word layout, not XML page breaks |

Word's table collection reports logical tables, while separate adjacent
`w:tbl` elements without intervening paragraphs can render as one logical
table. This is a real instrumentation mismatch, not evidence of Word losing
eight tables. Microsoft's official `Tables.Count` contract counts objects in
the Word table collection; it does not promise one object per XML element.

## Correction

- `inspect_docx` continues reporting the raw `tables` count for OOXML
  inventory and adds `word_main_story_table_groups`: count of **consecutive
  direct-body** `w:tbl` runs, separated by any paragraph or other body child.
- P17 validates Word's `Tables.Count` against that derived group count.
  Its evidence preserves **both** values (`ooxml_table_elements` and
  `ooxml_adjacent_table_groups`) instead of overwriting or concealing them.
- Nested tables and block-wrapper tables (`w:sdt` and similar) are not yet
  modelled as Word main-story table collection members. The group count is
  `null` and native parity returns **blocked**, not a guessed success.
- Any unexplained Word count mismatch remains **fail**; if Word reports fewer
  paragraphs than the OOXML source, it also remains **fail**. Corrupt or
  missing document bodies cannot proceed to native rendering.
- Source hashes, exclusive read-only Word lease, backend identity, heading
  positions, table pages, complete PDF signature and fail-closed G5/G6
  statuses remain unchanged.

## Regression

Synthetic, publicly shareable DOCX fixtures recreate the Contoso table
topology (50 elements / 42 groups) without copying private content.
Adversarial controls cover separated tables, falsely high/low Word table
counts, nested/wrapped unsupported tables, malformed source, and spoofed
group measurements. End-to-end native Microsoft Word and all-page PDFium
captures must still be run on the private 30-page candidate before claiming
this fix is validated for that source.

See [P17 native Word renderer](VISUAL_QA_V2_P17_WORD_NATIVE_PAGINATION.md)
and [P19 every-page evidence](P19_WORD_ALL_PAGE_EVIDENCE.md) for the
remaining independent visual, figure and report-claim gates.
