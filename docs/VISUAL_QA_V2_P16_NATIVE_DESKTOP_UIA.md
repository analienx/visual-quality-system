# P16 — Native Desktop UI Automation witness for Contoso Deep Dive

Status: engineering implementation. It is **not** independent G2/G4/G6 acceptance.

## Why this closes a real detection gap

The P14 recorded trace validates a handwritten observation against real DAX,
but rightly cannot infer that the user actually interacted with Desktop.
P16 adds a *Windows-native executor*: Windows PowerShell/.NET UI Automation
executes named `SelectionItemPattern.Select/RemoveFromSelection` on the real
Power BI Desktop controls, then reads live native rendered values/bounds.

It works against an explicitly pinned already-running Desktop process, even
when the foreground session is locked, without a Power BI Service license,
a browser driver, screen coordinates, or keyboard injection.

The implementation makes these verifiable:

| Prior failure / risk | New actual Desktop signal | Regression |
|---|---|---|
| Year and "Reporting year" share/misalign a box | Distinct UIA heading/dropdown rectangles, vertical separation and alignment | label-dropdown overlap fails |
| Sales, Units, YoY and Gross Margin too tall or misaligned | Native title/value and card-container rectangles, size ratios, common baseline, no horizontal collision and bounded padding | uneven height, shifted title, excessive label height fail |
| Sales/Units KPI row misaligned to map below | Four native card-group rectangles checked against combined left Map span, right Channel span and lower Region panel edges/gutters | shifted/oversized card, misaligned map/channel or regional panel fail |
| Card numbers stale under Year | Actual slicer selection/readout and four rendered cards compared to executed source-bound DAX | wrong period, missing/false/blank numbers fail |
| Regional sales bars don't match regions | Native category-label/bar center alignment and actual numeric accessibility values validated against three DAX regions | wrong bar value or detached label fails |
| Region click visually changes nothing | Europe bar's actual UIA select/clear, Sales $2.48M under 2024 and return to $6.20M; compare with year+region DAX | absent selection/crossfilter/reset fails |
| "A transcript said click occurred" | Explicit allowlisted native UIA control-pattern invocations, action geometry and subsequent independent native readback | wrong PID, method, page contract, source, model or output fail closed |

The layout checks operate on *actual Windows accessibility geometry*, not
just PBIR `position` JSON. This is a crucial complement to screenshot-only
pixel occupancy and makes the original alignment misses reproducibly testable.
A native accessibility box still does **not** prove glyph ink is unclipped:
OCR/pixel detection remains necessary as a separate visual acceptance channel.

## Windows reproduction (disposable report only)

1. Open a disposable Contoso PBIP preview in Power BI Desktop; record its
   positive `PBIDesktop.exe` PID. Do not run on an unrelated user's report.
2. Capture the P14 live DAX oracle for that same physical project and PID.
3. Run the native executable proof:

```powershell
python -m scripts.contoso_p14_live_oracle "C:\\scratch\\disposable-Contoso" --desktop-pid 12345 --output "C:\\private\\oracle.json"

python -m scripts.contoso_p16_native_interaction "C:\\scratch\\disposable-Contoso" --desktop-pid 12345 --oracle "C:\\private\\oracle.json" --output "C:\\private\\native-uia.json"
```

The native adapter is `scripts/windows/contoso_native_uia.ps1`. It requires
no third-party PowerShell modules. The orchestrator refuses to overwrite
existing evidence, fingerprints the local PBIP wrapper/report/semantic model
before and after, verifies the PBIR interaction contract, and compares
native displayed *formatted numbers* using half-last-decimal rounding
intervals against unrounded DAX. It verifies All, 2023, 2024, 2025,
return to 2024, Europe region selection, clear Region, then restores All.
The initial baseline accepts a *genuinely observed* prior 2023/24/25/All
state if an earlier run was interrupted; it does not silently assume All.

The JSON contains an ordered event series with native KPI strings, native
bounding boxes, region values/selection, UTC timestamp and actual action
method. Keep this JSON and any Desktop screenshots private; never commit
business values or screenshots to Git.

Exit code 0 means `native_uia: pass`, **not** G4 acceptance. An observed
numeric/geometry mismatch exits 1; missing native controls, inputs or
Windows capability block with exit 2. All outcomes retain
`interactive: blocked`, `country_map: blocked`,
`independent_acceptance: blocked` and
`desktop_loaded_file_attested: false`.

## Still blocked — explicit next product steps

1. **Shape Map United States input**: the built-in Power BI Shape Map
   accessibility subtree exposes one image/"Plot area", not countries.
   Country selection needs an authorized interactive/unlocked Desktop
   observer or supported semantic hit-target mechanism. A human-approved
   map-geometry pixel click must verify selected state, KPI outcome and
   screenshot; it must not be simulated while LockApp is foreground.
2. **Independent rendered visual judgment**: combine accessibility for
   controls/text bounds, OCR text boxes for canvas map/chart/Word, image
   occupancy/SSIM for ink and clipping, and reviewer inspection. Normalize
   DPI/window geometry. Numeric equality alone cannot decide aesthetics.
3. **Safe automatic repair**: use allowlisted PBIR repair recipes, optionally
   ranked by 2D constraint optimization (hard no-overlap/gutters/text area;
   soft minimal movement/consistent rhythm). Generate a few isolated
   candidates; render them natively; require improved evidence **and**
   unmodified DAX/semantic bindings before promotion or rollback.
4. **DOCX functional verification**: render generated DOCX with actual
   Microsoft Word `Document.ExportAsFixedFormat` where available, compare
   extracted page/text geometries and source-bound claims, and require
   independent viewer review. DOCX XML structural checks alone are not
   equivalent to the paginated result.
5. **G6**: repeat inspect→diagnose→repair→native render→independent signoff
   across two *unrelated* PBIPs and one customer-useful DOCX before
   declaring the entire product releasable.

Useful official engineering references:
- Microsoft Windows UI Automation overview:
  https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/ui-automation-overview
- Microsoft WinApp CLI (optional interactive adapter):
  https://github.com/microsoft/WinAppCli
- Power BI Shape Map and its constraints:
  https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-shape-map
- Google OR-Tools CP-SAT 2D no-overlap:
  https://developers.google.com/optimization/reference/python/sat/python/cp_model
- Microsoft Word ExportAsFixedFormat:
  https://learn.microsoft.com/en-us/dotnet/api/microsoft.office.interop.word._document.exportasfixedformat
