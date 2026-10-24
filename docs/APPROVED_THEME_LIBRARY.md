# Approved Power BI theme library — 14 families, 28 modes

All fourteen approved families are selectable as actual Power BI report
theme presets in both Light and Dark, in addition to four legacy presets.
The three highlighted examples below are **real native Power BI Desktop screenshots**.
The other eleven are deliberately **color swatches only**, not simulated dashboards.
The same Contoso source report is used consistently for the real screenshots.

## Three featured palettes — authentic Power BI Desktop

[**Full gallery · three report pages per mode →**](REAL_THEME_SHOWCASE.md)
 · [Raw screenshot hashes and candidate digests](images/adaptive-showcase/PROVENANCE.json)

### Sunny Palette

| Light | Dark |
| :--- | :--- |
| [![Sunny Palette Light report](images/adaptive-showcase/sunny-palette-light/executive-overview.webp)](REAL_THEME_SHOWCASE.md) | [![Sunny Palette Dark report](images/adaptive-showcase/sunny-palette-dark/executive-overview.webp)](REAL_THEME_SHOWCASE.md) |

### Organic Palette

| Light | Dark |
| :--- | :--- |
| [![Organic Palette Light report](images/adaptive-showcase/organic-palette-light/executive-overview.webp)](REAL_THEME_SHOWCASE.md) | [![Organic Palette Dark report](images/adaptive-showcase/organic-palette-dark/executive-overview.webp)](REAL_THEME_SHOWCASE.md) |

### Graphite Red

| Light | Dark |
| :--- | :--- |
| [![Graphite Red Light report](images/adaptive-showcase/graphite-red-light/executive-overview.webp)](REAL_THEME_SHOWCASE.md) | [![Graphite Red Dark report](images/adaptive-showcase/graphite-red-dark/executive-overview.webp)](REAL_THEME_SHOWCASE.md) |

## Remaining eleven color families — true palette swatches

Each chip represents a packaged `dataColors` token from its selected mode;
the canvas/surface/text colors are taken directly from the same palette JSON.
These are not report screenshots or claims of independent native acceptance.

| Dark | Light |
| :--- | :--- |
| **#05 Okabe–Ito Night · Dark**<br>![#05 Okabe–Ito Night dark token swatch](images/approved-themes/swatches/okabe-ito-night-dark.svg) | **#05 Okabe–Ito Night · Light**<br>![#05 Okabe–Ito Night light token swatch](images/approved-themes/swatches/okabe-ito-night-light.svg) |
| **#08 Petrol & Gold · Dark**<br>![#08 Petrol & Gold dark token swatch](images/approved-themes/swatches/petrol-gold-dark.svg) | **#08 Petrol & Gold · Light**<br>![#08 Petrol & Gold light token swatch](images/approved-themes/swatches/petrol-gold-light.svg) |
| **#09 Indigo Ember · Dark**<br>![#09 Indigo Ember dark token swatch](images/approved-themes/swatches/indigo-ember-dark.svg) | **#09 Indigo Ember · Light**<br>![#09 Indigo Ember light token swatch](images/approved-themes/swatches/indigo-ember-light.svg) |
| **#12 Arctic Aurora · Dark**<br>![#12 Arctic Aurora dark token swatch](images/approved-themes/swatches/arctic-aurora-dark.svg) | **#12 Arctic Aurora · Light**<br>![#12 Arctic Aurora light token swatch](images/approved-themes/swatches/arctic-aurora-light.svg) |
| **#14 Mediterranean Terra · Dark**<br>![#14 Mediterranean Terra dark token swatch](images/approved-themes/swatches/mediterranean-terra-dark.svg) | **#14 Mediterranean Terra · Light**<br>![#14 Mediterranean Terra light token swatch](images/approved-themes/swatches/mediterranean-terra-light.svg) |
| **#15 Saffron & Spruce · Dark**<br>![#15 Saffron & Spruce dark token swatch](images/approved-themes/swatches/saffron-spruce-dark.svg) | **#15 Saffron & Spruce · Light**<br>![#15 Saffron & Spruce light token swatch](images/approved-themes/swatches/saffron-spruce-light.svg) |
| **#18 Autumn Editorial · Dark**<br>![#18 Autumn Editorial dark token swatch](images/approved-themes/swatches/autumn-editorial-dark.svg) | **#18 Autumn Editorial · Light**<br>![#18 Autumn Editorial light token swatch](images/approved-themes/swatches/autumn-editorial-light.svg) |
| **#19 Violet Ice · Dark**<br>![#19 Violet Ice dark token swatch](images/approved-themes/swatches/violet-ice-dark.svg) | **#19 Violet Ice · Light**<br>![#19 Violet Ice light token swatch](images/approved-themes/swatches/violet-ice-light.svg) |
| **#25 Electric Atelier · Dark**<br>![#25 Electric Atelier dark token swatch](images/approved-themes/swatches/electric-atelier-dark.svg) | **#25 Electric Atelier · Light**<br>![#25 Electric Atelier light token swatch](images/approved-themes/swatches/electric-atelier-light.svg) |
| **#26 Riviera Pop · Dark**<br>![#26 Riviera Pop dark token swatch](images/approved-themes/swatches/riviera-pop-dark.svg) | **#26 Riviera Pop · Light**<br>![#26 Riviera Pop light token swatch](images/approved-themes/swatches/riviera-pop-light.svg) |
| **#30 Bold Eclectic · Dark**<br>![#30 Bold Eclectic dark token swatch](images/approved-themes/swatches/bold-eclectic-dark.svg) | **#30 Bold Eclectic · Light**<br>![#30 Bold Eclectic light token swatch](images/approved-themes/swatches/bold-eclectic-light.svg) |

## Apply a palette without altering the source

```bash
vqs theme presets
vqs theme preview "examples/contoso-retail/Contoso Retail.pbip" --mode dark --palette-preset sunny-palette --out plan.json
vqs theme apply "examples/contoso-retail/Contoso Retail.pbip" --mode light --palette-preset organic-palette --candidate-root ./organic-candidate
vqs theme audit ./organic-candidate
```

Candidates are isolated and source-bound. Dynamic business rules are preserved;
literal category and supported numeric gradient colors are recolored under
the documented safety registry. See [theme engine](THEME_ENGINE.md) and
[approval manifest](APPROVED_THEME_SELECTION.json).
Native screenshots do not prove interaction-state styling or independent release
approval; those remain separate review gates.
