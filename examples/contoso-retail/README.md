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

**Source provenance:** The PBIR report's SHA-256 source digest is `0e94efc38bd1ec852e4e079afb13b626ec586d5a9506ea607f691dfffa60c847` — **exactly the same** as the independently verified source used for the five rendered screenshots. The semantic model's source digest (all TMDL files plus `definition.pbism`, stable sorted paths and NUL delimiters) is `30040bd3b229fc8507d30cf58e30d393b5b65e9317b2159f3066772aa715ae3f`. All 12 M partitions generate their own synthetic data.

The demo intentionally excludes `.pbi/cache.abf`, binary PBIX, full-resolution screenshot evidence, accounts, secrets, and anything tied to a private user filesystem. The installed Desktop rebuilds the cache on its first refresh. The screenshot previews are downscaled derivatives and are **not** a formal independent G2 visual-quality approval.

**Preventing future mismatches:** `tests/test_public_showcase_example.py` checks that the report source digest, page identities, demo-model structure, and all five published image hashes still match this checked-in example. If you change the PBIP, regenerate the images from the updated source and update the documented provenance in the same PR.
