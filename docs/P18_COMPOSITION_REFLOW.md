# P18 — Source-bound composition reflow (candidate only)

P12 proved VQS could **detect** the Contoso Deep-dive defects, but the
general `vqs propose` synthesizer did not offer layout fixes. P18 connects the
existing `layout.composition` detector to the existing typed repair pipeline.
No new UI, command, dependency, or report-specific ID is required.

## What it actually fixes

For a measured four-card KPI row above two approximately equal detail panels:

1. **Oversized KPIs:** cap each offending card height at 15% of the page;
   preserve unaffected card heights. If the entire row is uniform and too
   tall, move the panel band upward by the exact height reduction to retain
   existing vertical gutters.
2. **Card/detail horizontal misalignment:** project the left detail-panel
   edges to the first two KPI card anchors and the right panel to the last
   two. A tightly stacked, geometrically identical continuation panel follows
   its column, preserving its stack gap.
3. **Duplicate Year/container heading:** when both slicer title and field
   header are explicitly shown and the static detector proves they repeat the
   same token, hide only the container title. Preserve the field header,
   dropdown selection, filtering query and data bindings.

For example, the source-bound P10 Contoso fixture produces 13 scalar edits in
8 visual definitions (four KPI heights, three panel alignments/vertical moves,
one redundant slicer title). Its original 140-unit cards reduce to 108 on a
720-unit canvas; the detail panels snap to the original 2+2 card anchor lines.
This is **not** a pixel-certification claim; the application can still clip a
large callout within a newly reduced card, requiring native review and a
different approved candidate.

## Algorithm and safety envelope

The solver is a **deterministic bounded constraint projection**. It does not
attempt arbitrary report redesign or guess semantic intent:

- Recompute the `layout.composition` findings from source-bound `facts.rules`
  instead of trusting a text description or visual name.
- Require identifiable, finite, positive rectangles, a canvas, and an exact
  four-card source row. Disambiguate equal-width two-column panels using
  the already proven detector relationship.
- Fix only the axes entailed by the rule; keep `visual.query`, all filters,
  every field, z-order, tab order and theme/model files untouched.
- Check that all resulting rectangles remain inside the measured page and
  that **no pairwise overlap area increases**, including with visuals not
  participating in the grid. Reject an ambiguous/incomplete observation.
- Emit `chart.resize`, `spacing.adjust` and `theme.set` with literal `old`
  preconditions, exact visual selectors/write targets and the normal rollback
  recipe. The executor now checks literal preconditions for geometry and
  formatting leaves before writing the isolated candidate.
- Retain all existing VQS candidate confinement and downstream gates:
  Microsoft PBIR validation, native Desktop render, pixel/ink comparison,
  data-answer and interaction oracles, and independent release review.

The alternative for truly arbitrary multi-visual packing is an optimization
backend with integer grid coordinates and disjunctive rectangle constraints
(e.g. OR-Tools CP-SAT `add_no_overlap_2d`). That is deliberately **not** used
for this narrow, known signature: adding a solver dependency cannot replace
the missing *semantic constraints* or fresh visual verification, and unconstrained
packing could reshuffle a business narrative. A later backend can operate on
the same typed plan contract after source-grounded design relationships exist.

## Operator path

Existing source-bound review/proposal entry points now include this rule:

```text
vqs review <report.Report> --run-root runs --run-id layout-review
vqs propose --run-root runs --run-id layout-review --out candidate-plan.json
vqs repair candidate-plan.json --original <report.Report> --candidate-root <fresh-candidate.Report> --run-root runs --run-id layout-repair
```

For the exact archived Contoso regression, the reproducible one-command
fixture probe keeps both original and candidate in a new private workspace:

```console
python -m scripts.contoso_p18_candidate_probe --workspace <fresh-private-workspace>
```

It emits a compact `candidate_only`/`blocked` receipt with source hashes and
explicit pending Microsoft/native/independent gates. It never accepts an
already existing workspace.

Production use follows the pinned Microsoft CLI authoring gate. A proposal is
**not** an approved repair: blocked visual/DAX/interaction validation must
not be converted to `pass`. The archived P10 fixture is safe for automated
tests; real customer images and model data remain private and are never
included in this repository.

## Negative controls

`tests/test_p18_composition_reflow.py` proves the archived original detects
three faults, the plan is deterministic, all three clear after isolated
application, queries and source bytes survive, and an already repaired report
does nothing. Separate failures exercise missing rectangles, unsafe IDs,
stale `old` preconditions, new neighbor collision, individual card crowding,
and horizontal-only drift. The sealed `review → propose` path is exercised as
well as direct synthesis.

**Remaining release gates:** A successful candidate must be rendered in actual
Power BI Desktop with the right model and saved-state identity, checked for
card-value clipping at the new height, tested at supported slicer states, and
reviewed by a party other than its author. G4 country Shape Map click and G6
unrelated PBIP/DOCX independent corpus stay separate from this static feature.

## Windows validation evidence — 2026-10-19

On the isolated Windows/Power BI Desktop test host:

- Archived P10 source report tree digest
  `5cbee9f77c1eeb033875317b9b70b8525360df0b93b8d68e7ee7383189dc0d48`;
  candidate report tree digest
  `5853e2894762cc7cb458cdc242479e4f71791e2939da63413e14ca48594f13e6`.
  Source remained unchanged, 13 operations applied, eight visual files changed,
  and the static composition + confinement gates both passed.
- Pinned Microsoft `powerbi-report-author` 0.5.0 `validate`: **succeeded**, zero
  errors and zero warnings.
- The first Desktop preview rendered five pages but the fixture's fresh model
  lacked data: the **G1 data gate failed** despite clean geometry. This was not
  counted as visual/data acceptance.
- A second private candidate used the **same report files** and only a local
  cached ABF from the already populated disposable Contoso project. The TMDL
  digest on both sides matched exactly:
  `82375f803829b1abbd348036083a9c3e722176d878d7a3eb0ca50f280d444e7b`.
  The cache copy was SHA-identical, and the Microsoft validator was again clean.
- Real Desktop rendered **all five pages with populated data**; the Deep-dive
  Year header, compact four-card row, aligned Shape Map, donut and regional bar
  chart were visually reviewed. Cards had complete numerical values at the
  reduced height. Unrelated Stores & customers contains a pre-existing cramped
  table/scroll area that needs its own targeted review.
- P14 semantic DAX oracle: `pass`. P16 native UIAutomation: **9/9 witnessed
  Year and Region actions** with native card/geometry readback and DAX agreement.
  The native harness still returns `interactive: blocked` for Shape Map country
  selection, loaded-file attestation and independent verifier requirements.
- Raw DAX/UIA receipts remain in private local scratch, never in Git; both
  temporary full-canvas screenshot collections were reviewed then deleted by
  exact workflow-child path. No original report, PBIPDocumenter, customer
  content or semantic-model source was overwritten.

These tests prove substantial *functional candidate behavior*. They **do not**
grant G2 independent image approval, full G4 interactions or G6 product release.
