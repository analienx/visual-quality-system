# Power BI Theme Gallery — five colorways

**25 real Contoso report-page screenshot previews, five selectable themes.**
Every image derives from an actual Power BI Desktop capture of the same
five-page synthetic Contoso Retail PBIP with locally generated fictional data.
No UI mockups, customer data or AI-generated dashboards are used. The 1600px
public previews are resized from original 3915px Desktop captures retained
outside Git; both public and original SHA-256 hashes are in manifests.

## Compare the same report across five themes

| **Executive Blue Light** | **Executive Blue Dark** |
| :--- | :--- |
| [![Executive Blue Light executive overview](images/themes/light/executive-overview.png)](images/themes/light/executive-overview.png) | [![Executive Blue Dark executive overview](images/themes/blue-dark/executive-overview.png)](images/themes/blue-dark/executive-overview.png) |

| **Graphite Mint** | **Warm Basalt** |
| :--- | :--- |
| [![Graphite Mint executive overview](images/themes/graphite-mint/executive-overview.png)](images/themes/graphite-mint/executive-overview.png) | [![Warm Basalt executive overview](images/themes/warm-basalt/executive-overview.png)](images/themes/warm-basalt/executive-overview.png) |

**Slate Lavender**

[![Slate Lavender executive overview](images/themes/slate-lavender/executive-overview.png)](images/themes/slate-lavender/executive-overview.png)

## View every captured page

| Page | Executive Blue Light | Executive Blue Dark | Graphite Mint | Warm Basalt | Slate Lavender |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Executive overview | [View PNG](images/themes/light/executive-overview.png) | [View PNG](images/themes/blue-dark/executive-overview.png) | [View PNG](images/themes/graphite-mint/executive-overview.png) | [View PNG](images/themes/warm-basalt/executive-overview.png) | [View PNG](images/themes/slate-lavender/executive-overview.png) |
| Products & brands | [View PNG](images/themes/light/products-and-brands.png) | [View PNG](images/themes/blue-dark/products-and-brands.png) | [View PNG](images/themes/graphite-mint/products-and-brands.png) | [View PNG](images/themes/warm-basalt/products-and-brands.png) | [View PNG](images/themes/slate-lavender/products-and-brands.png) |
| Stores & customers | [View PNG](images/themes/light/stores-and-customers.png) | [View PNG](images/themes/blue-dark/stores-and-customers.png) | [View PNG](images/themes/graphite-mint/stores-and-customers.png) | [View PNG](images/themes/warm-basalt/stores-and-customers.png) | [View PNG](images/themes/slate-lavender/stores-and-customers.png) |
| Markets & drivers | [View PNG](images/themes/light/markets-and-drivers.png) | [View PNG](images/themes/blue-dark/markets-and-drivers.png) | [View PNG](images/themes/graphite-mint/markets-and-drivers.png) | [View PNG](images/themes/warm-basalt/markets-and-drivers.png) | [View PNG](images/themes/slate-lavender/markets-and-drivers.png) |
| Deep-dive insights | [View PNG](images/themes/light/deep-dive-insights.png) | [View PNG](images/themes/blue-dark/deep-dive-insights.png) | [View PNG](images/themes/graphite-mint/deep-dive-insights.png) | [View PNG](images/themes/warm-basalt/deep-dive-insights.png) | [View PNG](images/themes/slate-lavender/deep-dive-insights.png) |

## Select a palette

| Mode | CLI preset | Design |
| :--- | :--- | :--- |
| light | `executive-blue` | Bright corporate |
| dark | `executive-blue` | Deep navy |
| dark | `graphite-mint` | Graphite / jade |
| dark | `warm-basalt` | Charcoal / gold |
| dark | `slate-lavender` | Slate / violet |

```console
vqs theme presets
vqs theme preview REPORT --mode dark --palette-preset graphite-mint --out theme-plan.json
vqs theme apply REPORT --mode dark --palette-preset graphite-mint --candidate-root ./candidate-graphite
vqs theme audit ./candidate-graphite
```

Custom palette JSON is also supported using `--palette`.

## Filter-pane, slicer and dropdown behavior

The image captures show the dark or light report canvas, closed in-report
slicers, and the native filter pane. The engine styles page-level
outspacePane and filterCard, including Available/Applied card roles, and
supported slicer header/items/searchBox colors without modifying
filter definitions, selectors or the semantic model.

**The expanded slicer dropdown, selected-card popovers, filter flyouts,
and user interaction states have not received independent screenshot
review.** A screenshot with a closed dropdown is not proof of its expanded
colors or behavior.

## Capture provenance and acceptance boundaries

These are genuine synthetic-demo presentation previews, not raw G2 runtime
evidence. Each page was captured via the official Power BI Desktop authoring
interface after Microsoft Modeling MCP Full processing. Every palette is
sourced from the identical five-page Contoso report and Git revision
[1a5f4ca](https://github.com/analienx/visual-quality-system/commit/1a5f4cac96b82820f1dd2670eae00a748a921a6d),
and passed [official Microsoft authoring validation](https://github.com/analienx/visual-quality-system/actions/runs/39977461272).

- [Executive Blue Light public-preview and source-capture hash manifest](images/themes/light/manifest.json)
- [Executive Blue Dark public-preview and source-capture hash manifest](images/themes/blue-dark/manifest.json)
- [Graphite Mint public-preview and source-capture hash manifest](images/themes/graphite-mint/manifest.json)
- [Warm Basalt public-preview and source-capture hash manifest](images/themes/warm-basalt/manifest.json)
- [Slate Lavender public-preview and source-capture hash manifest](images/themes/slate-lavender/manifest.json)

Structural validity and beautiful captures do not replace G2 independent
visual acceptance and G6 owner release approval. The PR remains a draft
until those checks are signed off. These demo screenshots are safe for the
public project because all report values are generated fictional data.

See [Theme Engine](THEME_ENGINE.md) and
[Colorway Design Rationale](THEME_COLORWAYS.md).
