# Developer journey: inspect to verified bundle review

Scope: the installed `vqs` commands that work today on a synthetic
or real report, to their actual supported static boundary. Every
`vqs` command below is executed verbatim (modulo paths) by
`tests/test_r6_e08_journey.py` on two unrelated synthetic projects;
if this page and that oracle disagree, the oracle wins and this page
is a bug. Exit codes: 0 pass, 1 fail, 2 blocked.

## 0. Install and tool availability

```console
pip install .
vqs doctor
```

`vqs doctor` reports external capabilities and never installs or
gates. `report_author` is the Microsoft-guided `powerbi-report-author`
executable (documented distribution channel
`@microsoft/powerbi-report-authoring-cli`).

Without it, repair records an explicit direct fallback. Desktop
capture needs
the Desktop Bridge plus a saved
report/PID; the journey oracle uses synthetic stand-in renders that
are labeled as such — pixels stay uncorroborated.

## 1. Inspect

```console
vqs inspect sales.Report --model sales.SemanticModel --out inspect.json
```

Measures check-ready facts into an envelope (exit 0). Blocking
coverage gaps (unreadable sources) block instead.

## 2. Measure and check

```console
vqs measure sales.Report --model sales.SemanticModel --out facts.json
vqs check facts.json --run-root runs --run-id sales1
```

`measure` emits one scoped binding per projection: a measure reused
in two visuals yields two bindings with distinct
page/visual/role/projection identity — never one collapsed row.
`check` seals the verdict (exit 0/1/2) with a G0-only observation.
Boundary: the CLI passes no source evidence, so a CLI check run
carries no acceptance-bindable envelope (`envelope_sha256` null);
envelope emission needs the Python API with `source_sha256`.

## 3. Typed candidate repair

```console
vqs validate-plan plan.json --original sales.Report --candidate-root candidate-sales.Report --run-root runs --run-id vp1
vqs repair plan.json --original sales.Report --candidate-root candidate-sales.Report --run-root runs --run-id repair1 --authoring-backend direct
```

`validate-plan` fails closed on non-allowlisted operations and on
model/DAX/RLS targets without an owner approval id. `repair`
materializes a disposable candidate, applies typed visual edits only
(the executor cannot touch model bytes), and validates the
candidate. `--authoring-backend direct` is the explicit typed-writer
fallback; `auto` (default) probes the Microsoft CLI first and
records any fallback; `microsoft` never falls back silently —
invalid fails, warnings block unless `--authoring-allow-warnings` is
given, missing/timeout/error blocks. The run seals `authoring.json`
and carries a top-level `authoring` block.

## 4. Verified bundle review

```console
vqs request-review candidate-sales.Report renders --fixer-id you > form-template.json
vqs bundle pack candidate-sales.Report renders bundle-you --fixer-id you
vqs bundle verify bundle-you
vqs adjudicate-bundle form.json --transport-bundle bundle-you --report candidate-sales.Report --run-root runs --run-id adj1
```

Complete the requested template into `form.json` (every verdict
carries its reason). `pack` binds renders, calibration, fixer, and
source identity; `verify` re-hashes and cross-checks. Adjudication
needs a verified transport or a live `--report` inventory —
otherwise coverage is unbound (blocked). A live report
inventory binds completeness only, not fixer/reviewer identity:
without a verified transport, reviewer separation is checked
against the form-declared fixer. Static ceiling: a
conformant form yields engine-level `static_conformance: pass`;
the sealed CLI verdict is `blocked` with rule
`image_review_required`. Static adjudication never passes; release
needs a capable image review of fresh full-canvas renders. A transport stale against the live report is
refused.

## Genuinely blocked gates (not this journey)

Live Desktop/model refresh, loaded DAX data, and full-canvas render
evidence (G1/G4); filtered/period scoped model answers; complete
DOCX all-page render/repair (G5); two-PBIP+DOCX WP11 release
acceptance; owner promotion; PBIPDocumenter consumer parity. These
stay explicitly blocked until their evidence exists.
