# VQS v0.1.1 - agent-first usability release candidate

**Status: implementation candidate, not a published release.**
The supported source-only v0.1.0 GitHub Release remains untouched.

## Scope

1. Wheel embeds approved Microsoft skill and upstream metadata lock,
   verifying 88 reviewed resources against the approved SHA-256 and CLI.
2. The `vqs fix Report.pbip` CLI resolves PBIP, single-report project
   root or `*.Report` paths unambiguously. Reuses the original sealed
   coordinator in repair/static mode; never overwrites the source.
3. `vqs run --summary` and modern MCP clients receive concise outcomes;
   complete sealed evidence remains in the private run directory.
4. MCP maintains 2024-11 legacy compatibility, adds 2025-11 handshake and
   the 2026-07 stateless lifecycle with structured outputs.
5. `vqs_theme` surfaces existing theme preset/preview/inspect/apply/audit,
   with explicit disposable candidate required for apply.
6. The installed wheel must prove seeded safe fixes and a fail-closed
   no-safe-candidate result against published synthetic Contoso.

## Release checklist

- [ ] Full regression and Linux 3.11/3.12/3.13 + Windows CI green.
- [ ] Wheel/sdist built from intended protected main and audited.
- [ ] Installed wheel works without an editable checkout or manual skill root.
- [ ] Modern and legacy MCP interoperability tested via stdio.
- [ ] Seeded positive repair creates verified disposable candidate and
      preserves original source bytes and semantics.
- [ ] Public Contoso no-safe candidate remains blocked, never fake PASS.
- [ ] Independent review and publication decision; SHA256SUMS verified.
- [ ] Explicit limitations in README, release notes and consumer docs.

## Deferred

Arbitrary Desktop repair-candidate reload and independent G2/G4/G6
certification (#16/#17), Shape Map country clicks, hidden-tooltip hover,
Word/DOCX (#13), hosted service, new palettes and PyPI deployment.
