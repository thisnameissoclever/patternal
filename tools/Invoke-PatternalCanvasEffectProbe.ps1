<#
.SYNOPSIS
    Decide whether a numeric control changes the drafted pattern by watching
    the 2D canvas rather than the text readouts.

.DESCRIPTION
    The control sweep found six numeric boxes that accept a value and move no
    readout. That is not proof they do nothing: the panels that summarise each
    section report only a few of their own values, so a control can redraft the
    pattern without any text changing. The canvas cannot hide it.

    This probe puts the 2D workspace on screen, captures the pattern canvas,
    changes one control, captures again, and compares the two images. A control
    that redraws the pattern is working and merely lacks feedback. A control
    that leaves the canvas identical in every mode has nothing to show for
    itself and needs a closer look at the code.

    It restores every value it changes and accepts nothing.
#>
[CmdletBinding()]
param(
    [string]$OutputPath = 'artifacts/control-sweep/canvas-effect-probe.json',
    [string]$ImageDirectory = 'artifacts/control-sweep/canvas',
    [int]$SettleMilliseconds = 900
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

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

function Resolve-ValueElement {
    param([System.Windows.Automation.AutomationElement]$Element)
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

function Get-TextValue {
    param([System.Windows.Automation.AutomationElement]$Element)
    try {
        return $Element.GetCurrentPattern(
            [System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    }
    catch { return $Element.Current.Name }
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

function Get-CanvasFingerprint {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Window,
        [Parameter(Mandatory)][string]$Path
    )
    # Redrafting replaces the canvas element, so the handle from before a change
    # is stale by the time the change lands. Look it up again every capture.
    $canvas = Find-Control -Elements (Get-RawDescendants -Root $Window) `
        -Key 'Interactive two dimensional pattern layout'
    if ($null -eq $canvas) { throw 'The pattern canvas disappeared between captures.' }
    $rectangle = $canvas.Current.BoundingRectangle
    $width = [int][Math]::Floor($rectangle.Width)
    $height = [int][Math]::Floor($rectangle.Height)
    if ($width -lt 1 -or $height -lt 1) { throw 'The pattern canvas has no area to capture.' }
    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CopyFromScreen(
                [int][Math]::Floor($rectangle.X), [int][Math]::Floor($rectangle.Y), 0, 0,
                (New-Object System.Drawing.Size($width, $height)))
        }
        finally { $graphics.Dispose() }
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally { $bitmap.Dispose() }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$probes = @(
    @{ Key = 'BackNeckDepthNumberBox';           Probe = 12 },
    @{ Key = 'SleeveCapHeightNumberBox';         Probe = 24 },
    @{ Key = 'LeftBustProjectionNumberBox';      Probe = 16 },
    @{ Key = 'RightBustProjectionNumberBox';     Probe = 16 },
    @{ Key = 'ShoulderDartMouthOffsetNumberBox'; Probe = 11 },
    @{ Key = 'ShoulderDartShareNumberBox';       Probe = 90 },
    # A control already known to move a readout, as a control for the method.
    @{ Key = 'NecklineWidthNumberBox';           Probe = 26 }
)

$window = Get-PatternalWindow
$elements = Get-RawDescendants -Root $window

# The canvas only exists while the 2D workspace is selected.
$flatTab = Find-Control -Elements $elements -Key 'Workspace2DTab'
if ($null -eq $flatTab) { $flatTab = Find-Control -Elements $elements -Key '2D FLAT' }
if ($null -ne $flatTab) {
    $flatTab.GetCurrentPattern(
        [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    Start-Sleep -Milliseconds 1500
    $elements = Get-RawDescendants -Root $window
}

$canvas = Find-Control -Elements $elements -Key 'Interactive two dimensional pattern layout'
if ($null -eq $canvas) { throw 'The pattern canvas was not found.' }

foreach ($name in @('Shirt construction draft', 'Bust shaping draft')) {
    $expander = Find-Control -Elements $elements -Key $name
    if ($null -ne $expander) {
        try {
            $pattern = $expander.GetCurrentPattern(
                [System.Windows.Automation.ExpandCollapsePattern]::Pattern)
            if ($pattern.Current.ExpandCollapseState.ToString() -ne 'Expanded') {
                $pattern.Expand()
                Start-Sleep -Milliseconds 400
            }
        }
        catch { }
    }
}
$elements = Get-RawDescendants -Root $window

$imageFull = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $ImageDirectory))
if (-not (Test-Path -LiteralPath $imageFull)) {
    New-Item -ItemType Directory -Path $imageFull -Force | Out-Null
}

$report = [ordered]@{
    schemaVersion = 'patterna.canvas-effect-probe/1.0'
    claims        = [ordered]@{ uxAccepted = $false; valuesVerifiedCorrect = $false }
    note          = 'A changed canvas proves the control redrafts the pattern. It does not prove the new pattern is correct.'
    probedAtUtc   = [DateTimeOffset]::UtcNow.ToString('O')
    canvasBounds  = $canvas.Current.BoundingRectangle.ToString()
    probes        = @()
}

foreach ($probe in $probes) {
    $element = Find-Control -Elements $elements -Key $probe.Key
    if ($null -eq $element) {
        $report.probes += [ordered]@{ id = $probe.Key; found = $false }
        continue
    }
    $valueElement = Resolve-ValueElement -Element $element
    $original = Get-TextValue -Element $valueElement
    $beforePath = Join-Path $imageFull ("{0}-before.png" -f $probe.Key)
    $afterPath = Join-Path $imageFull ("{0}-after.png" -f $probe.Key)
    $before = Get-CanvasFingerprint -Window $window -Path $beforePath
    Set-NumberBoxValue -Element $valueElement -Value ([double]$probe.Probe)
    Start-Sleep -Milliseconds $SettleMilliseconds
    $accepted = Get-TextValue -Element $valueElement
    $after = Get-CanvasFingerprint -Window $window -Path $afterPath
    Set-NumberBoxValue -Element $valueElement -Value ([double]$original)
    Start-Sleep -Milliseconds $SettleMilliseconds
    $restored = Get-TextValue -Element $valueElement
    $entry = [ordered]@{
        id             = $probe.Key
        found          = $true
        originalValue  = $original
        probeValue     = [double]$probe.Probe
        acceptedValue  = $accepted
        canvasBefore   = $before
        canvasAfter    = $after
        canvasChanged  = ($before -ne $after)
        restoredValue  = $restored
        restored       = ([double]$restored -eq [double]$original)
    }
    $report.probes += $entry
    Write-Output ("{0,-34} canvas changed: {1}" -f $probe.Key, $entry.canvasChanged)
}

$report.summary = [ordered]@{
    probed              = @($report.probes | Where-Object { $_.found }).Count
    redraftedThePattern = @($report.probes | Where-Object { $_.found -and $_.canvasChanged } |
                            ForEach-Object { $_.id })
    noVisibleEffect     = @($report.probes | Where-Object { $_.found -and -not $_.canvasChanged } |
                            ForEach-Object { $_.id })
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
Write-Output "Canvas effect probe written to $outputFile"
$report.summary | ConvertTo-Json -Depth 5
