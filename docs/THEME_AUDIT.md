# Theme audit — codebase-wide review for issue #80

Scope: how the existing VQS codebase handled color, theming, and
candidate safety before the adaptive theme engine, and what this change
does about it. Every claim below names the file it was read from.

## What existed

| Area | File | Finding |
| --- | --- | --- |
| CLI surface | [cli.py](/vqs/cli.py) | Many single-purpose subcommands (`inventory`, `measure`, `premium`, `repair`, `verify`, …) each with its own blocked/pass exit mapping; no theme command. New commands risk drifting exit-code and `--out` conventions. |
| PBIR parsing | [pbir.py](/vqs/pbir.py) | `read_report_files` is the single unified reader (parsed docs, per-file digests, explicit issues); `report_context` raises on fatal metadata. `visual_context` surfaces only the first 50 literals per visual (`_literals` limit), so a color inventory built on it would silently truncate. |
| Repair execution (G3) | [execute.py](/vqs/repair/execute.py) | Strong candidate safety to reuse as ideas: `tree_digest` (link/hardlink refusal), pre-copy pinning, `stage_candidate_workspace` (byPath model staging), `write_candidate_wrapper` (deterministic `.pbip` beside the candidate). But it is plan/op-shaped, not a whole-report transform. |
| Repair allowlist | [allowlist.py](/vqs/repair/allowlist.py) | Typed op allowlist with `theme.set`/`palette.assign` only; literal-old preconditions and root-overlap checks live here. A theme sweep does not fit the per-op plan shape without a dedicated transaction. |
| Repair recipes | [recipes.py](/vqs/repair/recipes.py) | `palette.assign` validates a single `#RRGGBB` leaf (`_COLOR_RE`); leaf paths ban `selector`/`Conditional`/`query` segments. Useful precedent: cosmetic edits must never address query/filter/selector leaves. |
| Premium preflight | [premium.py](/vqs/premium.py) | Advisory, source-bound design checks (`report_context`-based); explicitly never infers inherited/pixel facts. A theme engine must keep the same honesty: unknown effective color is `unknown`, never pass. |
| Review/adjudication | [adjudicate.py](/vqs/review/adjudicate.py), [muse.py](/vqs/review/muse.py) | Independent-review separation already exists; the fixer cannot self-approve. Theme output therefore stays a candidate + manifest, not an acceptance. |
| Report skill refs | [theming.md](/.agents/skills/powerbi-report-cli/references/authoring/theming.md), [re-theming-part-02.md](/.agents/skills/powerbi-report-cli/references/authoring/re-theming-part-02.md), [re-theming-part-03.md](/.agents/skills/powerbi-report-cli/references/authoring/re-theming-part-03.md), [formatting-overview.md](/.agents/skills/powerbi-report-cli/references/authoring/formatting-overview.md) | Microsoft documents the cascade (conditional > per-visual > container > page > theme), cache-busting theme filenames, slicer/table/card dark-mode specifics, and the Azure Maps `defaultStyle` enum. A hex-only sweep contradicts this guidance. |
| Sample report | [report.json](/examples/contoso-retail/Contoso%20Retail.Report/definition/report.json), registered theme `ContosoExecutive-4f18b4d2.json` | Real shape confirmed: `themeCollection.customTheme` + `resourcePackages` registration, page `objects.outspace` literals, per-visual container backgrounds. The engine's registry and registration update target exactly these paths. |
| Fixtures | [mini_report](/tests/powerbi/fixtures/mini_report/definition/report.json) | Minimal valid report (`version.json` 2.0.0 contract) used as the shape reference for the synthetic test fixture in [test_theme_engine.py](/tests/test_theme_engine.py). |

## Exactly three improvements

### 1. One path-aware planner shared by preview and apply — implemented now

Before: [recipes.py](/vqs/repair/recipes.py) binds one leaf per op;
there was no whole-report color inventory, so preview and apply could
drift. Now [theme.py](/vqs/theme.py) `build_plan` is the single planner:
`preview_plan` and `apply_theme` consume the same `changes` list, and
role comes from the JSON path + visual type (`role_for`), never from the
old hex. Status: **implemented** in `vqs/theme.py` + `vqs theme
inspect|preview|apply|audit` in [cli.py](/vqs/cli.py).

### 2. Candidate safety reused for a whole-project theme transaction — implemented now

Before: [execute.py](/vqs/repair/execute.py) proved atomic candidate
staging for repair plans, but a theme apply also needs a new registered
theme file, `report.json` re-registration, a sibling SemanticModel copy,
and a `.pbip` wrapper. Now `apply_theme` builds in a temp sibling,
renames atomically, refuses overlapping/linked/non-empty targets,
verifies the source digest before and after, and emits
`theme-manifest.json` with rollback instructions. Status:
**implemented**; the model copy is implemented locally (byte-identical,
digest-proven in the manifest) rather than importing
`stage_candidate_workspace`, whose report-dir-shaped candidate root does
not match the theme project-root layout.

### 3. Honest contrast and coverage accounting — implemented now, Desktop proof deferred

Before: [premium.py](/vqs/premium.py) is advisory-only and no WCAG
contrast engine existed for palettes. Now `palette_contrast_check`
fails closed (exit 2, blocked JSON listing violations), and every hex
occurrence is classified `supported|preserved|blocked|unknown|
not_applicable` with file/page/visual/pointer. Status: **implemented**
for static palette/audit checks. **Deferred:** native Desktop
all-pages rendering, slicer-dropdown/tooltip states, and independent
G2/G4 review (per [ACCEPTANCE_MATRIX.md](/docs/ACCEPTANCE_MATRIX.md)) —
static contrast must not be presented as visual acceptance.

## Overengineering challenge

The tempting maximal design — a generic JSON-patch engine, a
per-property schema database for every visual type, and automatic
conversion of literals to `ThemeDataColor` references — is rejected for
now. [allowlist.py](/vqs/repair/allowlist.py) already shows the cost of
broad write surfaces: every op needs preconditions, write-target
coverage, and rollback. The shipped registry is deliberately a strict,
enumerated path/type table in one stdlib module; unsupported types fail
closed as `blocked` instead of guessing. Deferred until Desktop
evidence justifies them: literal-to-theme-reference conversion (the
upstream hybrid-normalization preference), conditional-gradient
restyling, and embedded `applyTheme` session switching. Each deferred
item needs its own issue and native proof; none is implied by this
candidate engine.
