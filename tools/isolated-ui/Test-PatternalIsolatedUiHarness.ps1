[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$scriptFiles = @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps*1' -File -Recurse)
$parseFailures = [System.Collections.Generic.List[object]]::new()
foreach ($file in $scriptFiles) {
    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $file.FullName,
        [ref]$tokens,
        [ref]$parseErrors)
    foreach ($parseError in $parseErrors) {
        $parseFailures.Add([pscustomobject]@{
            File = $file.FullName
            Line = $parseError.Extent.StartLineNumber
            Message = $parseError.Message
        })
    }
}
if ($parseFailures.Count -gt 0) {
    $parseFailures | Format-Table -AutoSize
    throw 'The isolated UI harness contains PowerShell parser errors.'
}

$hostFiles = @($scriptFiles | Where-Object {
    $_.FullName -notmatch '\\guest\\' -and $_.Name -ne 'Test-PatternalIsolatedUiHarness.ps1'
})
$forbiddenHostPatterns = @(
    'SendInput',
    'mouse_event',
    'keybd_event',
    'vmconnect\.exe',
    'Start-Process[^\r\n]*WindowsSandbox\.exe',
    '&\s*["'']?WindowsSandbox\.exe',
    'Invoke-Item[^\r\n]*WindowsSandbox\.exe',
    'UIAutomationClient',
    'user32\.dll'
)
foreach ($file in $hostFiles) {
    $source = Get-Content -LiteralPath $file.FullName -Raw
    foreach ($pattern in $forbiddenHostPatterns) {
        if ($source -match $pattern) {
            throw "Host script '$($file.Name)' violates the isolated input boundary with pattern '$pattern'."
        }
    }
}

$hostModule = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Patternal.IsolatedUi.psm1') -Raw
$guestProvisioner = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'New-PatternalHyperVGuest.ps1') -Raw
if (-not $hostModule.Contains('function Export-PatternalGuestCredentialNote') -or
    -not $hostModule.Contains('$VmName.credentials.md') -or
    -not $guestProvisioner.Contains('Export-PatternalGuestCredentialNote -VmName $VmName')) {
    throw 'Guest provisioning no longer creates the machine-local plaintext credential note required for manual VMConnect login.'
}
if (-not $guestProvisioner.Contains('VM root ''$normalizedVmRoot'' must end with the exact VM name ''$VmName''.') -or
    -not $guestProvisioner.Contains('Dedicated to the Patternal project isolated UI lane.') -or
    -not $guestProvisioner.Contains('Do not reuse for unrelated work.')) {
    throw 'Guest provisioning no longer enforces a dedicated, unmistakably owned VM directory and metadata note.'
}

$guestRunnerPath = Join-Path $PSScriptRoot 'guest\Invoke-PatternalUiSmoke.ps1'
$guestRunner = Get-Content -LiteralPath $guestRunnerPath -Raw
foreach ($canvasSelectionContract in @(
    "'Back Torso pattern piece'",
    "'filled Back Torso geometry to select its piece without reframing'",
    "'09-2d-canvas-selection.png'"
)) {
    if (-not $guestRunner.Contains($canvasSelectionContract)) {
        throw "The guest suite no longer proves direct filled-geometry piece selection: $canvasSelectionContract"
    }
}
$persistentRunnerPath = Join-Path $PSScriptRoot 'guest\Start-PatternalGuestRunner.ps1'
$persistentRunner = Get-Content -LiteralPath $persistentRunnerPath -Raw
$persistentRunnerHostPath = Join-Path $PSScriptRoot 'Invoke-PatternalGuestRunner.ps1'
$persistentRunnerHost = Get-Content -LiteralPath $persistentRunnerHostPath -Raw
$guestInstaller = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'guest\Install-PatternalGuestPayload.ps1') -Raw
$payloadSync = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Sync-PatternalGuestPayload.ps1') -Raw
foreach ($contract in @(
    'patternal.guest-runner-request/1.0',
    'patternal.guest-runner-result/1.0',
    "'status'",
    "'launch'",
    "'screenshot'",
    "'close'",
    "'stop'"
)) {
    if (-not $persistentRunner.Contains($contract) -or -not $persistentRunnerHost.Contains($contract)) {
        throw "Persistent guest runner no longer shares required contract: $contract"
    }
}
if (-not $persistentRunner.Contains('hostInputInjected = $false') -or
    -not $persistentRunner.Contains('vmConnectLaunched = $false')) {
    throw 'Persistent guest runner results no longer record the host-input and VMConnect isolation boundary.'
}
if (-not $hostModule.Contains('function Start-PatternalVmForAutomation') -or
    -not $hostModule.Contains('$resumedSavedState = $vm.State -eq ''Saved''') -or
    -not $hostModule.Contains('Start-VM -Name $VmName | Out-Null') -or
    -not $persistentRunnerHost.Contains('Start-PatternalVmForAutomation -VmName $VmName') -or
    -not $payloadSync.Contains('Start-PatternalVmForAutomation -VmName $VmName')) {
    throw 'Host automation no longer stabilizes a resumed saved VM before guest work.'
}
if (-not $payloadSync.Contains('Start-PatternalVmForAutomation -VmName $VmName')) {
    throw 'Payload synchronization no longer uses the saved-state stabilization boundary.'
}
if (-not $guestInstaller.Contains("Register-ScheduledTask -TaskName 'Patternal Guest Runner'") -or
    -not $guestInstaller.Contains("New-ScheduledTaskTrigger -AtLogOn") -or
    -not $guestInstaller.Contains('-WindowStyle Hidden') -or
    -not $guestInstaller.Contains('$appxReused') -or
    -not $guestInstaller.Contains('$registrationReused') -or
    -not $payloadSync.Contains("Start-PatternalGuestRunner.ps1")) {
    throw 'The persistent runner install no longer preserves hidden interactive execution, idempotent AppX registration, logon startup, and payload synchronization.'
}
if (-not $payloadSync.Contains('[switch]$AllowRestore') -or
    -not $payloadSync.Contains('$buildArguments += ''--no-restore''') -or
    -not $payloadSync.Contains('rerun with -AllowRestore if restore is authorized')) {
    throw 'Payload synchronization no longer fails closed against an unreviewed dependency restore.'
}
$windowsPowerShellPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $windowsPowerShellPath -PathType Leaf)) {
    throw 'Windows PowerShell 5.1 is required to validate the guest runner compiler boundary.'
}
$escapedGuestRunnerPath = $guestRunnerPath.Replace("'", "''")
$guestCompilerCommand = @"
`$sourceText = Get-Content -LiteralPath '$escapedGuestRunnerPath' -Raw
`$sourceMatch = [regex]::Match(`$sourceText, "Add-Type -TypeDefinition @'\r?\n(?<source>[\s\S]*?)\r?\n'@")
if (-not `$sourceMatch.Success) {
    throw 'Guest C# source block was not found.'
}
Add-Type -TypeDefinition `$sourceMatch.Groups['source'].Value
"@
$encodedGuestCompilerCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($guestCompilerCommand))
$guestCompilerOutput = & $windowsPowerShellPath -NoLogo -NoProfile -NonInteractive -EncodedCommand $encodedGuestCompilerCommand 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Guest C# does not compile under Windows PowerShell 5.1: $($guestCompilerOutput -join [Environment]::NewLine)"
}
$xamlPath = Join-Path $repositoryRoot 'Patternal\MainPage.xaml'
$xaml = Get-Content -LiteralPath $xamlPath -Raw
$codeBehindPath = Join-Path $repositoryRoot 'Patternal\MainPage.xaml.cs'
$codeBehind = Get-Content -LiteralPath $codeBehindPath -Raw
if ($xaml -notmatch '(?s)<Canvas(?=[^>]*x:Name="PatternCanvas")(?=[^>]*Background="Transparent")[^>]*>') {
    throw 'The interactive pattern canvas no longer exposes a transparent hit-test surface for empty-space pointer drafting.'
}
if ($xaml.Contains('Exact measured MPFB body') -or $codeBehind.Contains('Exact measured MPFB body')) {
    throw 'The product UI again hard-codes the legacy MPFB backend name for every current collision body.'
}
$requiredAutomationNames = @(
    'Pattern workspace views',
    'Show pattern pieces panel',
    'Show avatar and material inspector',
    'Show seam allowance',
    'Show grainlines',
    'Link proportional measurements',
    'Show fitted bra',
    'Height in centimeters',
    'Full bust circumference in centimeters',
    'Natural waist circumference in centimeters',
    'Full hip circumference in centimeters',
    'Shoulder breadth in centimeters',
    'Torso length in centimeters',
    'Fabric weight in grams per square meter',
    'Fabric bias stretch percentage',
    'Edit pattern points',
    'Show pattern at calibrated actual size',
    'Calibrate pattern physical scale',
    'Inspect garment seam graph',
    'Reverse selected seam side B sewing direction',
    'Undo pattern geometry edit',
    'Show front cloth view',
    'Show right side cloth view',
    'Show rear cloth view',
    'Show left side cloth view',
    'Show front oblique cloth view',
    'Reset three dimensional camera'
)
foreach ($name in $requiredAutomationNames) {
    if (-not $guestRunner.Contains("'$name'")) {
        throw "Guest runner no longer exercises '$name'."
    }
    if (-not $xaml.Contains(('AutomationProperties.Name="{0}"' -f $name))) {
        throw "MainPage.xaml no longer exposes the automation name '$name'."
    }
}
$requiredCameraAutomationIds = @(
    'DrapeFrontCameraButton',
    'DrapeRightCameraButton',
    'DrapeRearCameraButton',
    'DrapeLeftCameraButton',
    'DrapeObliqueCameraButton',
    'DrapeFitCameraButton'
)
foreach ($automationId in $requiredCameraAutomationIds) {
    if (-not $guestRunner.Contains("'$automationId'")) {
        throw "Guest runner no longer targets camera automation ID '$automationId'."
    }
    if (-not $xaml.Contains(('x:Name="{0}"' -f $automationId))) {
        throw "MainPage.xaml no longer exposes camera automation ID '$automationId'."
    }
}
$requiredDrapeStateAutomationIds = @(
    'DrapeStaleSimulationState',
    'DrapeAcceptedSimulationState',
    'DrapeAvatarPreviewState'
)
foreach ($automationId in $requiredDrapeStateAutomationIds) {
    if (-not $guestRunner.Contains("'$automationId'")) {
        throw "Guest runner no longer targets 3D state automation ID '$automationId'."
    }
    if (-not $xaml.Contains(('AutomationProperties.AutomationId="{0}"' -f $automationId))) {
        throw "MainPage.xaml no longer exposes 3D state automation ID '$automationId'."
    }
}
foreach ($avatarStateContract in @(
    "'3D avatar follows edited measurements'",
    "'Avatar preview: MHR partial preview*'",
    "'Avatar preview: MHR baseline preview*'",
    "'15-3d-edited-measurement-avatar.png'",
    "'16-3d-restored-baseline-preview.png'"
)) {
    if (-not $guestRunner.Contains($avatarStateContract)) {
        throw "Guest runner no longer proves avatar-state contract $avatarStateContract."
    }
}
foreach ($patternLifecycleContract in @(
    "'2D guest pointer polygon drafting undo and redo'",
    '[PatternalGuestPointerInput]::Click',
    "'11-2d-pointer-polygon-draft.png'",
    "'2D calibrated actual-size workflow'",
    "'Measured calibration ruler length in centimeters'",
    "'11-2d-calibrated-actual-size.png'",
    "'2D internal line create update delete undo and redo'",
    "'Edit: Construction line 1'",
    "'Shoulder balance guide'",
    "'Delete line'",
    "'2D dart create update delete undo and redo'",
    "'Edit: Dart 1'",
    "'Waist shaping guide'",
    "'Delete dart'",
    "'2D existing-seam physical dart update undo and redo'",
    "'Cut and sew existing seam'",
    "'14-2d-existing-seam-physical-dart.png'",
    "'2D free-edge physical dart creation undo and redo'",
    "'Cut and sew free edge'",
    "'14-2d-free-edge-physical-dart.png'"
)) {
    if (-not $guestRunner.Contains($patternLifecycleContract)) {
        throw "Guest runner no longer proves the full 2D construction lifecycle contract $patternLifecycleContract."
    }
}
foreach ($persistenceContract in @(
    "'Dedicated test profile reset to bundled baseline'",
    "'NewPatternButton'",
    "'SVG export through packaged file picker'",
    "'ExportPatternButton'",
    "'pattern-round-trip.svg'",
    "'Named project Save As and Open round trip'",
    "'SavePatternProjectAsButton'",
    "'OpenPatternProjectButton'",
    "'pattern-round-trip.patterna'",
    "'complete packaged Patterna project file'",
    '$candidate.schemaVersion',
    "'Local snapshot save and startup restore round trip'",
    "'SavePatternSnapshotButton'",
    "'15-local-snapshot-restored.png'"
)) {
    if (-not $guestRunner.Contains($persistenceContract)) {
        throw "Guest runner no longer proves packaged persistence contract $persistenceContract."
    }
}
if (-not $guestRunner.Contains('Assert-RenderedScreenshotRegion')) {
    throw 'Guest runner no longer rejects visually blank avatar proof screenshots.'
}
foreach ($persistenceAutomationId in @(
    'NewPatternButton',
    'OpenPatternProjectButton',
    'SavePatternProjectAsButton',
    'ExportPatternButton',
    'SavePatternSnapshotButton'
)) {
    if (-not $xaml.Contains(('AutomationProperties.AutomationId="{0}"' -f $persistenceAutomationId))) {
        throw "MainPage.xaml no longer exposes persistence automation ID '$persistenceAutomationId'."
    }
}
foreach ($keyboardContract in @(
    "'Keyboard-only primary workspace navigation'",
    "'Focusable 2D controls expose accessible names'",
    "'Focusable 3D controls expose accessible names'",
    'Send-GuestKeys',
    "'{TAB}'",
    "'{ENTER}'",
    "'{ESC}'",
    "'{RIGHT}'",
    "'{LEFT}'",
    "'01-keyboard-focus-2d.png'"
)) {
    if (-not $guestRunner.Contains($keyboardContract)) {
        throw "Guest runner no longer proves keyboard accessibility contract $keyboardContract."
    }
}
foreach ($keyboardAutomationId in @(
    'EditPatternPointsButton',
    'EditAssemblyButton',
    'PiecesToggleButton',
    'InspectorToggleButton',
    'SimulateCommandButton',
    'SeamAllowanceToggle',
    'GrainlinesToggle',
    'WorkspaceTabs',
    'Workspace2DTab',
    'Workspace3DTab'
)) {
    if (-not $xaml.Contains(('AutomationProperties.AutomationId="{0}"' -f $keyboardAutomationId))) {
        throw "MainPage.xaml no longer exposes keyboard automation ID '$keyboardAutomationId'."
    }
}
foreach ($dialogLifecycleContract in @(
    'Select a new or existing straight internal line',
    'PatternInternalPathUpdateCommand',
    'PatternInternalPathDeleteCommand',
    'Select a new or existing dart',
    'PatternDartUpdateCommand',
    'PatternDartDeleteCommand'
)) {
    if (-not $codeBehind.Contains($dialogLifecycleContract)) {
        throw "MainPage.xaml.cs no longer exposes the full 2D construction lifecycle contract '$dialogLifecycleContract'."
    }
}
$viewport = Get-Content -LiteralPath (Join-Path $repositoryRoot 'Patternal\Assets\avatar3d.html') -Raw
if (-not $codeBehind.Contains('"avatar-state"') -or
    -not $codeBehind.Contains('Avatar preview: MHR partial preview') -or
    -not $codeBehind.Contains('Avatar preview: MHR baseline preview') -or
    -not $codeBehind.Contains('Avatar preview: 3D unsupported for this revision') -or
    -not $viewport.Contains("type:'avatar-state'")) {
    throw 'The packaged renderer no longer reports its measured-avatar preview state to the accessible WinUI surface.'
}
if (-not $viewport.Contains("mhrUnsupportedPreview?'3D UNSUPPORTED FOR REVISION':'MHR PREVIEW ONLY'") -or
    -not $viewport.Contains("mhrBaselinePreview?'mhr-baseline-preview':mhrMorphPreview?'mhr-morph-preview':mhrUnsupportedPreview?'mhr-unsupported-preview'") -or
    -not $viewport.Contains(":'MEASUREMENT PREVIEW'")) {
    throw 'The 3D viewport no longer distinguishes the MHR baseline, partial, unsupported, and non-MHR fallback states.'
}
if (-not $guestRunner.Contains('failureDiagnostics = $failureDiagnostics')) {
    throw 'Guest runner no longer preserves process and event-log diagnostics with failed UI evidence.'
}
if (-not $guestRunner.Contains('fatalScriptStackTrace = $fatalScriptStackTrace')) {
    throw 'Guest runner no longer preserves the failing PowerShell script line with failed UI evidence.'
}
$hostRunner = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Invoke-PatternalGuestUiSmoke.ps1') -Raw
foreach ($stagedRequestContract in @(
    'run-request-$runId.json',
    'Move-Item -LiteralPath $StagedRequestPath -Destination $RequestPath -Force',
    'Remove-Item -LiteralPath $StagedRequestPath -Force -ErrorAction SilentlyContinue'
)) {
    if (-not $hostRunner.Contains($stagedRequestContract)) {
        throw "Host runner no longer protects an active guest run from request overwrite: '$stagedRequestContract'."
    }
}
foreach ($windowsThemeContract in @(
    "[ValidateSet('Current', 'Light', 'Dark', 'HighContrastBlack', 'HighContrastWhite', 'HighContrast1', 'HighContrast2')]",
    'windowsTheme = $WindowsTheme',
    "'Guest Windows theme request'",
    'IsHighContrastEnabled',
    'Restore-GuestTheme',
    '$themePathMatches',
    "'Guest Windows theme restoration'"
)) {
    if (-not ($hostRunner.Contains($windowsThemeContract) -or $guestRunner.Contains($windowsThemeContract))) {
        throw "Isolated runner no longer proves Windows-theme contract '$windowsThemeContract'."
    }
}
foreach ($earlyExitContract in @(
    'LastTaskResult',
    'exited before writing result.json'
)) {
    if (-not $hostRunner.Contains($earlyExitContract)) {
        throw "Host runner no longer fails promptly when the guest task exits before evidence initialization: '$earlyExitContract'."
    }
}
foreach ($consoleSessionContract in @(
    'query.exe" session $sessionId',
    'tscon.exe" $sessionId /dest:console',
    'reconnectedToConsole',
    'GuestSession = $guestSession'
)) {
    if (-not $hostRunner.Contains($consoleSessionContract)) {
        throw "Host runner no longer recovers a disconnected interactive guest session through the supported console handoff: '$consoleSessionContract'."
    }
}
if (-not $guestRunner.Contains('[System.Drawing.Bitmap]::new([int]$width, [int]$height)')) {
    throw 'Guest screenshot capture no longer pins System.Drawing bitmap dimensions to integer pixels.'
}
if ($guestRunner.IndexOf('Invoke-ThreeDimensionalChecks -Window $window', [StringComparison]::Ordinal) -gt
    $guestRunner.IndexOf("'Disable linked proportions for isolated slider tests'", [StringComparison]::Ordinal)) {
    throw 'Guest runner no longer captures current accepted cloth before simulation-invalidating slider tests.'
}
if (-not $guestRunner.Contains("'ui-tree-failure.json'")) {
    throw 'Guest runner no longer preserves the live UI tree after a fatal interaction failure.'
}
foreach ($diagnosticLog in @('Application', 'Microsoft-Windows-AppModel-Runtime/Admin', 'Microsoft-Windows-TWinUI/Operational')) {
    if (-not $guestRunner.Contains("'$diagnosticLog'")) {
        throw "Guest runner no longer captures failure diagnostics from $diagnosticLog."
    }
}

$requiredSchemas = @(
    'patternal.isolated-ui-payload/1.0',
    'patternal.isolated-ui-install/1.0',
    'patternal.isolated-ui-request/1.0',
    'patternal.isolated-ui-result/1.0'
)
$allSource = $scriptFiles | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw }
foreach ($schema in $requiredSchemas) {
    if (-not ($allSource -match [regex]::Escape($schema))) {
        throw "Harness schema is missing: $schema"
    }
}

$syncScriptPath = Join-Path $PSScriptRoot 'Sync-PatternalGuestPayload.ps1'
$syncScript = Get-Content -LiteralPath $syncScriptPath -Raw
if ($syncScript.Contains('Get-FileHash')) {
    throw 'Guest payload synchronization again depends on PowerShell module auto-loading for SHA-256 identity checks.'
}
if (-not $syncScript.Contains('Get-PatternalFileSha256')) {
    throw 'Guest payload synchronization no longer uses the module-independent SHA-256 helper.'
}
$moduleSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Patternal.IsolatedUi.psm1') -Raw
$guestInstallerSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'guest\Install-PatternalGuestPayload.ps1') -Raw
foreach ($identitySource in @($moduleSource, $guestInstallerSource)) {
    if (-not $identitySource.Contains('[Array]::Sort($lines, [StringComparer]::Ordinal)') -or
        $identitySource.Contains('Sort-Object FullName')) {
        throw 'Payload directory identity is not using the same ordinal path ordering on host and guest.'
    }
}
if (-not $syncScript.Contains('Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force')) {
    throw 'Guest payload installation no longer permits the copied installer script in a clean Windows guest.'
}
if (-not $syncScript.Contains('Microsoft.WindowsAppRuntime.Redist.2.3.zip')) {
    throw 'Guest payload installation no longer pins the official Windows App Runtime redistributable fallback.'
}
if (-not $syncScript.Contains('dotnet-runtime-10.0.10-win-x64.exe')) {
    throw 'Guest payload installation no longer pins the official .NET 10 x64 runtime installer.'
}

$guestInstallerPath = Join-Path $PSScriptRoot 'guest\Install-PatternalGuestPayload.ps1'
$guestInstaller = Get-Content -LiteralPath $guestInstallerPath -Raw
foreach ($packageName in @(
    'Microsoft.WindowsAppRuntime.2.msix',
    'Microsoft.WindowsAppRuntime.Main.2.msix',
    'Microsoft.WindowsAppRuntime.Singleton.2.msix',
    'Microsoft.WindowsAppRuntime.DDLM.2.msix'
)) {
    if (-not $guestInstaller.Contains("'$packageName'")) {
        throw "Guest runtime fallback no longer installs $packageName."
    }
}
if (-not $guestInstaller.Contains("Get-AuthenticodeSignature -LiteralPath `$packagePath")) {
    throw 'Guest runtime fallback no longer validates every direct MSIX package signature.'
}
if (-not $guestInstaller.Contains("Get-AuthenticodeSignature -LiteralPath `$dotNetInstaller")) {
    throw 'Guest payload installation no longer validates the .NET runtime installer signature.'
}
if (-not $guestInstaller.Contains("'Microsoft Corporation'")) {
    throw 'Guest payload installation no longer requires Microsoft-signed prerequisites.'
}

$documentationPath = Join-Path $repositoryRoot 'docs\isolated-windows-ui-testing.md'
if (-not (Test-Path -LiteralPath $documentationPath)) {
    throw 'The isolated Windows UI testing workflow is not documented.'
}

$forbiddenDashes = [string][char]0x2013 + '|' + [string][char]0x2014
foreach ($file in @($scriptFiles) + @(Get-Item -LiteralPath $documentationPath)) {
    if ((Get-Content -LiteralPath $file.FullName -Raw) -match $forbiddenDashes) {
        throw "Forbidden dash punctuation appears in $($file.FullName)."
    }
}

[pscustomobject]@{
    ParsedFiles = $scriptFiles.Count
    Parser = 'Passed'
    HostInputBoundary = 'Passed'
    GuestCSharpCompiler = 'Windows PowerShell 5.1 passed'
    AutomationContracts = $requiredAutomationNames.Count
    Schemas = $requiredSchemas.Count
    Documentation = 'Passed'
    Result = 'Passed'
}
