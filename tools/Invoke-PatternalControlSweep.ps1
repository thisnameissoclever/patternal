<#
.SYNOPSIS
    Exercise every slider, numeric box, toggle, and list in the running
    Patternal window and record what each one actually did.

.DESCRIPTION
    A control that does nothing looks exactly like a control that works until
    someone moves it and watches. This sweep attaches to a running Patternal
    window, drives each control through its own UI Automation pattern rather
    than screen coordinates, and records the readouts before and after every
    change so that "the control responded" is backed by an observable effect
    somewhere else in the application.

    Every control is restored to the value it held before the sweep, and the
    report says whether the restore took.

    This is a live interaction check. It proves that controls accept input and
    that dependent readouts follow them. It does not judge whether the values
    are correct, it does not look at the rendered result, and it accepts
    nothing.
#>
[CmdletBinding()]
param(
    [string]$OutputPath = 'artifacts/control-sweep/control-sweep.json',
    [int]$SettleMilliseconds = 500,
    [int]$SlowSettleMilliseconds = 1200
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

# ---- Attaching to the window ----------------------------------------------

function Get-PatternalWindow {
    # A window element for an exited process lingers in the automation tree
    # with its subtree frozen, so bind to a process that is actually running.
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
    throw 'No running Patternal window was found. Start the app before sweeping.'
}

function Get-RawDescendants {
    <#
        A TreeScope.Descendants search over this window stops well short of the
        full tree, so walk the raw view and cache every element once.
    #>
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

# ---- Reading and driving controls ------------------------------------------

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
        # A WinUI NumberBox surfaces its value on an inner edit control.
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
    # A NumberBox commits on Enter or on losing focus, so setting the text
    # alone leaves the application's value untouched. Mirror what a user does.
    $Element.SetFocus()
    Start-Sleep -Milliseconds 120
    $Element.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern).SetValue([string]$Value)
    Start-Sleep -Milliseconds 120
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
}

function Get-RangeValue {
    param([Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Element)
    return $Element.GetCurrentPattern(
        [System.Windows.Automation.RangeValuePattern]::Pattern).Current
}

function Set-RangeValue {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory)][double]$Value
    )
    $Element.GetCurrentPattern(
        [System.Windows.Automation.RangeValuePattern]::Pattern).SetValue($Value)
}

function Expand-Element {
    param([System.Windows.Automation.AutomationElement]$Element)
    if ($null -eq $Element) { return $false }
    try {
        $pattern = $Element.GetCurrentPattern(
            [System.Windows.Automation.ExpandCollapsePattern]::Pattern)
        if ($pattern.Current.ExpandCollapseState.ToString() -ne 'Expanded') {
            $pattern.Expand()
            Start-Sleep -Milliseconds 400
        }
        return $true
    }
    catch { return $false }
}

# ---- Observable readouts ---------------------------------------------------

$readoutKeys = @(
    'GarmentEaseResultText',
    'ShirtConstructionResultText',
    'BustShapingResultText',
    'DrapeStaleSimulationState',
    'DrapeAvatarPreviewState',
    'HeightValueText', 'ChestValueText', 'WaistValueText',
    'HipValueText', 'ShoulderValueText', 'TorsoValueText',
    'FabricWeightValueText', 'FabricStretchValueText',
    'PatternPieceCountText', 'PatternZoomText', 'CanvasScaleText'
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
    foreach ($key in $readoutKeys) {
        if ($Before[$key] -ne $After[$key]) { $changed += $key }
    }
    return $changed
}

# ---- The inventory under test ----------------------------------------------

$sliders = @(
    @{ Key = 'HeightSlider';         Probe = 178 },
    @{ Key = 'ChestSlider';          Probe = 98 },
    @{ Key = 'WaistSlider';          Probe = 70 },
    @{ Key = 'HipSlider';            Probe = 96 },
    @{ Key = 'ShoulderSlider';       Probe = 42 },
    @{ Key = 'TorsoSlider';          Probe = 50 },
    @{ Key = 'FabricWeightSlider';   Probe = 300 },
    @{ Key = 'FabricStretchSlider';  Probe = 10 }
)

$numberBoxes = @(
    @{ Key = 'ChestEaseNumberBox';            Probe = 18; Expander = $null },
    @{ Key = 'WaistEaseNumberBox';            Probe = 18; Expander = $null },
    @{ Key = 'HipEaseNumberBox';              Probe = 20; Expander = $null },
    @{ Key = 'UpperArmEaseNumberBox';         Probe = 12; Expander = $null },
    @{ Key = 'ArmscyeEaseNumberBox';          Probe = 6;  Expander = $null },
    @{ Key = 'FrontWidthShareNumberBox';      Probe = 58; Expander = 'Shirt construction draft' },
    @{ Key = 'NecklineWidthNumberBox';        Probe = 20; Expander = 'Shirt construction draft' },
    @{ Key = 'FrontNeckDepthNumberBox';       Probe = 14; Expander = 'Shirt construction draft' },
    @{ Key = 'BackNeckDepthNumberBox';        Probe = 7;  Expander = 'Shirt construction draft' },
    @{ Key = 'ShoulderLengthNumberBox';       Probe = 15; Expander = 'Shirt construction draft' },
    @{ Key = 'ShoulderDropNumberBox';         Probe = 4;  Expander = 'Shirt construction draft' },
    @{ Key = 'ArmscyeDepthNumberBox';         Probe = 23; Expander = 'Shirt construction draft' },
    @{ Key = 'SleeveCapHeightNumberBox';      Probe = 19; Expander = 'Shirt construction draft' },
    @{ Key = 'FrontBalanceNumberBox';         Probe = 3;  Expander = 'Shirt construction draft' },
    @{ Key = 'ArmscyeScoopNumberBox';         Probe = 6;  Expander = 'Shirt construction draft' },
    @{ Key = 'UnderarmExtensionNumberBox';    Probe = 1.5; Expander = 'Shirt construction draft' },
    @{ Key = 'LeftDartIntakeNumberBox';       Probe = 3;  Expander = 'Bust shaping draft' },
    @{ Key = 'RightDartIntakeNumberBox';      Probe = 3;  Expander = 'Bust shaping draft' },
    @{ Key = 'BustPointSeparationNumberBox';  Probe = 24; Expander = 'Bust shaping draft' },
    @{ Key = 'DartTipOffsetNumberBox';        Probe = 4;  Expander = 'Bust shaping draft' },
    @{ Key = 'LeftBustHeightNumberBox';       Probe = 30; Expander = 'Bust shaping draft' },
    @{ Key = 'RightBustHeightNumberBox';      Probe = 30; Expander = 'Bust shaping draft' },
    @{ Key = 'LeftBustProjectionNumberBox';   Probe = 8;  Expander = 'Bust shaping draft' },
    @{ Key = 'RightBustProjectionNumberBox';  Probe = 8;  Expander = 'Bust shaping draft' },
    @{ Key = 'DartMouthDropNumberBox';        Probe = 8;  Expander = 'Bust shaping draft' },
    @{ Key = 'ShoulderDartMouthOffsetNumberBox'; Probe = 8; Expander = 'Bust shaping draft' },
    @{ Key = 'ShoulderDartShareNumberBox';    Probe = 60; Expander = 'Bust shaping draft' },
    @{ Key = 'BendNumberBox';                 Probe = 40; Expander = 'Advanced material physics' },
    @{ Key = 'FrictionNumberBox';             Probe = 0.8; Expander = 'Advanced material physics' }
)

$toggles = @(
    @{ Key = 'SeamAllowanceToggle';   ExpectedEnabled = $true },
    @{ Key = 'GrainlinesToggle';      ExpectedEnabled = $true },
    @{ Key = 'PiecesToggleButton';    ExpectedEnabled = $true },
    @{ Key = 'InspectorToggleButton'; ExpectedEnabled = $true },
    @{ Key = 'EditPatternPointsButton'; ExpectedEnabled = $true },
    @{ Key = 'EditAssemblyButton';    ExpectedEnabled = $true },
    @{ Key = 'LinkProportionsToggle'; ExpectedEnabled = $true },
    @{ Key = 'SolvedDrapeToggle';     ExpectedEnabled = $true; Slow = $true },
    @{ Key = 'ShowBraToggle';         ExpectedEnabled = $false },
    @{ Key = 'ReverseSeamSideBToggle'; ExpectedEnabled = $false },
    @{ Key = 'ClosureStateToggle';    ExpectedEnabled = $false }
)

# ---- The sweep -------------------------------------------------------------

$window = Get-PatternalWindow
$bounds = $window.Current.BoundingRectangle
$report = [ordered]@{
    schemaVersion = 'patterna.control-sweep/1.0'
    scope         = 'live-control-response-and-readout-effect'
    claims        = [ordered]@{
        packagedVisualQualityAccepted = $false
        uxAccepted                    = $false
        valuesVerifiedCorrect         = $false
    }
    notes         = @(
        'A responding control is not a correct control. This records that input is accepted and that dependent readouts follow, nothing more.',
        'Controls disabled by an unmet precondition are reported as such, not as failures.'
    )
    sweptAtUtc    = [DateTimeOffset]::UtcNow.ToString('O')
    window        = [ordered]@{
        width  = [int]$bounds.Width
        height = [int]$bounds.Height
        wideEnoughForAllPanels = ($bounds.Width -ge 1320)
    }
    sliders       = @()
    numberBoxes   = @()
    toggles       = @()
    summary       = [ordered]@{}
}

if (-not $report.window.wideEnoughForAllPanels) {
    $report.notes += "The window is $([int]$bounds.Width) px wide; below 1320 px the application hides whole panels, so some controls may be absent by design."
}

$elements = Get-RawDescendants -Root $window
Write-Output "Automation tree: $($elements.Count) elements"

# Open the collapsed sections that hold the construction and physics boxes.
foreach ($name in @('Shirt construction draft', 'Bust shaping draft', 'Advanced material physics')) {
    $expander = Find-Control -Elements $elements -Key $name
    if (Expand-Element -Element $expander) {
        Write-Output "Expanded: $name"
    }
    else {
        Write-Output "Could not expand: $name"
    }
}
$elements = Get-RawDescendants -Root $window

# ---- Sliders ----
foreach ($slider in $sliders) {
    $element = Find-Control -Elements $elements -Key $slider.Key
    if ($null -eq $element) {
        $report.sliders += [ordered]@{ id = $slider.Key; found = $false }
        continue
    }
    $range = Get-RangeValue -Element $element
    $original = [double]$range.Value
    $before = Get-ReadoutSnapshot -Elements $elements
    Set-RangeValue -Element $element -Value ([double]$slider.Probe)
    Start-Sleep -Milliseconds $SettleMilliseconds
    $after = Get-ReadoutSnapshot -Elements $elements
    $accepted = [double](Get-RangeValue -Element $element).Value
    Set-RangeValue -Element $element -Value $original
    Start-Sleep -Milliseconds $SettleMilliseconds
    $restored = [double](Get-RangeValue -Element $element).Value
    $report.sliders += [ordered]@{
        id             = $slider.Key
        found          = $true
        enabled        = $element.Current.IsEnabled
        minimum        = [double]$range.Minimum
        maximum        = [double]$range.Maximum
        originalValue  = $original
        probeValue     = [double]$slider.Probe
        acceptedValue  = $accepted
        movedToProbe   = ([Math]::Abs($accepted - [double]$slider.Probe) -lt 0.51)
        readoutsChanged = @(Compare-Readouts -Before $before -After $after)
        restoredValue  = $restored
        restored       = ([Math]::Abs($restored - $original) -lt 0.01)
    }
    Write-Output ("slider {0,-24} {1} -> {2} ({3} readouts moved)" -f `
        $slider.Key, $original, $accepted, $report.sliders[-1].readoutsChanged.Count)
}

# ---- Numeric boxes ----
foreach ($box in $numberBoxes) {
    $element = Find-Control -Elements $elements -Key $box.Key
    if ($null -eq $element) {
        $report.numberBoxes += [ordered]@{ id = $box.Key; found = $false; expander = $box.Expander }
        continue
    }
    $valueElement = Resolve-ValueElement -Element $element
    if ($null -eq $valueElement) {
        $report.numberBoxes += [ordered]@{
            id = $box.Key; found = $true; valuePatternAvailable = $false }
        continue
    }
    $original = Get-TextValue -Element $valueElement
    $before = Get-ReadoutSnapshot -Elements $elements
    Set-NumberBoxValue -Element $valueElement -Value ([double]$box.Probe)
    Start-Sleep -Milliseconds $SettleMilliseconds
    $accepted = Get-TextValue -Element $valueElement
    $after = Get-ReadoutSnapshot -Elements $elements
    Set-NumberBoxValue -Element $valueElement -Value ([double]$original)
    Start-Sleep -Milliseconds $SettleMilliseconds
    $restored = Get-TextValue -Element $valueElement
    $report.numberBoxes += [ordered]@{
        id              = $box.Key
        found           = $true
        expander        = $box.Expander
        enabled         = $element.Current.IsEnabled
        originalValue   = $original
        probeValue      = [double]$box.Probe
        acceptedValue   = $accepted
        movedToProbe    = ([double]$accepted -eq [double]$box.Probe)
        readoutsChanged = @(Compare-Readouts -Before $before -After $after)
        restoredValue   = $restored
        restored        = ([double]$restored -eq [double]$original)
    }
    Write-Output ("box    {0,-30} {1} -> {2} ({3} readouts moved)" -f `
        $box.Key, $original, $accepted, $report.numberBoxes[-1].readoutsChanged.Count)
}

# ---- Toggles ----
foreach ($toggle in $toggles) {
    $element = Find-Control -Elements $elements -Key $toggle.Key
    if ($null -eq $element) {
        $report.toggles += [ordered]@{ id = $toggle.Key; found = $false }
        continue
    }
    $enabled = $element.Current.IsEnabled
    $entry = [ordered]@{
        id                     = $toggle.Key
        found                  = $true
        enabled                = $enabled
        expectedEnabled        = $toggle.ExpectedEnabled
        enabledMatchesExpected = ($enabled -eq $toggle.ExpectedEnabled)
    }
    if (-not $enabled) {
        $entry.note = 'Disabled by an unmet precondition; not exercised.'
        $report.toggles += $entry
        Write-Output ("toggle {0,-24} disabled (expected {1})" -f $toggle.Key, $toggle.ExpectedEnabled)
        continue
    }
    $pattern = $element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
    $settle = if ($toggle.ContainsKey('Slow')) { $SlowSettleMilliseconds } else { $SettleMilliseconds }
    $before = Get-ReadoutSnapshot -Elements $elements
    $stateBefore = $pattern.Current.ToggleState.ToString()
    $pattern.Toggle()
    Start-Sleep -Milliseconds $settle
    $stateAfter = $pattern.Current.ToggleState.ToString()
    $after = Get-ReadoutSnapshot -Elements $elements
    $entry.stateBefore = $stateBefore
    $entry.stateAfterToggle = $stateAfter
    $entry.respondedToToggle = ($stateAfter -ne $stateBefore)
    $entry.readoutsChanged = @(Compare-Readouts -Before $before -After $after)
    if ($entry.respondedToToggle) {
        $pattern.Toggle()
        Start-Sleep -Milliseconds $settle
    }
    $entry.stateRestored = $pattern.Current.ToggleState.ToString()
    $entry.restored = ($entry.stateRestored -eq $stateBefore)
    $report.toggles += $entry
    Write-Output ("toggle {0,-24} {1} -> {2} ({3} readouts moved)" -f `
        $toggle.Key, $stateBefore, $stateAfter, $entry.readoutsChanged.Count)
}

# ---- Summary ----
$slidersFound = @($report.sliders | Where-Object { $_.found })
$boxesFound = @($report.numberBoxes | Where-Object { $_.found })
$togglesEnabled = @($report.toggles | Where-Object { $_.found -and $_.enabled })
$report.summary = [ordered]@{
    slidersDeclared        = $sliders.Count
    slidersFound           = $slidersFound.Count
    slidersMovedToProbe    = @($slidersFound | Where-Object { $_.movedToProbe }).Count
    slidersWithNoEffect    = @($slidersFound | Where-Object { $_.readoutsChanged.Count -eq 0 } |
                               ForEach-Object { $_.id })
    slidersNotRestored     = @($slidersFound | Where-Object { -not $_.restored } | ForEach-Object { $_.id })
    numberBoxesDeclared    = $numberBoxes.Count
    numberBoxesFound       = $boxesFound.Count
    numberBoxesMovedToProbe = @($boxesFound | Where-Object { $_.movedToProbe }).Count
    numberBoxesWithNoEffect = @($boxesFound | Where-Object { $_.readoutsChanged.Count -eq 0 } |
                               ForEach-Object { $_.id })
    numberBoxesNotRestored = @($boxesFound | Where-Object { -not $_.restored } | ForEach-Object { $_.id })
    togglesDeclared        = $toggles.Count
    togglesFound           = @($report.toggles | Where-Object { $_.found }).Count
    togglesEnabled         = $togglesEnabled.Count
    togglesResponded       = @($togglesEnabled | Where-Object { $_.respondedToToggle }).Count
    togglesWithUnexpectedEnabledState = @($report.toggles |
        Where-Object { $_.found -and -not $_.enabledMatchesExpected } | ForEach-Object { $_.id })
    missingControls        = @(
        ($report.sliders + $report.numberBoxes + $report.toggles) |
            Where-Object { -not $_.found } | ForEach-Object { $_.id })
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
Write-Output "Control sweep written to $outputFile"
$report.summary | ConvertTo-Json -Depth 6
