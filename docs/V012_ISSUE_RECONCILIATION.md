# v0.1.2 reconciliation of the open native issues

**Purpose.** [roadmap/README.md](../roadmap/README.md) items 2 and 3 for v0.1.2 ask
that [#115](https://github.com/analienx/visual-quality-system/issues/115),
[#116](https://github.com/analienx/visual-quality-system/issues/116),
[#117](https://github.com/analienx/visual-quality-system/issues/117) and
[#120](https://github.com/analienx/visual-quality-system/issues/120) be reconciled
against merged evidence, and closed **only** when their stated acceptance criteria
are actually met. This page is that reconciliation.

**It closes nothing.** Every one of these issues turns on evidence produced on the
owner's private Windows host, on a private Corporate Spend report that is
deliberately not in this repository, or on an owner signature. A reviewer reading
this page can see which criteria the merged code and public evidence satisfy and
which cannot be decided from the repository at all.

## How to read the status column

| Status | Meaning |
| :--- | :--- |
| **met (public)** | Satisfied by code, tests or public evidence in this repository, verifiable by anyone who clones it. |
| **claimed (private)** | The repository records a private-host run that satisfies the criterion. The claim is a repository record, **not** something this reconciliation verified; the raw receipts stay private by design. |
| **partial** | Some of the criterion is met; the rest is named. |
| **not met** | Not satisfied. |
| **owner only** | Cannot be satisfied by code at all; needs an owner decision or signature. |

A **claimed (private)** row is not acceptance. Per
[AGENTS.md](../AGENTS.md), missing, stale or unverifiable evidence is `blocked`,
never a pass, and no agent may convert a private run record into a G2/G4/G6
signature.

## #120 — Region ComboBox selection does not commit

The most nearly resolved of the four. The commit semantics the issue asks for were
found and implemented.

| Criterion | Status | Evidence |
| :--- | :--- | :--- |
| Determine genuine Desktop ComboBox commit semantics with an exact-PID, exact-source UIA adapter, not control-order or pixel assumptions | **met (public)** | `TogglePattern.Toggle()` on the uniquely named ListItem, then `ExpandCollapsePattern.Collapse()`. `InvokePattern` and `ValuePattern.SetValue` are recorded as *not* committing. Adapter: `vqs/powerbi/native_scripts/corporate_region_uia.ps1`; driver: `vqs.powerbi.corporate_region_acceptance`. Documented in [V012_NATIVE_G_ACCEPTANCE.md](V012_NATIVE_G_ACCEPTANCE.md). No simulated pointer coordinates. |
| Verify baseline Europe, select Latin America, restore Europe with a real UIA selection method and observed value changes | **claimed (private)** | "All three native steps passed on a fresh disposable Corporate session on 30 October." Private host, private report. |
| Independently execute scoped DAX for all three states and compare KPI values and filter context after redraw | **claimed (private)** | Recorded as independent scoped live DAX per state, distinct from the other region. Raw figures excluded from Git by design. |
| Prove before/after OS/Bridge/source identity, unchanged source hashes and mtimes, terminal dirty state, 3/3 native page capture | **claimed (private)** | Recorded as a strict PASS with 0 changed source files and 3/3 source-bound pages. The code path is public and now compares **content identity** (sha256 + size) rather than mtime, so an identical rewrite no longer aborts a genuine capture. |
| Negative tests: wrong PID/report, absent or ambiguous region, false UIA pattern support, action not committed, stale model, mismatched DAX, source mutation all BLOCK | **partial** | `tests/test_corporate_region_acceptance.py` blocks on wrong `pid`, wrong `pbip`, wrong `control_name`, wrong prior/observed state, `action: InvokePattern` (not committed), `selected_target: false`, `other_region_unselected: false`, a wrong and a NaN rendered KPI, an untrusted `schema`, indistinguishable or missing DAX, more than one PBIP, and a path that differs only as a string. **Not separately negative-tested: a stale semantic model.** Model identity is attested, but no test forces a stale model and asserts a block. |
| Keep private Corporate data, pixels, model cache and unredacted DAX off public Git | **met (public)** | Nothing Corporate is in this repository. |

**Disposition.** One public gap (a stale-model negative control) and three criteria
that only the owner can confirm from the private receipts. **Do not close** on this
reconciliation. An owner who has the 30 October receipts can close it once the
stale-model negative control exists.

## #115 — native Save attestation on the second PBIP

| Criterion | Status | Evidence |
| :--- | :--- | :--- |
| Record a complete before/after manifest, canonical paths, exact PID, schema/metadata source identities and an explicit classification of every changed file | **partial** | `vqs.powerbi.native_rebaseline` classifies changes and `desktop_native_provenance` records the full before/after inventory with sha256, size and mtime. The *published* classification of each file changed by the 30 October Save is private. |
| Distinguish Desktop-controlled metadata/cache serialization from changed active-page state and material mobile layout changes, using a narrowly reviewed allowlist | **met (public)** | `native_rebaseline._change_kind` treats `mobile.json` as `mobile_layout_requires_review` rather than harmless. |
| Either stabilize the candidate to a new exact source and rerun Save + native DAX + G4, or require explicit approval for any material change; no auto-approval, no source rewriting | **claimed (private)** | Recorded: a second disposable Save produced a strict PASS with 0 changed files; the rebaseline audit returns `stabilized_candidate_needs_independent_acceptance`, i.e. it refuses to self-approve. |
| Adversarial tests: changed DAX, filter, RLS, layout, wrong PID, changed mobile layout, unexpected metadata all fail closed | **partial** | Wrong PID, changed mobile layout and unexpected metadata are covered. **Changed DAX, changed filter and changed RLS are not separately negative-tested at the Save-witness layer.** |
| Reproduce on two unrelated PBIPs and retain post-interaction dirty-state evidence separately | **claimed (private)** | Recorded for fictional Contoso and private Corporate Spend. |
| Keep private Corporate source, cache, numbers and screenshots off the public repository | **met (public)** | Satisfied. |

**Disposition.** Two public test gaps (DAX/filter/RLS adversarial cases at the Save
layer) plus private-evidence criteria. **Do not close.**

## #116 — pin the exact two-PBIP acceptance subjects

| Criterion | Status | Evidence |
| :--- | :--- | :--- |
| Publish a *sanitized* two-subject approval manifest defining immutable hashes, intended revisions, page IDs, report/model identity, supported controls and evidence set | **not met** | `vqs.powerbi.acceptance_subjects` can *produce* a bound subject manifest, and the public Contoso subject is pinned by [docs/media/contoso-verified/PROVENANCE.json](media/contoso-verified/PROVENANCE.json). No sanitized **two-subject** approval manifest is published; the Corporate half exists only privately. |
| Declare distinct current release subject, historical source and superseded candidates; no "latest directory" or title-only lookup | **partial** | The current public subject is unambiguous. The private Corporate candidate lineage (21–27 Oct vs the offline-geo final) is described in prose in [V012_NATIVE_G_ACCEPTANCE.md](V012_NATIVE_G_ACCEPTANCE.md) rather than pinned in a machine-checkable manifest. |
| Fail closed on any report/model/candidate hash mismatch, including a screenshot bound to a different source or PID | **met (public)** | `acceptance_subjects.bound_subject` refuses receipts without a clean post-capture flag and distinguishes hash-only from source-bound evidence; `--capture-dir` labels unattested PNGs explicitly. |
| Record source provenance transitions from legitimate native Save and rebind new captures/oracles to the revised source | **met (public)** | `native_rebaseline` is exactly this path. |
| Reproduce 5/5 public Contoso and 3/3 private Corporate page inventories with current checksums and recorded filter/role states | **claimed (private)** for Corporate; **met (public)** for Contoso | Public: CI fails on a changed source, ZIP/model/content mismatch, absent page or changed screenshot. |
| An independent reviewer can trace artifact → source → model → PID → capture → DAX oracle → decision without unpinned scratch paths | **not met** | The private evidence is still referenced by scratch-folder paths (for example `vqs-independent-g-review-20261030`), which is what the issue objects to. |

**Disposition.** The one criterion that *could* be satisfied publicly — publishing a
sanitized two-subject manifest — is **not** satisfied. **Do not close.** This is the
issue with the clearest remaining public work.

## #117 — country click / tooltip hover, or a signed exclusion

| Criterion | Status | Evidence |
| :--- | :--- | :--- |
| Either implement source/PID-bound repeatable native UIA country-select on the real Shape Map and contextual tooltip hover, **or** obtain an explicit report-owner signed scope exclusion | **owner only** | Neither exists. No country-click or hover adapter is implemented, and no signed exclusion is recorded. [V012_NATIVE_G_ACCEPTANCE.md](V012_NATIVE_G_ACCEPTANCE.md) states both remain unsupported and that rendering the tooltip page is not hover proof. |
| On supported actions: before/after state, selected category, live filter context, DAX oracle, real capture, unchanged source, post-action dirty state | **not met** | Not applicable until an adapter exists. |
| Negative controls: wrong window/PID, missing or ambiguous element, clipped visual, unsupported version, wrong Year/Region/role, stale source, skipped hover all blocked | **not met** | Not applicable until an adapter exists. |
| Bind each result to the pinned two-PBIP manifest and an independent G2/G4 reviewer | **not met** | Depends on #116 and on an independent reviewer. |

**Disposition.** **Do not close, and do not treat as satisfied by the v0.1.2
distribution.** This is the single item where shipping v0.1.2 changes nothing: a
source-only release neither implements these interactions nor excludes them. The
release contract must keep stating that Shape Map country clicking and contextual
tooltip hover are **unsupported**, which [docs/CLI.md](CLI.md),
[docs/USER_GUIDE.md](USER_GUIDE.md) and the v0.1.2 release notes do.

**This needs an owner decision, not more code.** Until the owner either funds the
adapter or signs the exclusion, #117 blocks report-level G4 in
[#16](https://github.com/analienx/visual-quality-system/issues/16), independently of
how many releases ship.

## What v0.1.2 does and does not change for these issues

- It **does** make the public code paths that these issues depend on stricter and
  more honest: waivers can no longer clear missing evidence, a forged
  `owner-decision:` proof in a plan is refused, subject identity no longer changes
  with measurability, a blocked gate is annotated instead of silent, and capture
  compares content identity rather than timestamps.
- It **does not** add native evidence, sign anything, or satisfy any of the four
  issues. No work package moves to `verified`.
- [#16](https://github.com/analienx/visual-quality-system/issues/16) (independent
  report release gate) and #117 (native feature scope) stay open, as
  roadmap item 3 requires.

## Remaining public work, in priority order

1. **#116:** publish the sanitized two-subject approval manifest, and replace the
   private scratch-path references with pinned subject ids.
2. **#115:** add Save-layer adversarial tests for a changed DAX expression, a
   changed filter and changed RLS.
3. **#120:** add the one missing negative control — a stale semantic model must
   block.
4. **#117:** owner decision. No code task until then.
