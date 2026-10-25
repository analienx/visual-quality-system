# Contoso Retail · reproducible Power BI example

**This is the actual PBIP used to create the five dashboard screenshots in the repository README.** It is not a decorative mockup.

[Open the PBIP project](Contoso%20Retail.pbip) · [See the public screenshot gallery](../../docs/media/showcase/ASSET_PROVENANCE.md) · [Return to the main README](../../README.md)

## Open and reproduce

1. Clone this repository and open `examples/contoso-retail/Contoso Retail.pbip` with a recent **Power BI Desktop** installation that supports enhanced PBIP/PBIR and native Shape Map visuals.
2. **On first open, select Refresh now** when Desktop reports that relationships or tables need refreshing. The published project contains no imported local cache (`.pbi/cache.abf`), so the visuals initially display blanks until its embedded Power Query M partitions run. This behavior was directly tested on a fresh copy from this repository.
3. Open **Executive overview**. At the default Reporting year = All, the refreshed model should display approximately **$6.82M Sales**, **10.0% YoY growth**, and **33.9% gross margin**. The screenshots capture that same initial state, not a different report.
4. Browse the four other pages: **Products & brands**, **Stores & customers**, **Markets & drivers**, and **Deep-dive insights**. The deep-dive uses the report's native Shape Map; its availability can depend on Power BI Desktop settings.

No external server, company account, cloud data source, Excel/CSV file, credential, or premium subscription is needed to refresh the embedded **fictional demo data**. The report is a demonstration of inspected Power BI output, not a screenshot of a VQS app.

## Inspect the same report with VQS

From the repository root:

```bash
python -m pip install -e ".[test]"
vqs triage "examples/contoso-retail/Contoso Retail.pbip" --out quality.md
vqs premium "examples/contoso-retail/Contoso Retail.pbip" --init-contract design-intent.json
# Edit the generated intent, then:
vqs premium "examples/contoso-retail/Contoso Retail.pbip" --contract design-intent.json --out premium.md
```

The commands are read-only against the sample. For real Power BI Desktop capture and interaction testing, see the [native quickstart](../../docs/QUICKSTART.md).

## The five matching screenshots

| PBIR page | Public screenshot |
| --- | --- |
| Executive overview | [Executive overview](../../docs/media/showcase/executive-overview.webp) |
| Products & brands | [Products & brands](../../docs/media/showcase/products-brands.webp) |
| Stores & customers | [Stores & customers](../../docs/media/showcase/stores-customers.webp) |
| Markets & drivers | [Markets & drivers](../../docs/media/showcase/markets-drivers.webp) |
| Deep-dive insights | [Deep-dive with Shape Map](../../docs/media/showcase/deep-dive-map.webp) |

**Source provenance:** The PBIR report's SHA-256 source digest is `1c38fc2c2af5bc4595d0b015eed0ed828b70b9af8c8c9a6844bd5587a7a82d69` — **updated on 25 October** from the 22 October native Desktop source used for all five rendered screenshots. The semantic model's source digest (all TMDL files plus `definition.pbism`, stable sorted paths and NUL delimiters) is `30040bd3b229fc8507d30cf58e30d393b5b65e9317b2159f3066772aa715ae3f`. All 12 M partitions generate their own synthetic data.

The demo intentionally excludes `.pbi/cache.abf`, binary PBIX, full-resolution screenshot evidence, accounts, secrets, and anything tied to a private user filesystem. The installed Desktop rebuilds the cache on its first refresh. The screenshot previews are downscaled derivatives and are **not** a formal independent G2 visual-quality approval.

**Preventing future mismatches:** `tests/test_public_showcase_example.py` checks that the report source digest, page identities, demo-model structure, and all five published image hashes still match this checked-in example. If you change the PBIP, regenerate the images from the updated source and update the documented provenance in the same PR.


### Explicitly distinguishable categorical chart bars (25 October update)

The seven **categorical** bar/column charts intentionally assign stable
per-value colors using Power BI native `dataPoint.scopeId` identities,
referencing the active theme's eight `dataColors`. Region, brand,
subcategory, category, segment and store identity therefore remain visually
distinct even when different bars have similar sales or gross-margin values.
These are categorical colors, **not** approximate indicators of magnitude:
sales and margin are encoded by bar length and exact data labels. The
country Shape Map retains its **real measure-bound numeric gradient**.

The **gross margin vs 35% target** visual and the waterfall remain
measure-bound *business polarity* charts rather than categorical charts.
Graphite Red intentionally uses steel blue (instead of green) for the
positive/increase state and red for negative/below-target, without changing
the measure or conditional thresholds. The generic source caption uses
value-based words rather than promising particular hues.


### Channel category readability

The “How sales are delivered” chart uses separate Retail and Online
native category selectors and two contrasting `ThemeDataColor` references,
rather than a single wildcard bar fill. QVS premium now flags flat wildcard
fills on category charts as a high-priority risk. Conditional target-status
charts remain exempt because their colors represent business meaning, not
category identity.


### Categorical color identity — target chart correction

The Executive overview gross-margin-versus-35%-target chart now binds
Electronics, Home & Appliances and Sports & Outdoors to three separate
native `ThemeDataColor` category identities, rather than the old
wildcard conditional status red/green encoding. This preserves the
35% reference line, percentages, query bindings and performance labels,
while preventing Electronics and Sports & Outdoors from becoming identical
red bars. The QVS pre-capture gate also flags any future wildcard
conditional-fill regression on a multi-category chart.


### Regional movement presentation

The *Sales movement by region* chart uses a category-colored native
clustered column comparison. The `Reporting Year Sales Variance` DAX
measure, `Dim Store.Region` grouping and GM tooltip stay unchanged.
The previous cumulative waterfall's automatically generated Total bar
is no longer part of this visual; the net variance is the sum of
the three regional bars. This deliberate presentation trade-off avoids
reusing one Increase color for three different named regions.
