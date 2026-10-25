# Adaptive Power BI themes · release candidate · 24 October 2026

**Status: PR [#81](https://github.com/analienx/visual-quality-system/pull/81)
remains DRAFT and unmerged.** These are engineering candidate notes,
**not** a production release, independent G2 visual signoff or G6 merge approval.
The previous [21 October Power BI core notes](RELEASE_NOTES_2026-10-21.md)
remain valid for the code already in main.

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
  for the latest chart-assignment-quality implementation commit `dddae21fa2fa1ccee59361715a68d8ede1e3914c`.
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
  follow selected tokens while waterfall business semantics remain intact.

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
