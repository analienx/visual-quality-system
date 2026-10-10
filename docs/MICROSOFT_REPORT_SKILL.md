# Microsoft Power BI Report Skill + VQS — integration contract

Current tracked work: [issue #32](https://github.com/analienx/visual-quality-system/issues/32). Core independent acceptance remains [issue #22](https://github.com/analienx/visual-quality-system/issues/22) and draft PR #31.

## Sources and reviewed versions

| Artifact | Approved source / version |
| --- | --- |
| Official Microsoft skill | microsoft/skills-for-fabric / skills/powerbi-report-cli |
| Vendored skill | .agents/skills/powerbi-report-cli/ (all mode and topic reference files) |
| Provenance | .agents/skills/powerbi-report-cli-upstream.json (immutable commit, content tree SHA-256, skill metadata) |
| Microsoft authoring CLI | @microsoft/powerbi-report-authoring-cli / 0.5.0, public preview |
| Candidate tool | powerbi-report-author |
| VQS skill | .agents/skills/vqs/SKILL.md |

Microsoft official skill is a mode dispatcher: planning, design, authoring, management. It is not merely the command-line executable. Agents must load the relevant mode's reference instructions, not guess PBIR syntax or apply stale 2025-era report practices.

Preflight from the VQS checkout:

    python scripts/report_skill.py --check-cli

This is offline: checks exact installed skill bytes/version and actual CLI semantic version, **does not** install, fetch or patch anything. A missing/stale skill or CLI blocks Microsoft-dependent report authoring; VQS static inventory/measurement remains available. An approved version is not upgraded in the middle of a run.

Explicit upstream refresh: a weekly GitHub Actions workflow clones only Microsoft's skill subtree, proposes a PR containing the new snapshot/lock and **never auto-merges**. Review changed guidance, test the pinned CLI and update the pinned package if compatibility requires it. Locally, an operator with a verified upstream checkout can run:

    python scripts/report_skill.py --sync-from PATH-TO-OFFICIAL-SKILL --commit 40_HEX_SHA
    python scripts/report_skill.py --check-cli

Do not pass an arbitrary downloaded/unverified directory to the sync command. The synchronizer now requires a real Git checkout at the exact asserted SHA and verifies every upstream subtree file against its committed blob; uncommitted upstream changes, unexpected files, or a mismatched checkout are rejected. A human still reviews the proposed update before adoption.

## Single workflow: VQS coordinates; Microsoft informs

1. Resolve source PBIP/report/model and baseline digests.
2. Inspect/measure static facts with VQS; use Microsoft design skill when proposing design direction.
3. Before candidate report edits, use the Microsoft authoring skill plus CLI catalog / formatting / expression / theme metadata to construct source-valid typed operations.
4. VQS synthesizes conservative repair plans with source provenance; no arbitrary raw PBIR mutations, no original edits.
5. VQS writes only the disposable candidate; Microsoft CLI validates it with structured JSON diagnostics. CLI validation is schema validity, not design or acceptance.
6. **Exactly one** runtime preview controller owns the candidate and its source/PID/lease: current VQS Bridge path remains authoritative for an integrated run. Do not independently launch Microsoft preview in parallel; a unified preview adapter may replace the Bridge when independently proven.
7. Live Microsoft Modeling MCP validates DAX/readiness and re-asks the *same scoped questions* before and after when configured; unsupported filters/period/RLS remain blocked.
8. Re-render every affected page; review aesthetics, whitespace, alignment, typography, clipping, data labels, neighboring components and interactions. No geometry calibration without a proven transform.
9. An independent reviewer adjudicates source-bound evidence. Surface separate repaired / remaining / regressed / blocked states, with no self-approval.
10. Owner-only promotion uses VQS sealed diff, backup and rollback contract; neither schema success nor user text implies authenticated release authority.

For **standalone** authoring not inside VQS, follow Microsoft's validated authoring mode and its powerbi-report-author preview workflow, including page screenshots and review. Report-item transport/publishing is a separate management mode requiring explicit consent. Microsoft Modeling MCP owns semantic content; the report skill does not give permission to mutate TMDL or Fabric workspaces indirectly.

## Evidence requirements and known limitations

- Pin actual skill tree SHA, commit and CLI executable/version in records; library version numbers alone do not prove the running skill bytes. The vendor-tree digest is `sha256-lf-v1`: Git source text is normalized only for CRLF vs LF checkout differences, while content changes remain detectable. The subtree has `text eol=lf` in `.gitattributes` to prevent platform drift.
- The authoring CLI emits a documented JSON envelope: data.result = succeeded / succeededWithWarnings / failed, with errorCount, warningCount, diagnostic groups; an error envelope is not a validated candidate. VQS must parse the JSON and cross-check exit code; do not grep text for the word warning.
- Preview/source identity and PBIR↔PNG calibration are distinct; renderer identity alone never certifies geometric measurements.
- Portable synthetic Python/subprocess tests select the direct/static validator explicitly, independent of a globally installed CLI. The separate real Microsoft CI lane uses `scaffold --offline` to create a genuine schema-valid PBIP, verifies success with zero warnings, corrupts the isolated `definition.pbir`, and requires structured failure diagnostics. Neither test lane proves live Desktop usability.
- Runtime use of catalog/formatting helper operations and a unified preview port are follow-on tasks under issue #32; vendoring the skill and passing a genuine offline CLI test **do not** prove full VQS usability.
- The original Contoso project is read-only during integration. A 2026-10-10 read-only Microsoft CLI validation of the existing original produced 3 errors and 3 warnings (missing schemas, theme-name mismatch, subtitle height warnings and legacy map). Use it as a real-world **negative** regression, never silently patch the original.
- Manual invocation of the official skill is instruction routing. Enforcing it programmatically in every existing repair subcommand remains a tracked integration task until covered by public workflow tests.

## Independence and upgrade safety

Automated checks can detect drift and propose changes, but **always latest** must mean promptly reviewed, compatible and reproducible—not executing untested upstream instructions against production reports. Only merge the update once independent CI passes and candidate-only preview contracts are reconfirmed.
