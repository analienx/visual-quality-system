# VQS v0.2.0 — evidence you can hand to someone else

**Published 18 November 2026.** [Download the release](https://github.com/analienx/visual-quality-system/releases/tag/v0.2.0)
· [SHA-256 checksums](https://github.com/analienx/visual-quality-system/releases/download/v0.2.0/SHA256SUMS)
· [Exact released source](https://github.com/analienx/visual-quality-system/commit/af146efce3a9d9fd6c9894f7f3e6f2c1cbe53d37).

**Scope: Power BI static source review, safe candidate repair, and the evidence
around them.** This release adds **no** native Desktop capability. Shape Map
country clicking, contextual tooltip hover, generalized native repair reload and
Word/DOCX certification remain outside the supported scope. **v0.2.0 claims no
G2, G4 or G6 acceptance of any report.** A version release is not report
acceptance.

Scope was frozen by the owner on 16 November 2026
([#159](https://github.com/analienx/visual-quality-system/issues/159)); this
release is exactly what that decision names.

## What is new

### `vqs compare-renders` — rendered pixel observations (experimental)

Compares two exact-source page captures of the same report and reports, per
page, where their pixels differ and whether those differences fall inside the
rectangles of visuals the candidate edited.

```console
vqs compare-renders base-renders cand-renders \
  --baseline-report base/Sales.pbip --candidate-report cand/Sales.pbip
```

**In this version the overall verdict is always `blocked`, so the command
always exits 2.** That is deliberate, not a defect: data and answer parity are
not established (deferred as
[#131](https://github.com/analienx/visual-quality-system/issues/131)), so VQS
will not issue an overall regression verdict. **There is no input in v0.2.0
that supplies the missing evidence**, so a `pass` cannot be obtained — do not
build a CI step that waits for exit 0 or 1 from this command.

What you *do* get is the per-page detail in the result: the changed-pixel count
and fraction, the changed bounding box, the visuals whose PBIR bytes differ, the
rectangles the differences were checked against, and `pages_failed` listing any
page with changed pixels outside every edited rectangle. Read those
observations as diagnostics; the overall verdict remains `blocked`.

**What the pixel check actually establishes.** It tests whether changed pixels
fall inside the old and new rectangles of visuals whose PBIR bytes differ,
optionally enlarged by `--margin`. That is **containment, not attribution**: a
different visual, a theme effect or a data change can move pixels inside the
same rectangle. A page with no `pages_failed` entry has not been shown to be
free of unintended change; it has been shown that the differing pixels lie
within the edited rectangles.

`--margin` dilates each edited rectangle by that many canvas pixels. It is a
**declared tolerance, not a measurement**: it defaults to `0`, and the value
used is recorded in the result.

**Data checks, and their limit.** The comparison refuses to run when either
capture declares `data_population: unproven` (a cache-less report renders
`(Blank)` everywhere and still captures), when a readiness probe is missing or
reports the report unpopulated, or when the two captures' readiness probe
hashes differ. The producer hashes `COUNTROWS` on **one** table — not the query
definitions, answers, filters, roles or other tables — so **equal probe hashes
neither prove the two captures saw equal data nor establish that any pixel
difference was caused by the source change.** Differing hashes block; equal
hashes prove very little.

It also blocks when a capture is bound to a different source revision than the
report it is compared as, when page sets, PBIR canvas or capture scale differ,
and when the report canvas cannot be measured.

### `vqs evidence-report` — a readable account of a sealed run's stage ledger

Turns a sealed run's **stage ledger** into concise human-readable output:
recorded stage statuses, the before/after check names that are comparable, the
owner questions raised, and the candidate path.

```console
vqs evidence-report --run-id <id> [--run-root <dir>] [--out report.md]
```

**It does not list the edit set.** The report says so itself — changes are not
fully bound by the ledger. For the actual edits, inspect the candidate and the
run's change evidence. Binding a complete evidence envelope is deferred as
[#149](https://github.com/analienx/visual-quality-system/issues/149).

### Copyable agent / CI quality gate

`examples/ci/powerbi-quality.yml` is a ready-to-copy GitHub Actions workflow
that runs `vqs gate` on a pull request against its base revision, pinned to a
reviewed VQS commit, writing SARIF and `::error` annotations. It validates its
own configuration and refuses a placeholder revision, an absolute report path
or a `../` traversal.

### Capture readiness and guided adoption hardening

Capture readiness states what it does and does not prove rather than implying
data; the guided adoption step is shell-safe, so a run root containing a quote,
`$(...)`, a backtick or a trailing backslash cannot break or extend the command
an owner is told to run verbatim.

## Limits — read this before relying on the release

- **No report acceptance.** No G2, G4 or G6 signature is claimed, offered or
  implied. A green `vqs gate` is static source evidence: it means "this change
  introduced no new finding we can measure", not "this report is good".
- **`compare-renders` cannot pass in this version.** Its overall verdict is
  always `blocked` (exit 2). Its per-page output is pixel-containment
  observation, not attribution, causation or data-parity proof.
- **What the CI kit was exercised against.** The workflow's own steps were run
  against two checkouts of a copy of the fictional Contoso project, with VQS
  installed from the release revision into a clean environment: a pull request
  that introduced an overlap exited `1` with one `::error` line and a SARIF
  `new` result whose `artifactLocation.uri` was repository-relative, while an
  unchanged pull request exited `0` with the five pre-existing findings
  reported `unchanged` and no annotations. Repository-relative output is
  consistent with annotations landing on a pull request's changed files, but
  **actual annotation placement on a GitHub pull request was not observed.**
  By owner decision the kit is released as a copyable example on this
  evidence; a demonstration in a separate consumer repository is **not** a
  condition of this release.
- **Native Desktop evidence is unchanged from v0.1.2.** Nothing in this release
  was produced by a Desktop process, a render or live data.
- **Deferred to the v0.3 / acceptance track**, and explicitly *not* blocking
  this version:
  [#131](https://github.com/analienx/visual-quality-system/issues/131)
  data/answer evidence parity,
  [#142](https://github.com/analienx/visual-quality-system/issues/142)
  analytical design critique,
  [#149](https://github.com/analienx/visual-quality-system/issues/149)
  complete-envelope sealing, and the native two-report demonstration
  ([#152](https://github.com/analienx/visual-quality-system/issues/152),
  [#16](https://github.com/analienx/visual-quality-system/issues/16),
  [#115](https://github.com/analienx/visual-quality-system/issues/115)–[#120](https://github.com/analienx/visual-quality-system/issues/120)).

## Install

```console
pip install visual_quality_system-0.2.0-py3-none-any.whl
vqs doctor
```

Zero runtime dependencies, Python ≥ 3.11. Verify the artifacts against the
checksums published with the GitHub release, and the tag against the exact
commit it was built from.

## Upgrading from v0.1.2

No command was removed and no result schema broken. `compare-renders` and
`evidence-report` are new. Three behaviour changes are user-visible:

- **`vqs premium --contract` now fails closed on a non-object contract.** An
  explicitly supplied JSON `null`, or any other non-object, is refused with
  "premium design contract must be a JSON object"; a wrong-shaped archetype is
  reported as a contract error. If you previously passed a `null` contract and
  it was accepted, that invocation now blocks — supply a JSON object or drop
  the `--contract` flag.
- Capture readiness and guided adoption hardening, as above.
- **The compact result of `vqs fix` / `vqs_run` is now capped at 6,000
  encoded bytes.** It used to be unbounded, so a report with many cohorts
  could push tens of kilobytes into an agent's context. Over the budget, VQS
  gives up restatable guidance first (`next_actions`, `remaining`,
  `blocked_reasons`), then `regressions`, and keeps the decision record
  (`owner_decisions`, `waived`, `changes`, `fixed`) longest. A question the
  owner has **already answered** is a redundant echo and goes first, matched
  by its own `decision_id`; a question still **unanswered is never dropped**,
  however many of its siblings were answered — answers are partial by design,
  so one answer does not make the rest expendable. Entries are dropped whole,
  never halved, and a new `omitted` map counts what went.
  **Owner questions and their options are never truncated.** If the owner
  decisions alone exceed the budget, the result carries `compact_overflow`
  with an empty `needs_review`, stays `blocked`, and tells the reader to get
  the full result before answering — an omitted count on its own would leave
  an owner deciding without the basis for the decision. The overflow form is
  measured against the budget too, so it cannot exceed the limit it
  advertises: optional scalars are given up in a fixed order and listed in
  `omitted_fields`, and a `run_dir` too long to print becomes a
  `{bytes, sha256}` stand-in. `verdict`, `outcome`, `acceptance` and
  `promotion_performed` always survive.

  Plan for two things. The budget engages on **ordinary** runs: a routine
  repair of the committed fictional Contoso report prints about 5,990 bytes
  and already trims guidance, so do not parse `next_actions` or `remaining`
  as complete. And `next_actions` and `blocked_reasons` were already capped
  at 8 and 12 entries in the compact view before this release, so their
  `omitted` counts are relative to that capped view, not to the sealed run.
  Save the complete returned JSON with `--report-out <file>` on the
  invocation before answering or auditing. `run_dir` contains the sealed
  stage ledger; it does **not** contain a sealed copy of the complete
  returned envelope. Full-envelope binding remains deferred as #149.

Pin `VQS_REVISION` in the CI workflow to the reviewed release commit rather
than a moving branch.

## Published source and verification

Tag `v0.2.0` points to source commit
[`af146efce3a9d9fd6c9894f7f3e6f2c1cbe53d37`](https://github.com/analienx/visual-quality-system/commit/af146efce3a9d9fd6c9894f7f3e6f2c1cbe53d37).
The reviewed candidate was `8edaec4e7eb8250bf411a182dc1564658cc60724`;
the final merges preserved its source tree. The integration and hardening
work is merged in [#160](https://github.com/analienx/visual-quality-system/pull/160)
and [#167](https://github.com/analienx/visual-quality-system/pull/167), and
the integration work item [#159](https://github.com/analienx/visual-quality-system/issues/159)
is closed. This completes the version release, not native report acceptance.

The [published verification record](https://github.com/analienx/visual-quality-system/releases/tag/v0.2.0#released-source-and-verification)
links the scoped cross-reviews and records the final 15/15 hosted checks and
installed-wheel validation of the attached artifacts. It also records the
initial Windows long-temp-path overflow and the subsequent successful test
with a shorter temporary root. Those are distribution and source-workflow
checks; native Desktop, live DAX and G2/G4/G6 were not accepted by this release.

The release contains `visual_quality_system-0.2.0-py3-none-any.whl`,
`visual_quality_system-0.2.0.tar.gz` and the
[`SHA256SUMS` manifest](https://github.com/analienx/visual-quality-system/releases/download/v0.2.0/SHA256SUMS).
Use the manifest to verify the downloaded files. Later documentation
corrections do not rebuild or replace these artifacts or move the release tag.

## Further reading

[Quickstart](QUICKSTART.md) · [CLI reference](CLI.md) ·
[User guide](USER_GUIDE.md) · [Capabilities and limits](CAPABILITIES.md) ·
[Owner decisions and the PR gate](OWNER_DECISIONS_AND_PR_GATE.md) ·
[Acceptance matrix](ACCEPTANCE_MATRIX.md) ·
[Native evidence and limits](V012_NATIVE_G_ACCEPTANCE.md) ·
[v0.1.2 release notes](RELEASE_NOTES_v0.1.2.md)
