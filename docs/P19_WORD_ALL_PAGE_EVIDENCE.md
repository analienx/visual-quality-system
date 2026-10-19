# P19 — native Word all-page evidence (candidate only)

P17 verified that an isolated, read-only Microsoft Word session exported a
fingerprinted DOCX to PDF with Word-reported pagination. It did **not** prove
every page survived PDF decoding, provide a renderer-bound image for an actual
reviewer to inspect, or link the figures and claims to the Power BI report.

P19 adds exactly one bounded, auditable step: read the P17 pass receipt and the
same unchanged DOCX/PDF, decode every PDF page, compare page counts and sizes
with native Word, render numbered PNGs at 120 DPI, and hash them into one
private `index.json`. It never edits report or document sources and never
changes a `blocked` independent gate to `pass`.

## Workflow

On a Windows host with an exclusive Word lease, use the existing P17 exporter
on a **private disposable DOCX** (never a user-owned original):

```powershell
python -m scripts.word_p17_native_paginate C:\private\candidate.docx `
  --pdf C:\private\native.pdf --output C:\private\native.json
```

Install the optional decoder for the Python environment running P19:

```shell
python -m pip install '.[word-pages]'
```

Then run P19 using a **new, nonexistent** output directory:

```powershell
python -m scripts.word_p19_page_evidence C:\private\candidate.docx `
  --pdf C:\private\native.pdf `
  --native-receipt C:\private\native.json `
  --pages-dir C:\private\page-evidence
```

The new directory contains `page-0001.png` through `page-NNNN.png` and an
`index.json`. The JSON binds DOCX/SHA-256, PDF/SHA-256, P17 Word page count,
Word version, PDF parser version, DPI, per-page dimensions/byte counts/SHA-256,
text-word and embedded-PDF-image counts, conservative sampled ink coverage,
and flags. The full textual content is **not** embedded in the index; raw page
images are sensitive and must stay private.

The capture returns:

- `pass`: every page of the matched native PDF was decoded and captured to
  a hashed PNG, with source/PDF hashes unchanged after export.
- `fail`: contradicted source/PDF hashes, source path, page count, page size,
  decodability, or mid-capture integrity. No partial success index is left.
- `blocked`: missing native Word proof/backend, unavailable optional decoder,
  page/resource cap, source ambiguity or overwrite risk.

### What the image-level algorithm detects

1. **Missing/duplicated pages** — actual decoded page count must equal Word's
   count, with a consecutive `1..N` PNG and hash for each page.
2. **Wrong paper geometry** — PDF page dimensions must agree (within two PDF
   points) with a native Word section's portrait or landscape dimensions.
3. **Potentially blank pages** — pages without extracted words or PDF images
   and with fewer than 0.1% nonwhite pixels in a bounded color sample are
   marked `possibly_blank_page`; intentional blanks are not auto-failures.
4. **Potentially clipped text** — extracted words extending beyond the page
   boundaries by more than one point are marked `text_outside_page_bounds`.
5. **Image-only pages** — flagged for visual judgment because a perfect image
   hash does not establish that the illustration is readable, uncropped or
   semantically correct.

The PDF parser and bitmap rasterizer follow `pypdfium2`/PDFium's documented
`PdfPage.render()`, `PdfPage.get_textpage()` and `PdfPage.get_objects()` APIs.
PDFium and its Python bindings use permissive licenses, with bundled notices
and transitive license requirements documented upstream. The optional Pillow
dependency converts native bitmaps to PNG; no AGPL PDF engine is shipped.
These checks are *triage*, not OCR or proof of readable ink/contrast, valid
chart labels, footer continuity or correct report claims.

## Fail-closed / limits

- The exact P17 `source_sha256`, `pdf_sha256`, path, `Microsoft Word` backend,
  and `native_word_render: pass` are mandatory; consumer-supplied labels cannot
  turn an unverifiable render into Word output.
- Only a new local directory may be created. No existing output is replaced;
  on failure cleanup touches only files and a directory this invocation made.
- The PDF is bounded at 256 MiB; there are at most 250 pages, at most
  12 megapixels/32 MiB per page, and at most 512 MiB of PNG output. This is a
  practical first-release safety bound, not a document-size recommendation.
- Shape/ink heuristics can miss low-contrast, graphical and semantically wrong
  content. All-page human/vision review of the *actual images* is still needed.
- The raw DOCX image hashes are inventoried but cannot establish report figure
  provenance alone: Word may transcode images and a matching PNG may still
  come from a stale report revision. Live Power BI source binding and claim
  parity must be independently checked.
- Neither the underlying P17 Word receipt nor this index is a cryptographically
  authenticated independent verifier. G5 independent review and G6 release
  remain **blocked** until separate signed evidence meets the acceptance
  contract.

No change to current PRs is necessary for this evidence-only follow-up; P19
builds on P18 and must be independently reviewed before any merge.
