# P1 Desktop recovery — 27 October 2026

**Scope:** Power BI core only. [Independent release gate #16](https://github.com/analienx/visual-quality-system/issues/16) remains **OPEN**. No G6 approval or production tag.

## Verified engineering progress

- **Contoso:** Five populated Desktop pages captured, source-matched synthetic cache, live All/2023/2024/2025 DAX, and nine OS-bound Year/Region UI Automation interactions with same-context KPI readback. All remain provisional while strict loaded-source identity reports unsaved changes.
- **Corporate Spend (unrelated PBIP):** Disposable source repairs reduced native Microsoft authoring validation from **13 errors and 4 warnings** to **0 errors, 0 warnings**. All three pages were captured in Desktop with the source model populated. Europe-filtered live DAX against PID **93916** matched the visible measures: Actual $33,527,538, Plan $31,397,779, Variance $2,129,759 and Var to Plan 6.78%; ten country rows returned, and the project remained unchanged.
- **Corporate map:** The Azure Maps sign-in wall was replaced **in a private candidate only** with an offline native ranked country bar using its existing Country/Region column and Var to Plan % measure. First live render exposed a dollar-versus-percentage color-rule error; the final screenshot now has a percentage-based scale. This is not a geometric map and its analytic equivalence requires reviewer acceptance.
- **Formatting:** Five illegal midColor literals were replaced with **#FAFAFA**, the existing neutral midpoint of another Corporate Spend bar using the same blue/orange endpoints. One invalid zero-only outerPadding setting was removed; four duplicate page-filter identifiers were renamed without changing predicates. A 0/0 authoring result does **not** alone certify visual equivalence.
- **Originals and evidence:** All modifications above live in private disposable copies, with local receipts and screenshots; no PBIR model/cache or image from these runs was pushed to GitHub.

## What is wrong with Desktop and what the upgrade addresses

On the authorized Windows host, Desktop **2.157.1354.0** reported hasUnsavedChanges=true on multiple newly opened validated disposable PBIPs. A saved-source G0 check correctly blocks, even when model queries and native controls work. Windows Package Manager reported the Microsoft.PowerBI upgrade **2.159.883.0** available on 27 October. This is a *hypothesis to retest*, not proof that the upgrade fixes the dirty flag.

The Desktop Commander integration has exhausted its monthly execution quota, so installation **has not been confirmed**. No reconnection should be attempted. The user approved the Microsoft installer; the following verified-backup script is for direct execution on the user's authorized Windows machine, not a background automation.

## Guarded installation (PowerShell on the authorized Windows computer)

From the VQS repository root after the pull request has passed hosted Windows CI:

    # 1. Make and SHA-256 verify independent backups of the six known disposable sessions.
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\p1_desktop_upgrade_guarded.ps1

    # 2. Upgrade, after agreeing to discard in-memory state in those SIX disposable sessions.
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\p1_desktop_upgrade_guarded.ps1 -Apply -DiscardDisposableState

Stage 1 makes a new private byte-matched backup and **does not stop any program**. Stage 2 repeats the entire backup verification, checks exact executable, PID, path, and six-process allowlist, then closes only those six scratch reports and invokes pinned winget upgrade. Any extra/changed/unrecognized Desktop process, inaccessible file, mismatched backup, or unavailable installer **aborts**. Receipts stay under C:\Workspace\scratch\vqs-acceptance-20261026\desktop-upgrade-*; never upload those caches/receipts to public GitHub.

**Data-loss boundary:** Stage 2 deliberately discards uncommitted **in-memory** UI state of those six disposable sessions. Disk backups cannot preserve the in-memory state; do not apply while any real user editing session or irreplaceable unsaved work is open. The owner approved installing software, not ignoring this distinction.

## Strict post-upgrade acceptance protocol

1. Verify the installed version and reopen **new private disposable copies**, not an original user report. Verify exact report/model source fingerprint and populated model.
2. Run the Microsoft authoring CLI on both. Require native saved-state/source attestation of exact Desktop PID and report folder, with hasUnsavedChanges=false. If it remains dirty, **BLOCK**; never disable this guard.
3. Run the existing Contoso strict four-state DAX oracle and strict nine-step native Year/Region interaction witness, including restore to All and source-stability checks.
4. Run an **independent Corporate Spend** Region select/clear/restore test, verify the same filter and role context with live DAX, and separately inspect the chart substituted for the authenticated map. Contoso-specific UI Automation is not valid proof for another report.
5. Have a different reviewer inspect *all actual populated pages*, controls, chart categories/colors, legible matrix totals and negative controls. G2 and G4 only pass with source-bound evidence.
6. Obtain a separate explicit owner/publisher **G6** release decision. Until then leave issue #16 open and publish no production release.

Related: [Desktop source attestation contract](DESKTOP_SOURCE_ATTESTATION.md), [acceptance matrix](ACCEPTANCE_MATRIX.md), [22 October native dossier](POWER_BI_CORE_REPAIR_ACCEPTANCE_2026-10-22.md).
