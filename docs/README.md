# VQS documentation

Choose a path based on what you want to do. The **latest release (v0.2.0)** is a source-level Power BI CLI/MCP distribution. [Release notes](RELEASE_NOTES_v0.2.0.md) · [Release history](RELEASES.md) · [Download and checksums](https://github.com/analienx/visual-quality-system/releases/tag/v0.2.0)

<a id="start-here"></a>
<a id="the-everyday-loop"></a>

## Use VQS

1. [Install and run your first review or repair](USER_GUIDE.md#start-with-the-published-release).
2. [Use VQS with an AI agent](AI_AGENT_QUICKSTART.md), including local MCP setup.
3. [Understand supported capabilities and limits](CAPABILITIES.md).
4. [Answer an owner question or decide whether to adopt](OWNER_DECISIONS_AND_PR_GATE.md).
5. [Look up a command](CLI.md) or [use the PR regression gate](OWNER_DECISIONS_AND_PR_GATE.md#pull-request-gate-vqs-gate).

`vqs fix` works on a separate candidate. Missing evidence blocks rather than silently passing. The owner chooses offered options and separately authorizes adoption. Static source checks do not certify a report's Desktop rendering or live data.

<a id="the-evidence-contract"></a>

## Build or review VQS

- [v0.2 delivery plan and dependencies](../roadmap/README.md#next-product-milestone-v020--prove-better-outcomes)
- [Contribute and run tests](../CONTRIBUTING.md)
- [Architecture](ARCHITECTURE.md) and [agent/repair workflow](AGENT_AUTOFIX_ARCHITECTURE.md)
- [Acceptance gates and profiles](ACCEPTANCE_MATRIX.md)
- [Native source attestation](DESKTOP_SOURCE_ATTESTATION.md) and [Desktop engineering evidence](V012_NATIVE_G_ACCEPTANCE.md)
- [Power BI integration](CONSUMER_INTEGRATION.md) and [theme guide](THEME_ENGINE.md)

## Examples and engineering history

- [Fictional Contoso reference report](VERIFIED_CONTOSO_SHOWCASE.md) and [its reproducible PBIP](../examples/contoso-retail-verified/README.md)
- [Theme gallery](REAL_THEME_SHOWCASE.md) and [palette library](APPROVED_THEME_LIBRARY.md)
- [Release and engineering history](RELEASES.md), [changelog](../CHANGELOG.md), and the [archived status snapshot](../roadmap/STATUS.md)
- [Browse the full documentation directory](https://github.com/analienx/visual-quality-system/tree/main/docs)
- [Historical two-PBIP acceptance record](POWER_BI_CORE_ACCEPTANCE_2026-10-28.md) and current [release gate issue #16](https://github.com/analienx/visual-quality-system/issues/16)

Historical records explain what was observed at a particular revision; they are not current acceptance by themselves. Preserve their provenance and consult the linked current issues before relying on a capability claim. Power BI is the primary product; Word/DOCX is separately scoped.
