<#
.SYNOPSIS
    Capture the running Patternal window's 3D viewport from every fixed camera
    angle, with the packaged cloth solve shown and hidden.

.DESCRIPTION
    The application's own three-dimensional view is the thing a user judges the
    result by, so it has to be looked at from more than one side. This script
    attaches to an already-running Patternal window, drives the tab and the
    camera buttons through UI Automation rather than screen coordinates, and
    saves one image per angle for both viewport states.

    It reads the viewport's own bounding rectangle from UI Automation and
    captures exactly that region, so the images contain the rendered cloth and
    not the surrounding desktop.

    This produces evidence for a human to review. It renders no verdict, and it
    is not the isolated packaged gate, which runs in a separate Windows guest.
#>
[CmdletBinding()]
param(
    [string]$OutputDirectory = 'artifacts/packaged-drape-views-v1',
    [int]$SettleMilliseconds = 1800,
    [int]$LoadTimeoutSeconds = 40
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing

function Get-PatternalWindow {
    # A window element for an exited process can linger in the automation tree,
    # and its subtree is frozen at whatever it held when the process died. Bind
    # to the main window of a process that is actually running, so a restarted
    # app is never confused with the corpse of the one before it.
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
                if ($handles -contains $window.Current.NativeWindowHandle) {
                    return $window
                }
            }
        }
        Start-Sleep -Milliseconds 500
    }
    throw 'No running Patternal window was found. Start the app before capturing.'
}

function Wait-ForAutomationId {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)][string]$AutomationId,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )
    # The 3D controls appear only once the viewport's asynchronous asset refresh
    # finishes, which is slower than the tab switch that starts it.
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $element = Find-ByAutomationId -Root $Root -AutomationId $AutomationId
        if ($null -ne $element) { return $element }
        Start-Sleep -Milliseconds 500
    }
    throw "The control '$AutomationId' did not appear within $TimeoutSeconds seconds."
}

function Find-Descendant {
    <#
        A TreeScope.Descendants search over this window returns fewer than a
        hundred elements and never reaches the overlay controls that sit beside
        the WebView2 inside the drape grid, while a raw tree walk over the same
        window reaches all of them. Walk the raw tree so a control that is
        plainly on screen is never reported as missing.
    #>
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Root,
        [string]$AutomationId,
        [string]$Name,
        [int]$MaximumDepth = 40
    )
    $walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
    $pending = [System.Collections.Generic.Queue[object]]::new()
    $pending.Enqueue(@{ Element = $Root; Depth = 0 })
    while ($pending.Count -gt 0) {
        $entry = $pending.Dequeue()
        $element = $entry.Element
        try {
            if ($AutomationId -and $element.Current.AutomationId -eq $AutomationId) {
                return $element
            }
            if ($Name -and $element.Current.Name -eq $Name) {
                return $element
            }
        }
        catch {
            # An element can vanish between enumeration and inspection.
            continue
        }
        if ($entry.Depth -ge $MaximumDepth) { continue }
        try { $child = $walker.GetFirstChild($element) } catch { continue }
        while ($null -ne $child) {
            $pending.Enqueue(@{ Element = $child; Depth = $entry.Depth + 1 })
            try { $child = $walker.GetNextSibling($child) } catch { break }
        }
    }
    return $null
}

function Find-ByAutomationId {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)][string]$AutomationId
    )
    return Find-Descendant -Root $Root -AutomationId $AutomationId
}

function Find-ByName {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)][string]$Name
    )
    return Find-Descendant -Root $Root -Name $Name
}

function Invoke-Element {
    param([Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Element)
    $Element.GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}

function Get-ToggleState {
    param([Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Element)
    return $Element.GetCurrentPattern(
        [System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState.ToString()
}

function Set-ToggleState {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory)][ValidateSet('On', 'Off')][string]$State
    )
    $pattern = $Element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
    $deadline = (Get-Date).AddSeconds(10)
    while ($pattern.Current.ToggleState.ToString() -ne $State -and (Get-Date) -lt $deadline) {
        $pattern.Toggle()
        Start-Sleep -Milliseconds 400
    }
    return $pattern.Current.ToggleState.ToString()
}

function Save-ElementImage {
    param(
        [Parameter(Mandatory)][System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory)][string]$Path
    )
    $rectangle = $Element.Current.BoundingRectangle
    if ($rectangle.Width -lt 1 -or $rectangle.Height -lt 1) {
        throw 'The viewport reported an empty rectangle, so there is nothing to capture.'
    }
    $width = [int][Math]::Floor($rectangle.Width)
    $height = [int][Math]::Floor($rectangle.Height)
    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CopyFromScreen(
                [int][Math]::Floor($rectangle.X),
                [int][Math]::Floor($rectangle.Y),
                0, 0,
                (New-Object System.Drawing.Size($width, $height)))
        }
        finally { $graphics.Dispose() }
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally { $bitmap.Dispose() }
    return [ordered]@{
        path   = (Split-Path -Leaf $Path)
        width  = $width
        height = $height
        bytes  = (Get-Item -LiteralPath $Path).Length
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

# The six semantic views the acceptance contract requires, in its order.
$cameraViews = @(
    @{ Name = 'front';         Button = 'DrapeFrontCameraButton' },
    @{ Name = 'front-oblique'; Button = 'DrapeObliqueCameraButton' },
    @{ Name = 'left';          Button = 'DrapeLeftCameraButton' },
    @{ Name = 'back';          Button = 'DrapeRearCameraButton' },
    @{ Name = 'back-oblique';  Button = 'DrapeRearObliqueCameraButton' },
    @{ Name = 'right';         Button = 'DrapeRightCameraButton' }
)
$requiredViews = $cameraViews | ForEach-Object { $_.Name }

$window = Get-PatternalWindow

# The camera buttons only exist once the three-dimensional tab is realised.
# The tab is found by its automation id: a text label in the same window also
# carries the name "3D DRAPE", and a label cannot be selected.
$drapeTab = Wait-ForAutomationId -Root $window -AutomationId 'Workspace3DTab' -TimeoutSeconds 10
if ($null -eq $drapeTab) { $drapeTab = Find-ByName -Root $window -Name '3D DRAPE' }
if ($null -eq $drapeTab) { throw 'The 3D DRAPE tab was not found.' }
$drapeTab.GetCurrentPattern(
    [System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
Start-Sleep -Milliseconds 2500

$viewport = Find-ByName -Root $window -Name 'Internal browser cloth diagnostic'
if ($null -eq $viewport) { throw 'The 3D viewport element was not found.' }
$toggle = Wait-ForAutomationId -Root $window `
    -AutomationId 'SolvedDrapeToggle' -TimeoutSeconds $LoadTimeoutSeconds

$outputFull = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDirectory))
if (-not (Test-Path -LiteralPath $outputFull)) {
    New-Item -ItemType Directory -Path $outputFull -Force | Out-Null
}

$originalToggleState = Get-ToggleState -Element $toggle
$report = [ordered]@{
    schemaVersion = 'patterna.packaged-drape-view-capture/1.0'
    scope         = 'packaged-application-multi-angle-evidence'
    claims        = [ordered]@{
        packagedVisualQualityAccepted = $false
        isolatedGuestGateRan          = $false
    }
    notes         = @(
        'These images come from the packaged application running on this desktop.',
        'The isolated packaged gate runs in a separate Windows guest and did not run here.',
        'No image in this set has been reviewed; this script records evidence only.'
    )
    capturedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
    viewport      = [ordered]@{
        bounds = $viewport.Current.BoundingRectangle.ToString()
    }
    states        = @()
}

try {
    foreach ($state in @('solved-cloth', 'editing-view')) {
        $desired = if ($state -eq 'solved-cloth') { 'On' } else { 'Off' }
        $reached = Set-ToggleState -Element $toggle -State $desired
        if ($reached -ne $desired) {
            throw "The solved-cloth toggle would not move to $desired."
        }
        # Loading the packaged meshes is asynchronous, so give the first frame
        # after a state change longer than a camera move needs.
        Start-Sleep -Seconds ([Math]::Min(8, $LoadTimeoutSeconds))

        $captures = @()
        foreach ($view in $cameraViews) {
            $button = Find-ByAutomationId -Root $window -AutomationId $view.Button
            if ($null -eq $button) {
                $captures += [ordered]@{ view = $view.Name; found = $false }
                continue
            }
            Invoke-Element -Element $button
            Start-Sleep -Milliseconds $SettleMilliseconds
            $file = Join-Path $outputFull ("{0}-{1}.png" -f $state, $view.Name)
            $image = Save-ElementImage -Element $viewport -Path $file
            $image['view'] = $view.Name
            $image['found'] = $true
            $captures += $image
        }
        $report.states += [ordered]@{
            state          = $state
            toggleState    = $reached
            captures       = $captures
        }
    }
}
finally {
    Set-ToggleState -Element $toggle -State $originalToggleState | Out-Null
}

# The acceptance contract binds a human visual review to an exact set of images.
# The manifest is that binding: it lists the six required views with their
# hashes, and its own hash is what a review signs. It records no verdict.
$solved = $report.states | Where-Object { $_.state -eq 'solved-cloth' } | Select-Object -First 1
if ($null -ne $solved) {
    $captured = @($solved.captures | Where-Object { $_.found })
    $missing = @($requiredViews | Where-Object { $c = $_; -not ($captured | Where-Object { $_.view -eq $c }) })
    $manifest = [ordered]@{
        schemaVersion = 'patterna.six-view-manifest/1.0'
        claims        = [ordered]@{ visualQualityAccepted = $false; reviewed = $false }
        note          = 'These are the exact images a visual review must judge. Nothing here is a verdict.'
        capturedAtUtc = $report.capturedAtUtc
        requiredViews = $requiredViews
        missingViews  = $missing
        complete      = ($missing.Count -eq 0)
        views         = @($captured | ForEach-Object {
            [ordered]@{ view = $_.view; path = $_.path; width = $_.width; height = $_.height; sha256 = $_.sha256 }
        })
    }
    $manifestPath = Join-Path $outputFull 'six-view-manifest.json'
    [System.IO.File]::WriteAllText(
        $manifestPath,
        (($manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
        [System.Text.UTF8Encoding]::new($false))
    $report.sixViewManifest = [ordered]@{
        path     = 'six-view-manifest.json'
        complete = $manifest.complete
        sha256   = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    Write-Output ("Six-view manifest: complete={0} sha256={1}" -f $manifest.complete, $report.sixViewManifest.sha256)
}

$reportPath = Join-Path $outputFull 'drape-view-capture.json'
[System.IO.File]::WriteAllText(
    $reportPath,
    (($report | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
    [System.Text.UTF8Encoding]::new($false))
Write-Output "Captured views written to $outputFull"
$report | ConvertTo-Json -Depth 8
