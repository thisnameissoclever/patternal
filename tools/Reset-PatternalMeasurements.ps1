<#
.SYNOPSIS
    Put every detailed body measurement back to the value the application
    declares as its default.

.DESCRIPTION
    The measurement inspector has 145 numeric controls and no command that
    returns them to their defaults. Anything that probes them therefore leaves
    the profile altered, and the application persists that profile, so the
    change survives a restart. A person who explores the controls is in the
    same position.

    This reads the declared defaults out of
    `artifacts/preview-coverage/preview-dimension-coverage.json`, produced by
    `tools/audit_preview_dimension_coverage.py`, and drives each control back
    through the interface the way a person would: focus, set, then commit with
    Enter. It reports what it changed and what it could not reach, and verifies
    each value afterwards rather than assuming the write landed.

    This changes the running application's measurements, which is its purpose.
    It touches nothing else.
#>
[CmdletBinding()]
param(
    [string]$CoveragePath = 'artifacts/preview-coverage/preview-dimension-coverage.json',
    [string]$OutputPath = 'artifacts/preview-coverage/measurement-reset.json',
    [double]$ToleranceCm = 0.01
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

$walker = [System.Windows.Automation.TreeWalker]::RawViewWalker

function Get-PatternalWindow {
    $live = @(Get-Process -Name 'Patternal' -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 })
    if ($live.Count -eq 0) { throw 'No running Patternal window was found.' }
    $handles = $live | ForEach-Object { [int]$_.MainWindowHandle }
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, 'Patternal')
    $windows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Children, $condition)
    foreach ($window in $windows) {
        if ($handles -contains $window.Current.NativeWindowHandle) { return $window }
    }
    throw 'No live Patternal window matched a running process.'
}

function Get-AllControls {
    param($Root)
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
    param($All, [string]$Key)
    foreach ($element in $All) {
        try {
            if ($element.Current.AutomationId -eq $Key -or
                $element.Current.Name -eq $Key) { return $element }
        }
        catch { }
    }
    return $null
}

function Resolve-ValueElement {
    param($Element)
    if ($null -eq $Element) { return $null }
    try {
        $Element.GetCurrentPattern(
            [System.Windows.Automation.ValuePattern]::Pattern) | Out-Null
        return $Element
    }
    catch {
        $condition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Edit)
        return $Element.FindFirst(
            [System.Windows.Automation.TreeScope]::Descendants, $condition)
    }
}

$coverageFile = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $CoveragePath))
if (-not (Test-Path -LiteralPath $coverageFile)) {
    throw "Run tools/audit_preview_dimension_coverage.py first: $coverageFile is missing."
}
$dimensions = (Get-Content -LiteralPath $coverageFile -Raw | ConvertFrom-Json).dimensions
Write-Output "declared measurements: $($dimensions.Count)"

$window = Get-PatternalWindow
$tab = Find-Control (Get-AllControls $window) 'Workspace3DTab'
if ($null -ne $tab) {
    $tab.GetCurrentPattern(
        [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    Start-Sleep -Seconds 5
}

# A collapsed group exposes none of its controls to automation.
$expanded = 0
for ($pass = 0; $pass -lt 3; $pass++) {
    $opened = $false
    foreach ($element in (Get-AllControls (Get-PatternalWindow))) {
        try {
            $pattern = $element.GetCurrentPattern(
                [System.Windows.Automation.ExpandCollapsePattern]::Pattern)
            if ($pattern.Current.ExpandCollapseState.ToString() -eq 'Collapsed' -and
                $element.Current.ControlType.ProgrammaticName -notmatch 'ComboBox') {
                $pattern.Expand(); $expanded++; $opened = $true
                Start-Sleep -Milliseconds 200
            }
        }
        catch { }
    }
    if (-not $opened) { break }
}
Write-Output "measurement groups opened: $expanded"

$rows = @()
foreach ($dimension in $dimensions) {
    $all = Get-AllControls (Get-PatternalWindow)
    $element = Find-Control $all $dimension.automationName
    if ($null -eq $element) {
        $rows += [ordered]@{
            key = $dimension.key; automationName = $dimension.automationName
            found = $false; restored = $false
        }
        continue
    }
    $edit = Resolve-ValueElement $element
    if ($null -eq $edit) {
        $rows += [ordered]@{
            key = $dimension.key; automationName = $dimension.automationName
            found = $true; restored = $false
        }
        continue
    }

    $pattern = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $before = $pattern.Current.Value
    $wasDefault = ($before -as [double]) -ne $null -and
        [Math]::Abs([double]$before - $dimension.default) -lt $ToleranceCm
    if ($wasDefault) {
        $rows += [ordered]@{
            key = $dimension.key; automationName = $dimension.automationName
            found = $true; alreadyDefault = $true; restored = $true
            valueBefore = $before; valueAfter = $before
        }
        continue
    }

    $edit.SetFocus(); Start-Sleep -Milliseconds 120
    $pattern.SetValue([string]$dimension.default); Start-Sleep -Milliseconds 120
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    Start-Sleep -Milliseconds 900

    $after = $null
    $verify = Resolve-ValueElement (Find-Control (Get-AllControls (Get-PatternalWindow)) $dimension.automationName)
    if ($null -ne $verify) {
        $after = $verify.GetCurrentPattern(
            [System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    }
    $restored = ($after -as [double]) -ne $null -and
        [Math]::Abs([double]$after - $dimension.default) -lt $ToleranceCm

    $rows += [ordered]@{
        key = $dimension.key; automationName = $dimension.automationName
        found = $true; alreadyDefault = $false; restored = [bool]$restored
        valueBefore = $before; valueAfter = $after; declaredDefault = $dimension.default
    }
    Write-Output ("  {0,-46} {1} -> {2}  restored:{3}" -f `
        $dimension.automationName.Substring(0, [Math]::Min(46, $dimension.automationName.Length)),
        $before, $after, $restored)
}

$changed = @($rows | Where-Object { $_.found -and -not $_.alreadyDefault })
$failed = @($rows | Where-Object { $_.found -and -not $_.restored } | ForEach-Object { $_.key })
$absent = @($rows | Where-Object { -not $_.found } | ForEach-Object { $_.key })

$report = [ordered]@{
    schemaVersion = 'patterna.measurement-reset/1.0'
    claims        = [ordered]@{ accepted = $false }
    note          = 'Restores declared defaults through the interface and verifies each write. It does not reset garment ease, construction, or fabric controls.'
    resetAtUtc    = [DateTimeOffset]::UtcNow.ToString('O')
    measurements  = $rows
    summary       = [ordered]@{
        declared         = $dimensions.Count
        found            = @($rows | Where-Object { $_.found }).Count
        alreadyAtDefault = @($rows | Where-Object { $_.found -and $_.alreadyDefault }).Count
        changed          = $changed.Count
        notRestored      = $failed
        notFound         = $absent
    }
}

$outputFile = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
$directory = Split-Path -Parent $outputFile
if (-not (Test-Path -LiteralPath $directory)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
[System.IO.File]::WriteAllText(
    $outputFile,
    (($report | ConvertTo-Json -Depth 6) + [Environment]::NewLine),
    [System.Text.UTF8Encoding]::new($false))

Write-Output ""
Write-Output "Measurement reset written to $outputFile"
$report.summary | ConvertTo-Json -Depth 4
