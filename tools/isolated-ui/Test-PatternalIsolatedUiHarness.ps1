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

$guestRunnerPath = Join-Path $PSScriptRoot 'guest\Invoke-PatternalUiSmoke.ps1'
$guestRunner = Get-Content -LiteralPath $guestRunnerPath -Raw
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
    "'Avatar preview: editable measurement mesh*'",
    "'Avatar preview: fitted Antonia candidate*'",
    "'15-3d-edited-measurement-avatar.png'",
    "'16-3d-restored-fitted-avatar.png'"
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
    -not $codeBehind.Contains('Avatar preview: editable measurement mesh') -or
    -not $codeBehind.Contains('Avatar preview: fitted Antonia candidate') -or
    -not $viewport.Contains("type:'avatar-state'")) {
    throw 'The packaged renderer no longer reports its measured-avatar preview state to the accessible WinUI surface.'
}
if (-not $viewport.Contains("?'FITTED AVATAR CANDIDATE'") -or
    -not $viewport.Contains(":'MEASUREMENT PREVIEW'")) {
    throw 'The 3D viewport again presents both the fitted candidate and the low-detail measurement preview as one accepted anatomical avatar.'
}
if (-not $guestRunner.Contains('failureDiagnostics = $failureDiagnostics')) {
    throw 'Guest runner no longer preserves process and event-log diagnostics with failed UI evidence.'
}
if (-not $guestRunner.Contains('fatalScriptStackTrace = $fatalScriptStackTrace')) {
    throw 'Guest runner no longer preserves the failing PowerShell script line with failed UI evidence.'
}
$hostRunner = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Invoke-PatternalGuestUiSmoke.ps1') -Raw
foreach ($earlyExitContract in @(
    'LastTaskResult',
    'exited before writing result.json'
)) {
    if (-not $hostRunner.Contains($earlyExitContract)) {
        throw "Host runner no longer fails promptly when the guest task exits before evidence initialization: '$earlyExitContract'."
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
