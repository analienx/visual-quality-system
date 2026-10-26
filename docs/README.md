# VQS documentation

Choose the shortest path for what you want to accomplish. **Power BI is the core product**; Word/DOCX is independently scoped. Native evidence is distinct from deterministic source validation.

## Start here

| Your goal | Guide | Evidence / limitations |
| :--- | :--- | :--- |
| Understand VQS in 5 minutes | [Project overview](../README.md), [User guide](USER_GUIDE.md) | [Release status](RELEASE_NOTES_THEME_2026-10-24.md) |
| Ask an AI agent to fix supported report issues | [AI auto-fix quickstart](AI_AGENT_QUICKSTART.md) and [Component architecture](AGENT_AUTOFIX_ARCHITECTURE.md) | Disposable candidate, evidence-based verification, separate promotion approval |
| Check a PBIP for actual source defects | [CLI reference](CLI.md), [Quality guidance](PREMIUM_POWERBI.md) | [Acceptance matrix](ACCEPTANCE_MATRIX.md) |
| Create a source-safe Light/Dark report | [Theme engine](THEME_ENGINE.md), [28-mode palette library](APPROVED_THEME_LIBRARY.md) | [Native report screenshots](REAL_THEME_SHOWCASE.md) |
| Review the architecture | [Architecture](ARCHITECTURE.md) | [Simplified product flow](diagrams/product-flow.svg) |
| Run native Power BI checks | [P16 Desktop UIA](VISUAL_QA_V2_P16_NATIVE_DESKTOP_UIA.md), [Loaded-source attestation](DESKTOP_SOURCE_ATTESTATION.md) | [Power BI release gate](https://github.com/analienx/visual-quality-system/issues/16) |
| Inspect actual screenshots / hashes | [14-family native gallery](REAL_THEME_SHOWCASE.md) | [Screenshot provenance](images/adaptive-showcase/PROVENANCE.json) |
| Contribute or review changes | [Contributor guide](../CONTRIBUTING.md), [Changelog](../CHANGELOG.md) | [Release notes](RELEASE_NOTES_2026-10-21.md) |

## The evidence contract

1. **Source**: inspect versioned PBIR/TMDL, never silently alter a user's original report.
2. **Candidate**: generate an isolated, reversible change; verify its source and model hashes.
3. **Authoring**: use Microsoft's official report-author CLI for structural validation; zero schema errors does not prove correct pixels.
4. **Desktop**: verify populated screenshots, rendered labels and supported interactions against live DAX from the same report.
5. **Acceptance**: independent reviewer and release owner decide promotion; never self-award G2/G4/G6 acceptance based solely on CI.

The [original five-colorway Desktop gallery](THEME_GALLERY.md) is preserved as historical evidence. The [14-family native gallery](REAL_THEME_SHOWCASE.md) now contains 28 Light/Dark report variants with 56 source-bound Desktop screenshot previews. The [palette library](APPROVED_THEME_LIBRARY.md) compares all 28 color and control swatches, including family-specific dropdown and selected-state colors.
