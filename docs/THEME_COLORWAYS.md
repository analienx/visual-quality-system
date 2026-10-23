# Flat dark colorways — candidate design review

**Status:** design alternatives only. Do not substitute color swatches, JSON
schemas or hosted candidates for native Power BI Desktop screenshot acceptance.
Original `executive-blue` Light and Dark defaults are unchanged.

## Why these palettes

The current default Dark (`#0B1220` page, `#111C2E` cards,
`#1A2A44` elevated) makes almost every surface blue, competing with the
actual data. An executive report should be legible, restrained and
data-first. The three colorways use near-neutral surfaces, subtle tonal
elevation, a single sparing accent, and eight softer chart series.

### Options

| Role | Graphite Mint (preferred) | Warm Basalt | Slate Lavender |
| --- | --- | --- | --- |
| Canvas | `#17191C` | `#1A1A19` | `#191A21` |
| Surface | `#22262A` | `#252523` | `#242631` |
| Elevated | `#2D3236` | `#30302D` | `#303240` |
| Primary text | `#F4F4F0` | `#F5F3EA` | `#F4F4F8` |
| Accent | `#7CCFBA` | `#E1BE83` | `#B7ABEE` |
| Mood | neutral + fresh jade | editorial + understated gold | creative + subdued lilac |

Graphite Mint is the preferred *first native candidate*, not an imposed new
default. Its accents are less saturated and the neutral layers provide
separation with minimal outlines. Use color only to mark selection,
categorical difference or business meaning. Keep measure-bound red/green
semantics, waterfall polarity colors, dynamic `FillRule` and manual selectors
unchanged.

Contrast self-checks (WCAG relative luminance) ensure foreground on canvas,
surface and elevated, muted label on surface, selection contrast, tooltip
contrast and outline against both canvas and surface meet existing VQS
4.5:1 / 3:1 gates. The chart series are checked against the surface
background at 3:1 but are not certified color-blind distinguishable by
contrast alone. Legends/labels and direct values remain mandatory.

### References

- IBM Carbon: neutral-gray dominance and lighter dark elevation
  https://www.carbondesignsystem.com/building-blocks/foundations/color/overview
- Microsoft Fluent 2: neutral surfaces for hierarchy, brand color used
  purposefully https://fluent2.microsoft.design/color
- IBM Carbon data visualization: ordered categorical contrast
  https://www.carbondesignsystem.com/building-blocks/data-visualization/color-palettes
- Atlassian elevation: flat cards with subtle borders
  https://atlassian.design/foundations/elevation
- Tableau's softer categorical palettes:
  https://www.tableau.com/blog/colors-upgrade-tableau-10-56782

## Try without changing existing presets

```console
vqs theme preview "examples/contoso-retail/Contoso Retail.pbip" --mode dark --palette examples/theme-palettes/dark-graphite-mint.json --out graphite-plan.json
vqs theme apply "examples/contoso-retail/Contoso Retail.pbip" --mode dark --palette examples/theme-palettes/dark-graphite-mint.json --candidate-root /path/outside/source/contoso-graphite
vqs theme audit /path/outside/source/contoso-graphite
```

Swap `dark-graphite-mint.json` with `dark-warm-basalt.json` or
`dark-slate-lavender.json` to compare. Palette files contain `dark`
overrides only. Selecting any palette in Light mode must leave the Light
built-in unchanged.

The hosted `Authoring real-CLI probe` creates and validates all three
actual five-page Contoso PBIP projects on GitHub-hosted Windows and Ubuntu,
runs schema/contrast/model-invariance checks, and publishes disposable
`themed-contoso-colorways-<OS>` evidence artifacts. These are **not**
actual rendered images. Native Desktop screenshots on all five pages remain
a separate acceptance gate and require user design approval before
publishing screenshot evidence to README or the repo.
