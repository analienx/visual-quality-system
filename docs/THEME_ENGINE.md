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
| `preserved` | `ThemeDataColor` references, `FillRule`/conditional/dynamic expressions, scoped `dataPoint` fills, and data-point hexes outside the source `dataColors` — kept byte-identical, with a warning and exact path. Data-point fills matching a source `dataColors` index map by that index. |
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

## Limitations

- No Desktop toggle: this is a report authoring/conversion feature.
  It does not provide the Power BI Embedded JavaScript `applyTheme()`
  session switch, and Power BI Desktop's own dark UI mode does not
  darken the report canvas.
- No image pixels: static images, embedded SVGs, and opaque custom
  visuals are not recolored; unsupported visual types are `blocked`.
- No dynamic rules: conditional formatting, `FillRule`s, dynamic
  expressions, and scoped data-point colors are preserved, not
  restyled. Business meaning (for example red = overspend) is never
  inverted.
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
and does not emit those rejected report-global defaults. Therefore filter-pane
chrome is NOT certified dark/light in this version, and must be checked in
native Desktop. This known limitation is not concealed as full visual coverage.
