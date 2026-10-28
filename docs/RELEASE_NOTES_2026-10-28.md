# VQS Power BI — automated repair correction, 28 October 2026

**Status: engineering preview. No production release/tag, independent G2/G4 review or G6 owner approval.**

## Why a clean installed consumer returned BLOCKED

The Windows installed PBIPDocumenter bridge was previously validated against fictional Contoso and correctly reported three static failures. Its VQS repair stage produced no candidate and returned BLOCKED. Adversarial investigation found a **real evaluator false positive** and a **misleading agent handoff**. This is a core auto-fix effectiveness problem; the absence of a safe plan must never be presented as a successful repair.

### Engineering fixes

1. **Hidden PBIR source vs visible canvas.** The extra Markets & drivers decomposition tree is source-marked boolean isHidden=true, visually absent in earlier real Desktop screenshots, but VQS incorrectly included it in the overlap and formatting evaluation. The subsequent source sweep confirmed that the independent composition/reflow extractor also counted hidden visuals; its source measurement now applies the identical literal-boolean hidden check. Tests confirm 53 visible composition members while retaining 54 total source definitions. The correction preserves all 54 visual definitions and model binding checks while applying visible-layout and style rules to the actual 53 visible items. Two false layout collisions are resolved **without edits to any report source**.
2. **Agent decision handoff.** The VQS coordinator no longer instructs an autonomous agent to re-run a proposal it just completed with unchanged facts. When there is no safe candidate, the sealed summary reports repair_triage.status=no_safe_candidate, exact source-derived per-cohort/visual-pair decisions, and requires_proven_fix_or_owner_plan=true. Verdict is still BLOCKED and original promotion is always false.
3. **Precise unsupported-repair reasons.** The two remaining Contoso rule IDs are cross-page duplicate breakdown and inherited/explicit typography. There are **five specific evidence requests**; VQS does not arbitrarily remove one report chart or guess an inherited Power BI font size. A separate automated adversarial code review identified a same-rule repeated-finding suppression edge case; it was corrected with per-finding decision accounting and negative tests. The supplied owner-plan path is distinguished from an absent automatic plan, without bypassing plan validation. Hidden text contrast readings are excluded from visible rendering checks while hidden model/query bindings remain audited.

## Actual independent-ish checks (not a separate human signature)

- The targeted real-file tests proved the hidden visual stays in the 54-item inventory and its model references stay audited; exactly the previously flagged two overlaps return if isHidden is false, absent or a string, then disappear again when true.
- Fresh installed Windows PBIPDocumenter quality repair, isolated source interpreter/imports: two remaining rule IDs; 0 candidates; exact five decisions; sealed evidence_verified true; exit 2; original source digest unchanged; promotion false.
- Full regression and protected GitHub CI results are pinned to the accompanying pull request and must be green before merge. Do not interpret a no-safe-fix result as a passed remediation.

The remaining questions demand real design/effective-style evidence, not more trial-and-error UI reopening. Primary Power BI release gate [#16](https://github.com/analienx/visual-quality-system/issues/16), consumer [#17](https://github.com/analienx/visual-quality-system/issues/17), and the separate Word scope [#13](https://github.com/analienx/visual-quality-system/issues/13) remain distinct.

## Operator entry points

- [One-command AI agent auto-fix quickstart](AI_AGENT_QUICKSTART.md)
- [Real source-grounded triage and remaining cases](AUTO_REPAIR_TRIAGE_2026-10-28.md)
- [Source-bound consumer integration](CONSUMER_INTEGRATION.md)
- [Previous genuine Desktop G2/G4 evidence](RELEASE_NOTES_2026-10-27.md)

No private PBIP, semantic cache, unredacted screenshot, Corporate Spend data or Windows receipt is included in this repository update.
