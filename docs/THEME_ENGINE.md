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
of 9 (19 for the first two). These are **screening thresholds** and not
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
