# Product roadmap

VQS helps people and their agents improve Power BI reports with source-grounded checks, bounded candidate repairs and reviewable evidence. Microsoft tools supply authoring and structural validation. [Start with an AI agent](../docs/AI_AGENT_QUICKSTART.md) · [Capabilities and limits](../docs/CAPABILITIES.md) · [Architecture](../docs/ARCHITECTURE.md)

<a id="v012-published-scope-and-remaining-evidence"></a>

## Release path

| Version | Status | What it delivers |
| :--- | :--- | :--- |
| [v0.1.1](../docs/RELEASE_NOTES_v0.1.1.md) | Released 30 October 2026 | Local CLI/MCP and candidate repairs. |
| [v0.1.2](../docs/RELEASE_NOTES_v0.1.2.md) | Released 7 November 2026 | Source-only review, owner decisions, explicit adoption and static PR gates. [Download](https://github.com/analienx/visual-quality-system/releases/tag/v0.1.2) |
| v0.2.0 | In development; scope and release date not finalized | The proposed milestones below aim to prove better outcomes, including data-aware and rendered regression evidence. |

The source-only v0.1.2 release does not certify native Desktop rendering, live-data parity or a whole report. Those claims require separate evidence and acceptance; see the [acceptance matrix](../docs/ACCEPTANCE_MATRIX.md).

## Product direction

<img src="../docs/diagrams/vqs-product-loop-mobile.svg" alt="User and AI agent use Microsoft authoring and VQS to produce an evidenced candidate for review, or a blocked result needing a decision" width="720">

VQS inspects source, proposes bounded changes, repairs a copy and verifies what it can. The owner answers design questions and decides whether to adopt. An independent reviewer assesses the evidence for acceptance. Missing evidence is blocked, not a pass.

### Next product milestone: v0.2.0 — prove better outcomes

**Status checked 14 November 2026.** GitHub issues and PRs are the live sources for current status; check their current heads and reviews before starting work. A draft implementation and passing tests do not by themselves establish independent acceptance. Milestone order below expresses dependencies, not a promised release date.

**Status words:** *Released* means a published distribution; *draft implementation* means proposed code not integrated into a release; *blocked* means required evidence or capability is missing; *not started* means no implementation evidence has been identified; *independently verified* requires the applicable separate reviewer and proof. These describe different things and must not be inferred from a closed issue alone.

1. **Integrate the candidate — draft implementation.** Combine the existing v0.2 branches with published `main` while preserving v0.1.2. Done when the exact combined revision has appropriate regression and installed-wheel checks and independent review. Green CI alone is not native acceptance. [Integration PR #160](https://github.com/analienx/visual-quality-system/pull/160) · [Issue #159](https://github.com/analienx/visual-quality-system/issues/159)

2. **Prove data and answers — blocked.** Independently review a versioned contract, then build a producer and consumer binding loaded model, source, process, data snapshot, query and scope. Done when positive and negative controls cover wrong source/PID/model, changed data, roles/filters, truncation and missing evidence; unsupported contexts remain blocked. Equal row counts or echoed identities do not prove equal data. [Data evidence #131](https://github.com/analienx/visual-quality-system/issues/131)

3. **Verify rendered regressions — draft implementation; verdict blocked.** Source-bound capture and pixel observations exist, but data/answer and interaction parity are not established. After milestone 2, demonstrate before/after results for supported states with stale-capture and changed-answer controls. Missing proof remains blocked. [Render integrity #130](https://github.com/analienx/visual-quality-system/issues/130) · [Answer regression #133](https://github.com/analienx/visual-quality-system/issues/133)

4. **Demonstrate on two reports — blocked.** Two unrelated fictional PBIP sources have been inspected; current populated native captures, interactions and independent acceptance remain incomplete. After the supported evidence path and authorized native work are available, run the required checks on both reports and independently review the actual evidence. [Second PBIP #152](https://github.com/analienx/visual-quality-system/issues/152) · [Acceptance gate #16](https://github.com/analienx/visual-quality-system/issues/16)

5. **Add analytical design critique — contract proposal.** Define owner-declared audience, questions and context, and map them to source/evidence without inventing business intent or causality. Done after independent interface review, a compatible implementation and false-positive/unknown-state controls. Its final inclusion in v0.2 requires scope confirmation. [Intent contract #142](https://github.com/analienx/visual-quality-system/issues/142) · [Benchmark #118](https://github.com/analienx/visual-quality-system/issues/118)

6. **Present complete evidence — draft partial implementation; contract proposed.** A stage-ledger report exists, but it does not bind the complete returned result or all actual changes. Done after independent contract review, compatible sealing and tamper/stale/partial-write tests. Final v0.2 scope requires confirmation. [Evidence report #145](https://github.com/analienx/visual-quality-system/issues/145) · [Envelope contract #149](https://github.com/analienx/visual-quality-system/issues/149)

7. **Prepare distribution — not started for v0.2.** Finalize version, supported scope, installation, release notes and artifacts after the agreed milestones. Done with reviewed exact source, clean installs, checksums, documented limits and an owner release decision. This cannot substitute for a required report-acceptance gate. [Release history](../docs/RELEASES.md) · [Acceptance matrix](../docs/ACCEPTANCE_MATRIX.md)

**Already available or drafted:** v0.1.2 ships owner-answerable decisions and explicit adoption. A copyable agent/CI workflow is proposed in [#141](https://github.com/analienx/visual-quality-system/pull/141), with a follow-up in [#155](https://github.com/analienx/visual-quality-system/pull/155); actual consumer-workflow annotation placement has not been independently demonstrated. Capture readiness hardening is drafted in [#148](https://github.com/analienx/visual-quality-system/pull/148), [#151](https://github.com/analienx/visual-quality-system/pull/151) and [#156](https://github.com/analienx/visual-quality-system/pull/156). An echoed model name is a consistency check, not independent proof of the model loaded by Desktop.

### What the acceptance gates mean

The engineering matrix labels source/contracts **G0**, actual data/renderer readiness **G1**, independently reviewed design evidence **G2**, candidate repair safety **G3**, same-task regression **G4**, Word consistency **G5**, and separate suite acceptance **G6**. The Power BI core profile requires two unrelated PBIPs, applicable G0–G4 for each and independent G6; Word G5 belongs to its own optional profile. See the [full definitions](../docs/ACCEPTANCE_MATRIX.md).

A version release and a report's acceptance are different decisions. An owner can adopt only after reviewing the relevant candidate and evidence. Neither a source-only pass nor a published wheel certifies an arbitrary report.

## What is outside the current claim

Word/DOCX is separately scoped; Fabric Apps [#18](https://github.com/analienx/visual-quality-system/issues/18) is deferred. Shape Map country-specific clicking and hidden tooltip hover are not claimed as supported without separate proof. Do not upload private report data or screenshots to the public repository. Native work requires the appropriate host, evidence and permissions.

## How progress is tracked

- The [open issues](https://github.com/analienx/visual-quality-system/issues) and bounded work packages carry implementation ownership, blockers and review evidence.
- The [machine ledger](work_packages.json) records package state and dependencies. A closed issue or model's claim is not independent verification.
- The old [status snapshot](STATUS.md) is archived historical context, not a current release dashboard.
- [Release history](../docs/RELEASES.md) separates published distributions from engineering records.

Update this page when an actual capability, evidence gate or release state changes; retain the underlying historical records.
