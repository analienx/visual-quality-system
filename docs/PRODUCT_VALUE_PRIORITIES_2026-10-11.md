# VQS functionality-first review — 11 October 2026

## User outcome to optimize

Given a PBIP, VQS must find an actual report-design or analytical-usability
problem, identify exactly where it is, propose a credible improvement, safely
apply it to a disposable candidate, show *before vs after* render and data
evidence, and leave a simple decision: keep, revise, or reject.

Success is **measurable improvement per report**, not the number of contracts,
approval screens, seals, policy versions, or Python tests.

## Independent inventory of what works vs what does not

| User capability | Evidence as of draft PR #41 | Real limitation |
|---|---|---|
| Import existing PBIR/PBIP | `vqs triage` resolves local .pbip report and byPath model, inventories pages/visuals | File-based; no Fabric workspace browsing |
| Locate layout problems | Geometry bounds/overlap checks, exact source visual IDs and friendly page/chart types | A geometric overlap may be intentional; no screenshot decision |
| Produce safe fixes | Typed geometry repairs and a narrow bound precision edit path | No reliable generalized padding, alignment, theme, labels, navigation |
| Measure improvement | An out-of-canvas test chart was repaired and rechecked: 1 -> 0 source-rule failures | No **rendered** before/after pixel or business-answer acceptance |
| Inspect semantic intent | TMDL parsing and partial visual/field inventory | No ranked real analytical questions, missing-story map or authenticated answer test |
| Review visual quality | Image capture/adjudication framework exists | No unattended independent visual QC with complete coverage and actionable corrections |
| Generate new visuals | Design specification, some templates | Not a general reliable Power BI page/chart author |
| Operator experience | New one-command Markdown/JSON triage + optional typed plan | Repair/verify still expert steps; unknown evidence should be made obvious, not dumped as arbitrary blocked errors |

### Observed full Contoso Retail example (read-only)

The local PBIP contains **5 pages / 54 visuals**. Source-only checks
detected **1 potential overlap** on the *Markets & drivers* page and
**1 typography rule needing rendered evidence**, plus 3 decisions.
The auto-synthesizer offered **no** unsafe move because the layout is
ambiguous/no safe shift was found. This is meaningful *triage*,
but NOT a demonstrated visible defect or a complete quality score.

A separate disposable five-visual fixture gave a complete successful
static loop: **1 out-of-canvas issue -> 1 typed plan -> applied candidate
-> sealed verify pass -> 0 remaining measured rule failures**. Neither
experiment is a genuine Desktop image comparison.

## Immediate priorities (product before administrative work)

1. **P0: Actual render-delta loop** on two cloned PBIPs. Open only a
   disposable candidate through the single supported preview port,
   capture populated before/after full pages, measure visual/page crop
   differences and let an independent image-capable reviewer identify
   clipping, whitespace, alignment, readability, palette and hierarchy
   issues. Changes that alter business answers or worsen the rendering
   reject. Output one concise side-by-side report.
2. **P0: Useful repair breadth.** Implement geometry alignment/spacing
   *with neighboring objects*, label format/axis precision, typography,
   chart title and theme/palette **in actual eligible visual types**.
   Prove old/new source paths, vendor schema and real render.
   No unbounded edits or manual approval per harmless style property.
3. **P0: Analytical question coverage.** From actual field/measure
   roles and metadata, propose a short ranked list of questions already
   answerable by the report and valuable missing comparisons/trends/
   drill paths. Prove feasibility; unknown targets or misleading KPIs
   remain questions, not invented facts.
4. **P1: Template-driven chart/page creation** for core native
   bar/line/card/matrix charts with proven role bindings, then tested
   navigation, slicers, drillthrough and states. Desktop round-trip is
   required before declaring a template supported.
5. **P1: Simple operator experience:** one command to triage, one
   command to produce a candidate, one result explaining exactly
   what got better/worse or still cannot be checked.

Administrative follow-up should be **bounded to necessary write/promotion
trust checks**, not allowed to displace P0 visual/semantic usability. In
particular, a sealed static PASS or successful Microsoft schema CLI never
equals visible chart quality or correct filtered numbers.

## Next vertical acceptance

- Feed real `.pbip` input, not just a hand-authored minimal JSON fixture.
- Detect at least one *confirmed rendered defect* on a disposable report.
- Emit a specific page/visual-ID repair, run it in a candidate-only folder,
  and show before/after full-page + visual crop.
- Verify relevant field/measure bindings and a stable DAX answer case.
- Show one legitimate unsupported/ambiguous defect as a clear decision
  rather than repeatedly requesting owner approvals.
- Produce a short, comprehensible report with recommended next action.
- Run the same journey on another independent report format/content mix.

All of the above are **acceptance goals**, not achievements claimed by
PR #41. No merges or original Contoso edits.
