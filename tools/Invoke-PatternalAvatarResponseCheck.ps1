<#
.SYNOPSIS
    Check that moving a body measurement changes what the 3D viewport draws,
    not just the number beside it.

.DESCRIPTION
    The control sweep proves a slider accepts a value and that dependent text
    follows it. Neither shows whether anything on screen changed. A control
    that updates its readout while the render stands still is the exact shape
    of a customisation feature that looks complete and is not, and no amount of
    reading the user interface tree reveals it.

    This moves each control, captures the viewport before and after, and
    compares the images, recording the preview mode the application declared at
    the time.

    What a changed image proves is bounded, and the bound matters. The viewport
    draws the body and the garment together, and a body measurement re-drafts
    the pattern, so the garment alone can account for every changed pixel. The
    viewport exposes a `setGarmentVisible` entry point that nothing in the
    application calls, so the garment cannot be hidden through the interface
    and the two cannot be separated here. Read a changed image as "the control
    reached the renderer" and nothing more. For which dimensions the body
    itself can represent, read `tools/audit_preview_dimension_coverage.py`,
    which answers that from the declarations instead of from pixels.

    Every value is restored. This records behaviour and accepts nothing.
#>
[CmdletBinding()]
param(
    [string]$OutputPath = 'artifacts/avatar-response/avatar-response.json',
    [string]$ImageDirectory = 'artifacts/avatar-response',
    [int]$SettleSeconds = 4,
    [switch]$IncludeDetailedMeasurements,
    [int]$MeasurementLimit = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
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

function Find-Control {
    param($Root, [string]$Key)
    $pending = [System.Collections.Generic.Queue[object]]::new()
    $pending.Enqueue(@{ Element = $Root; Depth = 0 })
    while ($pending.Count -gt 0) {
        $entry = $pending.Dequeue()
        try {
            if ($entry.Element.Current.AutomationId -eq $Key -or
                $entry.Element.Current.Name -eq $Key) { return $entry.Element }
        }
        catch { continue }
        if ($entry.Depth -ge 40) { continue }
        try { $child = $walker.GetFirstChild($entry.Element) } catch { continue }
        while ($null -ne $child) {
            $pending.Enqueue(@{ Element = $child; Depth = $entry.Depth + 1 })
            try { $child = $walker.GetNextSibling($child) } catch { break }
        }
    }
    return $null
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

# A measurement box exposes its value on an inner edit element in some themes
# and on itself in others.
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

# The viewport draws its own status panel and legend along the bottom edge, and
# that panel's text names the current preview mode. Capturing it made every
# probe look like a change, because switching to the unsupported message
# rewrites those pixels. Excluding the strip removes that false signal. It does
# not isolate the body: the garment is still drawn, and the description above
# explains why that cannot be separated here.
$OverlayHeightPixels = 160

function Save-Viewport {
    param($Root, [string]$Path)
    $viewport = Find-Control $Root 'Internal browser cloth diagnostic'
    if ($null -eq $viewport) { throw 'The 3D viewport was not found.' }
    $rectangle = $viewport.Current.BoundingRectangle
    $width = [int]$rectangle.Width
    $height = [int]$rectangle.Height - $OverlayHeightPixels
    if ($height -lt 1) { throw 'The 3D viewport is too short to capture above its status panel.' }
    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CopyFromScreen(
                [int]$rectangle.X, [int]$rectangle.Y, 0, 0,
                (New-Object System.Drawing.Size($width, $height)))
        }
        finally { $graphics.Dispose() }
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally { $bitmap.Dispose() }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

# Probes are large enough that a body honouring them cannot look unchanged.
$sliders = @(
    @{ Id = 'ChestSlider';    Probe = 124 },
    @{ Id = 'WaistSlider';    Probe = 96 },
    @{ Id = 'HipSlider';      Probe = 122 },
    @{ Id = 'ShoulderSlider'; Probe = 48 },
    @{ Id = 'TorsoSlider';    Probe = 55 },
    @{ Id = 'HeightSlider';   Probe = 190 }
)

$window = Get-PatternalWindow
$tab = Find-Control $window 'Workspace3DTab'
if ($null -eq $tab) { $tab = Find-Control $window '3D DRAPE' }
if ($null -ne $tab) {
    $tab.GetCurrentPattern(
        [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    Start-Sleep -Seconds 6
}

$imageFull = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $ImageDirectory))
if (-not (Test-Path -LiteralPath $imageFull)) {
    New-Item -ItemType Directory -Path $imageFull -Force | Out-Null
}

$rows = @()
foreach ($slider in $sliders) {
    $window = Get-PatternalWindow
    $element = Find-Control $window $slider.Id
    if ($null -eq $element) {
        $rows += [ordered]@{ id = $slider.Id; found = $false; viewportChanged = $false }
        Write-Output ("{0,-16} MISSING" -f $slider.Id)
        continue
    }
    $range = $element.GetCurrentPattern([System.Windows.Automation.RangeValuePattern]::Pattern)
    $original = [double]$range.Current.Value
    $before = Save-Viewport $window (Join-Path $imageFull ("{0}-before.png" -f $slider.Id))
    $range.SetValue([double]$slider.Probe)
    Start-Sleep -Seconds $SettleSeconds

    $window = Get-PatternalWindow
    $after = Save-Viewport $window (Join-Path $imageFull ("{0}-after.png" -f $slider.Id))
    $state = Find-Control $window 'DrapeAvatarPreviewState'
    $stateText = if ($null -ne $state) { $state.Current.Name } else { $null }

    $element = Find-Control $window $slider.Id
    $element.GetCurrentPattern(
        [System.Windows.Automation.RangeValuePattern]::Pattern).SetValue($original)
    Start-Sleep -Seconds 3

    $rows += [ordered]@{
        id            = $slider.Id
        found         = $true
        originalValue = $original
        probeValue    = $slider.Probe
        viewportChanged = ($before -ne $after)
        previewState  = $stateText
        beforeSha256  = $before
        afterSha256   = $after
    }
    Write-Output ("{0,-16} {1} -> {2}   viewport changed: {3}" -f `
        $slider.Id, $original, $slider.Probe, ($before -ne $after))
}

# The six sliders above are the headline controls. The measurement inspector
# holds 151 more, and a body model that cannot represent one of them is not
# visible from the slider set alone.
$measurementRows = @()
if ($IncludeDetailedMeasurements) {
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

    $names = @(Get-AllControls (Get-PatternalWindow) |
        Where-Object {
            try { $_.Current.ControlType.ProgrammaticName -match 'Spinner' } catch { $false }
        } |
        ForEach-Object { $_.Current.Name } |
        Where-Object { $_ } |
        Sort-Object -Unique)
    if ($MeasurementLimit -gt 0 -and $names.Count -gt $MeasurementLimit) {
        $names = @($names | Select-Object -First $MeasurementLimit)
    }
    Write-Output "measurement controls to probe: $($names.Count)"

    foreach ($name in $names) {
        $window = Get-PatternalWindow
        $element = Find-Control $window $name
        if ($null -eq $element) { continue }
        $edit = Resolve-ValueElement $element
        if ($null -eq $edit) { continue }
        $value = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $original = $value.Current.Value
        if (-not ($original -as [double])) { continue }
        $probe = [double]$original + 6

        $safe = ($name -replace '[^A-Za-z0-9]', '_')
        $before = Save-Viewport $window (Join-Path $imageFull "$safe-before.png")
        $edit.SetFocus(); Start-Sleep -Milliseconds 150
        $value.SetValue([string]$probe); Start-Sleep -Milliseconds 150
        [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
        Start-Sleep -Seconds $SettleSeconds

        $window = Get-PatternalWindow
        $after = Save-Viewport $window (Join-Path $imageFull "$safe-after.png")
        $state = Find-Control $window 'DrapeAvatarPreviewState'
        $stateText = if ($null -ne $state) { $state.Current.Name } else { $null }

        $accepted = $null
        $restore = Resolve-ValueElement (Find-Control $window $name)
        if ($null -ne $restore) {
            $restorePattern = $restore.GetCurrentPattern(
                [System.Windows.Automation.ValuePattern]::Pattern)
            $accepted = $restorePattern.Current.Value
            $restore.SetFocus(); Start-Sleep -Milliseconds 150
            $restorePattern.SetValue([string]$original); Start-Sleep -Milliseconds 150
            [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
            Start-Sleep -Seconds 2
        }

        $tookTheValue = ($accepted -as [double]) -and
            ([Math]::Abs([double]$accepted - $probe) -lt 0.01)
        $measurementRows += [ordered]@{
            name             = $name
            originalValue    = $original
            probeValue       = $probe
            acceptedValue    = $accepted
            valueWasAccepted = [bool]$tookTheValue
            viewportChanged    = ($before -ne $after)
            previewState     = $stateText
            beforeSha256     = $before
            afterSha256      = $after
        }
        Write-Output ("  {0,-46} accepted:{1,-6} changed the viewport:{2}" -f `
            $name.Substring(0, [Math]::Min(46, $name.Length)), $tookTheValue, ($before -ne $after))
    }
}

$silent = @($rows | Where-Object { $_.found -and -not $_.viewportChanged } | ForEach-Object { $_.id })
$acceptedButStill = @($measurementRows |
    Where-Object { $_.valueWasAccepted -and -not $_.viewportChanged } |
    ForEach-Object { $_.name })
$report = [ordered]@{
    schemaVersion = 'patterna.avatar-response/1.1'
    claims        = [ordered]@{ accepted = $false; realismAccepted = $false }
    note          = 'A changed image proves the control reached the renderer. The viewport draws the body and the garment together and the garment cannot be hidden through the interface, so this does not prove the body moved, nor that any new shape is correct.'
    probedAtUtc   = [DateTimeOffset]::UtcNow.ToString('O')
    overlayHeightPixelsExcluded = $OverlayHeightPixels
    sliders       = $rows
    measurements  = $measurementRows
    summary       = [ordered]@{
        probed                     = @($rows | Where-Object { $_.found }).Count
        changedTheViewport             = @($rows | Where-Object { $_.found -and $_.viewportChanged }).Count
        changedNumberButNotTheViewport = $silent
        measurementsProbed         = $measurementRows.Count
        measurementsThatChangedTheViewport = @($measurementRows | Where-Object { $_.viewportChanged }).Count
        acceptedButViewportUnchanged   = $acceptedButStill
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
Write-Output "Avatar response written to $outputFile"
$report.summary | ConvertTo-Json -Depth 5
