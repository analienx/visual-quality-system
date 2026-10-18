# P12 — Contoso layout regression and missing VQS composition gates

**Status:** candidate-only design repair, requiring Microsoft structural
validation and source-bound full-canvas Desktop screenshot review before
acceptance. P11 semantic DAX oracle is a separate gate; neither one replaces
the other. **Source:** committed, screenshot-bound P10 Contoso fixture.

## Why previous checks missed defects visible to a human

The P10 suite tested two map/region visual migrations, asset existence,
Microsoft PBIR schema validity, and a screenshot/source provenance contract.
It did not test sibling-title redundancy, KPI/card height *relative to the
canvas*, or whether a four-card row's *two logical groups* align to the
detail panels beneath. `layout.no_visual_overlap` and
`layout.visuals_within_page` can both pass because the elements overlap
neither each other nor the page bounds. The `kpi_clipping` visual specialist
is merely a routing signal, not an executed oracles of density/padding.
The screenshot reviewer in P10 focused on the earlier map failure and did not
assert these composition constraints; a screenshot file's existence is not
pixel-level sign-off. That was a real missed review, not user preference drift.

| Concrete source problem | P10 PBIR | P12 target | Detection |
|---|---|---|---|
| Year slicer has 2 visible captions | VCO title `Year` + slicer header `Reporting year` | Keep one header (`Reporting year`), hide VCO title; y20/h80 | `redundant_slicer_caption` |
| Four KPI cards crowd dashboard | y136, h140 each (19.44% of 720) | y120, h104 each (14.44%) | `kpi_row_crowding` (15% cap) |
| KPI pairs don't align with the charts | KPI group seam x632/648; lower detail seam x648/664 | Map x24–632; right charts x648–1256 | `kpi_detail_grid_drift` |

The 720px page retains 24px outside margins and 16px horizontal gutters.
The bottom panels span y240–696 with a 16px vertical gutter on the right;
there is no uncontrolled whitespace expansion. **All measure queries,
categories, field bindings, interactivity metadata and TMDL are preserved.**

## Gate and repair contract

1. `measure_report` now emits `layout.composition` readings from the unified
   PBIR reader. The sealed VQS rule engine evaluates these static patterns;
   triage records source visual IDs and a candidate-only remediation.
2. Three conservative detectors: overlapping *meaningful* visible slicer
   captions; exactly four same-row KPI cards above 15% of page height; and
   misaligned 2+2 KPI group anchors where the two detail panels are already
   near-equal-width. Deliberately asymmetric dashboards are exempt from the
   third check. Tests prove each fail, and corrected geometry passes.
3. `python -m scripts.contoso_p12_layout_repair --output <new-private-path>`
   refuses existing targets, verifies the immutable P10 fixture, creates
   a disposable candidate, edits eight allowlisted report visuals, verifies
   every other byte including the model, and requires the new rule to pass.
   This is a *specific deterministic candidate repair*, not a promise that
   arbitrary reports may be auto-reflowed without a design contract.
4. On the run-owned Windows host: run the pinned `report_skill.py --check-cli`,
   Microsoft `powerbi-report-author validate`, selected-host status/open,
   screenshot the entire affected page, independently review full canvas and
   slicer/KPI/detail alignment. Structural pass alone is **not** acceptance.
5. Keep the candidate and real-data screenshots private; do not commit PBIP
   customer data, screenshots, runtime receipts, or altered P10 baseline.

## Further product work

- Compare OCR/vision detections from *multiple targeted passes* (spacing,
  hierarchy, density, labels, data correctness) against deterministic PBIR
  evidence, not one generic “looks good” prompt. Route disagreement to review.
- Add region-level visual padding/whitespace measurements on verified canvas
  crops before treating “too much whitespace” as a generic hard fail.
- Reuse the candidate-only repair control plane for source-bound multi-visual
  layout changes with before/after semantic assertions and native renders.
  Automatic geometry reflow must not infer intentional dashboard grids from
  arbitrary chart arrangements.
