# Power BI auto-repair triage — 28 October 2026

**Engineering preview only. No production G6 approval.** Auto-fix means source-provable, original-safe edits, not moving or deleting a visual merely to silence an unproven defect.

## Actual installed PBIPDocumenter Windows regression

The installed consumer ran static repair against the checked-in five-page fictional Contoso Retail PBIR, with sealed VQS evidence. The original three static failures included two geometric collisions with the Markets & drivers decomposition tree (visual a1b2c3d4e5f60718293a). Its PBIR **isHidden: true**, and the existing native Desktop screenshot shows it is not on the rendered page. The previous evaluator treated it as visible and rejected all available moves.

The corrected visibility-aware measurement skips **only actual boolean true** when calculating visible visual geometry, grain, map/tree content and typography. The complete source inventory remains **5 pages / 54 visual definitions**, with **53 visible geometry items**. Hidden fields remain in the source/model binding audit. Missing, false, and string "true" flags still count as visible. Both false collisions disappear **without changing a byte in the source report**.

## Remaining genuine questions, not safe autonomous edits

| Rule | Real observation | Required proof |
| :--- | :--- | :--- |
| insight.no_cross_page_duplicate_grain | Overview and Deep-dive repeat the same Region measure/dimension breakdown | Verify if this is intentional overview/detail reuse before replacing or deleting one |
| typography.format_declaration_consistency | Pivot grid textSize 10 vs 11; three separate axis/header cohorts mix inherited and explicit fonts | Native rendered effective-size and intentional hierarchy evidence before choosing a target or unsetting an override |

These may warrant improved design, but neither has an unambiguous source-only repair. No AI agent should select a business meaning or font-default value from guesswork.

## Agent-facing repair result

Call the integrated repair workflow **once per changed source revision**, validate the sealed evidence, and inspect:

- summary.candidate_status and summary.candidates_proposed: whether VQS actually created a candidate.
- summary.repair_triage.status and summary.repair_triage.decisions: exact check, decision status, affected cohort/visual and missing evidence.
- summary.remaining_findings, summary.new_regressions and summary.promotion_status: what is still unaccepted and whether the source was promoted.
- response blocked_reasons and next_actions: meaningful follow-up; **do not repeat propose on unchanged facts**.

On the verified real installed run, summary.repair_triage.status is **no_safe_candidate**, two rule IDs remain, five individual decisions explain why, and verdict remains **blocked (exit 2)**, evidence_verified=true, candidate=null, promotion_performed=false. These values are **not** a successful automatic repair. Collect the named render/design evidence or an owner-authorized source-bound plan and re-run; never overwrite the original.

## Acceptance and limits

Hidden/visible/unknown cases are tested against the actual committed Contoso PBIR. A separate regression checks the agent's sealed no-safe-candidate handoff and original source hash. See the correction PR for full-suite and protected CI evidence. Actual native G2/G4 and G6 release promotion remain separate. Neither this note nor any AI review constitutes an independent authorized release signature.

See [AI agent setup](AI_AGENT_QUICKSTART.md), [consumer integration](CONSUMER_INTEGRATION.md), [release issue #16](https://github.com/analienx/visual-quality-system/issues/16), and [consumer issue #17](https://github.com/analienx/visual-quality-system/issues/17).
