# Premium Power BI preflight — working guide

**Status:** advisory Power BI engineering feature. The report is not production-approved because this preflight passes. Independent rendered G2, current-source native G4 and two-unrelated-PBIP G6 acceptance remain mandatory.

## 1. Three commands, no cloud account

```bash
vqs triage path/to/Sales.pbip --out quality.md
vqs premium path/to/Sales.pbip --init-contract intent.json
vqs premium path/to/Sales.pbip --contract intent.json --out premium.md
```

The first command finds functional/source-level defects. The second creates a design-intent template with the actual source SHA-256 and every PBIR page ID. **Edit the template** to enter an audience, business question, page archetype, optional focal visual ID, and optional maximum data-area coverage (percent). The third command checks what source geometry and explicitly declared styles can support. It does not upload images, change Power BI or silently overwrite outputs.

## 2. What the contract means

- `schema = "vqs.premium-design/1"` and `source_sha256`: exact source identity; reject stale contracts.
- `pages[].page_id`: actual PBIR page ID, not title text; all pages must be listed once.
- `archetype`: `unspecified`, `executive`, `analytical`, `operational`, `narrative`. Informational owner intent, not inferred.
- `audience`, `primary_question`: optional explicit design rationale, initially `null` rather than fabricated.
- `focal_visual_id`: owner-declared most important view; verifies it is present and sufficiently prominent relative to peer analytical visuals. Without one, QVS does not invent a focal choice.
- `max_data_coverage_pct`: optional range 10–95; compares exact union of in-canvas data-visual rectangles against the canvas. A default report has **no imposed density budget**.
- `exceptions`: bounded page-specific list of the four known rule names; intentional asymmetric layouts can be accepted without disabling the rest.

Only explicitly declared size properties are compared; inherited Power BI/theme defaults cannot be treated as measured values. Peer KPI spacing is compared within a visible row, not across unrelated sections. Data rectangle overlap is unioned, not double-counted.

## 3. Reading a result

The `top_three` array lists at most three grounded, priority-ordered recommendations with exact page and visual IDs, evidence, and a proposed visual correction. CLI exit code is **1 for measured opportunities**, **0 for none**, and **2 for unreadable/stale contracts**; none of these is visual-release approval. Findings are **advisory design opportunities**, not preapproved repair plans; do not automate changes to the original report. If there are zero findings, the result says **no source-proven preflight violations**, not “premium accepted.”

`vqs assurance` carries the same source preflight as an advisory subsection next to independent rendered pixel measurements; it cannot elevate a G2/G4/G6 status. The existing `vqs review-images` uses an opt-in, image-capable reviewer on a hash-verified full-page capture; no model judgment alone approves a release.

## Categorical colors and visually similar bars

VQS now identifies two related but distinct source risks:

- **`color.palette_series_collision`** — the registered report theme
  declares near-indistinguishable `dataColors`. Reports the exact weakest
  index pairs, normal CIELAB ΔE76, approximate protan/deutan/tritan distances,
  and affected chart/page IDs. It is **not proof** all colors were drawn.
- **`color.numeric_gradient_category_ambiguity`** — a numeric
  measure-bound `FillRule` colors categorical bars. Similar measured
  values legitimately produce similar shades, but may make category identity
  hard to scan. This is *low-priority review advice*, never permission to
  discard a quantitative encoding or change the business measure.

The first-two-series readability screen is stricter because two thin lines
can merge visually at normal dashboard viewing sizes. The actual pixel-level
legibility still needs populated Desktop evidence, particularly for
color-vision deficiencies. Neither rule modifies any source.

## 4. The safe improvement loop

1. Generate/edit contract and use `vqs triage` plus `vqs premium` to identify concrete work.
2. Change only an isolated disposable PBIR candidate using the project's allowlisted authoring and repair tools.
3. Validate the candidate via the pinned Microsoft Report Author CLI, open it in the *correct* Desktop process, verify source and live data, and capture every affected full page.
4. Independently inspect all affected pages, neighbors, and relevant filters/interaction state against the design intent. Reject any numerical, behavioral, accessibility or visual regression.
5. Only an independent verifier/owner can approve G2/G4/G6. Word/DOCX never blocks the Power BI-only scope.

Source-based heuristics cannot perceive attractiveness, text clipping, actual semantic answers, or whether a chart deserves to exist. Those stay explicitly unverified until appropriate evidence arrives.


## Rendered matrix and table acceptance

The opt-in `vqs review-images` reviewer now evaluates a seventh explicit
`table_matrix_overflow` check in the same verified-canvas pass. It inspects
truncated/overlapping row labels and totals, clipped columns, and scrollbars
that hide required content. Scrollbars in intentionally scrollable tables are
not automatically defects. A page with no grid is explicitly reported as not
applicable in the check detail; this does not imply any grid was inspected.

Example: the Contoso Stores & customers matrix previously displayed long
semantic measure names, forcing scrolling despite `growToFit` and compact
text. The PBIR fixture now sets visual-only captions `Sales` and `GM %`
while keeping both original measure `queryRef`/`nativeQueryRef` bindings.
The source edit and image-review result are not a substitute for a fresh,
populated Power BI Desktop render and independent G2/G4/G6 acceptance.
