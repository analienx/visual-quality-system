# ADR 0001: R6 trust boundaries

Status: accepted (2026-10-05, candidate branch `work/wp02-integration-r2`)

## Context

The R6 deep review found eight trust gaps (E01-E08, issue #22):
projection bindings collapsed same-label visuals into one row;
gate claims rode producer seals beyond the observed gate; suite
membership, reviewer identity, and promotion authority were
self-declared; review forms certified their own completeness;
candidate validation depended on a non-Microsoft CLI; public docs
overstated release coverage. This ADR records the boundaries the
R6 remediation enforces. Details: `docs/JOURNEY.md`;
per-fix oracles `tests/test_r6_e01_bindings.py` through
`tests/test_r6_e08_journey.py`.

## Decisions

1. **Scoped projection identity (E01).** One binding per
   projection, keyed by page/visual/role/projection. A missing
   `queryRef` emits `query_ref_missing` plus `actual_unknown` and
   blocks; nothing collapses or guesses.
2. **Gate-specific producer capability (E02).** `vqs.check/1`
   observes G0 only. `run_check` strips caller seal keys, seals
   the actual observation (gate G0, actual verdict, no controls),
   and binds its own envelope. Mislabeled, forged, or relabeled
   claims fail; only a genuine observation clears exactly G0.
3. **Suite binding for G6 (E03).** The G6 gate binds a canonical
   suite digest; subject-less suite membership is digest-bound.
   Suite present means suite validated; G6/review present means
   suite required.
4. **Reviewer/editor/promotion split (E04).** Review binds
   `reviewer_run_id` plus `editor_run_id`; alias, self-review,
   and drift fail, missing or untrusted sides block. Promotion
   is a separate authority decision with no registered
   authorities: every promotion blocks pending owner action.
5. **Verified review authority (E05/E06).** Whole-source
   completeness needs a verified transport (full `verify()`
   object: per-page render digests and pixels, calibration,
   fixer, bundle identity) or a live report inventory; thin
   lookalikes fail as `transport_unverified`. Without either,
   coverage is unbound and blocked. Static adjudication never
   passes: the ceiling is `static_conformance: pass` with
   `image_review_required`.
6. **Explicit authoring backends (E07).** Candidate validation
   routes through `vqs/powerbi/author` with policies
   auto/microsoft/direct. Microsoft rejection fails, warnings
   block unless explicitly allowed, and outages block; failures
   never fall back silently, and every record states the
   Desktop/render limit. Model/DAX/RLS targets fail closed on
   the public path; the executor cannot touch model bytes.
7. **Truthful public surface (E08).** Docs state
   capability/implementation/independent-acceptance
   distinctions; the developer journey in `docs/JOURNEY.md` is
   executed step-by-step (modulo paths) by the two-project
   oracle to the static
   boundary. Live/Desktop, filtered/period answers, DOCX
   all-page render, WP11 release, and promotion stay explicitly
   blocked.

## Consequences

Acceptance verdicts now fail or block where R5 passed on
self-declared or borrowed authority. Genuine static evidence
(inspected sources, sealed observations, verified transports)
flows unchanged; everything else must present its authority or
stay blocked. No ledger, issue, or PR state advances on these
boundaries alone: independent review still decides.
