# Use VQS with an AI agent — 5-minute setup

**Your AI agent can inspect a Power BI report with VQS, explain concrete issues and propose safe improvements.** VQS supplies deterministic PBIP/PBIR/TMDL checks and evidence; the agent interprets results, prioritizes work and, with your approval, can prepare *separate candidate* changes. You do not have to learn VQS's internals.

This is a local-first **engineering preview**, not an automatically approved production-release service. A passing source check is not a guarantee that a report looks good or works when filtered.

## 1. Install VQS once

You need Python 3.11 or newer and access to your report's PBIP/PBIR files. In a terminal:

```bash
git clone https://github.com/analienx/visual-quality-system.git
cd visual-quality-system
python -m pip install -e .
vqs doctor
```

Run `vqs doctor` to see which optional native tools are installed. **Static report checks do not require Power BI Desktop, Microsoft sign-in, a subscription, or an AI API key.** Native screenshots and live DAX checks need an authorized Windows Power BI Desktop setup and the corresponding Microsoft tools; VQS does not install them for you.

## 2. Connect your agent — choose one path

### A. Your agent supports MCP tools (recommended)

VQS already ships a **local stdio MCP server**. Configure the *MCP client you actually use* to launch `python -m vqs.mcp` using the same Python environment in which you installed VQS.

For clients with a `mcpServers` configuration (such as Claude Desktop), the server entry looks like:

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

Use the **absolute path to your Python executable** instead of `python` when the agent application uses a different environment or cannot find VQS. Put the entry in the client's MCP settings; the exact settings location varies by client. Restart or reconnect the client and confirm that it discovers `vqs_inspect`, `vqs_review` and `vqs_run`. The MCP server uses local stdio, not a public HTTP endpoint.

For VS Code MCP configurations that use `servers` and `type`, the corresponding server entry is:

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

This is an MCP-compatible **local application setup**, not a claim that simply opening this GitHub repository grants a cloud chat access to your files. Your AI agent must be able to access the installed VQS MCP process and the authorized report path. Agent tools do not bypass normal OS file permissions.

### B. Your agent has a terminal, but not MCP

Give your coding agent (Codex, Claude Code, Muse or another terminal-capable agent) access to the checkout and ask it to run:

```bash
vqs review "path/to/Example.Report" --run-root "./private-vqs-runs" --run-id "first-review"
```

Replace `path/to/Example.Report` with an actual `*.Report` directory inside your PBIP project. This is a **read-only source review**; it writes evidence under the specified private run directory, never into the original report. Exit codes are `0` pass, `1` fail, `2` blocked. Your agent should check the JSON `verdict` *and* saved manifest, not treat every completed command as success.

## 3. Copy one of these prompts

**Find and explain issues (read-only):**

> Use VQS to inspect and review the Power BI report at `C:/my-reports/Sales.Report`. Begin with `vqs_inspect`, then `vqs_review` with `scope=static` and a unique run ID in a private run directory. Identify the five highest-priority **source-supported** issues, including page/visual IDs, why they matter and specific fixes. Do not modify my report. Distinguish pass, fail and blocked; don't invent screenshot findings.

**Plan safe improvements:**

> Review `C:/my-reports/Sales.Report` with VQS. Suggest no more than three changes with the biggest usability benefit, show the before/after source properties and explain what each cannot prove from code alone. Use `vqs_propose` only after a sealed review run. Do not apply changes to the original. Ask for my approval before creating an isolated repair candidate; verify source/model invariants and real affected-page rendering before recommending promotion.

**Try another Light/Dark theme (agent with terminal access):**

> Explore the available VQS theme presets for `C:/my-reports/Sales.pbip`. Preview an accessible dark theme, check per-chart categorical color distinctness, and explain the visual/control tokens that will change. After I approve, generate an isolated candidate using `vqs theme apply` and run `vqs theme audit`. Never overwrite the original PBIP, change business metrics or claim a static palette audit proves native Desktop appearance.

The theme CLI is a **separate command surface**; the current MCP server does not expose a dedicated `vqs_theme` tool. An MCP-only agent can inspect and review, but needs a separately authorized terminal/tool capability to invoke `vqs theme`.

## 4. What can the agent actually do?

| Goal | VQS tool | What is verified |
| --- | --- | --- |
| See what a report contains | `vqs_inspect` or `vqs inventory` | Pages, visual IDs, fields, source facts |
| Assess source quality | `vqs_review` or `vqs run --mode review` | Sealed source findings, explicit limits |
| Plan improvements | `vqs_propose` or `vqs run --mode propose` | Source-bound typed proposals |
| Make approved, reversible candidate edits | `vqs_repair`, `vqs_verify` | Allowlisted changes and candidate integrity, **not** instant release approval |
| Apply Light/Dark themes | `vqs theme preview/apply/audit` (**CLI**) | Palette / PBIR source audit; native Desktop review remains separate |
| Check actual appearance and interactions | Windows Desktop Bridge + `vqs capture` / supported UIA / live DAX | Real pixels, supported selection states and data when available |
| Publish a repaired original | Explicitly authorized promotion / independent release process | Never automatic merely because an agent says “looks good” |

**Important:** VQS treats `blocked` as **not verified**, not as a pass. Missing Desktop/Bridge, a stale image, wrong report PID, inaccessible model or unsupported click target is a meaningful limitation. A native screenshot alone is not proof that filtering or DAX semantics are correct.

## 5. Privacy, review and troubleshooting

- Keep customer PBIPs, screenshots, credentials and `.pbi/cache.abf` out of the public repo and public GitHub Actions artifacts. Use a local private evidence folder. Your **AI client** may have its own cloud-data policy; sharing business data with it is separate from running VQS locally and requires the appropriate authorization.
- Never grant the agent permission to overwrite your original report, perform tenant operations or publish reports merely to make a check pass. Use an isolated candidate, inspect its diff and obtain explicit **report-owner approval** before promotion.
- If no tools appear: confirm `python -m vqs.mcp` is being launched by the client, that client supports **local stdio MCP**, and that VQS is installed in the same Python environment. MCP itself is JSON-RPC on stdin/stdout, so launching it in a terminal does **not** display a chat UI.
- If an MCP call returns `blocked`, inspect its `blocked_reasons` and `next_actions`. Fix the missing input or capability, or report the limitation clearly. Do **not** silently downgrade `scope=desktop` or `scope=release` to static.
- For actual Windows capture instructions, see the [user guide](USER_GUIDE.md); for all command flags, see the [CLI reference](CLI.md); for verified acceptance and independent reviewer requirements, see the [acceptance matrix](ACCEPTANCE_MATRIX.md).
- If you are **developing VQS itself**, read [AGENTS.md](../AGENTS.md). That file sets developer/agent execution rules; this guide is for someone who simply wants to **use VQS with an agent**.

**Start small:** run a read-only VQS review on one report, let your agent explain the findings, and only then authorize a separate repair candidate.
