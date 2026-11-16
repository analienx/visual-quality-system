# VQS v0.2.0 — evidence you can hand to someone else

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

### `vqs compare-renders` — rendered before/after review (experimental)

Compares two exact-source page captures of the same report at pixel level and
requires every changed pixel to fall inside a visual the candidate actually
edited. It answers "did this repair change anything it was not supposed to?",
which neither structural PBIR validity nor a screenshot hash can.

```console
vqs compare-renders base-renders cand-renders \
  --baseline-report base/Sales.pbip --candidate-report cand/Sales.pbip
```

Exit `0` no unexplained difference · `1` a rendered regression · `2` blocked.

**Experimental, and deliberately hard to satisfy.** The verdict stays
`blocked` without answer evidence. It also blocks — never passes — when either
capture declares `data_population: unproven` (a cache-less report renders
`(Blank)` everywhere and still captures), when the two captures saw different
data, when a capture is bound to a different source revision than the report it
is compared as, when page sets, canvas or scale differ, or when the report
canvas cannot be measured. `--margin` is a **declared tolerance, not a
measurement**: it defaults to `0` and the value used is recorded in the result.

### `vqs evidence-report` — a readable account of a sealed run

Turns a sealed run into a concise human-readable report: what was found, what
was changed, what remains, and which gates are unresolved. The full sealed
evidence stays on disk and is not replaced by the summary.

```console
vqs evidence-report --run-id <id> [--run-root <dir>] [--out report.md]
```

### Copyable agent / CI quality gate

`examples/ci/powerbi-quality.yml` is a ready-to-copy GitHub Actions workflow
that runs `vqs gate` on a pull request against its base revision, pinned to a
reviewed VQS commit, with SARIF and `::error` annotations landing on the pull
request's changed files. It validates its own configuration and refuses a
placeholder revision, an absolute report path or a `../` traversal.

### Capture readiness and guided adoption hardening

Capture readiness states what it does and does not prove rather than implying
data; the guided adoption step is shell-safe, so a run root containing a quote,
`$(...)`, a backtick or a trailing backslash cannot break or extend the command
an owner is told to run verbatim.

## Limits — read this before relying on the release

- **No report acceptance.** No G2, G4 or G6 signature is claimed, offered or
  implied by this version. A green gate is static source evidence: it means
  "this change introduced no new finding we can measure", not "this report is
  good".
- **`compare-renders` is experimental**, and its verdict stays blocked without
  answer evidence. Treat a pass as "no *unexplained* rendered regression", never
  as design approval.
- **The CI kit was exercised against a simulated consumer layout, not a real
  third-party repository.** Running the workflow's own steps against two
  checkouts of a copy of the fictional Contoso report, VQS installed from the
  release revision into a clean environment: a pull request that introduced an
  overlap exited `1` with one `::error` on the changed `visual.json` and a
  SARIF `new` result at a repository-relative path, while an unchanged pull
  request exited `0` with the five pre-existing findings reported `unchanged`
  and no annotations. That demonstrates the kit's behaviour; it is **not**
  evidence of use in a third-party repository, which remains outstanding.
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
- Echoed model identifiers, matching row counts or passing source tests do
  **not** independently prove equality of loaded data and answers (#131).

## Install

```console
pip install visual_quality_system-0.2.0-py3-none-any.whl
vqs doctor
```

Zero runtime dependencies, Python ≥ 3.11. Verify the artifacts against the
checksums published with the GitHub release, and the tag against the exact
commit it was built from.

## Upgrading from v0.1.2

No command removed and no result schema broken. `compare-renders` and
`evidence-report` are new; everything else behaves as in v0.1.2, with the
capture-readiness and adoption hardening above. Pin `VQS_REVISION` in the CI
workflow to the reviewed release commit rather than a moving branch.

## Further reading

[Quickstart](QUICKSTART.md) · [CLI reference](CLI.md) ·
[User guide](USER_GUIDE.md) ·
[Owner decisions and the PR gate](OWNER_DECISIONS_AND_PR_GATE.md) ·
[Acceptance matrix](ACCEPTANCE_MATRIX.md) ·
[Native evidence and limits](V012_NATIVE_G_ACCEPTANCE.md) ·
[v0.1.2 release notes](RELEASE_NOTES_v0.1.2.md)
