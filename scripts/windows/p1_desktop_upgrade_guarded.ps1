# P1 controlled Power BI Desktop upgrade. No action on unlisted/non-scratch sessions.
# Preflight (default): backs up exact disposable PBIP projects and verifies files.
# Apply: -Apply -DiscardDisposableState explicitly permits ending only listed tests.
[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$DiscardDisposableState,
    [string]$EvidenceRoot = 'C:\Workspace\scratch\vqs-acceptance-20261026',
    [string]$TargetVersion = '2.159.883.0'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$desktopExe = 'C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe'
$expectedProjects = @(
    'C:\Workspace\scratch\vqs-theme-gallery-20261024\approved-candidates-6a81745\saffron-spruce-light\Contoso Retail.pbip'
    'C:\Workspace\scratch\vqs-acceptance-20261026\p1-saffron-cold-reopen-20261027\Contoso Retail.pbip'
    'C:\Workspace\scratch\vqs-acceptance-20261026\p1-saffron-populated-20261027\Contoso Retail.pbip'
    'C:\Workspace\scratch\vqs-p1-corporate-zero-diagnostics-20261027\Corporate Spend.pbip'
    'C:\Workspace\scratch\vqs-p1-corporate-offline-geo-20261027\Corporate Spend.pbip'
    'C:\Workspace\scratch\vqs-p1-corporate-offline-geo-final-20261027\Corporate Spend.pbip'
)
function Canonical([string]$path) {
    return [IO.Path]::GetFullPath($path).TrimEnd('\')
}
function SourceInventory([string]$root) {
    $prefix = (Canonical $root) + '\'
    $items = @{}
    $files = @(Get-ChildItem -LiteralPath $root -Force -File -Recurse)
    foreach ($file in $files) {
        $actual = Canonical $file.FullName
        if (-not $actual.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Backup source escapes its root: $actual"
        }
        # File hashes and relative paths must match in the backup.
        $rel = $actual.Substring($prefix.Length).ToLowerInvariant()
        if ($items.ContainsKey($rel)) { throw "Duplicate file name: $rel" }
        $items[$rel] = (Get-FileHash -LiteralPath $actual -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    if ($items.Count -lt 3) { throw "Incomplete source inventory for $root" }
    return $items
}
function CompareInventories($a, $b) {
    if ($a.Count -ne $b.Count) { return $false }
    foreach ($key in $a.Keys) {
        if (-not $b.ContainsKey($key) -or $a[$key] -ne $b[$key]) {
            return $false
        }
    }
    return $true
}
function TargetSessions {
    $expected = @{}
    foreach ($value in $expectedProjects) {
        $full = Canonical $value
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
            throw "Expected disposable PBIP not present: $full"
        }
        $expected[$full.ToLowerInvariant()] = $true
    }
    $found = @(Get-CimInstance Win32_Process -Filter "Name='PBIDesktop.exe'")
    if ($found.Count -ne $expected.Count) {
        throw "Found $($found.Count) Desktop sessions, expected $($expected.Count): refusing to touch any"
    }
    $sessions = @()
    foreach ($item in $found) {
        $pattern = '^"([^"]+\\PBIDesktop\.exe)"\s+"([^"]+\.pbip)"\s*$'
        $match = [regex]::Match([string]$item.CommandLine, $pattern,
                                [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if (-not $match.Success) {
            throw "Unexpected Desktop command-line form at PID $($item.ProcessId)"
        }
        if ((Canonical $match.Groups[1].Value) -ine (Canonical $desktopExe)) {
            throw "Unexpected Desktop executable for PID $($item.ProcessId)"
        }
        $project = Canonical $match.Groups[2].Value
        if (-not $expected.ContainsKey($project.ToLowerInvariant())) {
            throw "Unapproved Desktop project at PID $($item.ProcessId): $project"
        }
        $sessions += [pscustomobject]@{
            Pid = [int]$item.ProcessId
            Project = $project
            Root = (Split-Path -Parent $project)
            CommandLine = [string]$item.CommandLine
        }
    }
    if (@($sessions | Select-Object -ExpandProperty Project -Unique).Count -ne $expected.Count) {
        throw 'Two running Desktop instances claim the same project'
    }
    return $sessions
}
if ($Apply -and -not $DiscardDisposableState) {
    throw 'Applying the upgrade closes six disposable Desktop sessions. Require -DiscardDisposableState.'
}
if ($TargetVersion -ne '2.159.883.0') {
    throw 'Expected package version differs from the 27 October 2026 preflight; requalify first'
}
if (-not (Test-Path -LiteralPath $desktopExe -PathType Leaf)) {
    throw "Desktop executable missing: $desktopExe"
}
$beforeVersion = (Get-Item -LiteralPath $desktopExe).VersionInfo.ProductVersion
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw 'winget is unavailable; no installer launched'
}
$sessions = @(TargetSessions)
$evidence = Canonical $EvidenceRoot
if (-not (Test-Path -LiteralPath $evidence -PathType Container)) {
    throw "Expected private evidence directory missing: $evidence"
}
$run = Join-Path $evidence ("desktop-upgrade-" + (Get-Date -AsUTC -Format 'yyyyMMddTHHmmssfffZ'))
$backups = Join-Path $run 'backups'
New-Item -ItemType Directory -Path $backups -Force | Out-Null
$receipts = @()
try {
    foreach ($session in $sessions) {
        $dest = Join-Path $backups ("pid-" + $session.Pid)
        $original = SourceInventory $session.Root
        Copy-Item -LiteralPath $session.Root -Destination $dest -Recurse -Force -ErrorAction Stop
        $copy = SourceInventory $dest
        if (-not (CompareInventories $original $copy)) {
            throw "Backup of PID $($session.Pid) is not byte-identical: abort"
        }
        $receipts += [pscustomobject]@{
            Pid = $session.Pid
            Source = $session.Root
            Backup = $dest
            Files = $original.Count
            Verified = $true
        }
        Write-Host ("Backed up disposable PID {0}: {1} files" -f $session.Pid,$original.Count)
    }
    # Reject any changes to process identity during the potentially long backup.
    $current = @(TargetSessions)
    $pairsBefore = @($sessions | ForEach-Object { "$($_.Pid)|$($_.Project)" } | Sort-Object)
    $pairsAfter  = @($current  | ForEach-Object { "$($_.Pid)|$($_.Project)" } | Sort-Object)
    if ((@($pairsBefore) -join ';') -ne (@($pairsAfter) -join ';')) {
        throw 'Desktop session identity changed during backup'
    }
    $receipt = [ordered]@{
        Status = 'verified_backup'
        TimestampUtc = (Get-Date).ToUniversalTime().ToString('o')
        WindowsDesktopBefore = $beforeVersion
        ExpectedUpgrade = $TargetVersion
        ApplyRequested = [bool]$Apply
        Sessions = @($receipts)
        EvidenceRoot = $run
    }
    $receiptPath = Join-Path $run 'receipt.json'
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
    Write-Host "Private backup receipt: $receiptPath"
    if (-not $Apply) {
        Write-Host 'PREFLIGHT VERIFIED. No Desktop process was stopped and no installer was started.'
        exit 0
    }

    # The owner approved the upgrade and explicitly permitted discarding
    # in-memory state from the six verified disposable test instances only.
    foreach ($session in $sessions) {
        $running = Get-CimInstance Win32_Process -Filter "ProcessId=$($session.Pid)"
        if ($null -eq $running -or [string]$running.CommandLine -cne $session.CommandLine) {
            throw "Desktop PID $($session.Pid) changed before stop; abort"
        }
        Stop-Process -Id $session.Pid -Force -ErrorAction Stop
        Write-Host "Closed backed-up disposable Desktop PID $($session.Pid)"
    }
    Start-Sleep -Seconds 2
    if (@(Get-CimInstance Win32_Process -Filter "Name='PBIDesktop.exe'").Count -ne 0) {
        throw 'Power BI Desktop is still running: no installer started'
    }

    # Explicit version pin avoids a future silently changed "latest".
    $args = @('upgrade','--id','Microsoft.PowerBI','--exact','--version',
              $TargetVersion,'--accept-source-agreements',
              '--accept-package-agreements')
    & winget @args
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "winget installer returned code $code" }
    $afterVersion = (Get-Item -LiteralPath $desktopExe).VersionInfo.ProductVersion
    $receipt.WindowsDesktopAfter = $afterVersion
    $receipt.Status = 'installer_completed_requires_attestation'
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
    Write-Host "Installed Desktop version: $afterVersion"
    Write-Host 'Do not issue G2/G4/G6 approval yet. Open a fresh disposable PBIP,'
    Write-Host 'rerun strict saved-source attestation and the two-report native oracles.'
}
catch {
    Write-Error "Desktop upgrade safety gate stopped: $($_.Exception.Message)"
    throw
}
