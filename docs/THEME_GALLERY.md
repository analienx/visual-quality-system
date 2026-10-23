# Theme gallery — five selectable Power BI colorways

VQS can apply a light corporate theme or four selectable dark themes to a
Power BI PBIP report without modifying the source semantic model or filters.

| Preset | Mode | Palette | Screenshot evidence |
| --- | --- | --- | --- |
| executive-blue | light | Original corporate light | Native capture pending |
| executive-blue | dark | Original navy dark | Native capture pending |
| graphite-mint | dark | Charcoal and restrained mint | **5 real captured pages** |
| warm-basalt | dark | Warm charcoal and gold | Native capture blocked |
| slate-lavender | dark | Soft slate and violet | Native capture pending |

## Actual Desktop screenshots — Graphite Mint

All images below are **real Power BI Desktop screenshots**, not AI-generated
dashboard illustrations or unpopulated report shells. Captured from the actual
synthetic Contoso Retail PBIP after refreshing its locally generated Power Query
data, at 2× capture scale. The model contains invented public-demo records.

Source: [candidate commit 1a5f4ca](https://github.com/analienx/visual-quality-system/commit/1a5f4cac96b82820f1dd2670eae00a748a921a6d);
[Microsoft authoring workflow](https://github.com/analienx/visual-quality-system/actions/runs/39977461272).
See [image manifest](images/themes/graphite-mint/manifest.json) for dimensions,
SHA-256 digests and capture method.

### Executive overview

[![Graphite Mint — Executive overview](images/themes/graphite-mint/executive-overview.png)](images/themes/graphite-mint/executive-overview.png)

### Products & brands

[![Graphite Mint — Products & brands](images/themes/graphite-mint/products-and-brands.png)](images/themes/graphite-mint/products-and-brands.png)

### Stores & customers

[![Graphite Mint — Stores & customers](images/themes/graphite-mint/stores-and-customers.png)](images/themes/graphite-mint/stores-and-customers.png)

### Markets & drivers

[![Graphite Mint — Markets & drivers](images/themes/graphite-mint/markets-and-drivers.png)](images/themes/graphite-mint/markets-and-drivers.png)

### Deep-dive insights

[![Graphite Mint — Deep-dive insights](images/themes/graphite-mint/deep-dive-insights.png)](images/themes/graphite-mint/deep-dive-insights.png)

## Select any built-in theme

```console
vqs theme presets
vqs theme preview "Contoso Retail.pbip" --mode dark --palette-preset graphite-mint --out theme-plan.json
vqs theme apply "Contoso Retail.pbip" --mode dark --palette-preset graphite-mint --candidate-root ./candidates/graphite
vqs theme audit ./candidates/graphite
```

Change `--palette-preset` to `executive-blue`, `warm-basalt` or
`slate-lavender`. The default Light mode is available as
`--mode light --palette-preset executive-blue`. Custom JSON with `--palette`
remains supported. All five selected themes passed official Microsoft authoring
validation in GitHub-hosted Windows and Linux CI at commit `1a5f4ca`.

## Filters and dropdowns

VQS themes page-level `objects.outspacePane` and `objects.filterCard`:
filter-pane backgrounds, text, borders and text inputs; distinct Applied
and Available filter states. It also themes supported slicer item/header and
`searchBox` colors. This avoids incompatible global filter-pane visualStyles
groups rejected by the pinned authoring CLI.

These source-level appearance changes preserve all DAX, report filters,
bindings and slicer selections. **Closed dropdowns and the filter pane are
visible in the captured screenshots, but expanded dropdown/flyout states have
not been independently validated** and must not be implied as verified.

## Remaining capture gate

The GH-hosted candidate artifacts exist for all five options and validate
successfully. Native Power BI Desktop screenshots for the other four themes
are **not** present. Warm Basalt was opened in its own Desktop instance and
its isolated synthetic model processed, but Microsoft's official screenshot
command returned `HOST_UNAVAILABLE` afterwards. Under the local authoring
skill's terminal rule, we did not bypass the host or substitute illustrative
screenshots. Blue Light/Dark and Slate Lavender remain pending native capture.

This gallery does **not** assert final visual G2 acceptance of all themes.
The PR stays draft until the remaining real Desktop captures and a same-page
side-by-side review have been completed. The underlying validated PBIP projects
are attached as GitHub Actions artifacts, not published screenshots.

See [theme engine CLI documentation](THEME_ENGINE.md) and
[palette design rationale](THEME_COLORWAYS.md).
