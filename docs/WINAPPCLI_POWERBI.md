# Microsoft WinApp CLI and VQS Power BI native interactions

**Decision (22 October 2026): optional Windows diagnostic companion; not a mandatory VQS dependency or substitute for the existing signed native evidence.**

[WinApp CLI UI Automation documentation](https://github.com/microsoft/WinAppCli/blob/main/docs/ui-automation.md) · [Official release](https://github.com/microsoft/WinAppCli/releases/tag/v0.7.1) · [Current VQS architecture](ARCHITECTURE.md)

## Why it is useful

VQS already verifies real Power BI interactions using **.NET Windows UI Automation SelectionItemPattern** in the P16 native Contoso witness. Nine Year/Region actions were tested against a live DAX oracle; the Corporate Spend Sales Region selection/reset was also verified. The current mechanism already provides an exact Desktop PID, typed action evidence and state reconciliation.

WinApp CLI exposes those same Windows UIA capabilities as **structured CLI commands**:

| Need | WinApp CLI | Keep existing VQS authority |
| --- | --- | --- |
| Find/disambiguate a native Desktop control | `ui inspect`, `ui search` with JSON, type/root filters, semantic selector | Exact Desktop PID, report/source identity, no untrusted generic click |
| Inspect what a user can interact with | `ui get-property`, `ui get-value` | Live DAX and native, source-bound readback |
| Wait for a DAX-driven repaint | `ui wait-for --value ... --timeout ...` | Bounded G4 interaction state check (no immediate/stale readback pass) |
| Perform supported native actions | `ui invoke --action select/expand/collapse` where the element actually provides a UIA pattern | Existing allowlisted SelectionItemPattern witness with restoration checks |
| Capture a native window | `ui screenshot` for diagnostic context | **Power BI Desktop Bridge** remains authoritative for source-bound page captures and independently measured report-only pixels |

The tool is **not** a new API into Power BI. UIA cannot expose objects absent from Microsoft's accessible control tree. In particular, Shape Map country glyph selection may need a separately authorized, pixel-grounded experiment with a matching live DAX oracle; it is not made reliable merely by changing UIA clients. Injected `ui click`, `drag`, `send-keys --via send-input` need an **unlocked, foregroundable** interactive Desktop; none may bypass Windows security or a locked workstation. An unsupported action stays `blocked`, not a fabricated pass.

## Actual ZephyrusG16 pilot (22 October 2026)

- Microsoft [WinApp CLI 0.7.1](https://github.com/microsoft/WinAppCli/releases/tag/v0.7.1) downloaded as the official `winappcli-x64.zip` and extracted into an **isolated private scratch directory**. The `winapp.exe` binary showed a **valid Microsoft Corporation Authenticode signature**. No machine-wide install, PATH mutation or repo-bundled binary.
- `ui status -a 52828 --json` verified the **exact existing Power BI Desktop PID 52828**, app `PBIDesktop`, window `Contoso Retail`, per-monitor DPI 144 / scale 1.5.
- `ui search 'Fact Sales' -a 52828 --type TreeItem --json` discovered 6 matches in the Power BI model tree; a returned semantic selector was successfully passed to `ui get-property <selector> -a 52828 --property Name --json` to read the same native accessible name.
- `ui wait-for 'Nonexistent-vqs-probe-element-c17' -a 52828 --timeout 350 --json` returned `timedOut=true`, `found=false` and exit **1**, demonstrating a usable negative-control assertion.
- At the time of the pilot, the Desktop windows were **minimized** (accessible element positions near x=-30,000). Report page text/country map controls were not exposed as actionable on-screen targets. **No native interaction or country map click was attempted**, and no G2/G4/G6 acceptance conclusion changed.

The pilot proves that **read-only, exact-PID Power BI UIA inspection works** with the official CLI, not that WinApp CLI outperforms the existing P16 interaction recorder in real report journeys. The WinApp CLI upstream project still describes itself as **public preview**, and its `main` documentation can be ahead of the latest release. Prefer a version-pinned build and explicitly probe supported commands.

## How to use without coupling VQS to a preview dependency

Install from the [official release](https://github.com/microsoft/WinAppCli/releases/tag/v0.7.1) or, where available, `winget install Microsoft.winappcli --source winget`. A machine without the WinGet package can run the official signed ZIP portably; do **not** add its binaries to this repository.

In a Windows PowerShell session, set the local path to the verified executable:

```powershell
$env:WINAPP_CLI_TELEMETRY_OPTOUT = '1'
$winapp = 'C:\path\to\official\winapp.exe'
$pidTarget = 52828 # Replace with the exact authorized, already-open Desktop PID

& $winapp ui status -a $pidTarget --json
$result = & $winapp ui search 'Fact Sales' -a $pidTarget --type TreeItem --json | ConvertFrom-Json
# Multiple matching controls are expected; disambiguate before any mutation.
$found = @($result.matches | Where-Object { $_.name -eq 'Measure Group Table Fact Sales' })
if ($found.Count -gt 0) {
    & $winapp ui get-property $found[0].selector -a $pidTarget --property Name --json
}
```

**Do not persist sample selector IDs or PID numbers in runtime code.** Re-resolve selectors per run; inspect the exact target first. Do not invoke mutating UI operations against a customer's open report without an explicit scoped test and restoration procedure. Put any collected tree/screenshot JSON under ignored private run storage; accessibility output can contain business labels and values.

## Adoption threshold

Use WinApp CLI immediately for **optional diagnosis** when Windows UIA controls are hard to discover, when debugging wait/race failures, or when gathering an independent native tree description. **Keep direct .NET UIA** for existing evidence-backed Contoso/Corporate tests and the Desktop Bridge for rendering. Promote a first-party WinApp-driven interaction adapter only if it adds a specific previously unsupported, **source-bound + DAX-verified + reversible** operation and passes a real native A/B regression with independent evidence review. Otherwise, a second automation stack would add version drift and maintenance without improving the product.
