# VQS 2.0 — P7: native textbox padding and Azure Maps runtime rejection

**Date:** 2026-10-16
**Branch:** `work/vqs-textbox-padding-p7-r1` (stacked on P6 PR #45).
**Status:** Candidate-only implementation; unchanged original PBIP; no release approval.

## Practical usability problem

Two Contoso native `textbox` Subtitle visuals were only 32px high,
with 12px text and implicit 8+8px default padding. Microsoft's CLI
emitted `PBIR_TEXTBOX_HEIGHT_BELOW_FLOOR` twice.

Simply resizing to 35px passes static validation but would be WRONG
on `Markets_drivers`: the 32px subtitle starts at y=72, while
the Sales/Growth/Margin/Target KPI row starts at y=104. A height
increase to 35px causes a real geometric overlap.

### Experiments on independent private copies

Four variants were tested with actual `powerbi-report-author`
v0.5.0 against the same independently corrected metadata source:

| Variant | Microsoft errors | Subtitle warnings | Other warnings |
| --- | ---: | ---: | ---: |
| unchanged 32px and default padding | 0 | 2 | legacy Bing map (1) |
| explicit 2px top/bottom/left/right VCO padding | 0 | 0 | legacy Bing map (1) |
| explicit 0px padding | 0 | 0 | legacy Bing map (1) |
| 11px font only | 0 | 2 | legacy Bing map (1) |
| 35px height | 0 | 0 | legacy Bing map (1), but geometry overlap |

**Decision:** 2px explicit padding; preserve 32px height, text content,
font size, x/y/width and all neighboring objects. This is both a smaller
cosmetic change and a better fit than height modification.

## New deterministic typed repair

New allowlisted op `textbox.padding.compact`, with exact selector,
explicit `visual.visualContainerObjects.padding` path, `value:2`,
and proof preconditions `expected_height:32`,
`expected_font_size:"12px"`. It only acts on a simple native textbox
with one paragraph, one nonempty static text run, no existing padding
override and unchanged 32px position height. Any other visual
type/font/content/geometry/padding or value fails closed. The operation
inserts the officially documented native PBIR padding object with
top/bottom/left/right `2D` literals. It never edits query, semantic
model, report theme, visual ID or geometry.

VQS repair applies two operations to the two Subtitle visual.json files,
seals, and independently verifies candidate confinement and model
identity. The Microsoft paired diagnostic comparison reports:
**0 new errors, 0 new warnings, 2 cleared warnings, 1 remaining warning**.
The sealed VQS result stays separate from release authority.

### Related real product bug fixed

The VQS Desktop candidate wrapper builder previously always generated
a `.pbip` without `$schema`, even when the input's shortcut was valid.
This regressed metadata and caused the strict P6 comparison to block.
The new wrapper preserves a canonical Fabric PBIP schema from the
source shortcut, with the official pinned default for legacy projects.
Unsupported or unreadable source wrapper schemas fail rather than
silently substituting. The wrapper is still created only in a fresh
candidate workspace; existing shortcuts are never overwritten.

## Actual Desktop A/B evidence

Three independently owned Power BI Desktop sessions were opened with
complete, privately populated Contoso model projects:

- P6 metadata-normalized baseline; source/report-model digest:
  `d7f48500ff4aaa81c1a1ed592d31a368722c22f881dd972d9f87457c0d7bf734`.
- P7 2px subtitle-padding candidate; report-model digest:
  `b957dac6ab1af4f1fc42ce366b0ea333b78a5918191a2a612d3ded6589b04eeb`.
- P7 Azure-map type-only experimental candidate; report-model digest:
  `047ef76d034fa255ffd926113d5c67a32b32f996ee5d700846cd6c048e38a115`.

Every session passed live Microsoft Modeling MCP readiness; the same
Dim Customer query returned 12 source rows, and the probe query hash
was identical. Fresh default-state full-page captures were produced.

Lossless native-pixel comparison of the first two screenshots:
- `Markets_drivers`: 15,228 changed pixels, bounding box
  `[62,526,1168,562]`.
- Deep-dive `d9bc3b8f90439bcc`: 11,559 changed pixels, bounding box
  `[62,526,902,562]`.

All changed pixels in each page were confined to its visible subtitle
textline; no adjacent KPI, slicer, chart, map or filter-pane pixels changed.
Both subtitles remained readable and no new overlap was visible.
These are screenshot-coordinate observations; a PBIR-to-viewport transform
has not been calibrated. Source digest of the actual VQS typed candidate
exactly matches the separately freshly rendered P7 padding variant.

### Legacy Bing to Azure map: MUST NOT auto-convert

A separate scratch-only change `map` → `azureMap` retained the
`Category` country and `Size` sales bindings and passed Microsoft
static validation with **0 errors and 0 warnings**.

The real Power BI Desktop screenshot instead displayed **"To display
Azure Maps visuals, sign in."** The legacy Bing map displayed actual
country markers and labels. Consequently the proposed type-only
migration **failed functional visual parity and was rejected**.
A zero-warning static validator does not certify a functioning report.
The legacy Bing map remains unchanged in the accepted padding candidate.

## Remaining release gates

- One inherited legacy-map warning remains. Resolve Azure Maps authentication
  and independent visual behavior before attempting migration; do not
  suppress the warning or silently replace the map with a different chart.
- Scoped Sales/DAX result equality for filter and period changes, RLS and
  interactive matrix scroll have not been exercised. Model-source bytes
  are equal, but that is not dynamic semantic result proof.
- No latest original report mutation, merge, promotion or production edit.
  The R6/P6 assurance and independent review requirements continue to apply.
- All private renders/caches/paired receipts stay under
  `C:\Workspace\scratch\vqs-p7-*`, outside Git.

The critical outcome is functional: two actual warnings are fixed
without affecting neighboring visuals, while a superficially cleaner
but broken map migration is specifically prevented.
