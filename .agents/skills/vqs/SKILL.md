---
name: vqs
description: Deterministic Power BI quality review, source/model/render evidence, safe repair proposals, candidate-only mutation, independent adjudication and explicit promotion.
---

# VQS — orchestrated quality gate (not a competing report-authoring skill)

**One public workflow:** use vqs run --mode review|propose|repair --scope static|desktop|release for end-to-end VQS work. The CLI/MCP routes invoke the same coordinator. vqs doctor checks the environment without installing anything. Details: docs/CLI.md, docs/JOURNEY.md, docs/ACCEPTANCE_MATRIX.md.

## Mandatory Microsoft report skill before editing report content

The official powerbi-report-cli skill is vendored at ../powerbi-report-cli/SKILL.md, pinned by ../powerbi-report-cli-upstream.json. First run python scripts/report_skill.py --check-cli in this repo. Any blocked version, missing skill, tampered snapshot or missing CLI **blocks Microsoft-dependent authoring**; reading/measurement can still proceed. Never silently execute new upstream code or install @latest during an active repair.

Read the official skill root *and relevant mode references*:
- planning for new report requirements (approval barrier before implementation);
- design for design contracts and recommendations;
- authoring for existing PBIR/PBIP edits, validated visual schemas, formatting, themes, filters and preview;
- management only for separately approved Fabric report lifecycle changes.

Use powerbi-report-author catalog, formatting, expr, theme and validate rather than guessing report JSON property names. For authored content, validation must lead to loaded-current-source preview, affected-page screenshots, and review—not just a green schema exit.

## Division of responsibility

| Layer | Authoritative owner |
| --- | --- |
| Design advice and PBIR metadata | Official Microsoft powerbi-report-cli skill / authoring CLI |
| Semantic model inspection, live DAX, same-question regression | Microsoft Modeling MCP |
| Facts, deterministic quality rules, independent review, acceptance | VQS |
| Safe candidate planning and bounded repair | VQS typed preconditioned candidate-only engine |
| Candidate Desktop identity, data/render binding, sealing | VQS coordinator; ONE Desktop lifecycle |
| Promotion and rollback | VQS owner-controlled promotion, never implicit |

Microsoft skill guidance is an authoring reference, not proof of VQS acceptance. Structural validation does not certify data answers, rendered appearance, reviewer independence, or an approvable release.

For **standalone** report authoring outside an active VQS run, follow the official authoring reference and its powerbi-report-author preview path. For **VQS-owned** disposable candidate runs, do NOT independently open/reload/capture through a second preview controller: VQS currently owns the isolated Bridge open → PID/path/source lease → reload → screenshot lifecycle. The unified preview-port replacement is tracked in issue #32; until independently verified, preserve the safe single-host route rather than claiming the two tools are interchangeable.

## Safety and acceptance

- Source facts before pixel loops: vqs measure / vqs cycles / vqs check as appropriate. One-command vqs run is preferred for composition.
- Default to review/read-only, proposal/no source write, or isolated candidate repair. Never write the original or a model in a report-only repair; never use pbir.tools or arbitrary TMDL fallback.
- Preserve page filters, interactions, units, roles and meaningful design unless an authorized plan explicitly changes them. Exact source preconditions, typed operations, sealed diffs and model SHA must hold.
- Model facts/answers use Modeling MCP. Unsupported non-empty filter/period/RLS scopes stay **BLOCKED** until implemented.
- Before/after screenshots must belong to the exact candidate report, Desktop PID, source digest, page and data context. Render identity does not establish pixel-to-PBIR coordinate calibration.
- User-owned Desktop instances with unsaved work are never driven. A VQS-owned disposable instance has a separately evidenced ownership/save-state policy.
- After structural validation, independently review each affected page and neighboring visuals, answer regression if configured, and record fixed/remaining/new findings. The fixer cannot self-approve.
- No silent publish, release, merged PR or owner promotion; no report acceptance from a successful repair stage. Missing trusted reviewer authority keeps release BLOCKED.
- Keep renders, raw evidence, model caches, customer files, tokens and temporary run data out of public Git commits.

Compatibility/skill freshness issue: https://github.com/analienx/visual-quality-system/issues/32
Core live usability acceptance: https://github.com/analienx/visual-quality-system/issues/22
