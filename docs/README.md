# VQS documentation

Choose the shortest path for what you want to accomplish. **Power BI is the core product**; Word/DOCX is independently scoped. Native evidence is distinct from deterministic source validation.

[**Native G2/G4 rebaseline and exact-PID capture (next-release engineering)**](V012_NATIVE_G_ACCEPTANCE.md)

[**Current v0.1.1 release notes and supported scope**](RELEASE_NOTES_v0.1.1.md) |
[**Six-platform installed-wheel acceptance record**](V011_USABILITY_RELEASE_PLAN.md)

## Start here

| Your goal | Guide | Evidence / limitations |
| :--- | :--- | :--- |
| Install supported VQS v0.1.0 core | [Production distribution](PRODUCTION_DISTRIBUTION_v0.1.0.md) | [GitHub wheel and checksums](https://github.com/analienx/visual-quality-system/releases/tag/v0.1.0); native/report G2/G4/G6 excluded |
| Understand VQS in 5 minutes | [Project overview](../README.md), [User guide](USER_GUIDE.md) | [Current engineering release notes](RELEASE_NOTES_2026-10-28.md) |
| Ask an AI agent to fix supported report issues | [AI auto-fix quickstart](AI_AGENT_QUICKSTART.md) and [Component architecture](AGENT_AUTOFIX_ARCHITECTURE.md) | [Source-bound repair triage and real blockers](AUTO_REPAIR_TRIAGE_2026-10-28.md); disposable candidate, separate promotion approval |
| Check a PBIP for actual source defects | [CLI reference](CLI.md), [Quality guidance](PREMIUM_POWERBI.md) | [Acceptance matrix](ACCEPTANCE_MATRIX.md) |
| Create a source-safe Light/Dark report | [Theme engine](THEME_ENGINE.md), [28-mode palette library](APPROVED_THEME_LIBRARY.md) | [Native report screenshots](REAL_THEME_SHOWCASE.md) |
| Review the architecture | [Architecture](ARCHITECTURE.md) | [Simplified product flow](diagrams/product-flow.svg) |
| Run native Power BI checks | [P16 Desktop UIA](VISUAL_QA_V2_P16_NATIVE_DESKTOP_UIA.md), [Loaded-source attestation](DESKTOP_SOURCE_ATTESTATION.md) | [**Current two-PBIP G2/G4/G6 evidence and release decision**](POWER_BI_CORE_ACCEPTANCE_2026-10-28.md) · [Gate #16](https://github.com/analienx/visual-quality-system/issues/16) |
| Inspect the final synthetic Power BI Desktop report | [Five-page native Contoso showcase](VERIFIED_CONTOSO_SHOWCASE.md), [downloadable PBIP](../examples/contoso-retail-verified/README.md) | [Exact source / image hashes](media/contoso-verified/PROVENANCE.json); automated G2 and bounded G4 only |
| Inspect all historical Light/Dark themes | [14-family native gallery](REAL_THEME_SHOWCASE.md) | [Separate theme-candidate hashes](images/adaptive-showcase/PROVENANCE.json) |
| Integrate VQS into PBIPDocumenter | [Consumer integration](CONSUMER_INTEGRATION.md), [CLI reference](CLI.md) | Power BI-only integration may proceed; independent release acceptance remains [#16](https://github.com/analienx/visual-quality-system/issues/16) |
| Contribute or review changes | [Contributor guide](../CONTRIBUTING.md), [Changelog](../CHANGELOG.md) | [28 October repair correction](RELEASE_NOTES_2026-10-28.md) · [27 October evidence](RELEASE_NOTES_2026-10-27.md) · [26 October release history](RELEASE_NOTES_2026-10-26.md) |

## The evidence contract

1. **Source**: inspect versioned PBIR/TMDL, never silently alter a user's original report.
2. **Candidate**: generate an isolated, reversible change; verify its source and model hashes.
3. **Authoring**: use Microsoft's official report-author CLI for structural validation; zero schema errors does not prove correct pixels.
4. **Desktop**: verify populated screenshots, rendered labels and supported interactions against live DAX from the same report.
5. **Acceptance**: independent reviewer and release owner decide promotion; never self-award G2/G4/G6 acceptance based solely on CI.

The [original five-colorway Desktop gallery](THEME_GALLERY.md) is preserved as historical evidence. The [14-family native gallery](REAL_THEME_SHOWCASE.md) now contains 28 Light/Dark report variants with 56 source-bound Desktop screenshot previews. The [palette library](APPROVED_THEME_LIBRARY.md) compares all 28 color and control swatches, including family-specific dropdown and selected-state colors.
