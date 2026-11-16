<#
.SYNOPSIS
    Follow up the two open questions the control sweep leaves behind.

.DESCRIPTION
    The sweep reports two things it cannot explain on its own. Six numeric boxes
    accepted a new value and changed no readout, and two toggles were not in the
    tree at all. Both have an innocent explanation and a real-defect
    explanation, and only a targeted probe tells them apart.

    The toggles live in the assembly inspector, which is hidden until the
    assembly command is switched on, so this opens it and sweeps them there.

    The quiet numeric boxes may be mode-dependent: a shoulder-dart control has
    nothing to do while the garment is drafted with side darts. This switches
    the bust shaping mode and probes them again. A box that moves a readout in
    one mode and not another is working as designed but is not telling the user
    that, which is a user-experience defect rather than a dead control. A box
    that stays quiet in every mode needs a closer look.

    This records evidence and accepts nothing.
#>
[CmdletBinding()]
param(
    [string]$OutputPath = 'artifacts/control-sweep/control-follow-up.json',
    [int]$SettleMilliseconds = 600
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

function Get-PatternalWindow {
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $live = @(Get-Process -Name 'Patternal' -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowHandle -ne 0 })
        if ($live.Count -gt 0) {
            $handles = $live | ForEach-Object { [int]$_.MainWindowHandle }
            $condition = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, 'Patternal')
            $windows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
                [System.Windows.Automation.TreeScope]::Children, $condition)
            foreach ($window in $windows) {
                if ($handles -contains $window.Current.NativeWindowHandle) { return $window }
            }
        }
        Start-Sleep -Milliseconds 500
    }
    throw 'No running Patternal window was found.'
}

function Get-RawDescendants {
    param([Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Root)
    $walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
    $all = [System.Collections.Generic.List[object]]::new()
    $pending = [System.Collections.Generic.Queue[object]]::new()
    $pending.Enqueue(@{ Element = $Root; Depth = 0 })
    while ($pending.Count -gt 0) {
        $entry = $pending.Dequeue()
        $all.Add($entry.Element)
        if ($entry.Depth -ge 40) { continue }
        try { $child = $walker.GetFirstChild($entry.Element) } catch { continue }
        while ($null -ne $child) {
            $pending.Enqueue(@{ Element = $child; Depth = $entry.Depth + 1 })
            try { $child = $walker.GetNextSibling($child) } catch { break }
        }
    }
    return $all
}

function Find-Control {
    param(
        [Parameter(Mandatory)][System.Collections.Generic.List[object]]$Elements,
        [Parameter(Mandatory)][string]$Key
    )
    foreach ($element in $Elements) {
        try { if ($element.Current.AutomationId -eq $Key) { return $element } } catch { }
    }
    foreach ($element in $Elements) {
        try { if ($element.Current.Name -eq $Key) { return $element } } catch { }
    }
    return $null
}

function Get-TextValue {
    param([System.Windows.Automation.AutomationElement]$Element)
    if ($null -eq $Element) { return $null }
    try {
        return $Element.GetCurrentPattern(
            [System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    }
    catch { return $Element.Current.Name }
}

function Resolve-ValueElement {
    param([System.Windows.Automation.AutomationElement]$Element)
    if ($null -eq $Element) { return $null }
    try {
        $Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern) | Out-Null
        return $Element
    }
    catch {
        $editCondition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Edit)
        return $Element.FindFirst(
            [System.Windows.Automation.TreeScope]::Descendants, $editCondition)
    }
}

function Set-NumberBoxValue {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory)][double]$Value
    )
    $Element.SetFocus()
    Start-Sleep -Milliseconds 120
    $Element.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern).SetValue([string]$Value)
    Start-Sleep -Milliseconds 120
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
}

$readoutKeys = @(
    'GarmentEaseResultText', 'ShirtConstructionResultText', 'BustShapingResultText',
    'DrapeStaleSimulationState', 'DrapeAvatarPreviewState', 'PatternPieceCountText',
    'AssemblySummaryText', 'AssemblySeamLengthText', 'AssemblySeamMismatchText'
)

function Get-ReadoutSnapshot {
    param([Parameter(Mandatory)][System.Collections.Generic.List[object]]$Elements)
    $snapshot = [ordered]@{}
    foreach ($key in $readoutKeys) {
        $element = Find-Control -Elements $Elements -Key $key
        $snapshot[$key] = if ($null -eq $element) { $null } else { $element.Current.Name }
    }
    return $snapshot
}

function Compare-Readouts {
    param($Before, $After)
    $changed = @()
    foreach ($key in $readoutKeys) { if ($Before[$key] -ne $After[$key]) { $changed += $key } }
    return $changed
}

function Test-NumberBox {
    param(
        [Parameter(Mandatory)][System.Collections.Generic.List[object]]$Elements,
        [Parameter(Mandatory)][string]$Key,
        [Parameter(Mandatory)][double]$Probe
    )
    $element = Find-Control -Elements $Elements -Key $Key
    if ($null -eq $element) { return [ordered]@{ id = $Key; found = $false } }
    $valueElement = Resolve-ValueElement -Element $element
    $original = Get-TextValue -Element $valueElement
    $before = Get-ReadoutSnapshot -Elements $Elements
    Set-NumberBoxValue -Element $valueElement -Value $Probe
    Start-Sleep -Milliseconds $SettleMilliseconds
    $accepted = Get-TextValue -Element $valueElement
    $after = Get-ReadoutSnapshot -Elements $Elements
    Set-NumberBoxValue -Element $valueElement -Value ([double]$original)
    Start-Sleep -Milliseconds $SettleMilliseconds
    return [ordered]@{
        id              = $Key
        found           = $true
        enabled         = $element.Current.IsEnabled
        originalValue   = $original
        probeValue      = $Probe
        acceptedValue   = $accepted
        readoutsChanged = @(Compare-Readouts -Before $before -After $after)
    }
}

$window = Get-PatternalWindow
$elements = Get-RawDescendants -Root $window
$report = [ordered]@{
    schemaVersion = 'patterna.control-sweep-follow-up/1.0'
    claims        = [ordered]@{ uxAccepted = $false; valuesVerifiedCorrect = $false }
    probedAtUtc   = [DateTimeOffset]::UtcNow.ToString('O')
    assemblyOverlayToggles = @()
    bustModeProbe = [ordered]@{}
    findings      = @()
}

# ---- The two toggles that live behind the assembly command -----------------

$assemblyCommand = Find-Control -Elements $elements -Key 'EditAssemblyButton'
if ($null -eq $assemblyCommand) {
    $report.findings += 'The assembly command was not found, so its overlay could not be opened.'
}
else {
    $assemblyPattern = $assemblyCommand.GetCurrentPattern(
        [System.Windows.Automation.TogglePattern]::Pattern)
    if ($assemblyPattern.Current.ToggleState.ToString() -ne 'On') {
        $assemblyPattern.Toggle()
        Start-Sleep -Milliseconds 1200
    }
    $elements = Get-RawDescendants -Root $window
    foreach ($key in @('ReverseSeamSideBToggle', 'Reverse selected seam side B sewing direction',
                       'ClosureStateToggle', 'Close selected temporary garment closure')) {
        $element = Find-Control -Elements $elements -Key $key
        if ($null -eq $element) { continue }
        $entry = [ordered]@{
            id      = $key
            found   = $true
            enabled = $element.Current.IsEnabled
        }
        if ($element.Current.IsEnabled) {
            $pattern = $element.GetCurrentPattern(
                [System.Windows.Automation.TogglePattern]::Pattern)
            $before = Get-ReadoutSnapshot -Elements $elements
            $stateBefore = $pattern.Current.ToggleState.ToString()
            $pattern.Toggle()
            Start-Sleep -Milliseconds $SettleMilliseconds
            $entry.stateBefore = $stateBefore
            $entry.stateAfterToggle = $pattern.Current.ToggleState.ToString()
            $entry.respondedToToggle = ($entry.stateAfterToggle -ne $stateBefore)
            $entry.readoutsChanged = @(Compare-Readouts -Before $before `
                -After (Get-ReadoutSnapshot -Elements $elements))
            if ($entry.respondedToToggle) {
                $pattern.Toggle()
                Start-Sleep -Milliseconds $SettleMilliseconds
            }
            $entry.restored = ($pattern.Current.ToggleState.ToString() -eq $stateBefore)
        }
        else {
            $entry.note = 'Present but disabled: no seam or closure is selected in the overlay.'
        }
        $report.assemblyOverlayToggles += $entry
        Write-Output ("assembly toggle {0}: found, enabled={1}" -f $key, $entry.enabled)
    }
    if ($report.assemblyOverlayToggles.Count -eq 0) {
        $report.findings += 'The assembly overlay opened but neither seam toggle appeared in it.'
    }
    # Leave the command as it was found.
    if ($assemblyPattern.Current.ToggleState.ToString() -eq 'On') {
        $assemblyPattern.Toggle()
        Start-Sleep -Milliseconds 800
    }
}

# ---- The quiet numeric boxes, in each bust shaping mode ---------------------

$quietBoxes = @(
    @{ Key = 'BackNeckDepthNumberBox';           Probe = 7 },
    @{ Key = 'SleeveCapHeightNumberBox';         Probe = 19 },
    @{ Key = 'LeftBustProjectionNumberBox';      Probe = 8 },
    @{ Key = 'RightBustProjectionNumberBox';     Probe = 8 },
    @{ Key = 'ShoulderDartMouthOffsetNumberBox'; Probe = 8 },
    @{ Key = 'ShoulderDartShareNumberBox';       Probe = 60 }
)

$modeBox = Find-Control -Elements $elements -Key 'BustShapingModeComboBox'
if ($null -eq $modeBox) {
    $modeBox = Find-Control -Elements $elements -Key 'Bust shaping construction mode'
}
if ($null -eq $modeBox) {
    $report.findings += 'The bust shaping mode selector was not found, so the mode-dependent probe was skipped.'
}
else {
    $selection = $modeBox.GetCurrentPattern(
        [System.Windows.Automation.SelectionPattern]::Pattern)
    $originalMode = ($selection.Current.GetSelection() | ForEach-Object { $_.Current.Name }) -join ','
    $expand = $modeBox.GetCurrentPattern(
        [System.Windows.Automation.ExpandCollapsePattern]::Pattern)

    foreach ($modeName in @('Rotate intake to shoulder darts', 'Distribute intake across side and shoulder')) {
        $expand.Expand()
        Start-Sleep -Milliseconds 500
        $items = Get-RawDescendants -Root $window
        $item = Find-Control -Elements $items -Key $modeName
        if ($null -eq $item) {
            $expand.Collapse()
            $report.findings += "The bust shaping mode '$modeName' was not offered."
            continue
        }
        $item.GetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        Start-Sleep -Milliseconds 900
        $elements = Get-RawDescendants -Root $window
        $results = @()
        foreach ($box in $quietBoxes) {
            $results += Test-NumberBox -Elements $elements -Key $box.Key -Probe ([double]$box.Probe)
        }
        $report.bustModeProbe[$modeName] = $results
        foreach ($result in $results) {
            Write-Output ("{0,-18} {1,-34} readouts moved: {2}" -f `
                $modeName, $result.id, $result.readoutsChanged.Count)
        }
    }

    # Restore the mode the user had.
    $expand.Expand()
    Start-Sleep -Milliseconds 500
    $items = Get-RawDescendants -Root $window
    $item = Find-Control -Elements $items -Key $originalMode
    if ($null -ne $item) {
        $item.GetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    }
    else {
        $expand.Collapse()
    }
    Start-Sleep -Milliseconds 900
    $report.bustModeProbe['restoredMode'] = $originalMode
}

$outputFile = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
$outputDirectory = Split-Path -Parent $outputFile
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}
[System.IO.File]::WriteAllText(
    $outputFile,
    (($report | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
    [System.Text.UTF8Encoding]::new($false))
Write-Output "Follow-up written to $outputFile"
