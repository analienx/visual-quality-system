<div align="center">
  <img src="docs/media/showcase/vqs-brand.svg" width="100%" alt="Visual Quality System — inspect, improve and verify Power BI reports">
  <h2>Make every Power BI report worth trusting.</h2>
  <p><strong>Diagnose the source. Refine the design. Verify what users actually see.</strong></p>
  <p>Deterministic PBIP checks · Source-safe Light/Dark themes · Real Power BI Desktop evidence</p>
  <p>
    <a href="#try-it">Quick start</a> ·
    <a href="#real-power-bi-showcase">Real report screenshots</a> ·
    <a href="docs/README.md">Documentation</a> ·
    <a href="docs/ARCHITECTURE.md">Architecture</a>
  </p>
  <p>
    <a href="https://github.com/analienx/visual-quality-system/actions/workflows/ci.yml"><img src="https://github.com/analienx/visual-quality-system/actions/workflows/ci.yml/badge.svg" alt="GitHub CI status"></a>
    <img src="https://img.shields.io/badge/Python-3.11%2B-3270B7" alt="Python 3.11 and newer">
    <img src="https://img.shields.io/badge/License-Apache--2.0-18977A" alt="Apache 2.0">
    <img src="https://img.shields.io/badge/Status-engineering%20preview-E2A744" alt="Engineering preview, not production-certified">
  </p>
</div>

## Real Power BI showcase

**Seven curated families on the homepage. All 14 Light/Dark families in the full gallery.**
These are real, populated Power BI Desktop screenshots captured from one
fictional Contoso Retail report; none is a simulated dashboard.
Each screenshot is bound to the generating GitHub candidate and source hash.

**[Explore the complete 14-family native gallery](docs/REAL_THEME_SHOWCASE.md)**

[Open the exact fictional Power BI source report](examples/contoso-retail/Contoso%20Retail.pbip) — the screenshots are taken from validated variants of this PBIP. ·
[Compare all color and control tokens](docs/APPROVED_THEME_LIBRARY.md) ·
[View the provenance](docs/images/adaptive-showcase/PROVENANCE.json)

### Sunny Palette

Amber-orange and charcoal, with soft peach control surfaces.

| Light · actual report | Dark · actual report |
| :--- | :--- |
| [![Sunny Palette Light real Power BI report](docs/images/adaptive-showcase/sunny-palette-light/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#sunny-palette) | [![Sunny Palette Dark real Power BI report](docs/images/adaptive-showcase/sunny-palette-dark/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#sunny-palette) |

### Organic Palette

Cobalt, vivid magenta, green and cyan with differentiated controls.

| Light · actual report | Dark · actual report |
| :--- | :--- |
| [![Organic Palette Light real Power BI report](docs/images/adaptive-showcase/organic-palette-light/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#organic-palette) | [![Organic Palette Dark real Power BI report](docs/images/adaptive-showcase/organic-palette-dark/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#organic-palette) |

### Graphite Red

Graphite, ruby and carefully contrasted supporting hues — no green.

| Light · actual report | Dark · actual report |
| :--- | :--- |
| [![Graphite Red Light real Power BI report](docs/images/adaptive-showcase/graphite-red-light/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#graphite-red) | [![Graphite Red Dark real Power BI report](docs/images/adaptive-showcase/graphite-red-dark/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#graphite-red) |

### Indigo Ember

Indigo-violet balanced with warm editorial accents.

| Light · actual report | Dark · actual report |
| :--- | :--- |
| [![Indigo Ember Light real Power BI report](docs/images/adaptive-showcase/indigo-ember-light/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#indigo-ember) | [![Indigo Ember Dark real Power BI report](docs/images/adaptive-showcase/indigo-ember-dark/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#indigo-ember) |

### Petrol & Gold

Petrol and warm gold for a confident executive dashboard.

| Light · actual report | Dark · actual report |
| :--- | :--- |
| [![Petrol & Gold Light real Power BI report](docs/images/adaptive-showcase/petrol-gold-light/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#petrol-gold) | [![Petrol & Gold Dark real Power BI report](docs/images/adaptive-showcase/petrol-gold-dark/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#petrol-gold) |

### Riviera Pop

Expressive seaside color, controlled by a disciplined layout.

| Light · actual report | Dark · actual report |
| :--- | :--- |
| [![Riviera Pop Light real Power BI report](docs/images/adaptive-showcase/riviera-pop-light/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#riviera-pop) | [![Riviera Pop Dark real Power BI report](docs/images/adaptive-showcase/riviera-pop-dark/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#riviera-pop) |

### Okabe–Ito Night

Clear categorical hues and understated interface chrome.

| Light · actual report | Dark · actual report |
| :--- | :--- |
| [![Okabe–Ito Night Light real Power BI report](docs/images/adaptive-showcase/okabe-ito-night-light/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#okabe-ito-night) | [![Okabe–Ito Night Dark real Power BI report](docs/images/adaptive-showcase/okabe-ito-night-dark/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#okabe-ito-night) |

**[See all 14 palettes and 56 authentic report previews](docs/REAL_THEME_SHOWCASE.md)**

The gallery also shows Products & Brands, making all seven subcategory
colors easy to compare. Each control palette includes themed dropdown,
filter and selection surfaces. Interactive flyouts remain separately
reviewable; static screenshots are not interaction certification.

## Try it

Install and analyze a report **without Power BI Desktop, a Microsoft account or a cloud subscription**:

```bash
git clone https://github.com/analienx/visual-quality-system.git
cd visual-quality-system
python -m pip install -e ".[test]"
vqs triage tests/powerbi/fixtures/mini_report --out quality.md
```

Open `quality.md` to inspect the source-located findings; nothing in the report is changed.

### Re-theme a real PBIP, safely

```bash
vqs theme presets
vqs theme preview "examples/contoso-retail/Contoso Retail.pbip" --mode dark --palette-preset sunny-palette --out theme-plan.json
vqs theme apply "examples/contoso-retail/Contoso Retail.pbip" --mode light --palette-preset organic-palette --candidate-root ./organic-candidate
vqs theme audit ./organic-candidate
```

`preview` is read-only; `apply` creates a separate candidate and audit manifest. Generated candidates preserve source PBIP, semantic model, DAX, field bindings and business-measure predicates. The Contoso showcase now encodes product and region categories with distinct colors, while keeping business values and the 35% reference line. The generated candidate may need a first-open refresh in Power BI Desktop to populate its local sample model.

[**Theme engine guide**](docs/THEME_ENGINE.md) · [CLI reference](docs/CLI.md) · [Five-page sample](examples/contoso-retail/README.md)

## One workflow, verifiable boundaries

| Step | What it does | What establishes confidence |
| :--- | :--- | :--- |
| **Inspect** | Analyze PBIR layout, TMDL/DAX bindings, contrast and report structure | Deterministic source diagnostics and exact-path findings |
| **Improve** | Offer prioritized design changes; generate bounded, reversible repairs and palettes | Diff, candidate hash, Microsoft authoring schema and original-source invariance |
| **Observe** | Capture populated Power BI Desktop screens; check supported UIA interactions | Exact report/PID, native rendered images and live model DAX |
| **Review** | Package evidence and distinguish PASS, FAIL, unsupported and N/A states | Independent visual judgment and separate release/publisher approval |

<a href="docs/ARCHITECTURE.md"><img src="docs/diagrams/product-flow.svg" width="100%" alt="Power BI VQS system flow, from report files through deterministic checks, desktop evidence, and independent review"></a>

**Architecture in one sentence:** GitHub/Linux/Windows runners handle portable static analysis; a supported Windows Desktop session provides native pixels and interactions. [View the complete, simplified architecture](docs/ARCHITECTURE.md).

### Beyond a pretty screenshot

VQS provides an explicit `vqs premium` design contract for hierarchy, spacing and quality review, rather than claiming to know that a screenshot is attractive from source JSON alone. The engine validates **colors actually assigned to different categories inside each chart**, not merely the theme swatches. This catches near-duplicate Electronics/Sports colors, unscoped Retail/Online fills and **identical reds caused by conditional status fills** as HIGH-severity source findings. The 28-mode GitHub candidate workflow and pre-capture gate refuse to publish a candidate while any such violation remains. The 4–7-category normal/color-vision thresholds are **45/15**, and three-category limits are **50/19**. Ten chart regions per native mode undergo independent pixel checks before screenshot publication. Numeric gradients and business-status measures are preserved; distinct category colors are used where the showcase calls for category identity. The featured examples are authentic Desktop recaptures of the category-distinct, QVS-gated source. The bundled Contoso Retail report includes charts, tables, slicers and a **no-sign-in Shape Map**.

The distinct Corporate Spend subject has documented Azure Maps sign-in and schema-compatibility limitations; it is **not** presented as a fully certified cross-report success. Likewise, static authoring validation across **28 approved new Dark/Light modes** is not a claim that all 28 were independently rendered and visually signed off. Real interaction states and the `powerbi-core` release G2/G4/G6 acceptance remain separately gated.

[Evidence & acceptance](docs/ACCEPTANCE_MATRIX.md) · [Release candidates](docs/RELEASE_NOTES_THEME_2026-10-24.md) · [Acceptance issue #16](https://github.com/analienx/visual-quality-system/issues/16)

## Documentation

| For | Start here |
| :--- | :--- |
| **Power BI report authors** | [Getting started](docs/USER_GUIDE.md) · [Premium design guide](docs/PREMIUM_POWERBI.md) · [Theme palette library](docs/APPROVED_THEME_LIBRARY.md) |
| **BI platform engineers** | [Architecture](docs/ARCHITECTURE.md) · [CLI](docs/CLI.md) · [Power BI integration & native evidence](docs/VISUAL_QA_V2_P16_NATIVE_DESKTOP_UIA.md) |
| **Quality reviewers** | [Acceptance matrix](docs/ACCEPTANCE_MATRIX.md) · [Screenshot provenance](docs/images/adaptive-showcase/PROVENANCE.json) · [Native gallery](docs/REAL_THEME_SHOWCASE.md) |
| **Contributors** | [Contributor guide](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [All documentation](docs/README.md) |

VQS focuses on **Power BI**. Word/DOCX assurance is a separate optional component, not a blocker for a Power BI-only release. Source inspection is local by default; private customer screenshots and caches must not be checked in or uploaded without explicit authorization.

<sub>Apache-2.0 · Engineering preview · [Security & contribution guidance](CONTRIBUTING.md) · [Older five-theme native gallery](docs/THEME_GALLERY.md)</sub>


### Category-color acceptance gate

The 25 October screenshot audit exposed a previously missed **identical
below-target red** for Electronics and Sports & Outdoors, and weak
seven-category palette pairs. QVS now blocks wildcard conditional
status colors on categorical bar charts and requires stronger pairwise
separation (50/19 normal/simulated vision for three categories,
45/15 for four to seven). The refreshed synthetic Contoso sample uses
category-specific colors for the GM target and regional variance charts;
business measures, percentages and the 35% reference line remain.
A true waterfall total bar was intentionally replaced by a region
comparison to avoid identical increase colors. This is a
presentation trade-off, not a change to the underlying DAX.
Native gallery screenshots are independently source-hash bound.
