[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$installerPath = Join-Path $PSScriptRoot 'install_patterna_challenger_runtimes.ps1'
$lockPath = Join-Path $PSScriptRoot 'runtime-locks\mhr-py312-cpu-requirements.txt'
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($installerPath, [ref]$null, [ref]$errors) | Out-Null
if ($errors.Count -ne 0) {
    throw ($errors | ForEach-Object Message | Out-String)
}
$installer = Get-Content -LiteralPath $installerPath -Raw
$lock = Get-Content -LiteralPath $lockPath
foreach ($contract in @(
    'e4f4f205cd87c0fa106577ba1de4fc763e4eb197c924461d2ef7e6944e9d6b94',
    '50d84ce0c9bc57d6d72564efa21b66c19c4e5e7e9eddd528c4d9fa050f5cafec',
    'c62fb5b48472c366001bd2c39e6338dd5152c88624a1425ceacf0b17a164f9aa',
    'patterna.challenger-runtime/1.0',
    'patterna.challenger-runtime-catalog/1.0',
    "`$pythonVersion -ne '3.11.9'",
    'Expand-VerifiedZip',
    'Test-InstalledRuntime',
    '$output = @(& $FilePath @ArgumentList 2>&1)',
    '--require-hashes',
    '--no-index',
    'Remove-Item -LiteralPath $staging -Recurse -Force'
)) {
    if (-not $installer.Contains($contract)) {
        throw "Challenger runtime installer is missing contract: $contract"
    }
}
if ($lock.Count -ne 11 -or @($lock | Where-Object { $_ -notmatch '^[A-Za-z0-9_.-]+==[^ ]+ --hash=sha256:[0-9a-f]{64}$' }).Count -ne 0) {
    throw 'The MHR offline requirement lock must contain exactly 11 hash-pinned wheels.'
}
if ($installer.Contains('latest-release') -or $installer.Contains('pip install torch torchvision')) {
    throw 'The challenger installer must not use mutable release or unpinned package resolution.'
}
[pscustomobject]@{
    ParsedFiles = 2
    PinnedArchives = 2
    HashLockedWheels = $lock.Count
    ZipTraversalGuard = 'Passed'
    IdempotentPromotion = 'Passed'
    Result = 'Passed'
}
