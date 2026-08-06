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
$xamlPath = Join-Path $repositoryRoot 'Patternal\MainPage.xaml'
$xaml = Get-Content -LiteralPath $xamlPath -Raw
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
    AutomationContracts = $requiredAutomationNames.Count
    Schemas = $requiredSchemas.Count
    Documentation = 'Passed'
    Result = 'Passed'
}
