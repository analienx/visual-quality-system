# Adaptive theme engine (issue #80)

Apply a paired Light/Dark palette to an existing PBIP/PBIR report. The
engine updates the registered theme **and** supported inline overrides
by semantic role. It only ever writes a new candidate; the original
report, its semantic model, DAX, RLS, queries, filters, sorts,
selectors, and interactions are never modified.

## Commands

```console
vqs theme inspect REPORT --out theme-inventory.json
vqs theme preview REPORT --mode dark --out plan.json
vqs theme preview REPORT --mode light --palette executive.json --out plan.json
vqs theme apply REPORT --mode dark --candidate-root ./candidates/dark
vqs theme apply REPORT --mode light --palette executive.json --candidate-root ./candidates/light
vqs theme audit ./candidates/dark --out theme-audit.json
```

`REPORT` is a `*.Report` folder or a `.pbip` file (the sibling
`.Report` is resolved). `audit` accepts a candidate project folder, its
`.pbip`, or its `*.Report` folder. Exit codes follow the repo
convention: `0` pass, `1` demonstrated failure (audit), `2` blocked
(malformed input, unsafe candidate root, or palette contrast failure).

- `inspect` — read-only. Classifies known PBIR appearance hex/enum leaves; unsupported or ambiguous cases are explicitly reported.
- `preview` — read-only. Writes only the `--out` plan file. The plan is
  produced by the same planner `apply` uses, so previewed changes are
  exactly the applied changes.
- `apply` — writes a candidate **project**: `<Name>.Report`, a `.pbip`
  wrapper when the source project had one, a byte-identical sibling
  SemanticModel copy when `definition.pbir` `byPath` resolves inside
  the source project, and `theme-manifest.json` (source/candidate
  digests, palette hash, changes, counts, rollback). The candidate is
  built in a temp sibling and renamed atomically; the original digest
  is verified before and after. Refuses overlapping roots, symlinks or
  hardlinks in the source, and non-empty candidate roots.
- `audit` — re-inventories the candidate, verifies the manifest
  candidate digest, compares query/filter/sort/selector/interaction
  invariants and the model digest against the manifest-bound source,
  and checks resolved contrast pairs (foreground/canvas,
  foreground/surface, muted/surface, table-header fg/bg, slicer fg/bg).

Re-running `apply` with the same mode and palette on an
already-applied candidate is a no-op (empty plan, stable theme
filename). Applying light after dark (or the reverse) re-derives every
literal from its path role, so two-way conversion round-trips.

## Built-in palette selection

The installed VQS package includes **18 selectable preset families**:
**four backward-compatible legacy families** plus the **14 newly approved
families**, each available in Dark and Light (28 new modes). The legacy
families preserve their existing default and fallback behavior:

- `executive-blue` — existing Light and Dark
- `graphite-mint` — existing Dark override; Light inherits the default
- `warm-basalt` — existing Dark override; Light inherits the default
- `slate-lavender` — existing Dark override; Light inherits the default

The 14 approved additional families are `okabe-ito-night`, `petrol-gold`,
`indigo-ember`, `arctic-aurora`, `mediterranean-terra`,
`saffron-spruce`, `autumn-editorial`, `violet-ice`,
`electric-atelier`, `riviera-pop`, `bold-eclectic`, `graphite-red`,
`organic-palette`, and `sunny-palette`. See the
[approved 28-mode library](APPROVED_THEME_LIBRARY.md).

Use the same choices after packaging/installing, with no dependency on
the source repository's examples directory:

    vqs theme presets
    vqs theme preview REPORT --mode dark --palette-preset graphite-mint --out plan.json
    vqs theme apply REPORT --mode dark --palette-preset graphite-mint --candidate-root ./candidates/graphite
    vqs theme audit ./candidates/graphite

Explicit custom JSON is still supported using --palette but cannot be used
simultaneously with --palette-preset. Same source/mode/preset yields exactly
the same palette hash and candidate source-level changes.

## Palette format

One JSON file can carry both modes; a flat object is also accepted and
merges over the built-in `executive-blue` palette for the chosen mode:

```json
{
  "dark":  { "accent": "#7DD3FC", "canvas": "#0B1220" },
  "light": { "accent": "#1D4ED8" }
}
```

Roles: `canvas`, `surface`, `surfaceElevated`, `foreground`,
`mutedForeground`, `subtleText`, `outline`, `gridline`, `accent`,
`accentForeground`, `selection`, `selectionForeground`,
`slicerBackground`, `tableHeader`, `rowAlternate`, `tooltip`,
`dataColors` (at least 8), `good`, `neutral`, `bad`, `gradientMin`,
`gradientCenter`, `gradientMax`. All values must be `#RRGGBB`;
malformed palettes are blocked. The merged palette must pass WCAG
contrast self-checks (at least 4.5:1 for normal text pairs, 3:1 for
control boundaries such as `outline`); failures block with the exact
violating pairs. Unknown, transparent, or dynamic colors are reported
`unknown`, never passed.

## Coverage semantics

Each discovered PBIR color occurrence is classified with file, page, visual, JSON pointer,
old/new value, and role:

| Classification | Meaning |
| --- | --- |
| `supported` | Literal hex at a registry path; rewritten to the role color. |
| `supported-enum` | Azure Maps `defaultStyle`: light → `road`, dark → `night` (only when the property exists). |
| `preserved` | `ThemeDataColor` references, conditional/dynamic predicate structures, scoped `dataPoint` fills and data-point hexes outside source `dataColors` — kept unchanged with an exact-path warning. Data-point colors matching source `dataColors` map by stable series index. An unscoped chart `dataViewWildcard` fill (`matchingOption: 1`) maps to the first palette series color even when its old hardcoded hex is not in source `dataColors`; scoped business colors remain preserved. The **literal color stops** of supported `FillRule.linearGradient2/3` numeric ramps are safely recolored; their bound measures, thresholds and predicates remain unchanged. |
| `blocked` | Color on an unsupported/custom visual type, with exact path. |
| `unknown` | Transparent or alpha-channel colors; effective color cannot be resolved statically. |
| `not_applicable` | Hex outside a color property, and the superseded registered theme file. |

Role is derived from the property path and visual type (page
background/outspace → `canvas`; container background → `surface`;
title → `foreground`/`mutedForeground`; slicer header/items; chart
axes/legend/labels/gridlines; card value/label; textbox text runs;
shape fill/line/text; table/matrix headers, values, row headers,
totals), never from the old hex alone. The compiled theme is written
as `VQSAdaptive-<mode>-<12hex>.json` under
`StaticResources/RegisteredResources`, where the suffix is
`sha256(sourceDigest + paletteCanonical + mode)[:12]`, and registered
in `definition/report.json` (`themeCollection.customTheme` +
`resourcePackages`). The previous candidate theme file is removed only
inside the candidate.

## Categorical chart readability — 24 October corrective gate

The 14 approved families have **28 genuinely regenerated eight-series
categorical palettes**, with each family retaining its established first accent
and Light/Dark surface character. Color selection is now tested *against
other series*, not only the chart background. All 28 palettes must pass a
deterministic source-level color-separation screen with CIELAB ΔE76 minimum
24 for any pair (43 for the first two, commonly used by paired line charts),
plus separate approximate severe protan/deutan/tritan screening thresholds
of 9 (19 for the first two). The Machado matrices act on **linearized
sRGB**, not gamma-encoded RGB, before the CIELAB comparison. These are **screening thresholds** and not
medical claims, a complete accessibility guarantee or G2 native acceptance.

A bad approved preset fails when loaded; a custom/customer PBIP remains
supported. For existing reports, `vqs premium REPORT --format json` emits
`color.palette_series_collision` when a registered theme declares weak
categorical pairs in the presence of chart visuals. It marks these as
**source-proven palette risks, not witnessed pixels**. Another advisory,
`color.numeric_gradient_category_ambiguity`, flags numeric measure-driven
gradients on categorical bar/column charts, whose visually similar bars may
be *intentional quantitative encodings*. This does **not** remove or
reclassify a `FillRule`, replace DAX, or invert good/bad semantics.
Independently compare genuine native Power BI screenshots when judging
whether the original encoding meets business needs.

## Native text-contrast completion

Where a chart exposes a visible native legend (including donut/waterfall
examples and supported measure-bound gradient bars), supported
`legend.labelColor` is explicitly set rather than relying on a too-dim
built-in default. Shown visual subtitles without `fontColor` receive the
palette's contrast-safe muted text. This changes only appearance:
labels, measures, legend membership, titles, conditions and selectors remain
unchanged. Native screenshots, not schema validation alone, were used to
verify the initial dark-mode regression. Other, unsupported control states
remain blocked pending independent inspection.

## Limitations

- No Desktop toggle: this is a report authoring/conversion feature.
  It does not provide the Power BI Embedded JavaScript `applyTheme()`
  session switch, and Power BI Desktop's own dark UI mode does not
  darken the report canvas.
- No image pixels: static images, embedded SVGs, and opaque custom
  visuals are not recolored; unsupported visual types are `blocked`.
- No changes to dynamic business logic: conditional expressions, `FillRule`
  measures, thresholds/predicates and scoped data-point semantics remain
  unchanged. Only supported **literal numeric gradient color stops**
  (`linearGradient2/3`) can be restyled. Business meaning (for example
  red = overspend) is never inverted.
- Static proof only: schema-shaped output and WCAG ratios are not
  Desktop rendering, data, or design acceptance. Affected pages still
  need native render review per the acceptance matrix.
- Corporate Spend (#16) has pre-existing authoring-validation/export
  and Azure Maps authentication issues. Those are compatibility
  blockers, not theme regressions, and a sign-in wall cannot be fixed
  by swapping the basemap enum.

## Rollback

Delete the candidate project root and its `theme-manifest.json`. The
original report was never written; no other rollback step exists or is
needed.

## Separate integrity and appearance acceptance

Candidate audits return integrityStatus (manifest, model/query invariants
and static palette checks) and appearanceCoverageStatus (complete or partial).
An unresolved/blocked appearance leaf means overall status: unknown even if
integrity passes. This deliberately prevents a success claim for custom visuals,
dynamic transparency or other colors that are not statically resolvable.

On GitHub-hosted CI, scripts/theme_candidate_probe.py creates BOTH
Light and Dark versions of the actual 5-page Contoso PBIP, validates the theme
against Microsoft's October 2026 report-theme schema, checks each page canvas,
and invokes the real Microsoft report-authoring validator. This is not a
substitute for native Power BI Desktop rendering of actual content and slicers.

## Report filter-pane compatibility limit

The October 2026 Microsoft report-theme JSON Schema permits report-wide
outspacePane/filterCard defaults, but pinned Microsoft authoring CLI 0.5.0
rejects them as unknown formatting objects. For a validated authoring
candidate, this engine styles the actual page outspace and canvas explicitly
and does not emit those rejected report-global defaults. Instead, page-level PBIR
`outspacePane` and `filterCard` objects are styled as described below.
Schema validation confirms their structure, **not** the rendered open filter
flyout, search, selection or dropdown states; native Desktop review remains
required.

## Filter pane and dropdown chrome

The filter pane is now styled with page-level PBIR objects (outspacePane and
filterCard), not with rejected theme-level visualStyles groups. Every page
gets compatible background, label, outline, search/input and apply colors,
with distinct Available/Applied filter-card selectors. Existing report/page/
visual filter definitions, their values, bindings and applied selection
are NOT touched; only visual presentation properties are changed.
Supported slicer items, header and searchBox properties are themed.

Note that no structural validation can certify an opened dropdown
flyout or filter pane render: such states require native Power BI Desktop
screen captures and review. See docs/THEME_GALLERY.md.


## Initial five-family acceptance phase — expanded to all 14 on 25 October

The source Contoso sample encodes **categorical** dimensions with explicit
per-category `dataPoint.scopeId` + `ThemeDataColor` identities. Microsoft's
theme data-color IDs begin at **2**; indices 0/1 are reserved. Because
region, brand, category, subcategory, customer segment and store name identify
entities rather than numeric magnitude, those seven bar/column visuals
use distinct colors in all approved Light/Dark palettes. The genuine numeric
country Shape Map FillRule remains a separate measurable-color example.

Graphite Red deliberately avoids green throughout its theme roles: its
positive margin and waterfall-increase expressions use steel blue and
negative values stay red. In the synthetic Contoso candidate only, two
specifically identified positive appearance literals are recolored without
changing comparison conditions, thresholds, DAX or business category. Other
customer reports retain their conditionally formatted business colors.

The five featured gallery families are Sunny Palette, Organic Palette,
Graphite Red, Indigo Ember and Petrol & Gold. The remaining nine families
are displayed as compact palette swatches rather than fabricated screenshots.


## Per-visual category identity acceptance gate — 25 October

**A theme palette passing pairwise tests is not enough.** For built-in bar,
column and line series with explicit `dataPoint.scopeId` category selectors,
`vqs premium REPORT --format json` now resolves each native
`ThemeDataColor.ColorId` against that report's *active registered theme*,
with Microsoft's offset of two. It reports
`color.category_series_collision` (**HIGH**) with the exact chart ID,
category names, RGB colors and normal/approximate color-vision CIELAB distances
whenever two differently named categories receive identical or overly
similar colors in one chart. A two- or three-category chart requires
ΔE76 ≥ 50 and approximate simulated distance ≥ 19; charts with 4–7
categories now require 45 and 15 respectively. The previous 40/9
acceptance permitted visible near-collisions and was too permissive.
These are heuristic screening thresholds, not visual accessibility certification.

The pre-capture hard gate is now included in the official 28-candidate
GitHub authoring job. Reviewers may independently run:

```bash
python scripts/theme_gallery_color_gate.py /path/to/approved-theme-candidates --out category-preflight.json
```

Any unresolved category-color collision **exits nonzero**, stops the
candidate before screenshot creation, and records exactly which two category
assignments failed. Native screenshots are still needed to verify that
Microsoft Power BI rendered the expected colors. Continuous
`FillRule` measures and business-status conditions have separate semantics
and are never incorrectly described as distinct category identities.

The generic **Organic Palette** retains a vivid blue/pink/green/sky-blue
identity. **Sunny Palette** is anchored in warm orange and restrained grey,
with clearly contrasted supporting chart colors. Both use original custom
names and carry no claim of corporate affiliation or sponsorship.


### October 25 corrective acceptance revision

A pre-capture gate must also detect `color.category_conditional_shared_status`:
a wildcard conditional color on a categorical bar chart can color
multiple independent categories the **same red** when both fall below
a business threshold. The original Contoso Gross Margin target chart
demonstrated this failure even though its palette-wide chip distances
passed. The Contoso example now expresses categorical identities through
three distinct native fills while retaining the percentage data and
35% reference line; an explicit mutation regression reproduces the
old conditional-fill defect and proves QVS flags it.

For 4–7 category charts, distances below **45 CIELAB ΔE76** or
**15 approximate color-vision ΔE76** are now HIGH-severity errors,
not silently accepted. These are screening rules; actual pixel
rendering and independent perceptual review remain required.
This does not prohibit legitimate status-color encoding in non-category
business visuals, but it cannot certify that as distinct category colors.


### Final native screenshot acceptance: 100 chart regions

After the 28-mode source gate and Microsoft authoring validation,
run the *same* GitHub candidate artifacts in Power BI Desktop with
a real model refresh and capture all five pages in both modes for
each featured family. Then run:

```bash
python scripts/theme_native_category_pixel_gate.py /path/to/approved-candidates --out native-pixel-gate.json
```

The pixel gate checks the actual expected native theme colors for
**every series** in ten fixed synthetic Contoso chart regions,
across ten Light/Dark modes (100 checks). It covers 7 subcategories,
5 brands, 5 stores, 3 target GM bars, regional variance and
the supporting charts. It verifies source digest and exact
capture dimensions. It is deliberately *source-specific*, not a
universal image-recognition engine; separate independent screenshot
review remains essential. The published screenshot hashes must
also pass the ten-mode provenance audit.


### All 14 families: repeatable 168-check native gate

For the complete curated library, install the optional gallery dependencies
(`pip install -e ".[gallery,test]"`) and validate the **exact GitHub-generated**
28-mode candidate artifacts *after* five-page native Power BI Desktop capture:

```bash
python scripts/theme_gallery_color_gate.py ./approved-candidates --out pre-capture.json
python scripts/theme_native_category_pixel_gate.py ./approved-candidates --all-approved --out native-168-checks.json
python scripts/publish_approved_theme_gallery.py ./approved-candidates --authoring-head YOUR_EXACT_40_CHARACTER_GITHUB_SHA
```

The first gate checks actual assigned category colors before opening Desktop.
The second requires **140 chart checks** across all 28 modes (including
seven distinct product subcategory colors) plus **28 native Reporting Year
dropdown surface checks**, comparing pixels to the exact active palette
under the report's defined capture layout. It does not infer the appearance
of open menu flyouts or untested third-party visuals. The last command
publishes two real screenshot previews per mode, 28 token/control swatches
and full source/image provenance for the dedicated 14-family gallery.
Anomalous native screenshots must be investigated and recaptured, never
silently accepted by relaxing color separation.


### Unscoped categorical defaults and full five-page native coverage

The `color.category_unscoped_default` HIGH-risk rule covers
clustered/stacked categorical bar or column charts with a `Category`
query projection but **no explicit `dataPoint` assignments**.
These visuals inherit Power BI's single default series color across
different category values. The earlier pairwise rule could not
identify a pair because no native color assignments existed.
A synthetic Contoso Deep-dive regional-sales chart exposed the gap;
the source now assigns scope-based Europe/North America/Asia Pacific
color IDs 2/3/4 while preserving its sales measure.

The `--all-approved` native pixel gate now checks **11 populated
categorical/chart regions on all five report pages** in each of
28 Light/Dark modes (**308 chart checks**), plus 28 closed
Reporting Year dropdown background checks and 28 two-series
line-legend contrast/pixel checks (**364 checks total**).
The line-legend check additionally confirms that `mutedForeground`
is visible in the actual Desktop screenshot, preventing implicit
dark default text from slipping through. The regions are fixed
to the synthetic Contoso sample, not a universal visual classifier.
No source or gallery screenshot is accepted merely because the
screenshot CLI returned a successful exit code; blank/under-rendered
charts fail independently.
