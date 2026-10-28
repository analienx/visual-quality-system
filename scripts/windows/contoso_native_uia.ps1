# Native, dependency-free UI Automation adapter for the disposable Contoso PBIP.
# Actions are intentionally limited to the named Year slicer and Region bar.
# Never injects pointer/keyboard input, interacts with the locked foreground,
# changes PBIR files, or claims inaccessible Shape Map country interaction.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][int]$DesktopProcessId,
    [Parameter(Mandatory=$true)][ValidateSet('probe','year','region','clear-region')][string]$Action,
    [ValidateSet('All','2023','2024','2025','Europe','')][string]$Value = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes

function Find-Exact($scope, [string]$name, $kind) {
    $condition = New-Object System.Windows.Automation.AndCondition(
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty, $name)),
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty, $kind))
    )
    for ($attempt = 0; $attempt -lt 6; $attempt++) {
        $found = $scope.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
        if ($found.Count -eq 1) { return $found[0] }
        if ($found.Count -gt 1) {
            throw "ambiguous '$name' $kind controls, found $($found.Count)"
        }
        Start-Sleep -Milliseconds 250
    }
    throw "expected exactly one '$name' $kind control, found 0 after waiting"
}


# Exact accessibility names for this one known same-query native Shape Map.
# UIA layout must survive a presentation-only title rename. Do NOT resolve
# by substring, page text, an arbitrary Group, or the first match.
function Find-Approved-MapGroup($report) {
    $names = @(
        ('Country sales ' + [char]0x00B7 + ' darker = higher '),
        'Country sales footprint ',
        'Country sales footprint Gold marks countries with sales; gray denotes no plotted data ',
        'Country sales footprint Gold shades indicate sales in highlighted countries; gray means no plotted data '
    )
    $matches = @()
    foreach ($label in $names) {
        $condition = New-Object System.Windows.Automation.AndCondition(
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, $label)),
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::Group)))
        $found = $report.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants, $condition)
        foreach ($item in $found) { $matches += $item }
    }
    if ($matches.Count -ne 1) {
        throw "exact expected Country Shape Map group missing or ambiguous: $($matches.Count)"
    }
    return $matches[0]
}

function Bounds($element) {
    for ($attempt = 0; $attempt -lt 6; $attempt++) {
        $r = $element.Current.BoundingRectangle
        if (-not $element.Current.IsOffscreen -and -not $r.IsEmpty -and
            $r.Width -gt 0 -and $r.Height -gt 0) {
            return @([int][math]::Round($r.X), [int][math]::Round($r.Y),
                     [int][math]::Round($r.Width), [int][math]::Round($r.Height))
        }
        Start-Sleep -Milliseconds 200
    }
    throw "UIA control remains hidden/empty: $($element.Current.Name)"
}

function Year-State($yearControl) {
    $yearTexts = @($yearControl.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Text))) |
        Where-Object { $_.Current.Name -in @('All','2023','2024','2025') })
    if ($yearTexts.Count -ne 1) {
        throw "Year display is absent or ambiguous (found $($yearTexts.Count) values)"
    }
    return $yearTexts[0].Current.Name
}

function Region-Rows($report) {
    $container = Find-Exact $report 'Regional sales ' ([System.Windows.Automation.ControlType]::Group)
    $list = Find-Exact $container 'Reporting Year Sales' ([System.Windows.Automation.ControlType]::List)
    $items = $list.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::ListItem)))
    if ($items.Count -ne 3) { throw "expected three rendered Region bars, found $($items.Count)" }
    $rows = @()
    foreach ($label in @('Europe','North America','Asia Pacific')) {
        $caption = Find-Exact $container $label ([System.Windows.Automation.ControlType]::Group)
        $captionRect = Bounds $caption
        $center = [double]$captionRect[1] + $captionRect[3] / 2
        $matched = @()
        foreach ($bar in $items) {
            $barRect = Bounds $bar
            $distance = [math]::Abs(($barRect[1] + $barRect[3] / 2) - $center)
            if ($distance -le 15.0) { $matched += $bar }
        }
        if ($matched.Count -ne 1) { throw "Region $label bar cannot be safely matched by rendered row" }
        $bar = $matched[0]
        $number = 0.0
        if (-not [double]::TryParse($bar.Current.Name,
            [System.Globalization.NumberStyles]::Float,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$number)) { throw "Region $label bar exposes no numeric value" }
        $selected = $bar.GetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern).Current.IsSelected
        $rows += [pscustomobject]@{
            name=$label; sales=$number; selected=[bool]$selected;
            label_rect=$captionRect; bar_rect=(Bounds $bar); item=$bar
        }
    }
    if (@($rows | Where-Object { $_.selected }).Count -gt 1) {
        throw 'more than one Region bar is selected'
    }
    return $rows
}

function Snapshot($report, $yearControl) {
    $images = $report.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Image)))
    $prefixes = @{
        Sales='Reporting Year Sales '
        Units='Reporting Year Units '
        YoY='Reporting Year Sales YoY % '
        GM='Reporting Year GM % '
    }
    $kpis = @{}
    $rects = @{}
    $titleRects = @{}
    $titles = @{
        Sales='Sales'; Units='Units sold'
        YoY='YoY growth'; GM='Gross margin'
    }
    $yearHeader = Find-Exact $report 'Reporting year' ([System.Windows.Automation.ControlType]::Text)
    foreach ($key in @('Sales','Units','YoY','GM')) {
        $title = Find-Exact $report $titles[$key] ([System.Windows.Automation.ControlType]::Text)
        $titleRects[$key] = Bounds $title
        $matches = @()
        foreach ($item in $images) {
            if ($item.Current.Name.StartsWith($prefixes[$key],
                 [System.StringComparison]::Ordinal) -and
                 $item.Current.Name.EndsWith('.') -and
                 ($key -ne 'Sales' -or -not $item.Current.Name.StartsWith(
                     'Reporting Year Sales YoY % ', [System.StringComparison]::Ordinal))) {
                $matches += $item
            }
        }
        if ($matches.Count -ne 1) { throw "missing/ambiguous native KPI readout: $key" }
        $caption = $matches[0].Current.Name
        $text = $caption.Substring($prefixes[$key].Length,
                                    $caption.Length - $prefixes[$key].Length - 1)
        if ([string]::IsNullOrWhiteSpace($text)) { throw "empty native KPI: $key" }
        $kpis[$key] = $text
        $rects[$key] = Bounds $matches[0]
    }
    $regions = @(Region-Rows $report)
    $layout = @{}
    $groupNames = @{
        Sales='Sales '; Units='Units sold '
        YoY='YoY growth '; GM='Gross margin '
        Channel='Units by channel '; Regional='Regional sales '
    }
    foreach ($name in @('Sales','Units','YoY','GM','Channel','Regional')) {
        $control = Find-Exact $report $groupNames[$name] ([System.Windows.Automation.ControlType]::Group)
        $layout[$name] = Bounds $control
    }
    $layout['Map'] = Bounds (Find-Approved-MapGroup $report)
    return [pscustomobject]@{
        year=(Year-State $yearControl)
        kpis=$kpis
        kpi_rects=$rects
        kpi_title_rects=$titleRects
        layout_rects=$layout
        year_label_rect=(Bounds $yearHeader)
        year_rect=(Bounds $yearControl)
        regions=@($regions | ForEach-Object {
            [pscustomobject]@{
                name=$_.name; sales=$_.sales; selected=$_.selected
                label_rect=$_.label_rect; bar_rect=$_.bar_rect
            }
        })
    }
}

if ($DesktopProcessId -le 0) { throw 'positive run-owned Desktop PID required' }
if ($Action -eq 'year' -and $Value -notin @('All','2023','2024','2025')) {
    throw 'Year action needs an exact allowlisted year'
}
if ($Action -eq 'region' -and $Value -ne 'Europe') {
    throw 'only the named Europe region is permitted in this Contoso witness'
}
if ($Action -in @('probe','clear-region') -and $Value -ne '') {
    throw 'probe/clear-region do not accept a value'
}
$process = Get-Process -Id $DesktopProcessId -ErrorAction Stop
if ($process.ProcessName -ne 'PBIDesktop' -or $process.MainWindowHandle -eq [intptr]::Zero) {
    throw 'target PID is not a visible Power BI Desktop main window'
}
$window = [System.Windows.Automation.AutomationElement]::FromHandle(
    [intptr]$process.MainWindowHandle)
if ($null -eq $window -or $window.Current.Name -notmatch '^Contoso Retail(?:\\s|$)') {
    throw 'Desktop window title is not the explicit Contoso Retail preview'
}
# Bridge connectivity does not prove that the desktop is rendered. A
# minimized Power BI window exposes an empty UIA root and no report group.
# Report the OS state precisely; this adapter must never raise or focus a
# user-owned window. An attested run-owned candidate can be restored by a
# separate operator action using WindowPattern.SetWindowVisualState(Normal).
$windowState = $window.GetCurrentPattern(
    [System.Windows.Automation.WindowPattern]::Pattern).Current.WindowVisualState
if ($windowState -eq [System.Windows.Automation.WindowVisualState]::Minimized -or
    $window.Current.BoundingRectangle.IsEmpty) {
    throw 'target Desktop window is minimized/unrendered: restore the attested disposable candidate before native UIA'
}
$report = Find-Exact $window 'Power BI Report' ([System.Windows.Automation.ControlType]::Group)
$yearControl = Find-Exact $report 'Year' ([System.Windows.Automation.ControlType]::ComboBox)
$actionRect = $null
$method = 'read_only'
if ($Action -eq 'year') {
    $method = 'SelectionItemPattern'
    $actionRect = Bounds $yearControl
    $expand = $yearControl.GetCurrentPattern(
        [System.Windows.Automation.ExpandCollapsePattern]::Pattern)
    if ($expand.Current.ExpandCollapseState -ne
        [System.Windows.Automation.ExpandCollapseState]::Expanded) { $expand.Expand() }
    $list = Find-Exact $window 'Year' ([System.Windows.Automation.ControlType]::List)
    $items = $list.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::ListItem)))
    if ($items.Count -ne 3) { throw 'Year slicer options differ from 2023/2024/2025' }
    $options = @{}
    $selected = @()
    foreach ($item in $items) {
        $name = $item.Current.Name
        if ($name -notin @('2023','2024','2025') -or $options.ContainsKey($name)) {
            throw 'duplicate or unexpected Year slicer option'
        }
        $options[$name] = $item
        $selectionPattern = $null
        $togglePattern = $null
        $supportsSelection = $item.TryGetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern,
            [ref]$selectionPattern)
        $supportsToggle = $item.TryGetCurrentPattern(
            [System.Windows.Automation.TogglePattern]::Pattern, [ref]$togglePattern)
        if ($supportsSelection) {
            if ($selectionPattern.Current.IsSelected) { $selected += $item }
        } elseif ($supportsToggle) {
            $toggleState = $togglePattern.Current.ToggleState
            if ($toggleState -eq [System.Windows.Automation.ToggleState]::Indeterminate) {
                throw "Year $name has an ambiguous tri-state toggle"
            }
            if ($toggleState -eq [System.Windows.Automation.ToggleState]::On) {
                $selected += $item
            }
        } else {
            throw "Year $name exposes neither selection nor toggle UIA pattern"
        }
    }
    if ($options.Count -ne 3 -or $selected.Count -gt 1) {
        throw 'Year selection/options are incomplete or ambiguous'
    }
    if ($Value -eq 'All') {
        if ($selected.Count -eq 1) {
            $selectionPattern = $null
            if ($selected[0].TryGetCurrentPattern(
                [System.Windows.Automation.SelectionItemPattern]::Pattern,
                [ref]$selectionPattern)) {
                $selectionPattern.RemoveFromSelection()
                $method = 'SelectionItemPattern.RemoveFromSelection'
            } else {
                $togglePattern = $null
                if (-not $selected[0].TryGetCurrentPattern(
                    [System.Windows.Automation.TogglePattern]::Pattern,
                    [ref]$togglePattern)) {
                    throw 'Year clear has no supported UIA selection/toggle pattern'
                }
                if ($togglePattern.Current.ToggleState -ne
                    [System.Windows.Automation.ToggleState]::On) {
                    throw 'Year clear target is not currently selected'
                }
                $togglePattern.Toggle()
                $method = 'TogglePattern.ToggleOff'
            }
        }
    } else {
        $item = $options[$Value]
        $selectionPattern = $null
        if ($item.TryGetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern,
            [ref]$selectionPattern)) {
            $selectionPattern.Select()
            $method = 'SelectionItemPattern.Select'
        } else {
            $togglePattern = $null
            if (-not $item.TryGetCurrentPattern(
                [System.Windows.Automation.TogglePattern]::Pattern,
                [ref]$togglePattern)) {
                throw "Year $Value cannot be selected without a UIA pattern"
            }
            if ($togglePattern.Current.ToggleState -eq
                [System.Windows.Automation.ToggleState]::Indeterminate) {
                throw "Year $Value has an ambiguous tri-state toggle"
            }
            if ($togglePattern.Current.ToggleState -eq
                [System.Windows.Automation.ToggleState]::Off) {
                # This slicer permits only one selected Year. Selecting a
                # new year via Toggle must clear the previous selection.
                $togglePattern.Toggle()
            }
            $method = 'TogglePattern.ToggleOn'
        }
    }
} elseif ($Action -in @('region','clear-region')) {
    $regions = @(Region-Rows $report)
    if ($Action -eq 'region') {
        $target = @($regions | Where-Object { $_.name -eq 'Europe' })[0]
        $actionRect = $target.bar_rect
        $target.item.GetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        $method = 'SelectionItemPattern.Select'
    } else {
        $selected = @($regions | Where-Object { $_.selected })
        $method = 'SelectionItemPattern.RemoveFromSelection'
        if ($selected.Count -eq 1) {
            $actionRect = $selected[0].bar_rect
            $selected[0].item.GetCurrentPattern(
                [System.Windows.Automation.SelectionItemPattern]::Pattern).RemoveFromSelection()
        }
    }
}
# A completed Year action must leave the slicer COLLAPSED as well as at the
# requested value. Otherwise the last All restoration leaves a dropdown over
# the KPI and creates misleading 'post repair' screenshots. Rebind after UI
# redraw rather than relying on the previous stale ExpandCollapsePattern.
if ($Action -eq 'year') {
    $collapsed = $false
    for ($attempt = 0; $attempt -lt 6; $attempt++) {
        try {
            $currentReport = Find-Exact $window 'Power BI Report' ([System.Windows.Automation.ControlType]::Group)
            $currentYear = Find-Exact $currentReport 'Year' ([System.Windows.Automation.ControlType]::ComboBox)
            $currentExpand = $currentYear.GetCurrentPattern(
                [System.Windows.Automation.ExpandCollapsePattern]::Pattern)
            if ($currentExpand.Current.ExpandCollapseState -eq
                [System.Windows.Automation.ExpandCollapseState]::Expanded) {
                $currentExpand.Collapse()
            }
            if ($currentExpand.Current.ExpandCollapseState -eq
                [System.Windows.Automation.ExpandCollapseState]::Collapsed) {
                $collapsed = $true
                break
            }
        } catch {
            # Power BI may temporarily replace the accessible slicer subtree.
        }
        Start-Sleep -Milliseconds 200
    }
    if (-not $collapsed) {
        throw 'Year action changed selection but did not restore collapsed UI state'
    }
}
# Power BI redraws its accessibility subtree asynchronously. Reacquire
# elements for readback; never repeat the selection itself on a transient miss.
$observed = $null
for ($attempt = 0; $attempt -lt 10; $attempt++) {
    try {
        $freshReport = Find-Exact $window 'Power BI Report' ([System.Windows.Automation.ControlType]::Group)
        $freshYear = Find-Exact $freshReport 'Year' ([System.Windows.Automation.ControlType]::ComboBox)
        $observed = Snapshot $freshReport $freshYear
        break
    } catch {
        if ($attempt -eq 9) { throw }
        Start-Sleep -Milliseconds 350
    }
}
[pscustomobject]@{
    schema='vqs.native-desktop-uia-observation/1'
    desktop_pid=$DesktopProcessId
    window_title=$window.Current.Name
    method=$method
    action=$Action
    requested_value=$Value
    action_rect=$actionRect
    utc=(Get-Date).ToUniversalTime().ToString('o')
    observed=$observed
} | ConvertTo-Json -Depth 12 -Compress
