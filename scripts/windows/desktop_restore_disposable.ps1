[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][int]$DesktopProcessId,
    [Parameter(Mandatory=$true)][string]$ExpectedPbip,
    [Parameter(Mandatory=$true)][string]$DisposableRoot
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=[IO.Path]::GetFullPath($DisposableRoot).TrimEnd('\') + '\'
$pbip=[IO.Path]::GetFullPath($ExpectedPbip)
if (-not $pbip.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'attempted to restore a non-disposable Desktop window'
}
$p=Get-CimInstance Win32_Process -Filter "ProcessId=$DesktopProcessId"
if ($null -eq $p -or $p.Name -ne 'PBIDesktop.exe' -or
    -not $p.CommandLine.Trim().EndsWith('"' + $pbip + '"',
                                      [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Desktop PID / actual project binding does not match'
}
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$process=Get-Process -Id $DesktopProcessId
if ($process.MainWindowHandle -eq [IntPtr]::Zero) {throw 'missing Desktop main window'}
$w=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$process.MainWindowHandle)
if ($w.Current.Name -ne [IO.Path]::GetFileNameWithoutExtension($pbip)) {
    throw 'unexpected Desktop window title'
}
$pattern=$w.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern)
$before=$pattern.Current.WindowVisualState.ToString()
if ($pattern.Current.WindowVisualState -eq [System.Windows.Automation.WindowVisualState]::Minimized) {
    $pattern.SetWindowVisualState([System.Windows.Automation.WindowVisualState]::Normal)
}
[pscustomobject]@{
    desktop_pid=$DesktopProcessId
    expected_pbip=$pbip
    before=$before
    after=$pattern.Current.WindowVisualState.ToString()
    utc=(Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Compress
