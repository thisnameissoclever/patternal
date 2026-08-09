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
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Threading;

public static class PatternalDisplayMode
{
    private const int ENUM_CURRENT_SETTINGS = -1;
    private const int CDS_UPDATEREGISTRY = 1;
    private const int DISP_CHANGE_SUCCESSFUL = 0;
    private const int DM_PELSWIDTH = 0x00080000;
    private const int DM_PELSHEIGHT = 0x00100000;
    private const uint WM_SETTINGCHANGE = 0x001A;
    private const uint SMTO_ABORTIFHUNG = 0x0002;
    private static readonly IntPtr HWND_BROADCAST = new IntPtr(0xffff);

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

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr SendMessageTimeout(
        IntPtr hWnd,
        uint message,
        UIntPtr wParam,
        string lParam,
        uint flags,
        uint timeout,
        out UIntPtr result);

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

    public static void BroadcastAccessibilityChange()
    {
        UIntPtr result;
        SendMessageTimeout(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            UIntPtr.Zero,
            "Accessibility",
            SMTO_ABORTIFHUNG,
            5000,
            out result);
    }
}

public static class PatternalGuestPointerInput
{
    private const uint INPUT_MOUSE = 0;
    private const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    private const uint MOUSEEVENTF_LEFTUP = 0x0004;

    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT
    {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint dwFlags;
        public uint time;
        public UIntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT
    {
        public uint type;
        public MOUSEINPUT mouse;
    }

    [DllImport("user32.dll")]
    private static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint count, INPUT[] inputs, int size);

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr window);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    public static bool BringToFront(int nativeWindowHandle)
    {
        return SetForegroundWindow(new IntPtr(nativeWindowHandle));
    }

    public static int ForegroundWindowHandle()
    {
        return GetForegroundWindow().ToInt32();
    }

    public static void Click(int x, int y)
    {
        if (!SetCursorPos(x, y))
        {
            throw new InvalidOperationException("The guest desktop rejected the requested pointer position.");
        }
        Thread.Sleep(60);
        var inputs = new[]
        {
            new INPUT { type = INPUT_MOUSE, mouse = new MOUSEINPUT { dwFlags = MOUSEEVENTF_LEFTDOWN } },
            new INPUT { type = INPUT_MOUSE, mouse = new MOUSEINPUT { dwFlags = MOUSEEVENTF_LEFTUP } }
        };
        var sent = SendInput((uint)inputs.Length, inputs, Marshal.SizeOf(typeof(INPUT)));
        if (sent != (uint)inputs.Length)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "The guest desktop did not accept the complete pointer click.");
        }
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

function Find-UiElementOnce {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)]
        [string]$Name
    )

    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        $Name)
    return $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Find-UiElementByAutomationIdOnce {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)]
        [string]$AutomationId
    )

    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $pending = [System.Collections.Generic.Queue[System.Windows.Automation.AutomationElement]]::new()
    $pending.Enqueue($Root)
    $visited = 0

    while ($pending.Count -gt 0 -and $visited -lt 2500) {
        $parent = $pending.Dequeue()
        $visited++
        try {
            $child = $walker.GetFirstChild($parent)
        }
        catch {
            continue
        }

        while ($child -and $visited -lt 2500) {
            try {
                if ($child.Current.AutomationId -eq $AutomationId) {
                    return $child
                }
                $pending.Enqueue($child)
            }
            catch {
            }

            try {
                $child = $walker.GetNextSibling($child)
            }
            catch {
                $child = $null
            }
        }
    }

    return $null
}

function Find-UiElementByAutomationId {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)]
        [string]$AutomationId,
        [ValidateRange(1, 180)]
        [int]$TimeoutSeconds = 20
    )

    return Wait-ForCondition -Description "UI element with automation ID '$AutomationId'" -TimeoutSeconds $TimeoutSeconds -Condition {
        Find-UiElementByAutomationIdOnce -Root $Root -AutomationId $AutomationId
    }
}

function Find-UiDescendantByAutomationId {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)]
        [string]$AutomationId
    )

    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $pending = [System.Collections.Generic.Stack[System.Windows.Automation.AutomationElement]]::new()
    $pending.Push($Root)
    while ($pending.Count -gt 0) {
        $parent = $pending.Pop()
        try {
            $child = $walker.GetFirstChild($parent)
        }
        catch {
            continue
        }
        $children = [System.Collections.Generic.List[System.Windows.Automation.AutomationElement]]::new()
        while ($child) {
            try {
                if ($child.Current.AutomationId -eq $AutomationId) {
                    return $child
                }
                $children.Add($child)
            }
            catch {
            }
            try {
                $child = $walker.GetNextSibling($child)
            }
            catch {
                $child = $null
            }
        }
        for ($index = $children.Count - 1; $index -ge 0; $index--) {
            $pending.Push($children[$index])
        }
    }
    return $null
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

function Set-UiTextValue {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory)]
        [string]$Value
    )

    $valuePattern = Get-UiPattern -Element $Element -Pattern ([System.Windows.Automation.ValuePattern]::Pattern) -PatternName 'ValuePattern'
    if ($valuePattern.Current.IsReadOnly) {
        throw "'$($Element.Current.Name)' is read-only."
    }
    $valuePattern.SetValue($Value)
    Wait-ForCondition -Description "'$($Element.Current.Name)' to contain '$Value'" -Condition {
        $valuePattern.Current.Value -eq $Value
    } | Out-Null
}

function Invoke-GuestPointerElement {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Window,
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Element
    )

    if ($Element.Current.ProcessId -ne $Window.Current.ProcessId) {
        throw "Refusing to click '$($Element.Current.Name)' outside the Patternal process."
    }
    $windowBounds = $Window.Current.BoundingRectangle
    $elementBounds = $Element.Current.BoundingRectangle
    $x = [int][math]::Round($elementBounds.Left + ($elementBounds.Width / 2.0))
    $y = [int][math]::Round($elementBounds.Top + ($elementBounds.Height / 2.0))
    if ($x -lt $windowBounds.Left -or $x -gt $windowBounds.Right -or
        $y -lt $windowBounds.Top -or $y -gt $windowBounds.Bottom) {
        throw "Refusing to click '$($Element.Current.Name)' outside the Patternal window."
    }
    [void][PatternalGuestPointerInput]::BringToFront($Window.Current.NativeWindowHandle)
    Start-Sleep -Milliseconds 100
    [PatternalGuestPointerInput]::Click($x, $y)
}

function Start-PatternalUiSession {
    param(
        [Parameter(Mandatory)]
        [string]$Aumid,
        [Parameter(Mandatory)]
        [string]$ExpectedWindowTitle
    )

    Start-Process -FilePath explorer.exe -ArgumentList "shell:AppsFolder\$Aumid"
    $launchedProcess = Wait-ForCondition -Description 'Patternal process' -TimeoutSeconds 60 -Condition {
        Get-Process -Name Patternal -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $launchedWindow = Wait-ForCondition -Description 'Patternal top-level window' -TimeoutSeconds 60 -Condition {
        $nameCondition = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::NameProperty,
            $ExpectedWindowTitle)
        $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $nameCondition)
    }
    $windowPattern = Get-UiPattern -Element $launchedWindow -Pattern ([System.Windows.Automation.WindowPattern]::Pattern) -PatternName 'WindowPattern'
    $windowPattern.SetWindowVisualState([System.Windows.Automation.WindowVisualState]::Maximized)
    Find-UiElement -Root $launchedWindow -Name 'Pattern workspace views' -TimeoutSeconds 60 | Out-Null
    return [pscustomobject]@{
        Process = $launchedProcess
        Window = $launchedWindow
    }
}

function Stop-PatternalUiSession {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Window,
        [int]$ProcessId
    )

    try {
        $windowPattern = Get-UiPattern -Element $Window -Pattern ([System.Windows.Automation.WindowPattern]::Pattern) -PatternName 'WindowPattern'
        $windowPattern.Close()
    }
    catch {
        if ($ProcessId -gt 0) {
            Get-Process -Id $ProcessId -ErrorAction SilentlyContinue | Stop-Process -Force
        }
    }
    Wait-ForCondition -Description 'Patternal process to exit' -TimeoutSeconds 30 -Condition {
        -not (Get-Process -Name Patternal -ErrorAction SilentlyContinue)
    } | Out-Null
}

function Select-UiComboBoxItem {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)]
        [string]$ComboBoxName,
        [Parameter(Mandatory)]
        [string]$ItemName
    )

    $comboBox = Find-UiElement -Root $Root -Name $ComboBoxName
    $expandCollapse = Get-UiPattern -Element $comboBox -Pattern ([System.Windows.Automation.ExpandCollapsePattern]::Pattern) -PatternName 'ExpandCollapsePattern'
    if ($expandCollapse.Current.ExpandCollapseState.ToString() -ne 'Expanded') {
        $expandCollapse.Expand()
    }
    $item = Find-UiElement -Root $Root -Name $ItemName
    $selection = Get-UiPattern -Element $item -Pattern ([System.Windows.Automation.SelectionItemPattern]::Pattern) -PatternName 'SelectionItemPattern'
    $selection.Select()
    Wait-ForCondition -Description "'$ItemName' to be selected in '$ComboBoxName'" -Condition {
        $selection.Current.IsSelected
    } | Out-Null
    if ($expandCollapse.Current.ExpandCollapseState.ToString() -eq 'Expanded') {
        $expandCollapse.Collapse()
    }
}

function Assert-UiComboBoxItemSelected {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory)]
        [string]$ComboBoxName,
        [Parameter(Mandatory)]
        [string]$ItemName
    )

    $comboBox = Find-UiElement -Root $Root -Name $ComboBoxName
    $expandCollapse = Get-UiPattern -Element $comboBox -Pattern ([System.Windows.Automation.ExpandCollapsePattern]::Pattern) -PatternName 'ExpandCollapsePattern'
    if ($expandCollapse.Current.ExpandCollapseState.ToString() -ne 'Expanded') {
        $expandCollapse.Expand()
    }
    $item = Find-UiElement -Root $Root -Name $ItemName
    $selection = Get-UiPattern -Element $item -Pattern ([System.Windows.Automation.SelectionItemPattern]::Pattern) -PatternName 'SelectionItemPattern'
    if (-not $selection.Current.IsSelected) {
        throw "'$ItemName' is not selected in '$ComboBoxName'."
    }
    if ($expandCollapse.Current.ExpandCollapseState.ToString() -eq 'Expanded') {
        $expandCollapse.Collapse()
    }
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
    $left = [int][math]::Floor($rect.Left)
    $top = [int][math]::Floor($rect.Top)
    $width = [int][math]::Floor($rect.Width)
    $height = [int][math]::Floor($rect.Height)
    if ($width -lt 100 -or $height -lt 100) {
        throw "Window bounds are invalid: left $left, top $top, width $width, height $height."
    }

    $bitmap = [System.Drawing.Bitmap]::new([int]$width, [int]$height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen(
            [int]$left,
            [int]$top,
            0,
            0,
            [System.Drawing.Size]::new([int]$width, [int]$height),
            [System.Drawing.CopyPixelOperation]::SourceCopy)
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Assert-RenderedScreenshotRegion {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Window,
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory)]
        [string]$Description
    )

    $windowBounds = $Window.Current.BoundingRectangle
    $elementBounds = $Element.Current.BoundingRectangle
    $bitmap = [System.Drawing.Bitmap]::new($Path)
    try {
        $left = [int][math]::Max(0, [math]::Floor($elementBounds.Left - $windowBounds.Left + ($elementBounds.Width * 0.2)))
        $top = [int][math]::Max(0, [math]::Floor($elementBounds.Top - $windowBounds.Top + ($elementBounds.Height * 0.2)))
        $right = [int][math]::Min($bitmap.Width - 1, [math]::Ceiling($elementBounds.Right - $windowBounds.Left - ($elementBounds.Width * 0.2)))
        $bottom = [int][math]::Min($bitmap.Height - 1, [math]::Ceiling($elementBounds.Bottom - $windowBounds.Top - ($elementBounds.Height * 0.2)))
        if ($right -le $left -or $bottom -le $top) {
            throw "$Description has invalid screenshot bounds."
        }

        $sampleStep = [int][math]::Max(8, [math]::Floor([math]::Min($right - $left, $bottom - $top) / 60))
        $sampleCount = 0
        $nonWhiteCount = 0
        for ($y = $top; $y -le $bottom; $y += $sampleStep) {
            for ($x = $left; $x -le $right; $x += $sampleStep) {
                $pixel = $bitmap.GetPixel($x, $y)
                $sampleCount++
                if ($pixel.R -lt 235 -or $pixel.G -lt 235 -or $pixel.B -lt 235) {
                    $nonWhiteCount++
                }
            }
        }
        $nonWhiteRatio = if ($sampleCount -gt 0) { $nonWhiteCount / $sampleCount } else { 0 }
        if ($nonWhiteRatio -lt 0.05) {
            throw "$Description is visually blank or has not repainted. Non-white sample ratio was $([math]::Round($nonWhiteRatio, 4))."
        }
        return [ordered]@{
            sampledPixels = $sampleCount
            nonWhitePixels = $nonWhiteCount
            nonWhiteRatio = [math]::Round($nonWhiteRatio, 4)
        }
    }
    finally {
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

function Get-FailureDiagnostics {
    param(
        [System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)]
        [DateTimeOffset]$StartedAt
    )

    $processState = $null
    if ($Process) {
        try {
            $Process.Refresh()
            $processState = [ordered]@{
                id = $Process.Id
                hasExited = $Process.HasExited
                responding = if ($Process.HasExited) { $false } else { $Process.Responding }
                mainWindowHandle = if ($Process.HasExited) { 0 } else { $Process.MainWindowHandle.ToInt64() }
                mainWindowTitle = if ($Process.HasExited) { $null } else { $Process.MainWindowTitle }
            }
        }
        catch {
            $processState = [ordered]@{ error = $_.Exception.Message }
        }
    }

    $events = [System.Collections.Generic.List[object]]::new()
    foreach ($logName in @(
        'Application',
        'Microsoft-Windows-AppModel-Runtime/Admin',
        'Microsoft-Windows-TWinUI/Operational'
    )) {
        try {
            $matchingEvents = Get-WinEvent -FilterHashtable @{
                LogName = $logName
                StartTime = $StartedAt.UtcDateTime
            } -ErrorAction Stop | Where-Object {
                $_.Level -le 3 -or
                $_.ProviderName -in @('.NET Runtime', 'Application Error', 'Windows Error Reporting') -or
                $_.Message -match 'Patternal|C513E361-86E8-4FBD-9FF7-FABA0EAFA8FE'
            } | Select-Object -First 30
            foreach ($eventRecord in $matchingEvents) {
                $message = [string]$eventRecord.Message
                if ($message.Length -gt 2000) {
                    $message = $message.Substring(0, 2000) + ' [truncated]'
                }
                $events.Add([ordered]@{
                    timeCreatedUtc = if ($eventRecord.TimeCreated) { $eventRecord.TimeCreated.ToUniversalTime().ToString('O') } else { $null }
                    logName = $logName
                    provider = $eventRecord.ProviderName
                    id = $eventRecord.Id
                    level = $eventRecord.LevelDisplayName
                    message = $message
                })
            }
        }
        catch {
            $events.Add([ordered]@{
                logName = $logName
                queryError = $_.Exception.Message
            })
        }
    }

    return [ordered]@{
        process = $processState
        events = @($events)
    }
}

function Invoke-ThreeDimensionalChecks {
    param(
        [Parameter(Mandatory)]
        [System.Windows.Automation.AutomationElement]$Window,
        [Parameter(Mandatory)]
        [string]$EvidenceDirectory
    )

    $tab3d = Find-UiElement -Root $Window -Name '3D DRAPE'
    Invoke-UiElement -Element $tab3d
    Find-UiElementByAutomationId -Root $Window -AutomationId 'DrapeFrontCameraButton' -TimeoutSeconds 120 | Out-Null
    Start-Sleep -Seconds 3

    $drapeState = Wait-ForCondition -Description 'truthful accepted or stale 3D state' -TimeoutSeconds 120 -Condition {
        $stale = Find-UiElementByAutomationIdOnce -Root $Window -AutomationId 'DrapeStaleSimulationState'
        if ($stale) {
            return [pscustomobject]@{ stale = $true; element = $stale }
        }
        $accepted = Find-UiElementByAutomationIdOnce -Root $Window -AutomationId 'DrapeAcceptedSimulationState'
        if ($accepted) {
            return [pscustomobject]@{ stale = $false; element = $accepted }
        }
        return $null
    }
    $staleNotice = if ($drapeState.stale) { $drapeState.element } else { $null }
    $evidencePrefix = if ($staleNotice) { '3d-stale-avatar' } else { '3d-cloth' }

    $cameraViews = @(
        [pscustomobject]@{ name = 'front'; control = 'Show front cloth view'; automationId = 'DrapeFrontCameraButton' },
        [pscustomobject]@{ name = 'right'; control = 'Show right side cloth view'; automationId = 'DrapeRightCameraButton' },
        [pscustomobject]@{ name = 'rear'; control = 'Show rear cloth view'; automationId = 'DrapeRearCameraButton' },
        [pscustomobject]@{ name = 'left'; control = 'Show left side cloth view'; automationId = 'DrapeLeftCameraButton' },
        [pscustomobject]@{ name = 'oblique'; control = 'Show front oblique cloth view'; automationId = 'DrapeObliqueCameraButton' },
        [pscustomobject]@{ name = 'fit'; control = 'Reset three dimensional camera'; automationId = 'DrapeFitCameraButton' }
    )
    $script:shotIndex = 2
    foreach ($view in $cameraViews) {
        Invoke-UiCheck -Name "3D camera: $($view.name)" -Check {
            $camera = Find-UiElementByAutomationId -Root $Window -AutomationId $view.automationId
            if (-not $camera.Current.IsEnabled) {
                throw "Camera control '$($view.control)' is disabled."
            }
            Invoke-UiElement -Element $camera
            Start-Sleep -Milliseconds 1200
            $shotPath = Join-Path $EvidenceDirectory ('{0:D2}-{1}-{2}.png' -f $script:shotIndex, $evidencePrefix, $view.name)
            Save-WindowScreenshot -Window $Window -Path $shotPath
            $script:screenshots.Add([pscustomobject]@{ name = "3d-$($view.name)"; file = [IO.Path]::GetFileName($shotPath) })
            $script:shotIndex++
            [ordered]@{ invoked = $view.control; screenshot = [IO.Path]::GetFileName($shotPath) }
        }
    }

    $script:uiTreeNodeCount = 0
    Convert-UiTreeNode -Element $Window | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $EvidenceDirectory 'ui-tree-3d.json') -Encoding utf8

    $tab2d = Find-UiElement -Root $Window -Name '2D FLAT'
    Invoke-UiElement -Element $tab2d
    Find-UiElement -Root $Window -Name 'Interactive two dimensional pattern layout' | Out-Null
    Add-ActionResult -Name 'Return to 2D workspace' -Passed $true -Details ([ordered]@{ selected = '2D FLAT' }) -ErrorMessage $null
    if ($staleNotice) {
        Add-ActionResult -Name 'Current accepted cloth is available' -Passed $false -Details ([ordered]@{
            staleNotice = $staleNotice.Current.Name
            cameraInterfaceExercised = $true
        }) -ErrorMessage 'The packaged baseline has no accepted cloth for its current pattern, body, assembly, and fabric revision.'
    }
    else {
        Add-ActionResult -Name 'Current accepted cloth is available' -Passed $true -Details ([ordered]@{
            cameraInterfaceExercised = $true
            capturedViews = $cameraViews.Count
        }) -ErrorMessage $null
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
$script:finalWindow = $null
$fatalError = $null
$fatalErrorType = $null
$fatalScriptStackTrace = $null
$failureDiagnostics = $null
$textScaleRegistryPath = 'HKCU:\Software\Microsoft\Accessibility'
$originalTextScaleExists = $false
$originalTextScalePercent = 100
$textScaleChanged = $false

try {
    $requestedTextScalePercent = if ($request.PSObject.Properties.Name -contains 'textScalePercent') {
        [int]$request.textScalePercent
    }
    else {
        100
    }
    New-Item -Path $textScaleRegistryPath -Force | Out-Null
    $originalTextScaleProperty = Get-ItemProperty -Path $textScaleRegistryPath -Name TextScaleFactor -ErrorAction SilentlyContinue
    if ($null -ne $originalTextScaleProperty -and $null -ne $originalTextScaleProperty.TextScaleFactor) {
        $originalTextScaleExists = $true
        $originalTextScalePercent = [int]$originalTextScaleProperty.TextScaleFactor
    }
    if ($requestedTextScalePercent -ne $originalTextScalePercent -or -not $originalTextScaleExists) {
        Set-ItemProperty -Path $textScaleRegistryPath -Name TextScaleFactor -Type DWord -Value $requestedTextScalePercent
        [PatternalDisplayMode]::BroadcastAccessibilityChange()
        $textScaleChanged = $true
        Start-Sleep -Milliseconds 750
    }

    $requestedDisplayWidth = if ($request.PSObject.Properties.Name -contains 'displayWidth') {
        [int]$request.displayWidth
    }
    else {
        1920
    }
    $requestedDisplayHeight = if ($request.PSObject.Properties.Name -contains 'displayHeight') {
        [int]$request.displayHeight
    }
    else {
        1080
    }
    [void][PatternalDisplayMode]::TrySet($requestedDisplayWidth, $requestedDisplayHeight)
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    if ($screen.Width -lt 1280 -or $screen.Height -lt 720) {
        throw "Guest display is too small for acceptance evidence: $($screen.Width) x $($screen.Height)."
    }
    if ($screen.Width -ne $requestedDisplayWidth -or $screen.Height -ne $requestedDisplayHeight) {
        throw "Guest display did not apply the requested $requestedDisplayWidth x $requestedDisplayHeight mode. Actual mode is $($screen.Width) x $($screen.Height)."
    }
    Add-ActionResult -Name 'Guest display resolution' -Passed $true -Details ([ordered]@{
        requestedWidth = $requestedDisplayWidth
        requestedHeight = $requestedDisplayHeight
        width = $screen.Width
        height = $screen.Height
    }) -ErrorMessage $null
    Add-ActionResult -Name 'Guest text scale request' -Passed $true -Details ([ordered]@{
        requestedPercent = $requestedTextScalePercent
        registryPercent = [int](Get-ItemProperty -Path $textScaleRegistryPath -Name TextScaleFactor -ErrorAction Stop).TextScaleFactor
        originalPercent = $originalTextScalePercent
    }) -ErrorMessage $null

    Get-Process -Name Patternal -ErrorAction SilentlyContinue | Stop-Process -Force
    $launchedSession = Start-PatternalUiSession -Aumid $request.aumid -ExpectedWindowTitle $request.expectedWindowTitle
    $process = $launchedSession.Process
    $window = $launchedSession.Window
    $automationRoot = [System.Windows.Automation.AutomationElement]::RootElement
    Add-ActionResult -Name 'Packaged launch' -Passed $true -Details ([ordered]@{ processId = $process.Id; title = $window.Current.Name; responsive = $process.Responding }) -ErrorMessage $null

    Start-Sleep -Seconds 2
    $startupShot = Join-Path $evidenceDirectory '01-startup-2d.png'
    Save-WindowScreenshot -Window $window -Path $startupShot
    $script:screenshots.Add([pscustomobject]@{ name = 'startup-2d'; file = [IO.Path]::GetFileName($startupShot) })

    $script:uiTreeNodeCount = 0
    Convert-UiTreeNode -Element $window | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $evidenceDirectory 'ui-tree-2d.json') -Encoding utf8

    Invoke-UiCheck -Name 'Dedicated test profile reset to bundled baseline' -Check {
        $preResetHeight = Find-UiElement -Root $window -Name 'Height in centimeters'
        $preResetHeightRange = Get-UiPattern -Element $preResetHeight -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $preResetLink = Find-UiElement -Root $window -Name 'Link proportional measurements'
        Set-ToggleState -Element $preResetLink -State 'Off'
        $disturbedHeight = if ([double]$preResetHeightRange.Current.Value + 0.5 -le [double]$preResetHeightRange.Current.Maximum) {
            [double]$preResetHeightRange.Current.Value + 0.5
        }
        else {
            [double]$preResetHeightRange.Current.Value - 0.5
        }
        $preResetHeightRange.SetValue($disturbedHeight)
        Wait-ForCondition -Description 'deliberately disturbed test profile height' -Condition {
            [math]::Abs([double]$preResetHeightRange.Current.Value - $disturbedHeight) -lt 0.001
        } | Out-Null

        $newPattern = Find-UiElementByAutomationId -Root $window -AutomationId 'NewPatternButton'
        Invoke-GuestPointerElement -Window $window -Element $newPattern
        $confirmNewPattern = Find-UiElement -Root $window -Name 'Create pattern'
        Invoke-GuestPointerElement -Window $window -Element $confirmNewPattern
        $baselineHeight = Find-UiElement -Root $window -Name 'Height in centimeters'
        $baselineHeightRange = Get-UiPattern -Element $baselineHeight -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $baselineLink = Find-UiElement -Root $window -Name 'Link proportional measurements'
        Wait-ForCondition -Description 'New to restore the bundled test profile' -Condition {
            if ([math]::Abs([double]$baselineHeightRange.Current.Value - 167) -lt 0.001 -and
                (Get-ToggleState -Element $baselineLink) -eq 'On') {
                $true
            }
            else {
                $null
            }
        } | Out-Null
        [ordered]@{
            deliberatelyDisturbedHeight = $disturbedHeight
            restoredHeight = [double]$baselineHeightRange.Current.Value
            linkedProportions = Get-ToggleState -Element $baselineLink
        }
    }

    if ($request.mode -ne 'persistence-only') {
        Invoke-ThreeDimensionalChecks -Window $window -EvidenceDirectory $evidenceDirectory

    Invoke-UiCheck -Name '2D zoom controls round trip' -Check {
        $zoomOut = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternZoomOutButton'
        $zoomLabel = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternZoomText'
        $zoomIn = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternZoomInButton'
        $fit = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFitButton'
        $originalZoom = $zoomLabel.Current.Name
        $originalZoomValue = [double]::Parse(
            $originalZoom.TrimEnd('%'),
            [Globalization.CultureInfo]::InvariantCulture)
        if (-not $zoomIn.Current.IsEnabled) {
            throw 'The pattern zoom-in control is disabled at the initial fitted view.'
        }

        Invoke-UiElement -Element $zoomIn
        $zoomedIn = Wait-ForCondition -Description 'pattern zoom label to increase' -Condition {
            $current = $zoomLabel.Current.Name
            $currentValue = [double]::Parse(
                $current.TrimEnd('%'),
                [Globalization.CultureInfo]::InvariantCulture)
            if ($currentValue -gt $originalZoomValue) { $current } else { $null }
        }
        if (-not $zoomOut.Current.IsEnabled) {
            throw 'The pattern zoom-out control did not enable after zooming in.'
        }

        Invoke-UiElement -Element $zoomOut
        Wait-ForCondition -Description 'pattern zoom label to return to its original value' -Condition {
            $zoomLabel.Current.Name -eq $originalZoom
        } | Out-Null

        Invoke-UiElement -Element $zoomIn
        $zoomedBeforeFit = Wait-ForCondition -Description 'pattern zoom label to increase before fitting' -Condition {
            $current = $zoomLabel.Current.Name
            $currentValue = [double]::Parse(
                $current.TrimEnd('%'),
                [Globalization.CultureInfo]::InvariantCulture)
            if ($currentValue -gt $originalZoomValue) { $current } else { $null }
        }
        $zoomedBeforeFitValue = [double]::Parse(
            $zoomedBeforeFit.TrimEnd('%'),
            [Globalization.CultureInfo]::InvariantCulture)
        if (-not $fit.Current.IsEnabled) {
            throw 'The fit-all-pattern-pieces control is disabled.'
        }
        Invoke-UiElement -Element $fit
        $fittedZoom = Wait-ForCondition -Description 'fit command to reduce the zoomed pattern view' -Condition {
            $current = $zoomLabel.Current.Name
            $currentValue = [double]::Parse(
                $current.TrimEnd('%'),
                [Globalization.CultureInfo]::InvariantCulture)
            if ($currentValue -lt $zoomedBeforeFitValue) { $current } else { $null }
        }
        Start-Sleep -Milliseconds 300
        $fitShotPath = Join-Path $evidenceDirectory '08-2d-fit.png'
        Save-WindowScreenshot -Window $window -Path $fitShotPath
        $script:screenshots.Add([pscustomobject]@{ name = '2d-fit'; file = [IO.Path]::GetFileName($fitShotPath) })

        [ordered]@{
            original = $originalZoom
            zoomedIn = $zoomedIn
            fitted = $fittedZoom
            screenshot = [IO.Path]::GetFileName($fitShotPath)
        }
    }

    Invoke-UiCheck -Name '2D selection and frame-selected workflow' -Check {
        $piece = Find-UiElement -Root $window -Name 'Back Torso'
        Invoke-UiElement -Element $piece
        $frame = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFrameSelectedButton'
        $zoomLabel = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternZoomText'
        if (-not $frame.Current.IsEnabled) {
            throw 'Frame selected is disabled after selecting Back Torso.'
        }
        Invoke-UiElement -Element $frame
        $framedZoom = Wait-ForCondition -Description 'frame-selected command to enlarge Back Torso' -Condition {
            $current = $zoomLabel.Current.Name
            $currentValue = [double]::Parse(
                $current.TrimEnd('%'),
                [Globalization.CultureInfo]::InvariantCulture)
            if ($currentValue -gt 100) { $current } else { $null }
        }
        Start-Sleep -Milliseconds 300
        $frameShotPath = Join-Path $evidenceDirectory '09-2d-frame-selected.png'
        Save-WindowScreenshot -Window $window -Path $frameShotPath
        $script:screenshots.Add([pscustomobject]@{ name = '2d-frame-selected'; file = [IO.Path]::GetFileName($frameShotPath) })
        [ordered]@{
            piece = 'Back Torso'
            zoom = $framedZoom
            screenshot = [IO.Path]::GetFileName($frameShotPath)
        }
    }

    Invoke-UiCheck -Name '2D accessible point edit undo and redo' -Check {
        $editMode = Find-UiElement -Root $window -Name 'Edit pattern points'
        $originalEditState = Get-ToggleState -Element $editMode
        Set-ToggleState -Element $editMode -State 'On'

        $pointHandle = Find-UiElement -Root $window -Name 'Back Torso start'
        if (-not $pointHandle.Current.IsEnabled) {
            throw 'The framed Back Torso start point is not independently selectable.'
        }
        Invoke-UiElement -Element $pointHandle

        $xCoordinate = Find-UiElement -Root $window -Name 'Selected pattern point X coordinate in centimeters'
        $range = Get-UiPattern -Element $xCoordinate -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        if ($range.Current.IsReadOnly) {
            throw 'The selected pattern point X coordinate is read-only.'
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

        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Wait-ForCondition -Description 'point edit and Undo command to commit' -Condition {
            ([math]::Abs([double]$range.Current.Value - $changed) -lt 0.001) -and $undo.Current.IsEnabled
        } | Out-Null
        $editShotPath = Join-Path $evidenceDirectory '10-2d-point-edit.png'
        Save-WindowScreenshot -Window $window -Path $editShotPath
        $script:screenshots.Add([pscustomobject]@{ name = '2d-point-edit'; file = [IO.Path]::GetFileName($editShotPath) })

        Invoke-UiElement -Element $undo
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Wait-ForCondition -Description 'point coordinate to restore after Undo' -Condition {
            ([math]::Abs([double]$range.Current.Value - $original) -lt 0.001) -and $redo.Current.IsEnabled
        } | Out-Null
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'point coordinate to return after Redo' -Condition {
            ([math]::Abs([double]$range.Current.Value - $changed) -lt 0.001) -and $undo.Current.IsEnabled
        } | Out-Null
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'point coordinate to finish restored' -Condition {
            [math]::Abs([double]$range.Current.Value - $original) -lt 0.001
        } | Out-Null

        $restored = [double]$range.Current.Value
        Set-ToggleState -Element $editMode -State $originalEditState
        [ordered]@{
            point = 'Back Torso start'
            originalX = $original
            changedX = $changed
            restoredX = $restored
            screenshot = [IO.Path]::GetFileName($editShotPath)
        }
    }

    Invoke-UiCheck -Name '2D accessible polygon drafting undo and redo' -Check {
        $fit = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFitButton'
        Invoke-UiElement -Element $fit
        $pieceCount = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText'
        $originalCountText = $pieceCount.Current.Name
        if ($originalCountText -notmatch '^(\d+) pieces$') {
            throw "Cannot read the original pattern piece count from '$originalCountText'."
        }
        $originalCount = [int]$Matches[1]

        $startDraft = Find-UiElement -Root $window -Name 'Draw a polygon pattern piece directly on the canvas'
        Invoke-UiElement -Element $startDraft
        $xCoordinate = Find-UiElement -Root $window -Name 'Canvas polygon point X coordinate in centimeters'
        $yCoordinate = Find-UiElement -Root $window -Name 'Canvas polygon point Y coordinate in centimeters'
        $addPoint = Find-UiElement -Root $window -Name 'Add the entered point to the canvas polygon'
        $finish = Find-UiElement -Root $window -Name 'Finish the polygon pattern piece'
        $xRange = Get-UiPattern -Element $xCoordinate -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $yRange = Get-UiPattern -Element $yCoordinate -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'

        $coordinates = @(
            @(80.0, 125.0),
            @(90.0, 125.0),
            @(90.0, 135.0),
            @(80.0, 135.0)
        )
        for ($coordinateIndex = 0; $coordinateIndex -lt $coordinates.Count; $coordinateIndex++) {
            $coordinate = $coordinates[$coordinateIndex]
            $xRange.SetValue([double]$coordinate[0])
            $yRange.SetValue([double]$coordinate[1])
            Wait-ForCondition -Description "polygon coordinate $($coordinateIndex + 1) to commit" -Condition {
                ([math]::Abs([double]$xRange.Current.Value - [double]$coordinate[0]) -lt 0.001) -and
                ([math]::Abs([double]$yRange.Current.Value - [double]$coordinate[1]) -lt 0.001)
            } | Out-Null
            Invoke-UiElement -Element $addPoint
            $expectedCornerCount = $coordinateIndex + 1
            Wait-ForCondition -Description "polygon corner $expectedCornerCount to be placed" -Condition {
                $status = Find-UiElementByAutomationId -Root $window -AutomationId 'CanvasDraftStatusText'
                $status.Current.Name -like "$expectedCornerCount corner*"
            } | Out-Null
        }
        Wait-ForCondition -Description 'polygon Finish command to enable after four entered points' -Condition {
            $finish.Current.IsEnabled
        } | Out-Null

        $draftShotPath = Join-Path $evidenceDirectory '11-2d-polygon-draft.png'
        Save-WindowScreenshot -Window $window -Path $draftShotPath
        $script:screenshots.Add([pscustomobject]@{ name = '2d-polygon-draft'; file = [IO.Path]::GetFileName($draftShotPath) })
        Invoke-UiElement -Element $finish

        $createdCount = $originalCount + 1
        Wait-ForCondition -Description 'new canvas polygon to increase the pattern piece count' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq "$createdCount pieces"
        } | Out-Null
        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to remove the canvas polygon' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq "$originalCount pieces"
        } | Out-Null
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'Redo to restore the canvas polygon' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq "$createdCount pieces"
        } | Out-Null
        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'final Undo to restore the original pattern piece count' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq "$originalCount pieces"
        } | Out-Null

        [ordered]@{
            originalPieceCount = $originalCount
            createdPieceCount = $createdCount
            restoredPieceCount = $originalCount
            enteredPoints = $coordinates.Count
            screenshot = [IO.Path]::GetFileName($draftShotPath)
        }
    }

    Invoke-UiCheck -Name '2D guest pointer polygon drafting undo and redo' -Check {
        $fit = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFitButton'
        Invoke-UiElement -Element $fit
        $originalCount = [int]((Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -replace '\D', '')
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Draw a polygon pattern piece directly on the canvas')
        $pointerDraftResult = $null
        try {
            $canvas = Find-UiElement -Root $window -Name 'Interactive two dimensional pattern layout'
            $canvasBounds = $canvas.Current.BoundingRectangle
            if ($canvasBounds.Width -lt 600 -or $canvasBounds.Height -lt 450) {
                throw "The visible pattern canvas is too small for deterministic pointer drafting: $($canvasBounds.Width) by $($canvasBounds.Height)."
            }
            [void][PatternalGuestPointerInput]::BringToFront($window.Current.NativeWindowHandle)
            Start-Sleep -Milliseconds 150
            $screenPoints = @(
                @([double]($canvasBounds.Left + ([double]$canvasBounds.Width * 0.58)), [double]($canvasBounds.Top + ([double]$canvasBounds.Height * 0.62))),
                @([double]($canvasBounds.Left + ([double]$canvasBounds.Width * 0.68)), [double]($canvasBounds.Top + ([double]$canvasBounds.Height * 0.62))),
                @([double]($canvasBounds.Left + ([double]$canvasBounds.Width * 0.68)), [double]($canvasBounds.Top + ([double]$canvasBounds.Height * 0.72))),
                @([double]($canvasBounds.Left + ([double]$canvasBounds.Width * 0.58)), [double]($canvasBounds.Top + ([double]$canvasBounds.Height * 0.72)))
            )
            for ($pointIndex = 0; $pointIndex -lt $screenPoints.Count; $pointIndex++) {
                $point = $screenPoints[$pointIndex]
                $screenX = [int][math]::Round($point[0])
                $screenY = [int][math]::Round($point[1])
                $hit = [System.Windows.Automation.AutomationElement]::FromPoint([System.Windows.Point]::new($screenX, $screenY))
                if (-not $hit -or $hit.Current.ProcessId -ne $window.Current.ProcessId) {
                    $hitSummary = if ($hit) { "'$($hit.Current.Name)' from process $($hit.Current.ProcessId)" } else { 'no UI Automation element' }
                    throw "Guest pointer coordinate $screenX,$screenY hit $hitSummary instead of the Patternal window process."
                }
                [PatternalGuestPointerInput]::Click($screenX, $screenY)
                $expectedCornerCount = $pointIndex + 1
                try {
                    Wait-ForCondition -Description "guest pointer polygon corner $expectedCornerCount to be placed" -Condition {
                        $status = Find-UiElementByAutomationId -Root $window -AutomationId 'CanvasDraftStatusText'
                        $status.Current.Name -like "$expectedCornerCount corner*"
                    } | Out-Null
                }
                catch {
                    $cursor = [System.Windows.Forms.Cursor]::Position
                    $foreground = [PatternalGuestPointerInput]::ForegroundWindowHandle()
                    throw "Guest click $expectedCornerCount at $screenX,$screenY hit '$($hit.Current.Name)' ($($hit.Current.ControlType.ProgrammaticName)); cursor ended at $($cursor.X),$($cursor.Y); foreground handle was $foreground; the draft status did not advance."
                }
            }

            $pointerDraftShotPath = Join-Path $evidenceDirectory '11-2d-pointer-polygon-draft.png'
            Save-WindowScreenshot -Window $window -Path $pointerDraftShotPath
            $script:screenshots.Add([pscustomobject]@{ name = '2d-pointer-polygon-draft'; file = [IO.Path]::GetFileName($pointerDraftShotPath) })

            $firstPoint = $screenPoints[0]
            [PatternalGuestPointerInput]::Click([int][math]::Round($firstPoint[0]), [int][math]::Round($firstPoint[1]))
            $createdCount = $originalCount + 1
            Wait-ForCondition -Description 'clicking the first pointer corner to close and create the polygon' -Condition {
                (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq "$createdCount pieces"
            } | Out-Null

            $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
            Invoke-UiElement -Element $undo
            Wait-ForCondition -Description 'Undo to remove the pointer-drafted polygon' -Condition {
                (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq "$originalCount pieces"
            } | Out-Null
            $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
            Invoke-UiElement -Element $redo
            Wait-ForCondition -Description 'Redo to restore the pointer-drafted polygon' -Condition {
                (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq "$createdCount pieces"
            } | Out-Null
            $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
            Invoke-UiElement -Element $undo
            Wait-ForCondition -Description 'final Undo to restore the original piece count after pointer drafting' -Condition {
                (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq "$originalCount pieces"
            } | Out-Null

            $pointerDraftResult = [ordered]@{
                originalPieceCount = $originalCount
                createdPieceCount = $createdCount
                restoredPieceCount = $originalCount
                pointerClicks = $screenPoints.Count + 1
                guestOnlyPointerInput = $true
                screenshot = [IO.Path]::GetFileName($pointerDraftShotPath)
            }
        }
        finally {
            $cancelDraft = Find-UiElementOnce -Root $window -Name 'Cancel canvas pattern drafting'
            if ($cancelDraft -and -not $cancelDraft.Current.IsOffscreen -and $cancelDraft.Current.IsEnabled) {
                try {
                    Invoke-UiElement -Element $cancelDraft
                }
                catch {
                }
            }
            for ($cleanupAttempt = 0; $cleanupAttempt -lt 4; $cleanupAttempt++) {
                $currentCount = [int]((Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -replace '\D', '')
                if ($currentCount -le $originalCount) {
                    break
                }
                $cleanupUndo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
                Invoke-UiElement -Element $cleanupUndo
                Wait-ForCondition -Description 'pointer-draft failure cleanup to reduce the piece count' -Condition {
                    [int]((Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -replace '\D', '') -lt $currentCount
                } | Out-Null
            }
        }
        $pointerDraftResult
    }

    Invoke-UiCheck -Name '2D calibrated actual-size workflow' -Check {
        $fit = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFitButton'
        Invoke-UiElement -Element $fit
        $zoomText = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternZoomText'
        $originalFitZoom = $zoomText.Current.Name
        $actualSizeButton = Find-UiElement -Root $window -Name 'Show pattern at calibrated actual size'
        $originalCalibrationAvailable = $actualSizeButton.Current.IsEnabled

        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Calibrate pattern physical scale')
        $measurementBox = Find-UiElement -Root $window -Name 'Measured calibration ruler length in centimeters'
        $measurementRange = Get-UiPattern -Element $measurementBox -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $originalMeasuredLength = [double]$measurementRange.Current.Value
        $measurementRange.SetValue(10.0)
        Wait-ForCondition -Description 'calibration ruler measurement to become 10 centimeters' -Condition {
            [math]::Abs([double]$measurementRange.Current.Value - 10.0) -lt 0.001
        } | Out-Null
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Save and show 1:1')

        Wait-ForCondition -Description 'calibrated actual-size zoom to reach 800 percent' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternZoomText').Current.Name -eq '800%'
        } | Out-Null
        $calibratedScaleName = '10 cm grid | 50 cm major | calibrated 1:1'
        Wait-ForCondition -Description 'scale label to report calibrated 1:1' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'CanvasScaleText').Current.Name -eq $calibratedScaleName
        } | Out-Null

        Invoke-UiElement -Element $fit
        Wait-ForCondition -Description 'Fit to leave calibrated actual size' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternZoomText').Current.Name -eq $originalFitZoom
        } | Out-Null
        Invoke-UiElement -Element $actualSizeButton
        Wait-ForCondition -Description '1:1 command to restore calibrated actual size' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternZoomText').Current.Name -eq '800%'
        } | Out-Null

        $actualSizeShotPath = Join-Path $evidenceDirectory '11-2d-calibrated-actual-size.png'
        Save-WindowScreenshot -Window $window -Path $actualSizeShotPath
        $script:screenshots.Add([pscustomobject]@{ name = '2d-calibrated-actual-size'; file = [IO.Path]::GetFileName($actualSizeShotPath) })

        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Calibrate pattern physical scale')
        if ($originalCalibrationAvailable) {
            $restoreMeasurementBox = Find-UiElement -Root $window -Name 'Measured calibration ruler length in centimeters'
            $restoreMeasurementRange = Get-UiPattern -Element $restoreMeasurementBox -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
            $restoreMeasurementRange.SetValue($originalMeasuredLength)
            Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Save and show 1:1')
        }
        else {
            Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Clear calibration')
        }
        Invoke-UiElement -Element $fit
        Wait-ForCondition -Description 'scale calibration test to restore the fitted zoom' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternZoomText').Current.Name -eq $originalFitZoom
        } | Out-Null
        Wait-ForCondition -Description 'scale calibration availability to restore' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternActualSizeButton').Current.IsEnabled -eq $originalCalibrationAvailable
        } | Out-Null

        [ordered]@{
            calibrationRulerDips = 320
            enteredMeasuredLengthCm = 10.0
            calibratedDipsPerCentimeter = 32.0
            actualSizeZoom = '800%'
            originalCalibrationAvailable = $originalCalibrationAvailable
            restoredFitZoom = $originalFitZoom
            screenshot = [IO.Path]::GetFileName($actualSizeShotPath)
        }
    }

    Invoke-UiCheck -Name '2D internal line create update delete undo and redo' -Check {
        $piece = Find-UiElement -Root $window -Name 'Back Torso'
        Invoke-UiElement -Element $piece
        $addInternalLine = Find-UiElement -Root $window -Name 'Add a precise internal line to the selected pattern piece'
        Invoke-UiElement -Element $addInternalLine
        $dialogPrimary = Find-UiElement -Root $window -Name 'Add line'
        $lineName = Find-UiElement -Root $window -Name 'Internal line name'
        if ($lineName.Current.Name -ne 'Internal line name') {
            throw 'The internal line dialog did not expose its named line field.'
        }
        Invoke-UiElement -Element $dialogPrimary

        $lineAutomationName = 'Back Torso internal construction line Construction line 1'
        Wait-ForCondition -Description 'new internal construction line to appear on Back Torso' -Condition {
            Find-UiElementOnce -Root $window -Name $lineAutomationName
        } | Out-Null

        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to remove the internal construction line' -Condition {
            -not (Find-UiElementOnce -Root $window -Name $lineAutomationName)
        } | Out-Null
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'Redo to restore the internal construction line' -Condition {
            Find-UiElementOnce -Root $window -Name $lineAutomationName
        } | Out-Null

        Invoke-UiElement -Element $addInternalLine
        Select-UiComboBoxItem -Root $window -ComboBoxName 'Select a new or existing straight internal line' -ItemName 'Edit: Construction line 1'
        Set-UiTextValue -Element (Find-UiElement -Root $window -Name 'Internal line name') -Value 'Shoulder balance guide'
        Select-UiComboBoxItem -Root $window -ComboBoxName 'Internal line purpose' -ItemName 'Fold'
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Apply line')

        $updatedLineAutomationName = 'Back Torso internal fold line Shoulder balance guide'
        Wait-ForCondition -Description 'updated fold line to replace the original construction line' -Condition {
            (Find-UiElementOnce -Root $window -Name $updatedLineAutomationName) -and
            -not (Find-UiElementOnce -Root $window -Name $lineAutomationName)
        } | Out-Null

        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to restore the original construction line' -Condition {
            (Find-UiElementOnce -Root $window -Name $lineAutomationName) -and
            -not (Find-UiElementOnce -Root $window -Name $updatedLineAutomationName)
        } | Out-Null
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'Redo to restore the updated fold line' -Condition {
            (Find-UiElementOnce -Root $window -Name $updatedLineAutomationName) -and
            -not (Find-UiElementOnce -Root $window -Name $lineAutomationName)
        } | Out-Null

        $lineShotPath = Join-Path $evidenceDirectory '12-2d-internal-line.png'
        Save-WindowScreenshot -Window $window -Path $lineShotPath
        $script:screenshots.Add([pscustomobject]@{ name = '2d-internal-line'; file = [IO.Path]::GetFileName($lineShotPath) })

        Invoke-UiElement -Element $addInternalLine
        Select-UiComboBoxItem -Root $window -ComboBoxName 'Select a new or existing straight internal line' -ItemName 'Edit: Shoulder balance guide'
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Delete line')
        Wait-ForCondition -Description 'Delete to remove the updated fold line' -Condition {
            -not (Find-UiElementOnce -Root $window -Name $updatedLineAutomationName)
        } | Out-Null
        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to restore the deleted fold line' -Condition {
            Find-UiElementOnce -Root $window -Name $updatedLineAutomationName
        } | Out-Null
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'final Redo to leave Back Torso without the test line' -Condition {
            -not (Find-UiElementOnce -Root $window -Name $updatedLineAutomationName)
        } | Out-Null

        [ordered]@{
            piece = 'Back Torso'
            createdLine = 'Construction line 1'
            updatedLine = 'Shoulder balance guide'
            updatedPurpose = 'fold'
            deleted = $true
            restored = $true
            screenshot = [IO.Path]::GetFileName($lineShotPath)
        }
    }

    Invoke-UiCheck -Name '2D dart create update delete undo and redo' -Check {
        $piece = Find-UiElement -Root $window -Name 'Back Torso'
        Invoke-UiElement -Element $piece
        $addDart = Find-UiElement -Root $window -Name 'Add a precise dart to the selected pattern piece'
        Invoke-UiElement -Element $addDart
        $dialogPrimary = Find-UiElement -Root $window -Name 'Add dart'
        $dartName = Find-UiElement -Root $window -Name 'Dart name'
        if ($dartName.Current.Name -ne 'Dart name') {
            throw 'The dart dialog did not expose its named dart field.'
        }
        Invoke-UiElement -Element $dialogPrimary

        $firstLegName = 'Back Torso dart Dart 1 first leg'
        $secondLegName = 'Back Torso dart Dart 1 second leg'
        Wait-ForCondition -Description 'new dart legs to appear on Back Torso' -Condition {
            (Find-UiElementOnce -Root $window -Name $firstLegName) -and
            (Find-UiElementOnce -Root $window -Name $secondLegName)
        } | Out-Null

        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to remove both dart legs' -Condition {
            -not (Find-UiElementOnce -Root $window -Name $firstLegName) -and
            -not (Find-UiElementOnce -Root $window -Name $secondLegName)
        } | Out-Null
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'Redo to restore both dart legs' -Condition {
            (Find-UiElementOnce -Root $window -Name $firstLegName) -and
            (Find-UiElementOnce -Root $window -Name $secondLegName)
        } | Out-Null

        Invoke-UiElement -Element $addDart
        Select-UiComboBoxItem -Root $window -ComboBoxName 'Select a new or existing dart' -ItemName 'Edit: Dart 1'
        Set-UiTextValue -Element (Find-UiElement -Root $window -Name 'Dart name') -Value 'Waist shaping guide'
        Select-UiComboBoxItem -Root $window -ComboBoxName 'Dart fold direction' -ItemName 'Right'
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Apply dart')

        $updatedFirstLegName = 'Back Torso dart Waist shaping guide first leg'
        $updatedSecondLegName = 'Back Torso dart Waist shaping guide second leg'
        Wait-ForCondition -Description 'updated dart legs to replace the original dart legs' -Condition {
            (Find-UiElementOnce -Root $window -Name $updatedFirstLegName) -and
            (Find-UiElementOnce -Root $window -Name $updatedSecondLegName) -and
            -not (Find-UiElementOnce -Root $window -Name $firstLegName) -and
            -not (Find-UiElementOnce -Root $window -Name $secondLegName)
        } | Out-Null

        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to restore the original dart legs' -Condition {
            (Find-UiElementOnce -Root $window -Name $firstLegName) -and
            (Find-UiElementOnce -Root $window -Name $secondLegName) -and
            -not (Find-UiElementOnce -Root $window -Name $updatedFirstLegName) -and
            -not (Find-UiElementOnce -Root $window -Name $updatedSecondLegName)
        } | Out-Null
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'Redo to restore the updated dart legs' -Condition {
            (Find-UiElementOnce -Root $window -Name $updatedFirstLegName) -and
            (Find-UiElementOnce -Root $window -Name $updatedSecondLegName) -and
            -not (Find-UiElementOnce -Root $window -Name $firstLegName) -and
            -not (Find-UiElementOnce -Root $window -Name $secondLegName)
        } | Out-Null

        $dartShotPath = Join-Path $evidenceDirectory '13-2d-dart.png'
        Save-WindowScreenshot -Window $window -Path $dartShotPath
        $script:screenshots.Add([pscustomobject]@{ name = '2d-dart'; file = [IO.Path]::GetFileName($dartShotPath) })

        Invoke-UiElement -Element $addDart
        Select-UiComboBoxItem -Root $window -ComboBoxName 'Select a new or existing dart' -ItemName 'Edit: Waist shaping guide'
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Delete dart')
        Wait-ForCondition -Description 'Delete to remove the updated dart legs' -Condition {
            -not (Find-UiElementOnce -Root $window -Name $updatedFirstLegName) -and
            -not (Find-UiElementOnce -Root $window -Name $updatedSecondLegName)
        } | Out-Null
        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to restore the deleted dart legs' -Condition {
            (Find-UiElementOnce -Root $window -Name $updatedFirstLegName) -and
            (Find-UiElementOnce -Root $window -Name $updatedSecondLegName)
        } | Out-Null
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'final Redo to leave Back Torso without the test dart' -Condition {
            -not (Find-UiElementOnce -Root $window -Name $updatedFirstLegName) -and
            -not (Find-UiElementOnce -Root $window -Name $updatedSecondLegName)
        } | Out-Null

        [ordered]@{
            piece = 'Back Torso'
            createdDart = 'Dart 1'
            updatedDart = 'Waist shaping guide'
            construction = 'annotation'
            updatedFoldDirection = 'right'
            deleted = $true
            restored = $true
            screenshot = [IO.Path]::GetFileName($dartShotPath)
        }
    }

    Invoke-UiCheck -Name '2D existing-seam physical dart update undo and redo' -Check {
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Front Torso')
        $originalFirstLeg = 'Front Torso dart Left side bust dart first leg'
        $originalSecondLeg = 'Front Torso dart Left side bust dart second leg'
        Wait-ForCondition -Description 'production left bust dart legs to be visible' -Condition {
            (Find-UiElementOnce -Root $window -Name $originalFirstLeg) -and
            (Find-UiElementOnce -Root $window -Name $originalSecondLeg)
        } | Out-Null

        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Add a precise dart to the selected pattern piece')
        Select-UiComboBoxItem -Root $window -ComboBoxName 'Select a new or existing dart' -ItemName 'Edit: Left side bust dart'
        Assert-UiComboBoxItemSelected -Root $window -ComboBoxName 'Dart construction mode' -ItemName 'Cut and sew existing seam'
        Set-UiTextValue -Element (Find-UiElement -Root $window -Name 'Dart name') -Value 'Left side bust dart verified'
        Select-UiComboBoxItem -Root $window -ComboBoxName 'Dart fold direction' -ItemName 'Right'
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Apply dart')

        $updatedFirstLeg = 'Front Torso dart Left side bust dart verified first leg'
        $updatedSecondLeg = 'Front Torso dart Left side bust dart verified second leg'
        Wait-ForCondition -Description 'updated sewn-edge bust dart legs to replace the originals' -Condition {
            (Find-UiElementOnce -Root $window -Name $updatedFirstLeg) -and
            (Find-UiElementOnce -Root $window -Name $updatedSecondLeg) -and
            -not (Find-UiElementOnce -Root $window -Name $originalFirstLeg) -and
            -not (Find-UiElementOnce -Root $window -Name $originalSecondLeg)
        } | Out-Null

        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to restore the original sewn-edge bust dart' -Condition {
            (Find-UiElementOnce -Root $window -Name $originalFirstLeg) -and
            (Find-UiElementOnce -Root $window -Name $originalSecondLeg) -and
            -not (Find-UiElementOnce -Root $window -Name $updatedFirstLeg)
        } | Out-Null
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'Redo to restore the updated sewn-edge bust dart' -Condition {
            (Find-UiElementOnce -Root $window -Name $updatedFirstLeg) -and
            (Find-UiElementOnce -Root $window -Name $updatedSecondLeg)
        } | Out-Null

        Invoke-UiElement -Element (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFrameSelectedButton')
        $existingDartShotPath = Join-Path $evidenceDirectory '14-2d-existing-seam-physical-dart.png'
        Save-WindowScreenshot -Window $window -Path $existingDartShotPath
        $script:screenshots.Add([pscustomobject]@{ name = '2d-existing-seam-physical-dart'; file = [IO.Path]::GetFileName($existingDartShotPath) })

        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'final Undo to restore the original production bust dart' -Condition {
            (Find-UiElementOnce -Root $window -Name $originalFirstLeg) -and
            (Find-UiElementOnce -Root $window -Name $originalSecondLeg) -and
            -not (Find-UiElementOnce -Root $window -Name $updatedFirstLeg)
        } | Out-Null
        Invoke-UiElement -Element (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFitButton')

        [ordered]@{
            piece = 'Front Torso'
            dart = 'Left side bust dart'
            constructionMode = 'sewn-edge'
            updatedFoldDirection = 'right'
            restored = $true
            screenshot = [IO.Path]::GetFileName($existingDartShotPath)
        }
    }

    Invoke-UiCheck -Name '2D free-edge physical dart creation undo and redo' -Check {
        Invoke-UiElement -Element (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFitButton')
        $originalPieceCount = [int]((Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -replace '\D', '')
        $assemblyMode = Find-UiElement -Root $window -Name 'Inspect garment seam graph'
        $assemblyOriginal = Get-ToggleState -Element $assemblyMode
        Set-ToggleState -Element $assemblyMode -State 'On'
        $assemblySummary = Find-UiElementByAutomationId -Root $window -AutomationId 'AssemblySummaryText'
        if ($assemblySummary.Current.Name -notmatch '^(\d+) permanent seams') {
            throw "Cannot read the initial physical-dart seam count from '$($assemblySummary.Current.Name)'."
        }
        $originalSeamCount = [int]$Matches[1]
        Set-ToggleState -Element $assemblyMode -State 'Off'
        $freeDartResult = $null
        try {
            Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Draw a polygon pattern piece directly on the canvas')
        $xCoordinate = Find-UiElement -Root $window -Name 'Canvas polygon point X coordinate in centimeters'
        $yCoordinate = Find-UiElement -Root $window -Name 'Canvas polygon point Y coordinate in centimeters'
        $addPoint = Find-UiElement -Root $window -Name 'Add the entered point to the canvas polygon'
        $finish = Find-UiElement -Root $window -Name 'Finish the polygon pattern piece'
        $xRange = Get-UiPattern -Element $xCoordinate -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $yRange = Get-UiPattern -Element $yCoordinate -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $coordinates = @(
            @(120.0, 140.0),
            @(130.0, 140.0),
            @(130.0, 150.0),
            @(120.0, 150.0)
        )
        foreach ($coordinate in $coordinates) {
            $xRange.SetValue([double]$coordinate[0])
            $yRange.SetValue([double]$coordinate[1])
            Invoke-UiElement -Element $addPoint
        }
        Invoke-UiElement -Element $finish
        $createdPieceCount = $originalPieceCount + 1
        Wait-ForCondition -Description 'temporary physical-dart polygon to be created' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq "$createdPieceCount pieces"
        } | Out-Null

        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Add a precise dart to the selected pattern piece')
        Set-UiTextValue -Element (Find-UiElement -Root $window -Name 'Dart name') -Value 'Free edge proof dart'
        Select-UiComboBoxItem -Root $window -ComboBoxName 'Dart construction mode' -ItemName 'Cut and sew free edge'
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Add dart')

            $freeFirstLeg = 'Canvas polygon 15 dart Free edge proof dart first leg'
            $freeSecondLeg = 'Canvas polygon 15 dart Free edge proof dart second leg'
            $physicalSeamCount = $originalSeamCount + 1
            Wait-ForCondition -Description 'free-edge dart legs to materialize in the 2D pattern' -Condition {
                (Find-UiElementOnce -Root $window -Name $freeFirstLeg) -and
                (Find-UiElementOnce -Root $window -Name $freeSecondLeg)
            } | Out-Null

            Invoke-UiElement -Element (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFrameSelectedButton')
            $freeDartShotPath = Join-Path $evidenceDirectory '14-2d-free-edge-physical-dart.png'
            Save-WindowScreenshot -Window $window -Path $freeDartShotPath
            $script:screenshots.Add([pscustomobject]@{ name = '2d-free-edge-physical-dart'; file = [IO.Path]::GetFileName($freeDartShotPath) })

            Set-ToggleState -Element $assemblyMode -State 'On'
            Wait-ForCondition -Description 'free-edge dart to add one physical closure seam' -Condition {
                (Find-UiElementByAutomationId -Root $window -AutomationId 'AssemblySummaryText').Current.Name -like "$physicalSeamCount permanent seams*"
            } | Out-Null

        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to remove the free-edge dart closure seam' -Condition {
            -not (Find-UiElementOnce -Root $window -Name $freeFirstLeg) -and
            (Find-UiElementByAutomationId -Root $window -AutomationId 'AssemblySummaryText').Current.Name -like "$originalSeamCount permanent seams*"
        } | Out-Null
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'Redo to restore the free-edge dart closure seam' -Condition {
            (Find-UiElementOnce -Root $window -Name $freeFirstLeg) -and
            (Find-UiElementByAutomationId -Root $window -AutomationId 'AssemblySummaryText').Current.Name -like "$physicalSeamCount permanent seams*"
        } | Out-Null
        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'final Undo to remove the free-edge dart' -Condition {
            -not (Find-UiElementOnce -Root $window -Name $freeFirstLeg) -and
            (Find-UiElementByAutomationId -Root $window -AutomationId 'AssemblySummaryText').Current.Name -like "$originalSeamCount permanent seams*"
        } | Out-Null
        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'final Undo to remove the temporary physical-dart polygon' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq "$originalPieceCount pieces"
        } | Out-Null
        Set-ToggleState -Element $assemblyMode -State $assemblyOriginal
        Invoke-UiElement -Element (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFitButton')

            $freeDartResult = [ordered]@{
                piece = 'Canvas polygon 15'
                dart = 'Free edge proof dart'
                constructionMode = 'sewn-free-edge'
                originalSeamCount = $originalSeamCount
                physicalSeamCount = $physicalSeamCount
                restoredPieceCount = $originalPieceCount
                screenshot = [IO.Path]::GetFileName($freeDartShotPath)
            }
        }
        finally {
            if ($null -eq $freeDartResult) {
                try {
                    Set-ToggleState -Element $assemblyMode -State 'Off'
                }
                catch {
                }
                $cancelDraft = Find-UiElementOnce -Root $window -Name 'Cancel canvas pattern drafting'
                if ($cancelDraft -and -not $cancelDraft.Current.IsOffscreen -and $cancelDraft.Current.IsEnabled) {
                    try {
                        Invoke-UiElement -Element $cancelDraft
                    }
                    catch {
                    }
                }
                for ($cleanupAttempt = 0; $cleanupAttempt -lt 5; $cleanupAttempt++) {
                    $currentPieceCount = [int]((Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -replace '\D', '')
                    if ($currentPieceCount -le $originalPieceCount) {
                        break
                    }
                    $cleanupUndo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
                    if (-not $cleanupUndo.Current.IsEnabled) {
                        break
                    }
                    Invoke-UiElement -Element $cleanupUndo
                    Start-Sleep -Milliseconds 300
                }
                try {
                    Set-ToggleState -Element $assemblyMode -State $assemblyOriginal
                    Invoke-UiElement -Element (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFitButton')
                }
                catch {
                }
            }
        }
        $freeDartResult
    }

    Invoke-UiCheck -Name '2D free sewing creation undo and redo' -Check {
        $fit = Find-UiElementByAutomationId -Root $window -AutomationId 'PatternFitButton'
        Invoke-UiElement -Element $fit
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Draw a polygon pattern piece directly on the canvas')
        $xCoordinate = Find-UiElement -Root $window -Name 'Canvas polygon point X coordinate in centimeters'
        $yCoordinate = Find-UiElement -Root $window -Name 'Canvas polygon point Y coordinate in centimeters'
        $addPoint = Find-UiElement -Root $window -Name 'Add the entered point to the canvas polygon'
        $finish = Find-UiElement -Root $window -Name 'Finish the polygon pattern piece'
        $xRange = Get-UiPattern -Element $xCoordinate -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $yRange = Get-UiPattern -Element $yCoordinate -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $coordinates = @(
            @(105.0, 125.0),
            @(115.0, 125.0),
            @(115.0, 135.0),
            @(105.0, 135.0)
        )
        foreach ($coordinate in $coordinates) {
            $xRange.SetValue([double]$coordinate[0])
            $yRange.SetValue([double]$coordinate[1])
            Wait-ForCondition -Description 'free sewing polygon coordinates to commit' -Condition {
                ([math]::Abs([double]$xRange.Current.Value - [double]$coordinate[0]) -lt 0.001) -and
                ([math]::Abs([double]$yRange.Current.Value - [double]$coordinate[1]) -lt 0.001)
            } | Out-Null
            Invoke-UiElement -Element $addPoint
        }
        Invoke-UiElement -Element $finish
        Wait-ForCondition -Description 'temporary free sewing polygon to be created' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq '15 pieces'
        } | Out-Null

        $editMode = Find-UiElement -Root $window -Name 'Edit pattern points'
        $editOriginal = Get-ToggleState -Element $editMode
        Set-ToggleState -Element $editMode -State 'On'
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Canvas polygon 15 edge-1 endpoint')
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Mark selected edge as the first free sewing side')
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Canvas polygon 15 edge-3 endpoint')
        Invoke-UiElement -Element (Find-UiElement -Root $window -Name 'Sew the marked edge to the selected edge')

        $assemblyMode = Find-UiElement -Root $window -Name 'Inspect garment seam graph'
        $assemblyOriginal = Get-ToggleState -Element $assemblyMode
        Set-ToggleState -Element $assemblyMode -State 'On'
        $summary = Find-UiElementByAutomationId -Root $window -AutomationId 'AssemblySummaryText'
        if ($summary.Current.Name -notmatch '^(\d+) permanent seams') {
            throw "Cannot read the assembly seam count from '$($summary.Current.Name)'."
        }
        $createdSeamCount = [int]$Matches[1]
        $seamShotPath = Join-Path $evidenceDirectory '14-2d-free-sewing.png'
        Save-WindowScreenshot -Window $window -Path $seamShotPath
        $script:screenshots.Add([pscustomobject]@{ name = '2d-free-sewing'; file = [IO.Path]::GetFileName($seamShotPath) })

        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to remove the free sewing seam' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'AssemblySummaryText').Current.Name -like "$($createdSeamCount - 1) permanent seams*"
        } | Out-Null
        $redo = Find-UiElement -Root $window -Name 'Redo pattern geometry edit'
        Invoke-UiElement -Element $redo
        Wait-ForCondition -Description 'Redo to restore the free sewing seam' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'AssemblySummaryText').Current.Name -like "$createdSeamCount permanent seams*"
        } | Out-Null
        $undo = Find-UiElement -Root $window -Name 'Undo pattern geometry edit'
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'final seam Undo before removing the temporary piece' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'AssemblySummaryText').Current.Name -like "$($createdSeamCount - 1) permanent seams*"
        } | Out-Null
        Invoke-UiElement -Element $undo
        Wait-ForCondition -Description 'Undo to remove the temporary free sewing polygon' -Condition {
            (Find-UiElementByAutomationId -Root $window -AutomationId 'PatternPieceCountText').Current.Name -eq '14 pieces'
        } | Out-Null
        Set-ToggleState -Element $assemblyMode -State $assemblyOriginal
        Set-ToggleState -Element $editMode -State $editOriginal

        [ordered]@{
            piece = 'Canvas polygon 15'
            sewnEdges = @('edge-1', 'edge-3')
            createdSeamCount = $createdSeamCount
            restoredPieceCount = 14
            screenshot = [IO.Path]::GetFileName($seamShotPath)
        }
    }

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

    Invoke-UiCheck -Name '3D avatar follows edited measurements' -Check {
        $heightSlider = Find-UiElement -Root $window -Name 'Height in centimeters'
        $heightRange = Get-UiPattern -Element $heightSlider -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $originalHeight = [double]$heightRange.Current.Value
        $step = [math]::Max([double]$heightRange.Current.SmallChange, 0.1)
        $changedHeight = if ($originalHeight + $step -le [double]$heightRange.Current.Maximum) {
            $originalHeight + $step
        }
        else {
            $originalHeight - $step
        }
        $tab3d = Find-UiElement -Root $window -Name '3D DRAPE'
        $tab2d = Find-UiElement -Root $window -Name '2D FLAT'
        try {
            $heightRange.SetValue($changedHeight)
            Wait-ForCondition -Description 'height slider to invalidate the fitted avatar candidate' -Condition {
                [math]::Abs([double]$heightRange.Current.Value - $changedHeight) -lt 0.001
            } | Out-Null
            Invoke-UiElement -Element $tab3d
            $avatarState = Find-UiElementByAutomationId -Root $window -AutomationId 'DrapeAvatarPreviewState' -TimeoutSeconds 120
            $changedState = Wait-ForCondition -Description '3D preview to display the editable measurement mesh' -TimeoutSeconds 120 -Condition {
                $currentName = $avatarState.Current.Name
                if ($currentName -like 'Avatar preview: editable measurement mesh*') { $currentName } else { $null }
            }
            $fitCamera = Find-UiElementByAutomationId -Root $window -AutomationId 'DrapeFitCameraButton' -TimeoutSeconds 120
            Invoke-UiElement -Element $fitCamera
            Start-Sleep -Seconds 4
            $changedShotPath = Join-Path $evidenceDirectory '15-3d-edited-measurement-avatar.png'
            Save-WindowScreenshot -Window $window -Path $changedShotPath
            $drapeViewport = Find-UiElement -Root $window -Name 'Internal browser cloth diagnostic'
            $changedRendering = Assert-RenderedScreenshotRegion -Path $changedShotPath -Window $window -Element $drapeViewport -Description 'Edited measurement avatar viewport'
            $script:screenshots.Add([pscustomobject]@{ name = '3d-edited-measurement-avatar'; file = [IO.Path]::GetFileName($changedShotPath) })
        }
        finally {
            try {
                $heightRange.SetValue($originalHeight)
                Wait-ForCondition -Description 'height slider to restore after 3D avatar proof' -Condition {
                    [math]::Abs([double]$heightRange.Current.Value - $originalHeight) -lt 0.001
                } | Out-Null
                Invoke-UiElement -Element $tab3d
                $avatarState = Find-UiElementByAutomationId -Root $window -AutomationId 'DrapeAvatarPreviewState' -TimeoutSeconds 120
                $restoredState = Wait-ForCondition -Description '3D preview to restore the fitted Antonia candidate' -TimeoutSeconds 120 -Condition {
                    $currentName = $avatarState.Current.Name
                    if ($currentName -like 'Avatar preview: fitted Antonia candidate*') { $currentName } else { $null }
                }
                $fitCamera = Find-UiElementByAutomationId -Root $window -AutomationId 'DrapeFitCameraButton' -TimeoutSeconds 120
                Invoke-UiElement -Element $fitCamera
                Start-Sleep -Seconds 4
                $restoredShotPath = Join-Path $evidenceDirectory '16-3d-restored-fitted-avatar.png'
                Save-WindowScreenshot -Window $window -Path $restoredShotPath
                $drapeViewport = Find-UiElement -Root $window -Name 'Internal browser cloth diagnostic'
                $restoredRendering = Assert-RenderedScreenshotRegion -Path $restoredShotPath -Window $window -Element $drapeViewport -Description 'Restored fitted avatar viewport'
                $script:screenshots.Add([pscustomobject]@{ name = '3d-restored-fitted-avatar'; file = [IO.Path]::GetFileName($restoredShotPath) })
            }
            finally {
                Invoke-UiElement -Element $tab2d
                Find-UiElement -Root $window -Name 'Interactive two dimensional pattern layout' | Out-Null
            }
        }
        [ordered]@{
            originalHeight = $originalHeight
            changedHeight = $changedHeight
            changedState = $changedState
            restoredState = $restoredState
            changedRendering = $changedRendering
            restoredRendering = $restoredRendering
            changedScreenshot = [IO.Path]::GetFileName($changedShotPath)
            restoredScreenshot = [IO.Path]::GetFileName($restoredShotPath)
        }
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
    }

    Invoke-UiCheck -Name 'SVG export through packaged file picker' -Check {
        $exportPath = Join-Path $evidenceDirectory 'pattern-round-trip.svg'
        $documentsDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
        $pickerFileName = "pattern-round-trip-$($request.runId).svg"
        $pickerPath = Join-Path $documentsDirectory $pickerFileName
        if (Test-Path -LiteralPath $exportPath) {
            throw "Refusing to overwrite existing export evidence: $exportPath"
        }
        if (Test-Path -LiteralPath $pickerPath) {
            throw "Refusing to overwrite existing picker export: $pickerPath"
        }
        $saveDialog = $null
        $pickerCompleted = $false
        try {
            $exportButton = Find-UiElementByAutomationId -Root $window -AutomationId 'ExportPatternButton'
            Invoke-GuestPointerElement -Window $window -Element $exportButton
            $saveDialog = Find-UiElement -Root $automationRoot -Name 'Save As' -TimeoutSeconds 30
            $fileNameHost = Find-UiDescendantByAutomationId -Root $saveDialog -AutomationId 'FileNameControlHost'
            if (-not $fileNameHost) {
                $script:uiTreeNodeCount = 0
                Convert-UiTreeNode -Element $saveDialog |
                    ConvertTo-Json -Depth 20 |
                    Set-Content -LiteralPath (Join-Path $evidenceDirectory 'ui-tree-save-as-unexpected.json') -Encoding utf8
                throw 'The packaged SVG picker did not expose its file-name field.'
            }
            $fileNameEdit = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetFirstChild($fileNameHost)
            if (-not $fileNameEdit) {
                throw 'The packaged SVG picker file-name host did not expose its editable child.'
            }
            $fileNameEdit.SetFocus()
            Start-Sleep -Milliseconds 100
            [System.Windows.Forms.SendKeys]::SendWait('^a')
            [System.Windows.Forms.SendKeys]::SendWait($pickerFileName)
            Start-Sleep -Milliseconds 150
            Invoke-GuestPointerElement -Window $saveDialog -Element (Find-UiElement -Root $saveDialog -Name 'Save')
            Wait-ForCondition -Description 'packaged SVG export file' -TimeoutSeconds 30 -Condition {
                Test-Path -LiteralPath $pickerPath
            } | Out-Null
            $pickerCompleted = $true
            Copy-Item -LiteralPath $pickerPath -Destination $exportPath
        }
        finally {
            if (-not $pickerCompleted -and $saveDialog) {
                try {
                    $pickerWindowPattern = Get-UiPattern -Element $saveDialog -Pattern ([System.Windows.Automation.WindowPattern]::Pattern) -PatternName 'WindowPattern'
                    $pickerWindowPattern.Close()
                    Wait-ForCondition -Description 'failed SVG picker to close' -TimeoutSeconds 10 -Condition {
                        -not (Find-UiElementOnce -Root $automationRoot -Name 'Save As')
                    } | Out-Null
                }
                catch {
                    try {
                        Invoke-GuestPointerElement -Window $saveDialog -Element (Find-UiElement -Root $saveDialog -Name 'Cancel' -TimeoutSeconds 5)
                    }
                    catch {
                    }
                }
            }
            if (Test-Path -LiteralPath $pickerPath) {
                Remove-Item -LiteralPath $pickerPath -Force
            }
        }
        Find-UiElement -Root $window -Name 'Pattern exported' | Out-Null
        $svg = Get-Content -LiteralPath $exportPath -Raw
        if ($svg -notlike '*<svg*' -or
            $svg -notlike '*Patternal patterna.garment/1.1*' -or
            $svg -notlike '*14 simulation panels*' -or
            $svg -notlike '*38 seams*') {
            throw 'The packaged SVG export is missing its expected document or construction metadata.'
        }
        [ordered]@{
            file = [IO.Path]::GetFileName($exportPath)
            bytes = (Get-Item -LiteralPath $exportPath).Length
            panels = 14
            seams = 38
        }
    }

    Invoke-UiCheck -Name 'Named project Save As and Open round trip' -Check {
        $projectEvidencePath = Join-Path $evidenceDirectory 'pattern-round-trip.patterna'
        $documentsDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
        $pickerFileName = "pattern-round-trip-$($request.runId).patterna"
        $pickerPath = Join-Path $documentsDirectory $pickerFileName
        if (Test-Path -LiteralPath $projectEvidencePath) {
            throw "Refusing to overwrite existing project evidence: $projectEvidencePath"
        }
        if (Test-Path -LiteralPath $pickerPath) {
            throw "Refusing to overwrite existing picker project: $pickerPath"
        }

        $activeWindow = Wait-ForCondition -Description 'Patternal window before named project round trip' -TimeoutSeconds 30 -Condition {
            $nameCondition = [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::NameProperty,
                [string]$request.expectedWindowTitle)
            $automationRoot.FindFirst([System.Windows.Automation.TreeScope]::Children, $nameCondition)
        }
        $height = Find-UiElement -Root $activeWindow -Name 'Height in centimeters'
        $heightRange = Get-UiPattern -Element $height -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $link = Find-UiElement -Root $activeWindow -Name 'Link proportional measurements'
        $fabricWeight = Find-UiElement -Root $activeWindow -Name 'Fabric weight in grams per square meter'
        $fabricWeightRange = Get-UiPattern -Element $fabricWeight -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $originalHeight = [double]$heightRange.Current.Value
        $originalLink = Get-ToggleState -Element $link
        $originalFabricWeight = [double]$fabricWeightRange.Current.Value
        $savedHeight = if ($originalHeight + 0.5 -le [double]$heightRange.Current.Maximum) {
            $originalHeight + 0.5
        }
        else {
            $originalHeight - 0.5
        }
        $savedFabricWeight = if ($originalFabricWeight + 5 -le [double]$fabricWeightRange.Current.Maximum) {
            $originalFabricWeight + 5
        }
        else {
            $originalFabricWeight - 5
        }
        $disturbedHeight = if ($savedHeight + 0.5 -le [double]$heightRange.Current.Maximum) {
            $savedHeight + 0.5
        }
        else {
            $savedHeight - 0.5
        }
        $disturbedFabricWeight = if ($savedFabricWeight + 5 -le [double]$fabricWeightRange.Current.Maximum) {
            $savedFabricWeight + 5
        }
        else {
            $savedFabricWeight - 5
        }

        $saveDialog = $null
        $openDialog = $null
        try {
            Set-ToggleState -Element $link -State 'Off'
            $heightRange.SetValue($savedHeight)
            $fabricWeightRange.SetValue($savedFabricWeight)
            Wait-ForCondition -Description 'named project values before Save As' -Condition {
                if ([math]::Abs([double]$heightRange.Current.Value - $savedHeight) -lt 0.001 -and
                    [math]::Abs([double]$fabricWeightRange.Current.Value - $savedFabricWeight) -lt 0.001) {
                    $true
                }
                else {
                    $null
                }
            } | Out-Null

            $saveProjectButton = Find-UiElementByAutomationId -Root $activeWindow -AutomationId 'SavePatternProjectAsButton'
            Invoke-GuestPointerElement -Window $activeWindow -Element $saveProjectButton
            $saveDialog = Find-UiElement -Root $automationRoot -Name 'Save As' -TimeoutSeconds 30
            $fileNameHost = Find-UiDescendantByAutomationId -Root $saveDialog -AutomationId 'FileNameControlHost'
            if (-not $fileNameHost) {
                throw 'The packaged project Save As picker did not expose its file-name field.'
            }
            $fileNameEdit = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetFirstChild($fileNameHost)
            if (-not $fileNameEdit) {
                throw 'The packaged project Save As picker file-name host did not expose its editable child.'
            }
            $fileNameEdit.SetFocus()
            Start-Sleep -Milliseconds 100
            [System.Windows.Forms.SendKeys]::SendWait('^a')
            [System.Windows.Forms.SendKeys]::SendWait($pickerFileName)
            Start-Sleep -Milliseconds 150
            Invoke-GuestPointerElement -Window $saveDialog -Element (Find-UiElement -Root $saveDialog -Name 'Save')
            Wait-ForCondition -Description 'packaged Patterna project file' -TimeoutSeconds 30 -Condition {
                Test-Path -LiteralPath $pickerPath
            } | Out-Null
            Copy-Item -LiteralPath $pickerPath -Destination $projectEvidencePath
            Find-UiElement -Root $activeWindow -Name 'Project saved' | Out-Null

            $project = Get-Content -LiteralPath $projectEvidencePath -Raw | ConvertFrom-Json
            if ($project.schemaVersion -ne 'patterna.project/1.0' -or
                [math]::Abs([double]$project.height - $savedHeight) -ge 0.001 -or
                [math]::Abs([double]$project.fabricWeight - $savedFabricWeight) -ge 0.001 -or
                [bool]$project.linkedProportions -or
                -not $project.values.patternStructuralEdits -or
                -not $project.values.seamSideBReverseOverrides -or
                -not $project.values.closureStateOverrides) {
                throw 'The named project file is missing its schema, exact scalar state, or editable construction payload.'
            }

            $heightRange.SetValue($disturbedHeight)
            $fabricWeightRange.SetValue($disturbedFabricWeight)
            Set-ToggleState -Element $link -State 'On'
            Wait-ForCondition -Description 'disturbed values before project Open' -Condition {
                if ([math]::Abs([double]$heightRange.Current.Value - $disturbedHeight) -lt 0.001 -and
                    [math]::Abs([double]$fabricWeightRange.Current.Value - $disturbedFabricWeight) -lt 0.001 -and
                    (Get-ToggleState -Element $link) -eq 'On') {
                    $true
                }
                else {
                    $null
                }
            } | Out-Null

            $openProjectButton = Find-UiElementByAutomationId -Root $activeWindow -AutomationId 'OpenPatternProjectButton'
            Invoke-GuestPointerElement -Window $activeWindow -Element $openProjectButton
            $openDialog = Find-UiElement -Root $automationRoot -Name 'Open' -TimeoutSeconds 30
            $projectListItem = Find-UiElement -Root $openDialog -Name $pickerFileName -TimeoutSeconds 30
            Invoke-UiElement -Element $projectListItem
            Invoke-GuestPointerElement -Window $openDialog -Element (Find-UiElement -Root $openDialog -Name 'Open')
            try {
                Wait-ForCondition -Description 'named project values to restore after Open' -TimeoutSeconds 30 -Condition {
                    if ([math]::Abs([double]$heightRange.Current.Value - $savedHeight) -lt 0.001 -and
                        [math]::Abs([double]$fabricWeightRange.Current.Value - $savedFabricWeight) -lt 0.001 -and
                        (Get-ToggleState -Element $link) -eq 'Off') {
                        $true
                    }
                    else {
                        $null
                    }
                } | Out-Null
            }
            catch {
                $script:uiTreeNodeCount = 0
                Convert-UiTreeNode -Element $activeWindow |
                    ConvertTo-Json -Depth 20 |
                    Set-Content -LiteralPath (Join-Path $evidenceDirectory 'ui-tree-project-open-failure.json') -Encoding utf8
                $failureShotPath = Join-Path $evidenceDirectory '15-named-project-open-failure.png'
                Save-WindowScreenshot -Window $activeWindow -Path $failureShotPath
                $script:screenshots.Add([pscustomobject]@{ name = 'named-project-open-failure'; file = [IO.Path]::GetFileName($failureShotPath) })
                $errorNotice = Find-UiElementOnce -Root $activeWindow -Name 'Project could not be opened'
                if ($errorNotice) {
                    throw 'Patterna rejected the named project file. See ui-tree-project-open-failure.json for the product message.'
                }
                throw
            }
            Find-UiElement -Root $activeWindow -Name 'Project opened' | Out-Null
            Start-Sleep -Milliseconds 350

            $projectShotPath = Join-Path $evidenceDirectory '15-named-project-restored.png'
            Save-WindowScreenshot -Window $activeWindow -Path $projectShotPath
            $script:screenshots.Add([pscustomobject]@{ name = 'named-project-restored'; file = [IO.Path]::GetFileName($projectShotPath) })
            [ordered]@{
                file = [IO.Path]::GetFileName($projectEvidencePath)
                bytes = (Get-Item -LiteralPath $projectEvidencePath).Length
                schema = [string]$project.schemaVersion
                savedHeight = $savedHeight
                restoredHeight = [double]$heightRange.Current.Value
                savedFabricWeight = $savedFabricWeight
                restoredFabricWeight = [double]$fabricWeightRange.Current.Value
                linkedProportions = Get-ToggleState -Element $link
                screenshot = [IO.Path]::GetFileName($projectShotPath)
            }
        }
        finally {
            foreach ($dialog in @($saveDialog, $openDialog)) {
                if ($dialog) {
                    try {
                        $dialogWindowPattern = Get-UiPattern -Element $dialog -Pattern ([System.Windows.Automation.WindowPattern]::Pattern) -PatternName 'WindowPattern'
                        $dialogWindowPattern.Close()
                    }
                    catch {
                    }
                }
            }
            if ($activeWindow) {
                try {
                    $cleanupHeight = Find-UiElement -Root $activeWindow -Name 'Height in centimeters' -TimeoutSeconds 5
                    $cleanupHeightRange = Get-UiPattern -Element $cleanupHeight -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
                    $cleanupHeightRange.SetValue($originalHeight)
                    $cleanupLink = Find-UiElement -Root $activeWindow -Name 'Link proportional measurements' -TimeoutSeconds 5
                    Set-ToggleState -Element $cleanupLink -State $originalLink
                    $cleanupFabricWeight = Find-UiElement -Root $activeWindow -Name 'Fabric weight in grams per square meter' -TimeoutSeconds 5
                    $cleanupFabricWeightRange = Get-UiPattern -Element $cleanupFabricWeight -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
                    $cleanupFabricWeightRange.SetValue($originalFabricWeight)
                }
                catch {
                }
            }
            if (Test-Path -LiteralPath $pickerPath) {
                Remove-Item -LiteralPath $pickerPath -Force
            }
        }
    }

    Invoke-UiCheck -Name 'Local snapshot save and startup restore round trip' -Check {
        $activeWindow = Wait-ForCondition -Description 'Patternal window after SVG picker' -TimeoutSeconds 30 -Condition {
            $nameCondition = [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::NameProperty,
                [string]$request.expectedWindowTitle)
            $automationRoot.FindFirst([System.Windows.Automation.TreeScope]::Children, $nameCondition)
        }
        $activeProcess = Get-Process -Name Patternal -ErrorAction Stop | Select-Object -First 1
        $height = Find-UiElement -Root $activeWindow -Name 'Height in centimeters'
        $heightRange = Get-UiPattern -Element $height -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
        $originalHeight = [double]$heightRange.Current.Value
        $testHeight = if ($originalHeight + 0.5 -le [double]$heightRange.Current.Maximum) {
            $originalHeight + 0.5
        }
        else {
            $originalHeight - 0.5
        }
        $link = Find-UiElement -Root $activeWindow -Name 'Link proportional measurements'
        $originalLink = Get-ToggleState -Element $link
        $testSnapshotWasSaved = $false
        try {
            Set-ToggleState -Element $link -State 'Off'
            $heightRange.SetValue($testHeight)
            Wait-ForCondition -Description 'snapshot test height' -Condition {
                [math]::Abs([double]$heightRange.Current.Value - $testHeight) -lt 0.001
            } | Out-Null
            Invoke-UiElement -Element (Find-UiElementByAutomationId -Root $activeWindow -AutomationId 'SavePatternSnapshotButton')
            Find-UiElement -Root $activeWindow -Name 'Snapshot saved' | Out-Null
            $testSnapshotWasSaved = $true

            Stop-PatternalUiSession -Window $activeWindow -ProcessId $activeProcess.Id
            $restoredSession = Start-PatternalUiSession -Aumid $request.aumid -ExpectedWindowTitle $request.expectedWindowTitle
            $activeWindow = $restoredSession.Window
            $activeProcess = $restoredSession.Process
            $restoredHeight = Find-UiElement -Root $activeWindow -Name 'Height in centimeters'
            $restoredHeightRange = Get-UiPattern -Element $restoredHeight -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
            if ([math]::Abs([double]$restoredHeightRange.Current.Value - $testHeight) -ge 0.001) {
                throw "Saved height $testHeight did not restore after packaged relaunch."
            }
            $observedRestoredHeight = [double]$restoredHeightRange.Current.Value
            $restoredLink = Find-UiElement -Root $activeWindow -Name 'Link proportional measurements'
            if ((Get-ToggleState -Element $restoredLink) -ne 'Off') {
                throw 'The saved link-proportions state did not restore after packaged relaunch.'
            }

            $restoredHeightRange.SetValue($originalHeight)
            Wait-ForCondition -Description 'original snapshot height' -Condition {
                [math]::Abs([double]$restoredHeightRange.Current.Value - $originalHeight) -lt 0.001
            } | Out-Null
            Set-ToggleState -Element $restoredLink -State $originalLink
            Invoke-UiElement -Element (Find-UiElementByAutomationId -Root $activeWindow -AutomationId 'SavePatternSnapshotButton')
            Find-UiElement -Root $activeWindow -Name 'Snapshot saved' | Out-Null

            Stop-PatternalUiSession -Window $activeWindow -ProcessId $activeProcess.Id
            $finalSession = Start-PatternalUiSession -Aumid $request.aumid -ExpectedWindowTitle $request.expectedWindowTitle
            $activeWindow = $finalSession.Window
            $activeProcess = $finalSession.Process
            $finalHeight = Find-UiElement -Root $activeWindow -Name 'Height in centimeters'
            $finalHeightRange = Get-UiPattern -Element $finalHeight -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
            if ([math]::Abs([double]$finalHeightRange.Current.Value - $originalHeight) -ge 0.001) {
                throw 'The original snapshot height did not survive the cleanup relaunch.'
            }
            $finalLink = Find-UiElement -Root $activeWindow -Name 'Link proportional measurements'
            if ((Get-ToggleState -Element $finalLink) -ne $originalLink) {
                throw 'The original link-proportions state did not survive the cleanup relaunch.'
            }
            $script:finalWindow = $activeWindow
            $snapshotShotPath = Join-Path $evidenceDirectory '15-local-snapshot-restored.png'
            Save-WindowScreenshot -Window $activeWindow -Path $snapshotShotPath
            $script:screenshots.Add([pscustomobject]@{ name = 'local-snapshot-restored'; file = [IO.Path]::GetFileName($snapshotShotPath) })
            [ordered]@{
                originalHeight = $originalHeight
                savedHeight = $testHeight
                restoredHeight = $observedRestoredHeight
                cleanupHeight = [double]$finalHeightRange.Current.Value
                linkState = $originalLink
                screenshot = [IO.Path]::GetFileName($snapshotShotPath)
            }
        }
        finally {
            if ($testSnapshotWasSaved -and -not $script:finalWindow -and $activeWindow) {
                try {
                    $cleanupHeight = Find-UiElement -Root $activeWindow -Name 'Height in centimeters' -TimeoutSeconds 5
                    $cleanupHeightRange = Get-UiPattern -Element $cleanupHeight -Pattern ([System.Windows.Automation.RangeValuePattern]::Pattern) -PatternName 'RangeValuePattern'
                    $cleanupHeightRange.SetValue($originalHeight)
                    $cleanupLink = Find-UiElement -Root $activeWindow -Name 'Link proportional measurements' -TimeoutSeconds 5
                    Set-ToggleState -Element $cleanupLink -State $originalLink
                    Invoke-UiElement -Element (Find-UiElementByAutomationId -Root $activeWindow -AutomationId 'SavePatternSnapshotButton' -TimeoutSeconds 5)
                    $script:finalWindow = $activeWindow
                }
                catch {
                }
            }
        }
    }

}
catch {
    $fatalError = $_.Exception.Message
    $fatalErrorType = $_.Exception.GetType().FullName
    $fatalScriptStackTrace = $_.ScriptStackTrace
    $failureDiagnostics = Get-FailureDiagnostics -Process $process -StartedAt $startedAt
    Add-ActionResult -Name 'Fatal runner error' -Passed $false -Details $null -ErrorMessage $fatalError
    if ($window) {
        try {
            $failureShot = Join-Path $evidenceDirectory '99-failure.png'
            Save-WindowScreenshot -Window $window -Path $failureShot
            $script:screenshots.Add([pscustomobject]@{ name = 'failure'; file = [IO.Path]::GetFileName($failureShot) })
        }
        catch {
        }
        try {
            $script:uiTreeNodeCount = 0
            Convert-UiTreeNode -Element $window | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $evidenceDirectory 'ui-tree-failure.json') -Encoding utf8
        }
        catch {
        }
    }
}
finally {
    $windowToClose = if ($script:finalWindow) { $script:finalWindow } else { $window }
    if ($windowToClose -and -not [bool]$request.keepAppOpen) {
        try {
            $closePattern = Get-UiPattern -Element $windowToClose -Pattern ([System.Windows.Automation.WindowPattern]::Pattern) -PatternName 'WindowPattern'
            $closePattern.Close()
        }
        catch {
            Get-Process -Name Patternal -ErrorAction SilentlyContinue | Stop-Process -Force
        }
    }

    if ($textScaleChanged) {
        if ($originalTextScaleExists) {
            Set-ItemProperty -Path $textScaleRegistryPath -Name TextScaleFactor -Type DWord -Value $originalTextScalePercent
        }
        else {
            Remove-ItemProperty -Path $textScaleRegistryPath -Name TextScaleFactor -ErrorAction SilentlyContinue
        }
        [PatternalDisplayMode]::BroadcastAccessibilityChange()
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
            requestedTextScalePercent = $requestedTextScalePercent
            restoredTextScalePercent = $originalTextScalePercent
        }
        process = if ($process) { [ordered]@{ id = $process.Id; responding = $process.Responding } } else { $null }
        hostInputInjected = $false
        vmConnectLaunched = $false
        actions = @($script:actions)
        screenshots = @($script:screenshots)
        fatalError = $fatalError
        fatalErrorType = $fatalErrorType
        fatalScriptStackTrace = $fatalScriptStackTrace
        failureDiagnostics = $failureDiagnostics
    }
    $result | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $evidenceDirectory 'result.json') -Encoding utf8
}
