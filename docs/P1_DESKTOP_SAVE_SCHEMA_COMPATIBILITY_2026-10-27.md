# Native Desktop Save / PBIP schema compatibility — P1 engineering finding

**Observed on 27 October 2026, Power BI Desktop 2.159.883.0.** This is
a reproduction on an isolated *fictional Contoso* candidate, not a production
release certificate or a claim about every Desktop installation.

## Reproduced conflict

- A fresh local PBIP with a matching, populated `byPath` model opened in
  Desktop with `hasUnsavedChanges=true`, despite having no post-open source edits.
- The exact native **Save** UI Automation button (`AutomationId=save`,
  `InvokePattern`) was invoked on an explicitly PID/path-bound **disposable**
  Contoso Desktop window. The Desktop Bridge then reported
  `hasUnsavedChanges=false`.
- Native Save rewrote/touched **24** project metadata/source files, but only
  **two** differed in bytes: the PBIP wrapper and `definition.pbir`.
  Desktop removed the two `$schema` declarations. Report visuals and model
  source definitions remained byte-identical in this witness.
- The existing strict source attestor correctly **blocks** files modified after
  launch: a genuine Save is not independently distinguished from an unexplained
  external file write. Without the two `$schema` declarations, the pinned
  Microsoft report-authoring validator returned **2 errors**. With these
  declarations restored, it returned **0 errors, 1 warning**. The remaining
  warning is `PBIR_SCHEMA_UNREACHABLE` from the remote Microsoft schema
  endpoint; do not interpret skipped schema checks as full validation.

## Exact, bounded auto-repair

`scripts/normalize_saved_pbip_metadata.py` adds **only two missing**
`$schema` declarations, using Microsoft's declared schema URLs, to a
disposable candidate in a separately specified scratch root. It verifies
source-defined local `byPath` model identity and the JSON document's
semantic equivalence, refuses conflicting schema values, preserves unrelated
report/model content, and produces a private JSON receipt. Default is dry run.

```console
python -m scripts.normalize_saved_pbip_metadata DISPOSABLE_PROJECT_DIR --disposable-root PRIVATE_SCRATCH_ROOT --output PRIVATE_SCRATCH_ROOT/schema-preview.json
python -m scripts.normalize_saved_pbip_metadata DISPOSABLE_PROJECT_DIR --disposable-root PRIVATE_SCRATCH_ROOT --apply --output PRIVATE_SCRATCH_ROOT/schema-applied.json
powerbi-report-author validate DISPOSABLE_PROJECT_DIR/YourReport.pbip --format json
```

**This does not repair or certify the loaded-file attestation itself.** A
schema-only *external* edit after Desktop's native Save remains a modification
after process start. Keep native source attestation, G2/G4, independent review,
and G6 production promotion **BLOCKED** until a trustworthy, independently
reviewed native-save/source-normalization provenance witness proves the exact
persisted report and model identity. Never reset file times or falsely report
the current strict attestor as passed. Keep report datasets, screenshot evidence
and Desktop logs private.

See [issue #16](https://github.com/analienx/visual-quality-system/issues/16)
and [Desktop source attestation](DESKTOP_SOURCE_ATTESTATION.md).
