# Adaptive Power BI themes · release and integration history

> **Current status (26 October):** 14-family adaptive theme implementation is
> merged, and [#80](https://github.com/analienx/visual-quality-system/issues/80)
> is **closed**. Any still-unverified interactive/theme P3 review, the
> independent two-PBIP G2/G4 tests and production G6 are tracked in
> still-open [#16](https://github.com/analienx/visual-quality-system/issues/16).
> See [latest engineering release notes](RELEASE_NOTES_2026-10-26.md) and
> [agent-first README](../README.md). Historical sections below preserve
> their *then-current* draft/PR status and are not the current release state.

## Adaptive themes integrated into main — 26 October 2026

Owner-approved [PR #81](https://github.com/analienx/visual-quality-system/pull/81)
was merged to `main` at [`9770a52`](https://github.com/analienx/visual-quality-system/commit/9770a52f934daf45c72b1081e11b87009f95ea0b).
The 14-family / 28-mode adaptive-theme feature, its exact-source native
Contoso evidence (140 captures, 364/364 pixel/control checks) and the
56-image public gallery are now integrated. The original authoring commit
`6bb62da` remains in Git history for provenance. The full local test suite
passed 1,860 tests (11 skipped), and all PR CI, authoring and R6 jobs passed.

**Release boundary:** this was approval to merge the **feature**, not
independent `powerbi-core` production acceptance. The two unrelated
PBIP G2/G4 scenarios and broader release G6 remain open in
[issue #16](https://github.com/analienx/visual-quality-system/issues/16).
The implementation issue [#80](https://github.com/analienx/visual-quality-system/issues/80)
has since been **closed as completed**; its unverified P3 interaction checks
were explicitly moved to issue #16, **not marked passed**.

## Earlier engineering evidence — 24–25 October 2026 (historical state)


## Native gallery verified against current authoring source — 25 October 2026

- **Source:** GitHub authoring commit [6bb62da](https://github.com/analienx/visual-quality-system/commit/6bb62da26d7589dca492571fa5f2ee444e369117) and [workflow run 40224195761](https://github.com/analienx/visual-quality-system/actions/runs/40224195761). All 2,352 downloaded candidate files matched the local candidate set.
- **Pre-capture QVS:** 28/28 approved Light/Dark modes passed with zero categorical-color findings.
- **Native Desktop:** 140/140 genuine five-page captures; **364/364** source-specific pixel checks passed (308 charts, 28 closed dropdowns, 28 line legends). Graphite Red had zero suspect green/teal pixels across its ten pages under the documented screening rule.
- **Publication:** 56 authentic derived WebP previews and 28 palette/control swatches; the provenance file binds source, candidate, model, palette, raw captures and public-image digests.
- **Boundaries:** open flyouts, broad G2/G4 interactions, unrelated PBIPs and explicit owner G6 promotion are **not approved** by this evidence. PR #81 remains draft and unmerged.



## Historical 14-family gallery (source 4987bd7) — 25 October

**The prior gallery engineering candidate used source commit
`4987bd77f03a0d8a8822861408c62165ff542f69` and gallery publication
`47086c318f1ec1bde315643752b5ac5edbbb59cc`.** This supersedes the
historical five-family references below without deleting their audit trail. The exact-head native evidence is now the 364-check edition documented above.

- All 14 approved themes are available in both Light and Dark: **28 genuine
  Power BI Desktop modes** from one consistent synthetic report.
- **140** complete raw native page captures and **56** published Executive
  and Products & Brands screenshots with SHA-256 provenance.
- **140** rendered category/series checks and **28** real closed-dropdown
  appearance checks passed, alongside the QVS pre-capture source gate.
- The homepage presents seven curated Light/Dark pairs with direct links to
  the dedicated full gallery; the full gallery shows both modes and both
  page views for every family, alongside selectable appearance tokens.
- Each theme has its own slicer/dropdown background and selection contrast.
  Organic uses cobalt and magenta with green/cyan identity; Sunny uses
  documented orange/peach/grey as visual inspiration, with darker
  chart-safe equivalents where needed.
- The scope does **not** include visual acceptance of open dropdown flyouts
  or comprehensive G2/G4 interaction behavior. Owner G6 merge approval is
  still separate. This PR remains draft and unmerged.


**Status: PR [#81](https://github.com/analienx/visual-quality-system/pull/81)
remains DRAFT and unmerged.** These are engineering candidate notes,
**not** a production release, independent G2 visual signoff or G6 merge approval.
The previous [21 October Power BI core notes](RELEASE_NOTES_2026-10-21.md)
remain valid for the code already in main.

## 14 approved families — refreshed native gallery, 25 October

**Source revision:** `4987bd77f03a0d8a8822861408c62165ff542f69`, with GitHub
CI, official Power BI authoring and R6 all passing at that revision.
The 14-family expansion uses that exact 28-mode GitHub authoring
artifact, with five genuine native Power BI Desktop pages captured per
mode (**140 private full-page captures**). The homepage shows seven
curated Light/Dark families; the dedicated complete gallery shows all
14 with **56 representative real screenshots**, and 28 swatches show
their actual data and navigation-control colors.

The selection/control palette now varies meaningfully by family in
Power BI slicers, dropdowns, applied filter cards and supporting
appearance. The brighter Organic and Sunny identity colors are
allocated to appropriate chart/control roles while preserving the
categorical legibility gate. **28/28 QVS source checks and 168/168
native pixel checks** passed, including all seven subcategory bars
and themed closed-dropdown surfaces. An anomalous tinted native
capture was quarantined and retaken rather than accepted.

Generated assets include SHA-256 provenance for all 56 published WebP
previews and every original native capture. Screenshot proof is limited
to default report states; open slicer menus, interactive G2/G4
and release-owner G6 acceptance are not inferred from these results.

## Final corrected source and gallery evidence — 25 October

Historical corrected-source **candidate**, not a production merge:
`587eda95c46770bdffd0c20992506c8bfbb94426`. The official GitHub CI, R6 and Microsoft
report-authoring probes for this exact source completed successfully.
The regenerated GitHub artifact contains 28 validated source-bound
Power BI candidates, one per approved palette/mode.

Native QA exposed a real defect in the previously published gallery:
both *Electronics* and *Sports & Outdoors* were red in the GM target
chart. The same screenshot review exposed weak 7-category hue
separation and confirmed that palette-wide checks were insufficient.
QVS now flags wildcard conditional colors on multi-category bars and
screens actual assigned colors at stronger normal/CVD thresholds.
The 35% target and business values remain; regional variance now
uses distinct native category bars instead of repeating a waterfall
Increase color (the cumulative Total bar is intentionally absent).

An **earlier** native gallery was captured only *after* all 28
GitHub candidates passed the independent QVS pre-capture gate.
Five Light/Dark theme pairs, 50 real Desktop pages and 30 public WebP
previews are source/candidate/model/palette and SHA-256 bound.
The `scripts/theme_native_category_pixel_gate.py` acceptance additionally
verifies 10 distinct chart regions per mode (**100 checks**) against
the exact active theme colors, covering *all seven* product
subcategories rather than only the first three bars. These checks
are screening heuristics, not independent G2 aesthetic signoff.

## What is ready

- 14 **new approved** palette families × paired Dark/Light = **28** modes.
  They supplement four legacy families, giving 18 selectable identifiers
  without breaking the original default behavior.
- Reversible `vqs theme inspect/preview/apply/audit`, candidate confinement
  and manifest/source/model integrity invariants.
- Report/page/filter-card/slicer appearance plus deterministic categorical
  chart series, the unscoped wildcard chart fills observed in actual Desktop
  evidence, and supported numerical `linearGradient2/3` color stops.
  Bound business measures, filter selections, conditional thresholds and
  positive/negative meaning remain unchanged.
- CI, R6 and official Microsoft report-authoring validation all **passed**
  for an earlier implementation commit `dddae21fa2fa1ccee59361715a68d8ede1e3914c`; the newer exact candidate is identified above.
  GitHub regenerated and validated **28 five-page Contoso PBIP candidates**
  (140 page definitions); structural validation alone does not certify pixels.
- A [curated real Power BI Desktop showcase](REAL_THEME_SHOWCASE.md) captures
  all five native pages for **Sunny, Organic, Graphite Red, Indigo Ember and Petrol & Gold**, in both modes
  (50 genuine native page captures). The public gallery embeds three
  representative report pages per mode (30 resized WebP images), and the
  [capture provenance](images/adaptive-showcase/PROVENANCE.json) records
  raw/public SHA-256, candidate/model/source identities and the exact code
  used. The remaining 9 family pairs are [token-only color swatches](APPROVED_THEME_LIBRARY.md),
  not invented report screenshots. The earlier five-colorway
  [native gallery](THEME_GALLERY.md) is retained separately.
- Verified native Sunny Dark subtitle and chart-legend appearance, after
  correction for implicit low-contrast text; guarded wildcard chart fills
  follow selected tokens while the original DAX measures remain unchanged; the regional waterfall is deliberately shown as a category-colored column comparison.

## Categorical readability remediation — follow-up

The 24 October native image critique exposed poorly separated line and
categorical series. **All 28 approved mode dictionaries have been rebuilt**,
and an accidentally enforced Graphite Red monochrome test was removed.
A new CIELAB plus approximate color-vision screening check is applied to
each eight-color approved mode, and the existing `vqs premium` command
surfaces weak theme series and ambiguous numeric-gradient-on-category charts
as explicitly **advisory** findings. Continuous numeric ramps and
conditional business good/bad colors are not converted into arbitrary
categorical colors.

**Capture integrity:** all ten featured Light/Dark modes were recaptured
from the GitHub-hosted **`dddae21`** candidate artifact after refreshing
their isolated Desktop models. The public WebP gallery (30 representative
pages) and all 18 token swatches have been regenerated from these final
palette dictionaries. The [SHA-256 provenance](images/adaptive-showcase/PROVENANCE.json)
binds the exact full-resolution source captures, public report-only crops,
palette hashes and candidate/model digests to that revision. Earlier
`b113f77` screenshot derivatives were replaced, not relabeled.

## 25 October category-level pre-capture QA gate

The previous palette-level check missed actual in-chart collisions:
Organic Light assigned Electronics `#1B4298` and Sports & Outdoors
`#177DAD`, only 39.53 ΔE76 apart. A shared literal wildcard fill
also assigned Retail and Online the same blue. Both problems have
been fixed in the source and QVS itself.

`vqs premium` now resolves the report's **actual category names and
native color assignments**, issuing high-priority
`color.category_series_collision` and
`color.category_wildcard_shared_fill` findings before rendering.
All 28 generated source-bound theme candidates must pass the updated
`scripts/theme_approved_library_probe.py` step and a separate
`scripts/theme_gallery_color_gate.py` verification **before** any
Desktop screenshot is used as gallery evidence. The exact `dddae21`
GitHub-hosted candidate set passed 28/28 with no reported collisions,
confirmed by the independent local pre-capture command.

Color optimization now keeps Sunny's orange/grey-led design and Organic's
blue/pink/green/sky-blue visual identity. These generic themes are neither
affiliated with nor advertised by external companies. The source PBIP
preserves quantitative and business-status encodings: the country
Shape Map retains its measure-bound gradient, and Graphite Red
positive/negative semantics remain blue/red respectively.

## Finite remaining acceptance gates

1. **G2 native appearances:** capture and independently review both modes
   of representative new presets (especially Organic Palette, Sunny Palette
   and Graphite Red), then cover remaining themes to the approved extent.
   Check actual category differentiation, text, legends, density, gradients,
   card padding and map behavior—not just token contrast.
2. **G2 interactions:** verify expanded slicer dropdown, search, filter pane
   (Available/Applied) and selection states in actual Power BI Desktop.
3. **G6 release signoff:** separate owner approval after independent evidence
   review; PR must stay draft/unmerged until then.

**Known limits:** An official report-theme schema pass is not a Desktop pixel
pass; embedded images and opaque/custom visuals are not magically recolored.
Microsoft's pinned authoring validator rejects some global filter-pane theme
defaults, so the candidate applies supported page-level properties instead.
Real flyout styling still needs native review. Azure Maps sign-in limitations
of the separate Corporate Spend sample are not repaired by theme changes.

**Source integrity:** No company affiliation is asserted for the original
generic Organic Palette or Sunny Palette. Rewriting a feature branch and
deleting older Actions runs removes reachable advertised names but cannot
guarantee GitHub server-side garbage collection of unreachable commits.


## 25 October: Graphite Red / categorical clarity completion

Seven original synthetic Contoso bar/column report visuals encoded
categories using very similar numeric-gradient shades. The report now
explicitly uses PBIR scoped category identities with compiled palette
series indices (Microsoft theme color IDs start at 2). The value remains
encoded by bar length and exact data labels. The country Shape Map retains
the genuine quantitative color ramp.

Graphite Red has no green appearance role, and its original >=35% success,
waterfall increase and positive margin action-table text use blue while
negative/below-target still uses red.
Only the appearance colors change; DAX, thresholds, data bindings and numeric
results remain intact. The generic chart caption is color-neutral.
Five selected families now have ten Light/Dark live Desktop modes, 50 private
native full-page captures and 30 public report-only WebP previews; the other
nine families have 18 paired color swatches. Hash provenance binds these
images to GitHub-generated candidates from implementation commit `dddae21fa2fa1ccee59361715a68d8ede1e3914c`.
Independent G2/G4/G6 release approval remains separate.


## 25 October: strengthened category-color gate (second review)

Following a direct user review of the remote gallery, a critical
visual defect remained: the Gross Margin versus 35% target chart
displayed Electronics and Sports & Outdoors in exactly the same
below-target red. The previous detector exempted conditional business
status fills, so it returned a false sense of category-color
acceptance. New `color.category_conditional_shared_status` source
findings and a regression fixture require owners to resolve such
multi-category status reuse before claiming category identity.

The standard 7-category perceptual acceptance now requires
CIELAB ΔE76 >= 45 and approximate simulated protan/deutan/tritan
ΔE76 >= 15 for every in-chart pair (formerly only 40/9).
Two/three-category charts retain a more stringent 50/19.
The 28 Light/Dark palette data sets were regenerated within these
bounds; Graphite Red remains green-free. GM target values and its
35% reference line remain bound and visible. The prior waterfall
was changed to a category-colored regional variance comparison;
its implicit cumulative Total bar is no longer shown. The original
DAX variance measure and region grouping remain.

The updated gallery must only show real Power BI Desktop captures
created after these new gate checks, with report/model/palette and
capture hashes tied to the correct source. Old gallery hashes are
not evidence for this revised source.


## Native line-chart legend contrast final correction

Independent scrutiny of the complete 28-mode Desktop gallery found a
remaining dark-mode readability defect: the two-series *Monthly sales*
line-chart legend inherited Microsoft's very dark default text, even
when the active palette specified a readable `mutedForeground`.
The source-safe theme adaptation now adds an explicit PBIR
`visual.objects.legend[0].properties.labelColor` using that theme token
for built-in `lineChart` visuals with a title and no existing legend
entry. It does not change the legend's visibility, measure bindings,
line colors, axes or DAX.

Six parameterized regression cases cover Organic, Sunny and Arctic Aurora
Light/Dark, including a minimum 4.5:1 palette token/surface contrast and
original report/query invariance. The exact Microsoft-authored candidate
must be opened and inspected in Power BI Desktop before regenerating
the 140-page screenshot evidence.


## Deep-dive unscoped category fill correction

A final native five-page audit found that Deep-dive insights
→ Regional sales still rendered Europe, North America and
Asia Pacific in one identical default color. The previous QVS
assignment-pair detector did not recognize *missing assignments*:
without `visual.objects.dataPoint`, it had no pair to measure.

The synthetic Contoso regional bars now have explicit unique
PBIR scope selectors and native theme colors 2, 3 and 4,
with unchanged region and Reporting Year Sales bindings.
New `color.category_unscoped_default` HIGH-severity QVS output
flags categorical bar/column charts with a category axis but no
explicit per-category fills. GitHub's 28-candidate authoring
workflow and standalone pre-capture gate reject that finding.
The refreshed gallery must not reuse the earlier source hash.
