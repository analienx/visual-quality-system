# P21 — detect rendered Word field errors and broken bookmarks

P17 now proves **native Word pagination**, and P19 proves **all-page PDF
capture**, but neither implies the text on those pages is correct. A fresh,
private 30-page Contoso export gave 30/30 page images with no blank or
out-of-bounds flag, yet its first page visibly repeated **“Error! Bookmark
not defined.”** throughout the table of contents.

## Evidence and root cause

The private Contoso DOCX inspected on 2026-10-19 has:

- 26 internal `w:hyperlink/@w:anchor` targets;
- 0 `w:bookmarkStart/@w:name` definitions;
- 26 visibly broken Word reference results on the PDF first page; and
- reviewable template placeholders (`ORG logo`, `[To be confirmed]`,
  `[Document Owner]`).

This is a **real source/document defect**, not a PDF pagination shortfall.
The source and PDF remain private. A passing all-page image capture is not
equivalent to document usability or the independent G5 verdict.

## Added measurements

1. OOXML inventory records `bookmark_definitions`,
   `internal_bookmark_links`, and `unresolved_internal_bookmark_links`.
   External hyperlinks are not mistaken for missing internal bookmark targets.
   The inspector does not rewrite bookmarks or block reading the source, so
   the actual Word rendering can still show the failure.
2. Each decoded PDF page undergoes a **bounded, normalized text scan** for
   known English Microsoft Word field results: undefined bookmark, missing
   reference source, and missing table-of-contents entries. Only rule IDs and
   occurrence counts leave the scanner, not private surrounding text.
3. Visible template placeholders are tracked as `review_required`, not
   automatic semantic failures.
4. `rendered_field_integrity: fail` means a recognized Word error phrase
   really appeared in the native PDF. `document_bookmark_integrity: fail`
   means an internal OOXML hyperlink points to an absent bookmark. Both can
   be `not_detected`, which is **not** a blanket pass: other languages, fonts
   drawn as paths, screenshots and unexpected error wording need OCR and
   independent review.
5. `all_page_capture` remains `pass` if complete, source-bound PNGs were
   produced—even when `rendered_field_integrity` is `fail`. No failing field
   can be concealed by the raster capture status. Independent G5/G6 stays
   blocked in all cases until a different authorized reviewer signs off.

## Repair policy

This phase **detects and explains** the defect; it does not invent missing
bookmark targets, blindly delete broken links or silently rebuild a document
in place. A safe repair follow-on must work on a fresh disposable DOCX,
validate that Word recognizes its TOC field, run a supported Word
`TableOfContents.Update()` or a separately reviewed source-document fix,
then export through native Word and recheck all pages, headings, hyperlinks,
figures and report claim parity. Any moved page numbers or sections require
new review. Never patch the user's original PBIPDocumenter file.

Microsoft's Word object model documents
[`TableOfContents.Update`](https://learn.microsoft.com/en-us/office/vba/api/word.tableofcontents.update),
and the [Word support guidance](https://support.microsoft.com/en-au/word/update-a-table-of-contents)
distinguishes updating a full TOC from updating page numbers alone.

The English patterns are deliberately limited and versioned. Product owners
must not interpret `not_detected` as independent document correctness.
