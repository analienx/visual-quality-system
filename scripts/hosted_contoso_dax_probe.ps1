# Account-free, host-local Contoso DAX proof in the ephemeral GitHub Windows VM.
# Uses the Analysis Services engine launched by Power BI Desktop, not Fabric.
# Always reports a bounded outcome; a missing engine cannot become a PASS.
param(
  [Parameter(Mandatory=$true)][string]$Out
)
$ErrorActionPreference = "Stop"
$record = [ordered]@{
  contract = "vqs.github-hosted-contoso-dax/1"
  status = "blocked"
  engine_process_seen = $false
  port_candidates = 0
  assembly_loaded = $false
  target_measure = "Reporting Year Sales"
  query = 'EVALUATE ROW("Sales", [Reporting Year Sales])'
  result = $null
  scope = "actual_contoso_measure_local_model"
  actual_model_proven = $false
  release_verdict = "blocked"
  diagnostic = $null
}
try {
  if (Test-Path -LiteralPath $Out) { throw "Receipt exists; refusing overwrite" }
  $processes = @([System.Diagnostics.Process]::GetProcessesByName("msmdsrv"))
  $record.engine_process_seen = ($processes.Count -gt 0)
  if ($processes.Count -eq 0) { throw "No Desktop Analysis Services engine" }
  $pbi = Join-Path $env:ProgramFiles "Microsoft Power BI Desktop"
  $packageAssembly = Join-Path $env:RUNNER_TEMP "vqs-adomd-net472\Microsoft.AnalysisServices.AdomdClient.dll"
  if (Test-Path -LiteralPath $packageAssembly) {
    Add-Type -Path $packageAssembly -ErrorAction Stop
    $record.client_source = "microsoft_nuget_19.117.0_net472"
  } else {
    try {
      Add-Type -AssemblyName "Microsoft.AnalysisServices.AdomdClient" -ErrorAction Stop
      $record.client_source = "desktop_global_assembly_cache"
    } catch {
      $assemblies = @(Get-ChildItem -LiteralPath $pbi -Filter "Microsoft.AnalysisServices.AdomdClient.dll" -Recurse -File -ErrorAction Stop)
      if ($assemblies.Count -eq 0) { throw "No ADOMD client from official NuGet, GAC or Desktop" }
      Add-Type -Path $assemblies[0].FullName -ErrorAction Stop
      $record.client_source = "desktop_local_bin"
    }
  }
  $record.assembly_loaded = $true
  $roots = @(
    (Join-Path $env:LOCALAPPDATA "Microsoft\Power BI Desktop\AnalysisServicesWorkspaces"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\Power BI Desktop Store App\AnalysisServicesWorkspaces")
  )
  $portFiles = @()
  foreach($folder in $roots) {
    if(Test-Path $folder) {
      $portFiles += @(Get-ChildItem -LiteralPath $folder -Recurse -Filter msmdsrv.port.txt -File -ErrorAction SilentlyContinue)
    }
  }
  $record.port_candidates = $portFiles.Count
  if($portFiles.Count -eq 0) { throw "No local Desktop workspace port file" }
  if($portFiles.Count -gt 16) { throw "Unexpected number of engine workspaces" }
  foreach($portFile in $portFiles) {
    # Power BI Desktop may write msmdsrv.port.txt in UTF-16LE without a
    # reliably detected BOM. Attempt native UTF-16 first, then ASCII/UTF-8.
    $bytes = [System.IO.File]::ReadAllBytes($portFile.FullName)
    $trimChars = [char[]]@(0, 0xFEFF, 9, 10, 13, 32)
    $raw = [System.Text.Encoding]::Unicode.GetString($bytes).Trim($trimChars)
    $number = 0
    if(-not [int]::TryParse($raw, [ref]$number)) {
      $raw = [System.Text.Encoding]::UTF8.GetString($bytes).Trim($trimChars)
    }
    $number = 0
    if(-not [int]::TryParse($raw, [ref]$number) -or $number -lt 1 -or $number -gt 65535) {
      continue
    }
    $connection = $null
    $reader = $null
    try {
      $connection = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$number;Connect Timeout=8")
      $connection.Open()
      $cmd = $connection.CreateCommand()
      $cmd.CommandText = 'EVALUATE ROW("Sales", [Reporting Year Sales])'
      $cmd.CommandTimeout = 12
      $reader = $cmd.ExecuteReader()
      if ($reader.Read()) {
        $value = $reader.GetValue(0)
        if ($null -ne $value -and $value -ne [DBNull]::Value) {
          $sales = [double]::Parse([string]$value, [System.Globalization.CultureInfo]::InvariantCulture)
          if (-not [double]::IsNaN($sales) -and -not [double]::IsInfinity($sales)) {
            $record.result = [ordered]@{
              sales = $sales
              row_count = 1
              non_null_numeric_sales = $true
              source = "Contoso Reporting Year Sales measure"
            }
            $record.status = "model_query_executed"
            $record.actual_model_proven = $true
            break
          }
        }
      }
    } catch {
      # Other engine ports can belong to the blank synthetic PBIP. Try each
      # isolated workspace; no error implies successful target-model scope.
      $record.diagnostic = "At least one engine port did not resolve the Contoso measure"
    } finally {
      if ($null -ne $reader) { $reader.Close() }
      if ($null -ne $connection) { $connection.Close() }
    }
  }
  if (-not $record.actual_model_proven) {
    throw "No reachable local model returned the Contoso Sales measure"
  }
} catch {
  $record.status = "blocked"
  $record.diagnostic = [string]$_.Exception.Message
} finally {
  $record | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $Out -Encoding UTF8
  $record | ConvertTo-Json -Depth 7
}
