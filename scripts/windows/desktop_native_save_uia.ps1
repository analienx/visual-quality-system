[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][int]$DesktopProcessId,
    [Parameter(Mandatory=$true)][string]$ExpectedPbip,
    [Parameter(Mandatory=$true)][string]$DisposableRoot
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=[IO.Path]::GetFullPath($DisposableRoot).TrimEnd('\') + '\'
$file=[IO.Path]::GetFullPath($ExpectedPbip)
if (-not $file.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'requested PBIP is outside private disposable root'
}
if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or
    [IO.Path]::GetExtension($file) -ne '.pbip') {
    throw 'missing physical scratch PBIP'
}
$cim=Get-CimInstance Win32_Process -Filter "ProcessId=$DesktopProcessId"
if ($null -eq $cim -or $cim.Name -ne 'PBIDesktop.exe') {
    throw 'OS process is not Power BI Desktop'
}
# Windows process arguments are quoted for space-bearing physical .pbip paths.
if (-not $cim.CommandLine.Trim().EndsWith('"' + $file + '"',
                                   [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Desktop PID does not own the requested disposable PBIP'
}
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p=Get-Process -Id $DesktopProcessId
if ($p.MainWindowHandle -eq [IntPtr]::Zero) {
    throw 'Desktop process has no native window'
}
$w=[System.Windows.Automation.AutomationElement]::FromHandle(
    [IntPtr]$p.MainWindowHandle)
if ($w.Current.Name -ne [IO.Path]::GetFileNameWithoutExtension($file)) {
    throw 'Desktop title does not match the physical PBIP'
}
$condition=New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button)
$buttons=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition)
$matches=@()
foreach($b in $buttons) {
    if ($b.Current.Name -ne 'Save' -or $b.Current.AutomationId -ne 'save' -or
        -not $b.Current.IsEnabled -or $b.Current.IsOffscreen) { continue }
    $rect=$b.Current.BoundingRectangle
    if ($rect.IsEmpty -or $rect.Width -le 0 -or $rect.Height -le 0) { continue }
    $pat=$null
    if ($b.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,
                                [ref]$pat)) {
        $matches += [pscustomobject]@{element=$b;pattern=$pat;rectangle=$rect.ToString()}
    }
}
if ($matches.Count -lt 1 -or
    @($matches | Select-Object -ExpandProperty rectangle -Unique).Count -ne 1) {
    throw 'native Save controls are missing or ambiguous'
}
$start=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
$matches[0].pattern.Invoke()
[pscustomobject]@{
    schema='vqs.native-desktop-save-ui-control/1'
    method='InvokePattern'
    pid=$DesktopProcessId
    window=$w.Current.Name
    automation_id='save'
    button='Save'
    action_epoch=$start
    matching_button_count=$matches.Count
    button_rectangle=$matches[0].rectangle
} | ConvertTo-Json -Compress
