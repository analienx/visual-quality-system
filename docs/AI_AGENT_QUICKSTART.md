# Fix a Power BI report with an AI agent — 5-minute setup

**Give the agent the report and a goal. It should fix supported defects, not bury you in analysis.** VQS performs source-bound diagnostics, synthesizes safe typed repairs, writes an isolated candidate, verifies what actually changed and records what still needs native Desktop evidence. The agent runs that workflow and reports results. **Only promotion of the original or material business changes require a separate decision from the report owner.**

**[How the complete auto-fix architecture works — components, why each exists, and the end-to-end sequence](AGENT_AUTOFIX_ARCHITECTURE.md)**

VQS `v0.1.0` distributes the **source-bound CLI/MCP and allowlisted candidate-repair core** for operational use; **native Desktop visual acceptance and independent report release remain preview/gated**. It can automatically repair some defects, not every possible visual or semantic problem. A candidate that passes a static repair step is *not* automatically proven production-ready.

## Next-release shortcut: v0.1.1 (development candidate)

After installing the v0.1.1 **candidate wheel** on a supported local
machine, the default safe source workflow becomes:

```bash
vqs doctor
vqs fix "C:/Reports/Sales.pbip" --run-root "C:/private/vqs-runs"
```

The new `fix` command accepts the PBIP project path directly, discovers
an unambiguous report and semantic model, never overwrites the source, and
returns a compact `Fixed / Needs review / Blocked` summary. Underlying
machine-readable run evidence remains in the private run directory.
`vqs run ... --mode repair` remains available with its full advanced
options. An ambiguous inherited font size or deliberate cross-page chart
reuse is **not** a safe auto-edit; the agent must request the missing design
decision instead of inventing one.

The next version also exposes `vqs_theme` through MCP and supports the
modern stateless MCP protocol while preserving legacy clients. This section
describes an **unreleased candidate**, not a claim that v0.1.1 is already on
the public Releases page. For an existing v0.1.0 installation, use the
documented `vqs run` workflow below.

## 1. Install the local VQS engine once

Requirements: Python 3.11+ and authorized local access to your PBIP/PBIR project.

```bash
git clone https://github.com/analienx/visual-quality-system.git
cd visual-quality-system
python -m pip install -e .
vqs doctor
```

Static source review and supported candidate repairs need **no Power BI Desktop, Microsoft account, AI API key or cloud subscription**. Native screenshots, live DAX and interaction tests require an authorized Windows Power BI Desktop host and its Microsoft tools. The agent can check capabilities with `vqs doctor` and must report what's unavailable.

## 2. Connect your agent (MCP is best; terminal also works)

### Agent supports local MCP tools

VQS has its own local stdio MCP server: `python -m vqs.mcp` (also installed as `vqs-mcp`). For clients using a `mcpServers` config (for example, Claude Desktop):

```json
{
  "mcpServers": {
    "vqs": {
      "command": "python",
      "args": ["-m", "vqs.mcp"]
    }
  }
}
```

For VS Code configurations that use `servers` entries:

```json
{
  "servers": {
    "vqs": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "vqs.mcp"]
    }
  }
}
```

Enter the JSON in your **client's MCP settings** (location varies); replace `python` with the **absolute interpreter path** if the agent uses another environment. Restart or reconnect. The agent should discover `vqs_run`, `vqs_inspect`, `vqs_review`, `vqs_propose`, `vqs_repair` and `vqs_verify`. MCP is a local tool protocol, not a web service; merely opening this GitHub repo in a cloud chat doesn't grant the chat access to your computer or confidential reports.

### Agent supports a terminal but not MCP

Codex, Muse and other terminal-enabled agents can use the **same engine** directly:

```bash
vqs run "C:/Reports/Sales.Report" --mode repair --scope static --run-root "C:/private/vqs-runs" --run-id "sales-autofix-001"
```

Use your actual `*.Report` folder inside the PBIP project. This command asks VQS to **find and apply supported fixes to a disposable candidate**—not to edit the original. Use a **fresh run ID and private run root** every attempt. An agent should inspect the structured output, including `summary.candidate_status`, `summary.repair_triage.decisions`, `summary.resolved_findings`, `summary.new_regressions` and blocked stages, rather than equating a completed process with a successful report.

`--scope static` verifies source/candidate checks only. For native proof the agent must set up the supported Windows Desktop/Bridge/model/reviewer path separately and run the `desktop` scope with explicit permissions. It cannot silently treat a static result as native acceptance.

## 3. One prompt: let the agent handle the work

> **Fix my Power BI report** at `C:/Reports/Sales.pbip` using VQS. You can autonomously inspect it, prioritize the most impactful *supported* UX and correctness defects, synthesize an allowlisted repair plan, apply changes in **new disposable candidates**, verify exact source/model diffs and rerun quality checks. Use `vqs_run` with **`mode=repair`** and `scope=static` (or `vqs run --mode repair --scope static`) and keep evidence private. If a safe source-grounded theme would improve the report, preview/apply/audit it through the VQS CLI as an isolated candidate. When authorized Windows Power BI Desktop is available, inspect native renderings, supported interactions and live DAX. Iterate on evidence up to two times, never alter the original, never invent a repair, and never override an authoring validator failure. Return **Fixed / Verified / Still blocked** and the candidate path, not a long diagnostic report. Ask me only before changing business meaning, sharing private data, or promoting the original.

This is the **recommended default**. Approval for autonomous *candidate* edits need not be repeated at each safe step. Approval for production, DAX/RLS changes, customer-data disclosure or overwriting the original is **not included**.

## 4. What will actually happen?

1. **Understand the real report:** the agent calls `vqs_run(mode=repair)`, which invokes PBIR/TMDL inspection, source-based quality checks, and typed proposal synthesis. Missing or ambiguous measurements are **blocked** rather than invented.
2. **Fix what is safe:** the VQS repair engine only executes supported allowlisted operations (e.g. geometry/spacing, formatting and other typed visual changes), writes a separate candidate, records a rollback recipe and checks exact write boundaries. If no safe proposal exists, the agent **must not fabricate a candidate**. Read summary.repair_triage.decisions for the exact unresolved cohort or visual pair; collect fresh source-bound design/render evidence or use an owner-authorized plan. Do not repeatedly run propose with unchanged facts. [See the real Contoso hidden-visual false-positive correction and the repair handoff contract](AUTO_REPAIR_TRIAGE_2026-10-28.md).
3. **Prove the result:** verify original integrity and declared diffs, run the Microsoft Report Author structural checks where required, rerun VQS quality inspection, and optionally perform native Desktop page captures and live DAX/accessible filter comparisons. The built-in coordinator never promotes.
4. **Return a decision-ready result:** identify completed repairs, remaining blockers and evidence gaps, not just severity labels. A candidate can be source-verified while the report remains **not accepted** because native evidence or an inherited property is unresolved.

The exact module and tool responsibilities—and **why** multiple components are needed—are in the [auto-fix architecture and workflow](AGENT_AUTOFIX_ARCHITECTURE.md). In particular, **agent reasoning** and **deterministic validation** are different jobs: the agent decides what to improve, VQS verifies only what the evidence supports.

## 5. If you want a specific improvement

**Premium redesign / theme:** tell the agent, *"Improve the report's visual hierarchy, spacing, categorical colors and dropdown contrast. Use `vqs premium` to ground the design intent and `vqs theme preview/apply/audit` to build an isolated candidate; review actual rendered pages before recommending it."*

**Correct a layout defect:** tell it, *"Find and automatically fix supported overlapping or clipped visuals; keep all measure and filter semantics, preserve the original, verify the change and report only remaining blockers."*

**Prepare a full release candidate:** tell it, *"Perform VQS candidate repair, verify on real Power BI Desktop with supported controls/DAX and prepare private evidence for an independent reviewer. Don't publish or overwrite the original without explicit authorization."*

The current published v0.1.0 MCP server has nine tools and no dedicated
theme tool, so v0.1.0 requires an authorized terminal for theme operations.
The upcoming v0.1.1 candidate adds `vqs_theme` for inspect/preview/apply/audit,
requiring an explicit candidate root before any write. `vqs_promote` remains
a separate explicit action, never part of automatic candidate fixing.

## 6. Safety and failure behavior

- **`pass`** means the requested evidence-backed gate passed; **`fail`** means a demonstrated violation; **`blocked`** means the evidence or capability was unavailable. A sealed stage saying `repair: pass` can coexist with overall `blocked`: **the repaired report is not necessarily accepted**.
- **Do not bypass validation** by replacing the Microsoft authoring CLI with a looser static backend for a production claim. The portable `direct` backend is useful for source-only test fixtures but isn't equivalent to Microsoft authoring or real Desktop.
- **Don't send confidential PBIPs, screenshots, model caches, credentials or tenant data to cloud agents without explicit authorization.** Use a private evidence folder and follow your client's data policies; never commit them to public GitHub.
- Wrong Desktop PID, unsaved state, stale source, inaccessible native controls or unsupported map sign-in must stop the affected check—not silently turn it green.
- `AGENTS.md` is for **developing VQS itself**, not end-user setup. The [CLI guide](CLI.md), [native user guide](USER_GUIDE.md) and [release acceptance matrix](ACCEPTANCE_MATRIX.md) give implementation and testing details.

**Bottom line:** one user request → agent-led `mode=repair` → safe isolated edits → measured verification → concise result; independent promotion remains controlled.
