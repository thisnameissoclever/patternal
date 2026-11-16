<#
.SYNOPSIS
    Exercise the running Patternal window's toggles and numeric controls through
    UI Automation and record what each one actually did.

.DESCRIPTION
    This is a local interaction check, not the isolated packaged UI gate. It
    attaches to an already-running Patternal window, drives real controls
    through their UI Automation patterns rather than screen coordinates, and
    writes a JSON report of every before-and-after state it observed. It proves
    that controls respond and that readouts follow them; it does not prove
    packaged visual quality, and it accepts nothing.

    Every control is restored to its original value before the script exits.
#>
[CmdletBinding()]
param(
    [string]$OutputPath = 'artifacts/local-ui-check/local-ui-check.json',
    [int]$SettleMilliseconds = 900
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

function Get-PatternalWindow {
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $condition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty, 'Patternal')
        $window = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
            [System.Windows.Automation.TreeScope]::Children, $condition)
        if ($null -ne $window) {
            return $window
        }
        Start-Sleep -Milliseconds 500
    }
    throw 'No running Patternal window was found. Start the app before running this check.'
}

function Find-ByAutomationId {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)][string]$AutomationId
    )
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, $AutomationId)
    return $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Find-ByName {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)][string]$Name
    )
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, $Name)
    return $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Resolve-ValueElement {
    param([System.Windows.Automation.AutomationElement]$Element)
    if ($null -eq $Element) { return $null }
    try {
        $Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern) | Out-Null
        return $Element
    }
    catch {
        # A WinUI NumberBox surfaces its value on an inner edit control.
        $editCondition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Edit)
        $edit = $Element.FindFirst(
            [System.Windows.Automation.TreeScope]::Descendants, $editCondition)
        return $edit
    }
}

function Get-TextValue {
    param([System.Windows.Automation.AutomationElement]$Element)
    if ($null -eq $Element) { return $null }
    try {
        $value = $Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        return $value.Current.Value
    }
    catch {
        return $Element.Current.Name
    }
}

function Set-NumericValue {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory)][double]$Value
    )
    # A WinUI NumberBox commits on Enter or lost focus, so setting the text
    # alone leaves the app's value unchanged. This mirrors what a user does:
    # focus the field, replace the text, and press Enter.
    $Element.SetFocus()
    Start-Sleep -Milliseconds 150
    $pattern = $Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $pattern.SetValue([string]$Value)
    Start-Sleep -Milliseconds 150
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
}

function Get-ToggleState {
    param([System.Windows.Automation.AutomationElement]$Element)
    if ($null -eq $Element) { return $null }
    $toggle = $Element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
    return $toggle.Current.ToggleState.ToString()
}

function Invoke-Toggle {
    param([System.Windows.Automation.AutomationElement]$Element)
    $toggle = $Element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
    $toggle.Toggle()
}

$window = Get-PatternalWindow
$report = [ordered]@{
    schemaVersion = 'patterna.local-ui-check/1.0'
    scope         = 'live-control-response-only'
    claims        = [ordered]@{ packagedVisualQualityAccepted = $false; uxAccepted = $false }
    checkedAtUtc  = [DateTimeOffset]::UtcNow.ToString('O')
    window        = [ordered]@{
        name = $window.Current.Name
        bounds = $window.Current.BoundingRectangle.ToString()
    }
    numericChecks = @()
    toggleChecks  = @()
    notes         = @()
}

$readout = Find-ByAutomationId -Root $window -AutomationId 'GarmentEaseResultText'
if ($null -eq $readout) {
    $report.notes += 'GarmentEaseResultText was not found; numeric readout comparisons were skipped.'
}

# ---- Numeric ease controls -------------------------------------------------
$easeControls = @(
    @{ Id = 'ChestEaseNumberBox'; Probe = 20.0 },
    @{ Id = 'WaistEaseNumberBox'; Probe = 20.0 },
    @{ Id = 'HipEaseNumberBox';   Probe = 20.0 }
)
foreach ($control in $easeControls) {
    $element = Find-ByAutomationId -Root $window -AutomationId $control.Id
    if ($null -eq $element) {
        $report.numericChecks += [ordered]@{ id = $control.Id; found = $false }
        continue
    }
    $valueElement = Resolve-ValueElement -Element $element
    if ($null -eq $valueElement) {
        $report.numericChecks += [ordered]@{ id = $control.Id; found = $true; valuePatternAvailable = $false }
        continue
    }
    $originalValue = Get-TextValue -Element $valueElement
    $beforeReadout = Get-TextValue -Element $readout
    Set-NumericValue -Element $valueElement -Value $control.Probe
    Start-Sleep -Milliseconds $SettleMilliseconds
    $afterValue = Get-TextValue -Element $valueElement
    $afterReadout = Get-TextValue -Element $readout
    # Restore exactly what the user had.
    Set-NumericValue -Element $valueElement -Value ([double]$originalValue)
    Start-Sleep -Milliseconds $SettleMilliseconds
    $restoredReadout = Get-TextValue -Element $readout
    $report.numericChecks += [ordered]@{
        id              = $control.Id
        found           = $true
        originalValue   = $originalValue
        probeValue      = $control.Probe
        acceptedValue   = $afterValue
        readoutBefore   = $beforeReadout
        readoutAfter    = $afterReadout
        readoutRestored = $restoredReadout
        readoutChanged  = ($beforeReadout -ne $afterReadout)
        readoutReverted = ($beforeReadout -eq $restoredReadout)
    }
}

# ---- Toggle controls -------------------------------------------------------
$toggleIds = @(
    'SeamAllowanceToggle',
    'GrainlinesToggle',
    'LinkProportionsToggle',
    'ShowBraToggle'
)
foreach ($toggleId in $toggleIds) {
    $element = Find-ByAutomationId -Root $window -AutomationId $toggleId
    if ($null -eq $element) {
        $report.toggleChecks += [ordered]@{ id = $toggleId; found = $false }
        continue
    }
    $enabled = $element.Current.IsEnabled
    $before = Get-ToggleState -Element $element
    $changed = $false
    $after = $before
    if ($enabled) {
        Invoke-Toggle -Element $element
        Start-Sleep -Milliseconds $SettleMilliseconds
        $after = Get-ToggleState -Element $element
        $changed = ($after -ne $before)
        if ($changed) {
            Invoke-Toggle -Element $element
            Start-Sleep -Milliseconds $SettleMilliseconds
        }
    }
    $report.toggleChecks += [ordered]@{
        id             = $toggleId
        found          = $true
        enabled        = $enabled
        stateBefore    = $before
        stateAfterToggle = $after
        respondedToToggle = $changed
        stateRestored  = (Get-ToggleState -Element $element)
    }
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
Write-Output "Local UI check written to $outputFile"
$report | ConvertTo-Json -Depth 8
