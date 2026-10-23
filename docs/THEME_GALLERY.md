# Theme gallery — five real Power BI colorways

The gallery will be generated from **actual Contoso Retail PBIP candidates**.
These are the five selectable themes:

| Preset | Mode | Design intent | Palette source |
| --- | --- | --- | --- |
| executive-blue | light | Clean corporate default | built-in |
| executive-blue | dark | Existing cool navy | built-in |
| graphite-mint | dark | Neutral graphite + restrained jade | bundled |
| warm-basalt | dark | Warm charcoal + gold | bundled |
| slate-lavender | dark | Soft slate + violet | bundled |

## Preview and choose

Use the packaged preset registry (available in installed VQS wheels):

```sh
vqs theme presets
vqs theme preview "Contoso Retail.pbip" --mode dark --palette-preset graphite-mint --out theme-plan.json
vqs theme apply "Contoso Retail.pbip" --mode dark --palette-preset graphite-mint --candidate-root ./output/graphite
vqs theme audit ./output/graphite
```

Use `--palette path/to/colors.json` for custom colors instead of
`--palette-preset`. The original report and semantic model are unchanged.

## Report screenshots

**Native Power BI Desktop render gallery is awaiting exact-candidate
captures and human review.** No palette mockups or generated dashboard
images are presented as real Power BI screenshot evidence. Once captures
are available, each colorway must show the same five Contoso pages at a
fixed viewport and zoom. Filters-pane and slicer-dropdown states must be
captured and assessed separately, with applied/available card colors
visible. The screenshots will be published only when they are actual
captured demo renders with recorded digest, Desktop build and user
approval. Static authoring success does not substitute for that check.

The continuous-integration authoring workflow exports all five
theme candidate projects as GitHub artifacts, covering schema validity
and source/model invariants. Use those exact candidates as the source
of native Desktop captures. Do not commit personal or customer reports,
data, token caches or raw bridge logs.

## Filters and slicer styling

Page-level `objects.outspacePane` now controls the filter pane chrome
(background, foreground, input, border, apply action) and
`objects.filterCard` applies distinct appearance to `Applied` and
`Available` state selectors. This is intentionally **page level**:
the pinned Microsoft authoring CLI rejects global theme
`visualStyles["*"]["*"].filterCard` and `outspacePane`, despite them
being allowed by the current Microsoft theme JSON schema.

Slicer items/header/searchBox colors are written only using supported
PBIR properties. Filter definitions, query selections and bookmarks are
not changed. Unsupported native dropdown popover pixels and report
filter flyouts remain a visual acceptance question until Desktop
screenshots demonstrate behavior.

References: Microsoft filter-pane metadata
https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-report-filter
and pinned local Power BI authoring skill filter-pane reference.
