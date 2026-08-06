[CmdletBinding()]
param(
    [string]$RequestPath = 'C:\PatternalTest\run-request.json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

if (-not ('PatternalDisplayMode' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class PatternalDisplayMode
{
    private const int ENUM_CURRENT_SETTINGS = -1;
    private const int CDS_UPDATEREGISTRY = 1;
    private const int DISP_CHANGE_SUCCESSFUL = 0;
    private const int DM_PELSWIDTH = 0x00080000;
    private const int DM_PELSHEIGHT = 0x00100000;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct DEVMODE
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmDeviceName;
        public short dmSpecVersion;
        public short dmDriverVersion;
        public short dmSize;
        public short dmDriverExtra;
        public int dmFields;
        public int dmPositionX;
        public int dmPositionY;
        public int dmDisplayOrientation;
        public int dmDisplayFixedOutput;
        public short dmColor;
        public short dmDuplex;
        public short dmYResolution;
        public short dmTTOption;
        public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel;
        public int dmPelsWidth;
        public int dmPelsHeight;
        public int dmDisplayFlags;
        public int dmDisplayFrequency;
        public int dmICMMethod;
        public int dmICMIntent;
        public int dmMediaType;
        public int dmDitherType;
        public int dmReserved1;
        public int dmReserved2;
        public int dmPanningWidth;
        public int dmPanningHeight;
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool EnumDisplaySettings(string deviceName, int modeNum, ref DEVMODE devMode);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int ChangeDisplaySettings(ref DEVMODE devMode, int flags);

    public static bool TrySet(int width, int height)
    {
        var mode = new DEVMODE();
        mode.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
        if (!EnumDisplaySettings(null, ENUM_CURRENT_SETTINGS, ref mode))
        {
            return false;
        }

        mode.dmPelsWidth = width;
        mode.dmPelsHeight = height;
        mode.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT;
        return ChangeDisplaySettings(ref mode, CDS_UPDATEREGISTRY) == DISP_CHANGE_SUCCESSFUL;
    }
}
'@
}

function Wait-ForCondition {
    param(
        [Parameter(Mandatory)]
        [scriptblock]$Condition,
        [Parameter(Mandatory)]
        [string]$Description,
        [ValidateRange(1, 180)]
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $value = & $Condition
        if ($value) {
            return $value
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTimeOffset]::UtcNow -lt $deadline)

    throw "Timed out waiting for $Description."
}

function Find-UiElement {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)]
        [string]$Name,
        [ValidateRange(1, 120)]
        [int]$TimeoutSeconds = 20
    )

    return Wait-ForCondition -Description "UI element '$Name'" -TimeoutSeconds $TimeoutSeconds -Condition {
        $condition = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::NameProperty,
            $Name)
        $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
    }
}

function Get-UiPattern {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationPattern]$Pattern,
        [Parameter(Mandatory)]
        [string]$PatternName
    )

    $patternObject = $null
    if (-not $Element.TryGetCurrentPattern($Pattern, [ref]$patternObject)) {
        throw "'$($Element.Current.Name)' does not expose $PatternName."
    }
    return $patternObject
}

function Invoke-UiElement {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Element
    )

    $selection = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$selection)) {
        $selection.Select()
        return
    }

    $invoke = Get-UiPattern -Element $Element -Pattern ([System.Windows.Automation.InvokePattern]::Pattern) -PatternName 'InvokePattern'
    $invoke.Invoke()
}

function Get-ToggleState {
    param([System.Windows.Automation.AutomationElement]$Element)
    $toggle = Get-UiPattern -Element $Element -Pattern ([System.Windows.Automation.TogglePattern]::Pattern) -PatternName 'TogglePattern'
    return $toggle.Current.ToggleState.ToString()
}

function Set-ToggleState {
    param(
        [System.Windows.Automation.AutomationElement]$Element,
        [ValidateSet('On', 'Off', 'Indeterminate')]
        [string]$State
    )

    $toggle = Get-UiPattern -Element $Element -Pattern ([System.Windows.Automation.TogglePattern]::Pattern) -PatternName 'TogglePattern'
    if ($toggle.Current.ToggleState.ToString() -eq $State) {
        return
    }
    $toggle.Toggle()
    Wait-ForCondition -Description "'$($Element.Current.Name)' to become $State" -Condition {
        $toggle.Current.ToggleState.ToString() -eq $State
    } | Out-Null
}

function Test-ToggleRoundTrip {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string]$Name
    )

    $element = Find-UiElement -Root $Root -Name $Name
    if (-not $element.Current.IsEnabled) {
        throw "Toggle '$Name' is disabled."
    }
    $original = Get-ToggleState -Element $element
    $opposite = if ($original -eq 'On') { 'Off' } else { 'On' }
    Set-ToggleState -Element $element -State $opposite
    Set-ToggleState -Element $element -State $original
    return [ordered]@{ original = $original; changed = $opposite; restored = $original }
}

function Test-SliderRoundTrip {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string]$Name
    )

    $element = Find-UiElement -Root $Root -Name $Name
    if (-not $element.Current.IsEnabled) {
        throw "Slider '$Name' is disabled."
    }
    $range = Get-UiPattern -Element $element -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
    if ($range.Current.IsReadOnly) {
        throw "Slider '$Name' is read-only."
    }

    $original = [double]$range.Current.Value
    $step = [math]::Max([double]$range.Current.SmallChange, 0.1)
    $changed = if ($original + $step -le [double]$range.Current.Maximum) {
        $original + $step
    }
    else {
        $original - $step
    }
    $range.SetValue($changed)
    Wait-ForCondition -Description "slider '$Name' to change" -Condition {
        [math]::Abs([double]$range.Current.Value - $changed) -lt 0.001
    } | Out-Null
    $range.SetValue($original)
    Wait-ForCondition -Description "slider '$Name' to restore" -Condition {
        [math]::Abs([double]$range.Current.Value - $original) -lt 0.001
    } | Out-Null
    return [ordered]@{ original = $original; changed = $changed; restored = $original; step = $step }
}

function Save-WindowScreenshot {
    param(
        [System.Windows.Automation.AutomationElement]$Window,
        [string]$Path
    )

    $rect = $Window.Current.BoundingRectangle
    $width = [math]::Floor($rect.Width)
    $height = [math]::Floor($rect.Height)
    if ($width -lt 100 -or $height -lt 100) {
        throw "Window bounds are invalid: $width x $height."
    }

    $bitmap = [System.Drawing.Bitmap]::new($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen(
            [math]::Floor($rect.Left),
            [math]::Floor($rect.Top),
            0,
            0,
            [System.Drawing.Size]::new($width, $height),
            [System.Drawing.CopyPixelOperation]::SourceCopy)
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Convert-UiTreeNode {
    param(
        [System.Windows.Automation.AutomationElement]$Element,
        [int]$Depth = 0,
        [int]$MaxDepth = 8
    )

    if ($script:uiTreeNodeCount -ge 2500) {
        return $null
    }
    $script:uiTreeNodeCount++

    try {
        $node = [ordered]@{
            name = $Element.Current.Name
            automationId = $Element.Current.AutomationId
            controlType = $Element.Current.ControlType.ProgrammaticName
            enabled = $Element.Current.IsEnabled
            offscreen = $Element.Current.IsOffscreen
            children = @()
        }
        if ($Depth -ge $MaxDepth) {
            return [pscustomobject]$node
        }

        $children = [System.Collections.Generic.List[object]]::new()
        $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
        $child = $walker.GetFirstChild($Element)
        while ($child -and $script:uiTreeNodeCount -lt 2500) {
            $converted = Convert-UiTreeNode -Element $child -Depth ($Depth + 1) -MaxDepth $MaxDepth
            if ($converted) {
                $children.Add($converted)
            }
            $child = $walker.GetNextSibling($child)
        }
        $node.children = @($children)
        return [pscustomobject]$node
    }
    catch {
        return [pscustomobject]@{ name = '<unavailable>'; error = $_.Exception.Message; children = @() }
    }
}

function Add-ActionResult {
    param(
        [string]$Name,
        [bool]$Passed,
        [object]$Details,
        [string]$ErrorMessage
    )

    $script:actions.Add([pscustomobject]@{
        name = $Name
        passed = $Passed
        details = $Details
        error = $ErrorMessage
        completedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
    })
    if (-not $Passed) {
        $script:failedActionCount++
    }
}

function Invoke-UiCheck {
    param(
        [string]$Name,
        [scriptblock]$Check
    )

    try {
        $details = & $Check
        Add-ActionResult -Name $Name -Passed $true -Details $details -ErrorMessage $null
    }
    catch {
        Add-ActionResult -Name $Name -Passed $false -Details $null -ErrorMessage $_.Exception.Message
    }
}

if (-not (Test-Path -LiteralPath $RequestPath)) {
    throw "UI request does not exist: $RequestPath"
}
$request = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
if ($request.schema -ne 'patternal.isolated-ui-request/1.0') {
    throw "Unsupported request schema: $($request.schema)"
}

$evidenceDirectory = Join-Path $request.evidenceRoot $request.runId
if (Test-Path -LiteralPath $evidenceDirectory) {
    throw "Refusing to overwrite evidence directory: $evidenceDirectory"
}
New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null

$script:actions = [System.Collections.Generic.List[object]]::new()
$script:screenshots = [System.Collections.Generic.List[object]]::new()
$script:failedActionCount = 0
$script:uiTreeNodeCount = 0
$startedAt = [DateTimeOffset]::UtcNow
$window = $null
$process = $null
$fatalError = $null

try {
    [void][PatternalDisplayMode]::TrySet(1920, 1080)
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    if ($screen.Width -lt 1280 -or $screen.Height -lt 720) {
        throw "Guest display is too small for acceptance evidence: $($screen.Width) x $($screen.Height)."
    }
    Add-ActionResult -Name 'Guest display resolution' -Passed $true -Details ([ordered]@{ width = $screen.Width; height = $screen.Height }) -ErrorMessage $null

    Get-Process -Name Patternal -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Process -FilePath explorer.exe -ArgumentList "shell:AppsFolder\$($request.aumid)"
    $process = Wait-ForCondition -Description 'Patternal process' -TimeoutSeconds 60 -Condition {
        Get-Process -Name Patternal -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    $automationRoot = [System.Windows.Automation.AutomationElement]::RootElement
    $window = Wait-ForCondition -Description 'Patternal top-level window' -TimeoutSeconds 60 -Condition {
        $nameCondition = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::NameProperty,
            [string]$request.expectedWindowTitle)
        $automationRoot.FindFirst([System.Windows.Automation.TreeScope]::Children, $nameCondition)
    }
    $windowPattern = Get-UiPattern -Element $window -Pattern ([System.Windows.Automation.WindowPattern]::Pattern) -PatternName 'WindowPattern'
    $windowPattern.SetWindowVisualState([System.Windows.Automation.WindowVisualState]::Maximized)
    Find-UiElement -Root $window -Name 'Pattern workspace views' -TimeoutSeconds 60 | Out-Null
    Add-ActionResult -Name 'Packaged launch' -Passed $true -Details ([ordered]@{ processId = $process.Id; title = $window.Current.Name; responsive = $process.Responding }) -ErrorMessage $null

    Start-Sleep -Seconds 2
    $startupShot = Join-Path $evidenceDirectory '01-startup-2d.png'
    Save-WindowScreenshot -Window $window -Path $startupShot
    $script:screenshots.Add([pscustomobject]@{ name = 'startup-2d'; file = [IO.Path]::GetFileName($startupShot) })

    $script:uiTreeNodeCount = 0
    Convert-UiTreeNode -Element $window | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $evidenceDirectory 'ui-tree-2d.json') -Encoding utf8

    foreach ($toggleName in @(
        'Show pattern pieces panel',
        'Show avatar and material inspector',
        'Show seam allowance',
        'Show grainlines'
    )) {
        Invoke-UiCheck -Name "Toggle round trip: $toggleName" -Check {
            Test-ToggleRoundTrip -Root $window -Name $toggleName
        }
    }

    $linkElement = Find-UiElement -Root $window -Name 'Link proportional measurements'
    $originalLinkState = Get-ToggleState -Element $linkElement
    Invoke-UiCheck -Name 'Disable linked proportions for isolated slider tests' -Check {
        Set-ToggleState -Element $linkElement -State 'Off'
        [ordered]@{ original = $originalLinkState; testState = 'Off' }
    }

    foreach ($sliderName in @(
        'Height in centimeters',
        'Full bust circumference in centimeters',
        'Natural waist circumference in centimeters',
        'Full hip circumference in centimeters',
        'Shoulder breadth in centimeters',
        'Torso length in centimeters',
        'Fabric weight in grams per square meter',
        'Fabric bias stretch percentage'
    )) {
        Invoke-UiCheck -Name "Slider round trip: $sliderName" -Check {
            Test-SliderRoundTrip -Root $window -Name $sliderName
        }
    }

    Invoke-UiCheck -Name 'Restore linked proportions' -Check {
        Set-ToggleState -Element $linkElement -State $originalLinkState
        [ordered]@{ restored = $originalLinkState }
    }

    Invoke-UiCheck -Name 'Fitted bra availability contract' -Check {
        $bra = Find-UiElement -Root $window -Name 'Show fitted bra'
        if ($bra.Current.IsEnabled) {
            $roundTrip = Test-ToggleRoundTrip -Root $window -Name 'Show fitted bra'
            [ordered]@{ available = $true; roundTrip = $roundTrip }
        }
        else {
            [ordered]@{ available = $false; disabled = $true; reason = 'No fitted display asset matches the current avatar revision.' }
        }
    }

    Invoke-UiCheck -Name 'Assembly seam direction undo refresh' -Check {
        $editMode = Find-UiElement -Root $window -Name 'Edit pattern points'
        $assemblyMode = Find-UiElement -Root $window -Name 'Inspect garment seam graph'
        $editOriginal = Get-ToggleState -Element $editMode
        $assemblyOriginal = Get-ToggleState -Element $assemblyMode
        Set-ToggleState -Element $assemblyMode -State 'On'
        $reverse = Find-UiElement -Root $window -Name 'Reverse selected seam side B sewing direction'
        if (-not $reverse.Current.IsEnabled) {
            throw 'The selected default seam cannot be edited.'
        }
        $originalReverse = Get-ToggleState -Element $reverse
        $changedReverse = if ($originalReverse -eq 'On') { 'Off' } else { 'On' }
        Set-ToggleState -Element $reverse -State $changedReverse
        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Wait-ForCondition -Description 'Undo command to become enabled' -Condition { $undo.Current.IsEnabled } | Out-Null
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'seam direction toggle to refresh after Undo' -Condition {
            (Get-ToggleState -Element $reverse) -eq $originalReverse
        } | Out-Null
        Set-ToggleState -Element $assemblyMode -State $assemblyOriginal
        Set-ToggleState -Element $editMode -State $editOriginal
        [ordered]@{ original = $originalReverse; changed = $changedReverse; restoredAfterUndo = $originalReverse }
    }

    $tab3d = Find-UiElement -Root $window -Name '3D DRAPE'
    Invoke-UiElement -Element $tab3d
    Find-UiElement -Root $window -Name 'Show front cloth view' -TimeoutSeconds 60 | Out-Null
    Start-Sleep -Seconds 3

    $cameraViews = @(
        [pscustomobject]@{ name = 'front'; control = 'Show front cloth view' },
        [pscustomobject]@{ name = 'right'; control = 'Show right side cloth view' },
        [pscustomobject]@{ name = 'rear'; control = 'Show rear cloth view' },
        [pscustomobject]@{ name = 'left'; control = 'Show left side cloth view' },
        [pscustomobject]@{ name = 'oblique'; control = 'Show front oblique cloth view' },
        [pscustomobject]@{ name = 'fit'; control = 'Reset three dimensional camera' }
    )
    $script:shotIndex = 2
    foreach ($view in $cameraViews) {
        Invoke-UiCheck -Name "3D camera: $($view.name)" -Check {
            $camera = Find-UiElement -Root $window -Name $view.control
            if (-not $camera.Current.IsEnabled) {
                throw "Camera control '$($view.control)' is disabled."
            }
            Invoke-UiElement -Element $camera
            Start-Sleep -Milliseconds 1200
            $shotPath = Join-Path $evidenceDirectory ('{0:D2}-3d-{1}.png' -f $script:shotIndex, $view.name)
            Save-WindowScreenshot -Window $window -Path $shotPath
            $script:screenshots.Add([pscustomobject]@{ name = "3d-$($view.name)"; file = [IO.Path]::GetFileName($shotPath) })
            $script:shotIndex++
            [ordered]@{ invoked = $view.control; screenshot = [IO.Path]::GetFileName($shotPath) }
        }
    }

    $script:uiTreeNodeCount = 0
    Convert-UiTreeNode -Element $window | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $evidenceDirectory 'ui-tree-3d.json') -Encoding utf8

    Invoke-UiCheck -Name 'Return to 2D workspace' -Check {
        $tab2d = Find-UiElement -Root $window -Name '2D FLAT'
        Invoke-UiElement -Element $tab2d
        Find-UiElement -Root $window -Name 'Interactive two dimensional pattern layout' | Out-Null
        [ordered]@{ selected = '2D FLAT' }
    }
}
catch {
    $fatalError = $_.Exception.Message
    Add-ActionResult -Name 'Fatal runner error' -Passed $false -Details $null -ErrorMessage $fatalError
    if ($window) {
        try {
            $failureShot = Join-Path $evidenceDirectory '99-failure.png'
            Save-WindowScreenshot -Window $window -Path $failureShot
            $script:screenshots.Add([pscustomobject]@{ name = 'failure'; file = [IO.Path]::GetFileName($failureShot) })
        }
        catch {
        }
    }
}
finally {
    if ($window -and -not [bool]$request.keepAppOpen) {
        try {
            $closePattern = Get-UiPattern -Element $window -Pattern ([System.Windows.Automation.WindowPattern]::Pattern) -PatternName 'WindowPattern'
            $closePattern.Close()
        }
        catch {
            Get-Process -Name Patternal -ErrorAction SilentlyContinue | Stop-Process -Force
        }
    }

    $finishedAt = [DateTimeOffset]::UtcNow
    $result = [ordered]@{
        schema = 'patternal.isolated-ui-result/1.0'
        runId = $request.runId
        passed = $script:failedActionCount -eq 0
        startedAtUtc = $startedAt.ToString('O')
        finishedAtUtc = $finishedAt.ToString('O')
        durationSeconds = [math]::Round(($finishedAt - $startedAt).TotalSeconds, 3)
        machine = [ordered]@{
            computerName = $env:COMPUTERNAME
            userName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            osVersion = [Environment]::OSVersion.Version.ToString()
            primaryDisplay = if ([System.Windows.Forms.Screen]::PrimaryScreen) {
                [ordered]@{ width = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width; height = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height }
            } else { $null }
        }
        process = if ($process) { [ordered]@{ id = $process.Id; responding = $process.Responding } } else { $null }
        hostInputInjected = $false
        vmConnectLaunched = $false
        actions = @($script:actions)
        screenshots = @($script:screenshots)
        fatalError = $fatalError
    }
    $result | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $evidenceDirectory 'result.json') -Encoding utf8
}
