# Contoso Retail · real Power BI Desktop reference

**Five genuine native pages · fictitious M-generated retail data · live-DAX verified · 8 native Year/Region interactions passed.**

[View the five-page screenshot walkthrough](../../docs/VERIFIED_CONTOSO_SHOWCASE.md) ·
[Source / image provenance](../../docs/media/contoso-verified/PROVENANCE.json) ·
[Return to the VQS homepage](../../README.md)

## Open in Power BI Desktop

1. Clone the public [VQS repository](https://github.com/analienx/visual-quality-system) and open [Contoso Retail.pbip](Contoso%20Retail.pbip) using a current Power BI Desktop build with PBIP/PBIR support.
2. The project includes its **fictional imported model snapshot** in `Contoso Retail.SemanticModel/.pbi/cache.abf`, intentionally permitted **only for this synthetic demonstration**. No Microsoft 365 trial, Azure Maps authentication, external service, customer database or credential is required.
3. In **Executive overview**, Reporting year = All, expect ~**$6.82M Sales, 10.0% YoY and 33.9% GM**. Browse the other pages: Products & brands, Stores & customers, Markets & drivers, Deep-dive insights. The Shape Map uses an included public world-country TopoJSON URL and local synthetic model data.
4. To regenerate a screenshot, use an authorized Windows Power BI Desktop environment with the VQS [native quickstart](../../docs/QUICKSTART.md). Never substitute HTML mockups for actual Desktop images.

## What is source-matched?

- `Contoso Retail.Report/` and `Contoso Retail.SemanticModel/` plus `Contoso Retail.pbip`: the actual tested report and self-generated demo model, with only **two schema metadata declarations restored** for strict Microsoft authoring compatibility (**0 errors, 0 warnings**).
- `evidence/strict-native-source.zip`: the **exact Desktop-native saved source** from which five source-bound page screenshots, four KPI live-DAX checks and native Year/Region interactions were validated. Desktop Save omits two `$schema` declarations; this ZIP intentionally preserves that exact fingerprint. The main PBIP restores just those declarations for clean source authoring.
- [Five native full-page PNGs](../../docs/media/contoso-verified/native/) and the derived [report-only WebP previews](../../docs/VERIFIED_CONTOSO_SHOWCASE.md). Each PNG/WebP hash and crop is pinned in [provenance](../../docs/media/contoso-verified/PROVENANCE.json). The preview crop simply excludes Power BI Desktop's surrounding Filters pane and chrome; the actual pixels originate from Desktop.
- `tests/test_public_verified_contoso.py` fails CI if the example source, exact native snapshot, page identities, data-source safety checks or any screenshot hash drifts.

**Explicit limitation:** automated visual review reported zero visible P1/P2 defects on these five pages, and the exercised Year/Region behavior matched live DAX. This **does not** certify country-specific Shape Map click, true contextual Tooltip hover, generalized arbitrary reports, a distinct authorized human G2/G4 reviewer or owner G6 production approval. No public production-release tag is implied.

## Relationship to the 14-theme gallery

The [14-family / 28-mode theme gallery](../../docs/REAL_THEME_SHOWCASE.md) is a **separate historical showcase** built from an earlier source-identifiable Contoso project at [`examples/contoso-retail`](../contoso-retail/README.md). Its 56 Light/Dark previews were **not** recaptured from this final Dark reference. Both sources and their provenance remain checked in rather than presenting historical images as if they came from a newer PBIP.

## Agent quickstart

```bash
python -m pip install -e ".[test]"
vqs triage "examples/contoso-retail-verified/Contoso Retail.pbip" --out quality.md
vqs premium "examples/contoso-retail-verified/Contoso Retail.pbip" --init-contract design-intent.json
```

VQS doesn't silently repair or replace this original. To ask an agent to attempt source-safe **candidate-only auto-fixing**, use [the agent-first guide](../../docs/AI_AGENT_QUICKSTART.md) and [repair architecture](../../docs/AGENT_AUTOFIX_ARCHITECTURE.md). For genuine native interaction and DAX, use the Desktop/Modeling tools on Windows; CI can verify source, hashes and file safety on Linux.
