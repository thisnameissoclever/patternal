<#
.SYNOPSIS
    Exercise the controls the main sweep cannot reach: the 3D camera buttons and
    the seam toggles hidden behind the assembly overlay.

.DESCRIPTION
    The control sweep covers the sliders, numeric boxes, and toggles that are
    present as soon as the window opens. Two groups are not: the 3D camera
    buttons exist only while the drape tab is selected, and the two seam toggles
    exist only after the assembly overlay is opened and a relationship is
    selected in it. Controls nobody can reach are controls nobody has tested.

    A camera button is checked by looking rather than by clicking. Each one is
    invoked and the viewport is captured, so a button that is wired to nothing
    is caught by producing the same image as the view before it, which no
    amount of successful clicking would reveal.

    Every control is left as it was found. This records behaviour and accepts
    nothing.
#>
[CmdletBinding()]
param(
    [string]$OutputPath = 'artifacts/control-sweep/workspace-sweep.json',
    [string]$ImageDirectory = 'artifacts/control-sweep/camera',
    [int]$SettleMilliseconds = 1500
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
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

function Wait-ForControl {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Window,
        [Parameter(Mandatory)][string]$Key,
        [int]$TimeoutSeconds = 40
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $found = Find-Control -Elements (Get-RawDescendants -Root $Window) -Key $Key
        if ($null -ne $found) { return $found }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Invoke-Element {
    param([Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Element)
    $Element.GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}

function Get-ViewportFingerprint {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Window,
        [Parameter(Mandatory)][string]$Path
    )
    $viewport = Find-Control -Elements (Get-RawDescendants -Root $Window) `
        -Key 'Internal browser cloth diagnostic'
    if ($null -eq $viewport) { throw 'The 3D viewport was not found.' }
    $rectangle = $viewport.Current.BoundingRectangle
    $width = [int][Math]::Floor($rectangle.Width)
    $height = [int][Math]::Floor($rectangle.Height)
    if ($width -lt 1 -or $height -lt 1) { throw 'The viewport has no area.' }
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

$cameraButtons = @(
    'DrapeFrontCameraButton',
    'DrapeRightCameraButton',
    'DrapeRearCameraButton',
    'DrapeLeftCameraButton',
    'DrapeObliqueCameraButton',
    'DrapeRearObliqueCameraButton',
    'DrapeFitCameraButton'
)

$window = Get-PatternalWindow
$imageFull = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $ImageDirectory))
if (-not (Test-Path -LiteralPath $imageFull)) {
    New-Item -ItemType Directory -Path $imageFull -Force | Out-Null
}

$report = [ordered]@{
    schemaVersion = 'patterna.workspace-sweep/1.0'
    scope         = 'controls the main sweep cannot reach'
    claims        = [ordered]@{ uxAccepted = $false; visualQualityAccepted = $false }
    sweptAtUtc    = [DateTimeOffset]::UtcNow.ToString('O')
    cameraButtons = @()
    assemblyToggles = @()
    notes         = @()
}

# ---- 3D camera buttons -----------------------------------------------------

$elements = Get-RawDescendants -Root $window
$drapeTab = Find-Control -Elements $elements -Key 'Workspace3DTab'
if ($null -eq $drapeTab) { $drapeTab = Find-Control -Elements $elements -Key '3D DRAPE' }
if ($null -eq $drapeTab) {
    $report.notes += 'The 3D tab was not found, so the camera buttons were not swept.'
}
else {
    $drapeTab.GetCurrentPattern(
        [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    Start-Sleep -Milliseconds 2500

    $solved = Wait-ForControl -Window $window -Key 'SolvedDrapeToggle'
    if ($null -ne $solved) {
        $pattern = $solved.GetCurrentPattern(
            [System.Windows.Automation.TogglePattern]::Pattern)
        $originalSolved = $pattern.Current.ToggleState.ToString()
        if ($originalSolved -ne 'On') {
            $pattern.Toggle()
            Start-Sleep -Seconds 8
        }
    }
    else {
        $report.notes += 'The solved-cloth toggle did not appear; cameras were swept on whatever the viewport showed.'
        $originalSolved = $null
    }

    $previous = $null
    $previousName = $null
    foreach ($button in $cameraButtons) {
        $element = Find-Control -Elements (Get-RawDescendants -Root $window) -Key $button
        if ($null -eq $element) {
            $report.cameraButtons += [ordered]@{ id = $button; found = $false }
            Write-Output ("camera {0,-32} MISSING" -f $button)
            continue
        }
        Invoke-Element -Element $element
        Start-Sleep -Milliseconds $SettleMilliseconds
        $path = Join-Path $imageFull ("{0}.png" -f $button)
        $fingerprint = Get-ViewportFingerprint -Window $window -Path $path
        $entry = [ordered]@{
            id            = $button
            found         = $true
            enabled       = $element.Current.IsEnabled
            image         = (Split-Path -Leaf $path)
            sha256        = $fingerprint
            differsFromPrevious = ($null -eq $previous) -or ($fingerprint -ne $previous)
            previousButton = $previousName
        }
        $report.cameraButtons += $entry
        Write-Output ("camera {0,-32} changed the view: {1}" -f $button, $entry.differsFromPrevious)
        $previous = $fingerprint
        $previousName = $button
    }

    if ($null -ne $solved -and $null -ne $originalSolved) {
        $pattern = $solved.GetCurrentPattern(
            [System.Windows.Automation.TogglePattern]::Pattern)
        while ($pattern.Current.ToggleState.ToString() -ne $originalSolved) {
            $pattern.Toggle()
            Start-Sleep -Milliseconds 800
        }
    }
}

# ---- Assembly overlay seam toggles -----------------------------------------

$elements = Get-RawDescendants -Root $window
$flatTab = Find-Control -Elements $elements -Key 'Workspace2DTab'
if ($null -eq $flatTab) { $flatTab = Find-Control -Elements $elements -Key '2D FLAT' }
if ($null -ne $flatTab) {
    $flatTab.GetCurrentPattern(
        [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    Start-Sleep -Milliseconds 1500
}

$assembly = Find-Control -Elements (Get-RawDescendants -Root $window) -Key 'EditAssemblyButton'
if ($null -eq $assembly) {
    $report.notes += 'The assembly command was not found.'
}
else {
    $assemblyPattern = $assembly.GetCurrentPattern(
        [System.Windows.Automation.TogglePattern]::Pattern)
    $originalAssembly = $assemblyPattern.Current.ToggleState.ToString()
    if ($originalAssembly -ne 'On') {
        $assemblyPattern.Toggle()
        Start-Sleep -Milliseconds 1500
    }

    # Each seam toggle applies to one kind of relationship: one to a permanent
    # seam, the other to a temporary closure. Selecting only the first entry
    # leaves whichever kind it is not permanently untested, so each toggle gets
    # its own search for a relationship that brings it to life.
    $combo = Find-Control -Elements (Get-RawDescendants -Root $window) `
        -Key 'Selected seam or garment closure'
    $relationshipCount = 0
    if ($null -eq $combo) {
        $report.notes += 'The assembly relationship selector was not found.'
    }
    else {
        $expand = $combo.GetCurrentPattern(
            [System.Windows.Automation.ExpandCollapsePattern]::Pattern)
        $expand.Expand()
        Start-Sleep -Milliseconds 800
        $relationshipCount = @($combo.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::ListItem)))).Count
        $expand.Collapse()
        Start-Sleep -Milliseconds 400
        $report.notes += "The assembly selector offered $relationshipCount relationships."
    }

    function Select-Relationship {
        param([int]$Index)
        $box = Find-Control -Elements (Get-RawDescendants -Root $window) `
            -Key 'Selected seam or garment closure'
        if ($null -eq $box) { return $false }
        $pattern = $box.GetCurrentPattern(
            [System.Windows.Automation.ExpandCollapsePattern]::Pattern)
        $pattern.Expand()
        Start-Sleep -Milliseconds 500
        $entries = @($box.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::ListItem))))
        if ($Index -ge $entries.Count) { $pattern.Collapse(); return $false }
        $entries[$Index].GetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        Start-Sleep -Milliseconds 900
        return $true
    }

    foreach ($key in @('Reverse selected seam side B sewing direction',
                       'Close selected temporary garment closure')) {
        $element = $null
        $selectedIndex = -1
        for ($index = 0; $index -lt [Math]::Max(1, $relationshipCount); $index++) {
            if (-not (Select-Relationship -Index $index)) { break }
            $candidate = Find-Control -Elements (Get-RawDescendants -Root $window) -Key $key
            if ($null -ne $candidate -and $candidate.Current.IsEnabled) {
                $element = $candidate
                $selectedIndex = $index
                break
            }
            if ($null -ne $candidate) { $element = $candidate }
        }
        if ($null -eq $element) {
            # A control the document cannot support is correctly absent. Read the
            # overlay's own summary so an inapplicable control is not reported as
            # a missing one.
            $summaryElement = Find-Control -Elements (Get-RawDescendants -Root $window) `
                -Key 'AssemblySummaryText'
            $summary = if ($null -ne $summaryElement) { $summaryElement.Current.Name } else { $null }
            $inapplicable = ($key -match 'closure') -and ($summary -match '\b0 closures\b')
            $report.assemblyToggles += [ordered]@{
                id             = $key
                found          = $false
                inapplicable   = $inapplicable
                overlaySummary = $summary
                note           = if ($inapplicable) {
                    'Absent by design: this garment declares no closures.'
                } else {
                    'Not present, and the overlay does not explain why.'
                }
            }
            Write-Output ("assembly {0,-52} absent (inapplicable={1})" -f $key, $inapplicable)
            continue
        }
        $entry = [ordered]@{
            id = $key
            found = $true
            enabled = $element.Current.IsEnabled
            enabledByRelationshipIndex = $selectedIndex
            relationshipsTried = [Math]::Max(1, $relationshipCount)
        }
        if ($element.Current.IsEnabled) {
            $pattern = $element.GetCurrentPattern(
                [System.Windows.Automation.TogglePattern]::Pattern)
            $before = $pattern.Current.ToggleState.ToString()
            $pattern.Toggle()
            Start-Sleep -Milliseconds 900
            $after = $pattern.Current.ToggleState.ToString()
            $entry.stateBefore = $before
            $entry.stateAfterToggle = $after
            $entry.respondedToToggle = ($after -ne $before)
            if ($entry.respondedToToggle) {
                $pattern.Toggle()
                Start-Sleep -Milliseconds 900
            }
            $entry.restored = ($pattern.Current.ToggleState.ToString() -eq $before)
        }
        else {
            $entry.note = 'Present but disabled against every relationship the overlay offered.'
        }
        $report.assemblyToggles += $entry
        Write-Output ("assembly {0,-52} enabled={1}" -f $key, $entry.enabled)
    }

    if ($assemblyPattern.Current.ToggleState.ToString() -ne $originalAssembly) {
        $assemblyPattern.Toggle()
        Start-Sleep -Milliseconds 1000
    }
}

$report.summary = [ordered]@{
    cameraButtonsDeclared = $cameraButtons.Count
    cameraButtonsFound    = @($report.cameraButtons | Where-Object { $_.found }).Count
    cameraButtonsThatChangedTheView = @(
        $report.cameraButtons | Where-Object { $_.found -and $_.differsFromPrevious }).Count
    cameraButtonsWithNoVisibleEffect = @(
        $report.cameraButtons | Where-Object { $_.found -and -not $_.differsFromPrevious } |
            ForEach-Object { $_.id })
    assemblyTogglesFound   = @($report.assemblyToggles | Where-Object { $_.found }).Count
    assemblyTogglesEnabled = @($report.assemblyToggles | Where-Object { $_.found -and $_.enabled }).Count
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
Write-Output "Workspace sweep written to $outputFile"
$report.summary | ConvertTo-Json -Depth 5
