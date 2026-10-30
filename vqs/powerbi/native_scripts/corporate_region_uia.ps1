param(
    [Parameter(Mandatory=$true)][int]$DesktopProcessId,
    [Parameter(Mandatory=$true)][string]$ExpectedPbip,
    [Parameter(Mandatory=$true)][ValidateSet('Europe','Latin America')][string]$TargetRegion
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes

$proc = Get-Process -Id $DesktopProcessId -ErrorAction Stop
if ($proc.ProcessName -ne 'PBIDesktop') { throw 'Incorrect process executable' }
$os = Get-CimInstance Win32_Process -Filter "ProcessId = $DesktopProcessId"
if ($null -eq $os -or $os.Name -ne 'PBIDesktop.exe') { throw 'Windows PID identity absent' }
$command = [string]$os.CommandLine
$parts = [regex]::Matches($command, '(?i)"([^"]+\.pbip)"|([^\s"]+\.pbip)(?=\s|$)')
if ($parts.Count -ne 1) { throw 'Expected one OS-owned PBIP argument' }
$arg = if($parts[0].Groups[1].Success){$parts[0].Groups[1].Value}else{$parts[0].Groups[2].Value}
$expected = [System.IO.Path]::GetFullPath($ExpectedPbip)
$actual = [System.IO.Path]::GetFullPath($arg)
if (-not [string]::Equals($expected,$actual,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Wrong source PBIP for Desktop PID'
}
if ($proc.MainWindowHandle -eq 0) { throw 'No native Desktop accessibility window' }
$window = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$proc.MainWindowHandle)
$c = New-Object System.Windows.Automation.AndCondition(
 (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Sales Region')),
 (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::ComboBox)))
$controls = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,$c)
if ($controls.Count -ne 1){throw 'Missing or ambiguous Sales Region ComboBox'}
$combo = $controls[0]
$valuePattern = $combo.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$expandPattern = $combo.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
$before = [string]$valuePattern.Current.Value
if ($expandPattern.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Collapsed){
    $expandPattern.Expand()
}
Start-Sleep -Milliseconds 250

function Get-ExactOption([string]$Name) {
    $cond = New-Object System.Windows.Automation.AndCondition(
      (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,$Name)),
      (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::ListItem)))
    $matches = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond)
    if($matches.Count -ne 1){throw ('Missing or ambiguous region item: '+$Name)}
    return $matches[0]
}
$targetItem = Get-ExactOption $TargetRegion
$togglePattern = $targetItem.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
if ($togglePattern.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::On){
    $togglePattern.Toggle()
}
Start-Sleep -Milliseconds 250
$otherRegion = if($TargetRegion -eq 'Europe'){'Latin America'}else{'Europe'}
$other = Get-ExactOption $otherRegion
$otherToggle = $other.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
# These two states are verified before committing; do not toggle another
# item or quietly turn a multi-selection into single selection.
if ($togglePattern.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::On) {
    throw 'Target option was not toggled on'
}
if ($otherToggle.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::Off) {
    throw 'Other region stayed selected; single region was not proved'
}
if ($expandPattern.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Collapsed) {
    $expandPattern.Collapse()
}
$observed = ''
for($i = 0;$i -lt 15;$i++){
    Start-Sleep -Milliseconds 250
    $observed = [string]$valuePattern.Current.Value
    if($observed.StartsWith($TargetRegion,[StringComparison]::Ordinal)){break}
}
if (-not $observed.StartsWith($TargetRegion,[StringComparison]::Ordinal)) {
    throw 'Collapsed slicer did not commit expected region'
}
Start-Sleep -Milliseconds 300
$nodes = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$kpis = @()
foreach($node in $nodes){
    if($node.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button) {
        $name = [string]$node.Current.Name
        if($name -match '^Var to Plan %,?\s*([-+]?\d+(?:\.\d+)?)%\s+card$'){
            $kpis += $Matches[1]
        }
    }
}
if($kpis.Count -ne 1){throw 'Native variance KPI readback missing or ambiguous'}
$result = [ordered]@{
    schema = 'vqs.native-corporate-region-uia/1'
    pid = $DesktopProcessId
    pbip = $actual
    control_name = 'Sales Region'
    before = $before
    target = $TargetRegion
    observed = $observed
    action = 'TogglePattern + ExpandCollapsePattern.Collapse'
    selected_target = $true
    other_region_unselected = $true
    # Values remain only in private scratch; do not commit these receipts.
    variance_pct_ui = [double]::Parse($kpis[0],[Globalization.CultureInfo]::InvariantCulture)
}
$result | ConvertTo-Json -Compress -Depth 4
