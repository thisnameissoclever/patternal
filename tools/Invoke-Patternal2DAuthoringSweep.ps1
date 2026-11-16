<#
.SYNOPSIS
    Exercise the 2D pattern authoring workspace and record what each control
    actually does to the drawn pattern.

.DESCRIPTION
    The control sweep covers the measurement and construction inputs, and the
    workspace sweep covers the 3D camera. Neither touches the 2D side: the
    piece list, the drawing overlays, the point inspector and the edit history
    are the surface a user spends most of their time in, and nothing was
    checking that they respond.

    This selects the 2D workspace, then for each control captures the pattern
    canvas, operates the control, and captures again. A toggle that redraws the
    canvas is doing something; one that leaves every pixel identical is
    reported. Selecting each piece in turn is checked the same way, because a
    piece list that does not change the drawing is a list of labels.

    The canvas is captured on its own rather than the whole window, so a change
    means the pattern changed rather than some panel's text.

    Every toggle is returned to the state it was found in, and the piece
    selection is restored. This records behaviour and accepts nothing.
#>
[CmdletBinding()]
param(
    [string]$OutputPath = 'artifacts/authoring-2d/authoring-2d-sweep.json',
    [string]$ImageDirectory = 'artifacts/authoring-2d',
    [int]$SettleSeconds = 3
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing

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

function Save-Canvas {
    param([string]$Path)
    $all = Get-AllControls (Get-PatternalWindow)
    $canvas = Find-Control $all 'PatternScrollViewer'
    if ($null -eq $canvas) { throw 'The 2D pattern canvas was not found.' }
    $rectangle = $canvas.Current.BoundingRectangle
    $width = [int]$rectangle.Width
    $height = [int]$rectangle.Height
    if ($width -lt 1 -or $height -lt 1) { throw 'The 2D pattern canvas has no area on screen.' }
    $full = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
    $directory = Split-Path -Parent $full
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CopyFromScreen(
                [int]$rectangle.X, [int]$rectangle.Y, 0, 0,
                (New-Object System.Drawing.Size($width, $height)))
        }
        finally { $graphics.Dispose() }
        $bitmap.Save($full, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally { $bitmap.Dispose() }
    return (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
}

$window = Get-PatternalWindow
$tab = Find-Control (Get-AllControls $window) 'Workspace2DTab'
if ($null -eq $tab) { throw 'The 2D workspace tab was not found.' }
$tab.GetCurrentPattern(
    [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
Start-Sleep -Seconds $SettleSeconds

$imageFull = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $ImageDirectory))
if (-not (Test-Path -LiteralPath $imageFull)) {
    New-Item -ItemType Directory -Path $imageFull -Force | Out-Null
}

# Overlay toggles: each one draws something onto the pattern, so operating it
# has to change the drawing.
$toggleRows = @()
foreach ($id in @('SeamAllowanceToggle', 'GrainlinesToggle')) {
    $element = Find-Control (Get-AllControls (Get-PatternalWindow)) $id
    if ($null -eq $element) {
        $toggleRows += [ordered]@{ id = $id; found = $false }
        Write-Output ("{0,-24} MISSING" -f $id)
        continue
    }
    $pattern = $element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
    $original = $pattern.Current.ToggleState.ToString()
    $before = Save-Canvas (Join-Path $ImageDirectory "$id-before.png")
    $pattern.Toggle()
    Start-Sleep -Seconds $SettleSeconds
    $after = Save-Canvas (Join-Path $ImageDirectory "$id-after.png")
    $element = Find-Control (Get-AllControls (Get-PatternalWindow)) $id
    $nowPattern = $element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
    $switched = $nowPattern.Current.ToggleState.ToString()
    $nowPattern.Toggle()
    Start-Sleep -Seconds $SettleSeconds
    $element = Find-Control (Get-AllControls (Get-PatternalWindow)) $id
    $restored = $element.GetCurrentPattern(
        [System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState.ToString()
    $toggleRows += [ordered]@{
        id = $id; found = $true; enabled = $element.Current.IsEnabled
        originalState = $original; switchedState = $switched
        stateChanged = ($original -ne $switched)
        canvasChanged = ($before -ne $after)
        restored = ($restored -eq $original)
    }
    Write-Output ("{0,-24} {1} -> {2}   canvas changed: {3}   restored: {4}" -f `
        $id, $original, $switched, ($before -ne $after), ($restored -eq $original))
}

# The piece list: selecting a piece has to change what is drawn, or it is a
# list of labels.
$pieceRows = @()
$list = Find-Control (Get-AllControls (Get-PatternalWindow)) 'PatternPiecesList'
$originalPiece = $null
if ($null -ne $list) {
    $selection = $list.GetCurrentPattern([System.Windows.Automation.SelectionPattern]::Pattern)
    $items = @($list.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition))
    $current = @($selection.Current.GetSelection())
    if ($current.Count -gt 0) { $originalPiece = $current[0].Current.Name }
    Write-Output "pattern pieces listed: $($items.Count)"
    foreach ($item in $items) {
        $name = $item.Current.Name
        $before = Save-Canvas (Join-Path $ImageDirectory "piece-before.png")
        $item.GetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        Start-Sleep -Seconds $SettleSeconds
        $after = Save-Canvas (Join-Path $ImageDirectory ("piece-" + ($name -replace '[^A-Za-z0-9]', '_') + ".png"))
        # Selecting the piece that is already selected is not expected to
        # redraw anything, so it must not be reported as a piece that failed to.
        $wasSelected = ($name -eq $originalPiece)
        $pieceRows += [ordered]@{
            name = $name; alreadySelected = $wasSelected
            canvasChanged = ($before -ne $after)
        }
        Write-Output ("  piece {0,-34} canvas changed: {1}{2}" -f `
            $name, ($before -ne $after), $(if ($wasSelected) { "   (already selected)" } else { "" }))
    }
    if ($null -ne $originalPiece) {
        $restore = $items | Where-Object { $_.Current.Name -eq $originalPiece } | Select-Object -First 1
        if ($null -ne $restore) {
            $restore.GetCurrentPattern(
                [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
            Start-Sleep -Seconds $SettleSeconds
        }
    }
}

# Authoring commands: record whether each is present and whether the interface
# offers it, without invoking the ones that change the pattern.
$commandRows = @()
foreach ($id in @(
        'EditPatternPointsButton', 'UndoPatternEditButton', 'RedoPatternEditButton',
        'DrawPolygonPieceButton', 'AddInternalPathButton', 'AddDartButton',
        'EditPatternPiecePropertiesButton', 'ExportPatternButton',
        'ResetPatternPointButton', 'SplitPatternSegmentButton',
        'ConvertPatternSegmentToCurveButton', 'ConvertPatternSegmentToLineButton',
        'AddPatternNotchButton', 'MarkSewingEdgeButton', 'CompleteSewingEdgeButton')) {
    $element = Find-Control (Get-AllControls (Get-PatternalWindow)) $id
    $commandRows += [ordered]@{
        id = $id
        found = ($null -ne $element)
        enabled = if ($null -ne $element) { [bool]$element.Current.IsEnabled } else { $false }
    }
}
$missingCommands = @($commandRows | Where-Object { -not $_.found } | ForEach-Object { $_.id })
Write-Output ""
Write-Output ("authoring commands present: {0}/{1}" -f `
    @($commandRows | Where-Object { $_.found }).Count, $commandRows.Count)

# The point inspector and its commands only exist once point editing is on, so
# a sweep that never turns it on reports them missing and learns nothing.
$editModeRows = @()
$pointCommands = @(
    'ResetPatternPointButton', 'SplitPatternSegmentButton',
    'ConvertPatternSegmentToCurveButton', 'ConvertPatternSegmentToLineButton',
    'AddPatternNotchButton', 'MarkSewingEdgeButton', 'CompleteSewingEdgeButton',
    'SelectedPatternPointXNumberBox', 'SelectedPatternPointYNumberBox',
    'SelectedPatternSegmentLengthNumberBox', 'SelectedPatternSegmentAngleNumberBox')
$editButton = Find-Control (Get-AllControls (Get-PatternalWindow)) 'EditPatternPointsButton'
$editModeEntered = $false
if ($null -ne $editButton) {
    $beforeEdit = Save-Canvas (Join-Path $ImageDirectory 'edit-mode-before.png')
    try {
        $editButton.GetCurrentPattern(
            [System.Windows.Automation.TogglePattern]::Pattern).Toggle()
        $editModeEntered = $true
    }
    catch {
        try {
            $editButton.GetCurrentPattern(
                [System.Windows.Automation.InvokePattern]::Pattern).Invoke()
            $editModeEntered = $true
        }
        catch { }
    }
    Start-Sleep -Seconds $SettleSeconds
    $afterEdit = Save-Canvas (Join-Path $ImageDirectory 'edit-mode-after.png')
    Write-Output ""
    Write-Output ("point editing engaged: {0}   canvas changed: {1}" -f `
        $editModeEntered, ($beforeEdit -ne $afterEdit))
    foreach ($id in $pointCommands) {
        $element = Find-Control (Get-AllControls (Get-PatternalWindow)) $id
        $editModeRows += [ordered]@{
            id = $id
            found = ($null -ne $element)
            enabled = if ($null -ne $element) { [bool]$element.Current.IsEnabled } else { $false }
        }
        Write-Output ("  {0,-40} present: {1}" -f $id, ($null -ne $element))
    }
    if ($editModeEntered) {
        $editButton = Find-Control (Get-AllControls (Get-PatternalWindow)) 'EditPatternPointsButton'
        try {
            $editButton.GetCurrentPattern(
                [System.Windows.Automation.TogglePattern]::Pattern).Toggle()
        }
        catch {
            try {
                $editButton.GetCurrentPattern(
                    [System.Windows.Automation.InvokePattern]::Pattern).Invoke()
            }
            catch { }
        }
        Start-Sleep -Seconds $SettleSeconds
    }
}

$silentToggles = @($toggleRows |
    Where-Object { $_.found -and -not $_.canvasChanged } | ForEach-Object { $_.id })
$silentPieces = @($pieceRows |
    Where-Object { -not $_.canvasChanged -and -not $_.alreadySelected } |
    ForEach-Object { $_.name })

$report = [ordered]@{
    schemaVersion = 'patterna.authoring-2d-sweep/1.0'
    claims        = [ordered]@{ accepted = $false }
    note          = 'A changed canvas proves the control redrew the pattern. It says nothing about whether the new drawing is correct.'
    probedAtUtc   = [DateTimeOffset]::UtcNow.ToString('O')
    overlayToggles = $toggleRows
    pieces        = $pieceRows
    commands      = $commandRows
    pointEditing  = [ordered]@{ engaged = $editModeEntered; controls = $editModeRows }
    summary       = [ordered]@{
        togglesProbed          = @($toggleRows | Where-Object { $_.found }).Count
        togglesThatRedrew      = @($toggleRows | Where-Object { $_.found -and $_.canvasChanged }).Count
        togglesNotRestored     = @($toggleRows | Where-Object { $_.found -and -not $_.restored } | ForEach-Object { $_.id })
        togglesWithNoRedraw    = $silentToggles
        piecesProbed           = $pieceRows.Count
        piecesThatRedrew       = @($pieceRows | Where-Object { $_.canvasChanged }).Count
        pieceAlreadySelected   = @($pieceRows | Where-Object { $_.alreadySelected } | ForEach-Object { $_.name })
        piecesWithNoRedraw     = $silentPieces
        commandsPresent        = @($commandRows | Where-Object { $_.found }).Count
        commandsMissing        = $missingCommands
        pointEditingEngaged    = $editModeEntered
        pointControlsPresent   = @($editModeRows | Where-Object { $_.found }).Count
        pointControlsDeclared  = $editModeRows.Count
        pointControlsMissing   = @($editModeRows | Where-Object { -not $_.found } | ForEach-Object { $_.id })
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
Write-Output "2D authoring sweep written to $outputFile"
$report.summary | ConvertTo-Json -Depth 4
