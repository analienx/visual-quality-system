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

**Three distinctive palette families. Two modes each. Real, populated Power BI Desktop renders.**
All screenshots come from generated candidates of the same five-page [fictional Contoso Retail PBIP](examples/contoso-retail/README.md) ([open the exact source report](examples/contoso-retail/Contoso%20Retail.pbip)); none is a simulated dashboard or an AI-generated illustration.


### Sunny Palette
Warm amber, teal and coral, with a legible dark business surface.

| Light | Dark |
| :--- | :--- |
| [![Sunny Palette Light, native Contoso Executive report](docs/images/adaptive-showcase/sunny-palette-light/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#sunny-palette) | [![Sunny Palette Dark, native Contoso Executive report](docs/images/adaptive-showcase/sunny-palette-dark/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#sunny-palette) |

### Organic Palette
Grounded blues and fresh greens across contrasting light and dark.

| Light | Dark |
| :--- | :--- |
| [![Organic Palette Light, native Contoso Executive report](docs/images/adaptive-showcase/organic-palette-light/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#organic-palette) | [![Organic Palette Dark, native Contoso Executive report](docs/images/adaptive-showcase/organic-palette-dark/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#organic-palette) |

### Graphite Red
Restrained neutral surfaces with bold red accents.

| Light | Dark |
| :--- | :--- |
| [![Graphite Red Light, native Contoso Executive report](docs/images/adaptive-showcase/graphite-red-light/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#graphite-red) | [![Graphite Red Dark, native Contoso Executive report](docs/images/adaptive-showcase/graphite-red-dark/executive-overview.webp)](docs/REAL_THEME_SHOWCASE.md#graphite-red) |

**[Explore 18 genuine report screenshots](docs/REAL_THEME_SHOWCASE.md)** · [See provenance and SHA-256 hashes](docs/images/adaptive-showcase/PROVENANCE.json) · [Browse every approved palette](docs/APPROVED_THEME_LIBRARY.md)

Each featured mode was captured across all five pages in a disposable Desktop instance after refreshing its local model. Three representative pages per mode are published as lightweight WebP previews. The other **11 approved families** are shown as compact color swatches—no pretend report screenshots.

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

`preview` is read-only; `apply` creates a separate candidate and audit manifest. The original PBIP, semantic model, DAX, field bindings and business-color rules are preserved. The generated candidate may need a first-open refresh in Power BI Desktop to populate its local sample model.

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

VQS provides an explicit `vqs premium` design contract for hierarchy, spacing and quality review, rather than claiming to know that a screenshot is attractive from source JSON alone. The bundled Contoso Retail report includes charts, tables, slicers and a **no-sign-in Shape Map**.

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
