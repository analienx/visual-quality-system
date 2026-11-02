# VQS handover: native Power BI Desktop test on the Zephyrus

*Written 2 November 2026. Paste this file into the next session as the first message.*

## Your task in this session

Test VQS end to end on **real Power BI Desktop on my Zephyrus laptop**, and fix whatever can be fixed.
Work in `analienx/visual-quality-system` and follow `AGENTS.md` strictly.

## State at handover

| Item | State |
| --- | --- |
| `main` | `0a3abcd`, which includes PR #122 (owner decisions, `vqs gate`, review fixes) and PR #123 (review follow-ups, UTF-8 handling for non-ASCII paths) |
| PR #124 | **Open, all 14 checks green, NOT merged.** Branch `ccr-1e9536c1-0mcf8d`, head `d2630ed`. Adds `changes` + `adopt` to `vqs fix` results, plus AGENTS.md rules. **Merge only after I explicitly say so.** |
| Local tests | 2181 passed, 21 skipped, ruff clean |
| Copilot code review | Not enabled on the repo, so it never ran. Do not assume it passed. |
| Independent verifier | None yet. No work package is `verified`. Do not self-approve. Post reviews as `COMMENT`, never `APPROVE`. |

## What was proven on hosted runners (not yet on the Zephyrus)

The disposable runner (`.github/workflows/windows-desktop-probe.yml`) used Power BI Desktop 2.159, Bridge CLI 1.0.0, authoring CLI 0.5.0, and a copy of the fictional Contoso report. Results:

- A freshly opened PBIP reports `hasUnsavedChanges: true`. VQS capture correctly refuses until a witnessed native Save.
- After that Save: `screenshot-all` and VQS capture keep the report clean, and VQS capture **passes 5/5 pages**.
- It worked from a non-ASCII folder (`ContosoPřehledProbe`) without `psutil` (runs 41436087882 and 41400916127).
- The first native Save reports `verified: false` by design: it is a rebaseline transition, not a bug.

## Prerequisites on the Zephyrus (I set these up before starting)

1. Share a folder with the session, either Claude desktop app → **Settings → Claude Code → Remote Control** (add the VQS checkout or a scratch folder), or `claude remote-control` run in that folder. Keep the laptop unlocked.
2. Installed: Python ≥ 3.11, `pip install -e ".[test]"` in the checkout (use branch `ccr-1e9536c1-0mcf8d` to test PR #124), Node 22,
   `npm i -g @microsoft/powerbi-desktop-bridge-cli@1.0.0 @microsoft/powerbi-report-authoring-cli@0.5.0`, and Power BI Desktop.
3. Then call `list_computer_folders` → `request_computer_folder`. I approve the prompt on the laptop.

## Test plan (always on COPIES; never touch my original reports)

Use a scratch folder **with a non-ASCII name** (for example `C:\vqs-test\Přehled\`). Copy `examples/contoso-retail` there first; use a real report of mine only if I explicitly say so.

1. `vqs doctor`: all tools detected and the authoring skill attested.
2. `python -m pytest -q`: compare against 2181 passed / 21 skipped. Report Windows-only differences.
3. Static loop: `vqs fix <copy>.pbip --run-id z1` → blocked with questions → `vqs decisions template --run-id z1 --out answers.json`.
   **Show me the options. Do not pick them yourself.** Then `vqs fix ... --decisions answers.json --run-id z2` and check that `changes` lists 7 edits and `adopt` is present.
4. Microsoft backend: re-run step 3 with `--authoring-backend microsoft`. Expected: size edits on `visual.objects` pass the metadata gate. Container-title sizes are refused (known limitation).
5. Native: open the **candidate** copy in Desktop, do a witnessed native Save (`scripts/desktop_native_save_witness.py`), capture (`vqs capture` / `vqs.powerbi.native_capture_provenance`), and confirm the clean flag before and after.
6. Live data (only if I allow it): `vqs run --mode repair --scope desktop` with Modeling MCP, `--live-answers`.
7. `vqs gate <changed copy> --baseline <original copy> --sarif out.sarif`: exactly the changed findings are `new`.
8. Run `adopt` **only on a copy and only if I ask**: the original becomes `<report>.vqs-backup`.

## Rules (from AGENTS.md; non-negotiable)

- Keep private evidence (screenshots, receipts, run dirs) out of Git; commit hashes and booleans only.
- Every fix needs a failing-first regression test, a full suite run, and ruff.
- Blocked, unknown, missing or stale evidence is never a pass.
- Branch: if PR #124 is still open, add fixes there. If it has been merged, restart `ccr-1e9536c1-0mcf8d` from `main`.
- Open or merge PRs only when I ask.

## Open decisions for me

1. Should `format.declare_explicit` keep trusting an `owner-decision:` label inside a plan I supply with `--plan`, or must it be checked against the sealed answers?
2. Enable Copilot code review in the repo settings?
3. Who is the independent verifier for the ledger?

## Key references

`docs/OWNER_DECISIONS_AND_PR_GATE.md` · `docs/V012_NATIVE_G_ACCEPTANCE.md` (probe table) · `docs/CLI.md` · `CHANGELOG.md` · `AGENTS.md`
