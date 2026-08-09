[CmdletBinding()]
param(
    [ValidateSet('All', 'MHR', 'PPF')]
    [string]$Component = 'All',
    [string]$DestinationRoot = (Join-Path $env:LOCALAPPDATA 'Patterna\ChallengerRuntimes'),
    [string]$DownloadRoot = (Join-Path $env:LOCALAPPDATA 'Patterna\ChallengerRuntimes\downloads'),
    [string]$PythonPath = 'C:\Users\myema\AppData\Local\Programs\Python\Python312\python.exe',
    [switch]$Replace
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$mhr = [ordered]@{
    Name = 'MHR'
    Version = 'v1.0.1-py312-torch2.12.1-cpu'
    ArchiveName = 'mhr-v1.0.1-assets.zip'
    ArchiveUri = 'https://github.com/facebookresearch/MHR/releases/download/v1.0.1/assets.zip'
    ArchiveBytes = 198943157L
    ArchiveSha256 = 'e4f4f205cd87c0fa106577ba1de4fc763e4eb197c924461d2ef7e6944e9d6b94'
    ModelRelativePath = 'assets\mhr_model.pt'
    ModelBytes = 696110248L
    ModelSha256 = '352e271a6c42729c68554ceaea0c955e866970160c31e35506d782dc0f7377bc'
    LicenseRelativePath = 'assets\LICENSE.txt'
    LicenseBytes = 11358L
    LicenseSha256 = 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'
}
$ppf = [ordered]@{
    Name = 'PPF'
    Version = '2026-08-08-03-55-win64'
    ArchiveName = 'ppf-contact-solver-2026-08-08-03-55-win64.zip'
    ArchiveUri = 'https://github.com/st-tech/ppf-contact-solver/releases/download/2026-08-08-03-55/ppf-contact-solver-2026-08-08-03-55-win64.zip'
    ArchiveBytes = 447925491L
    ArchiveSha256 = '50d84ce0c9bc57d6d72564efa21b66c19c4e5e7e9eddd528c4d9fa050f5cafec'
    LicenseName = 'ppf-contact-solver-2026-08-08-03-55-LICENSE'
    LicenseUri = 'https://raw.githubusercontent.com/st-tech/ppf-contact-solver/2026-08-08-03-55/LICENSE'
    LicenseBytes = 11355L
    LicenseSha256 = 'c62fb5b48472c366001bd2c39e6338dd5152c88624a1425ceacf0b17a164f9aa'
    SolverRelativePath = 'target\release\ppf-contact-solver.exe'
    SolverSha256 = '07dcb3cbe14cdd2842ee3fbf9064b07a14ea551b6374bf5cdf2b944dc9ff90d2'
    ServerRelativePath = 'target\release\ppf-cts-server.exe'
    ServerSha256 = '19e5e15e87e95e1e8a471b9006f5b1f15fbcee6c9cb4d8fc128b0c074dda18bf'
    HeadlessRelativePath = 'examples\headless.py'
    HeadlessSha256 = 'f828c43ced386bab814bdc4dd6b8e4584ed7e2dfa027a9d5d4854c3819574850'
    ReadmeRelativePath = 'README.txt'
    ReadmeSha256 = '2ca503cea50681dcd019f08fd1127de7976686c50ef03273850ac5a41c2fb423'
    ThirdPartyLicenseRelativePath = 'THIRD_PARTY_LICENSES.txt'
    ThirdPartyLicenseSha256 = '4f726f1f78e405925c4f58a856d749756c9f91288bb0ef61bc5ab5bfbf103462'
}

function Get-LowerSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-FileIdentity {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][long]$Bytes,
        [Parameter(Mandatory)][string]$Sha256,
        [Parameter(Mandatory)][string]$Description
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing $Description at $Path"
    }
    $file = Get-Item -LiteralPath $Path
    if ($file.Length -ne $Bytes) {
        throw "$Description has $($file.Length) bytes; expected $Bytes."
    }
    $actualHash = Get-LowerSha256 $Path
    if ($actualHash -ne $Sha256) {
        throw "$Description SHA-256 is $actualHash; expected $Sha256."
    }
}

function Assert-FileHash {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Sha256,
        [Parameter(Mandatory)][string]$Description
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing $Description at $Path"
    }
    $actualHash = Get-LowerSha256 $Path
    if ($actualHash -ne $Sha256) {
        throw "$Description SHA-256 is $actualHash; expected $Sha256."
    }
}

function Expand-VerifiedZip {
    param(
        [Parameter(Mandatory)][string]$ArchivePath,
        [Parameter(Mandatory)][string]$Destination
    )
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $destinationFull = [System.IO.Path]::GetFullPath($Destination)
    $prefix = $destinationFull.TrimEnd('\') + '\'
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        foreach ($entry in $archive.Entries) {
            $entryPath = $entry.FullName.Replace('/', '\')
            $candidate = [System.IO.Path]::GetFullPath((Join-Path $destinationFull $entryPath))
            if (-not $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Archive entry escapes the owned staging root: $($entry.FullName)"
            }
        }
    }
    finally {
        $archive.Dispose()
    }
    New-Item -ItemType Directory -Path $destinationFull -Force | Out-Null
    [System.IO.Compression.ZipFile]::ExtractToDirectory($ArchivePath, $destinationFull)
}

function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList,
        [Parameter(Mandatory)][string]$Description
    )
    $output = @(& $FilePath @ArgumentList 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $details = ($output | Select-Object -Last 20) -join [Environment]::NewLine
        throw "$Description exited with code $exitCode.$([Environment]::NewLine)$details"
    }
    foreach ($line in $output) {
        Write-Verbose "$Description`: $line"
    }
}

function Write-JsonAtomic {
    param([Parameter(Mandatory)]$Value, [Parameter(Mandatory)][string]$Path)
    $temporary = "$Path.tmp-$([Guid]::NewGuid().ToString('N'))"
    [System.IO.File]::WriteAllText(
        $temporary,
        ($Value | ConvertTo-Json -Depth 12),
        [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Test-InstalledRuntime {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Version)
    $manifestPath = Join-Path $Path 'runtime-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        return $false
    }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        if ($manifest.schemaVersion -ne 'patterna.challenger-runtime/1.0' -or $manifest.version -ne $Version) {
            return $false
        }
        foreach ($entry in $manifest.entrypoints.PSObject.Properties) {
            $entryPath = Join-Path $Path $entry.Name
            if (-not (Test-Path -LiteralPath $entryPath -PathType Leaf)) {
                return $false
            }
            if ((Get-LowerSha256 $entryPath) -ne [string]$entry.Value) {
                return $false
            }
        }
        return $true
    }
    catch {
        return $false
    }
}

function Promote-StagedRuntime {
    param(
        [Parameter(Mandatory)][string]$Staging,
        [Parameter(Mandatory)][string]$Final,
        [Parameter(Mandatory)][string]$Version
    )
    if (Test-Path -LiteralPath $Final) {
        if (Test-InstalledRuntime -Path $Final -Version $Version) {
            Remove-Item -LiteralPath $Staging -Recurse -Force
            return [pscustomobject]@{ Path = $Final; Reused = $true; Backup = $null }
        }
        if (-not $Replace) {
            throw "An invalid or different runtime already exists at $Final. Re-run with -Replace to preserve it as a backup."
        }
        $backup = "$Final.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Move-Item -LiteralPath $Final -Destination $backup
        Move-Item -LiteralPath $Staging -Destination $Final
        return [pscustomobject]@{ Path = $Final; Reused = $false; Backup = $backup }
    }
    Move-Item -LiteralPath $Staging -Destination $Final
    return [pscustomobject]@{ Path = $Final; Reused = $false; Backup = $null }
}

function Install-MhrRuntime {
    $archivePath = Join-Path $DownloadRoot $mhr.ArchiveName
    Assert-FileIdentity $archivePath $mhr.ArchiveBytes $mhr.ArchiveSha256 'MHR v1.0.1 asset archive'
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw "Python 3.12 was not found at $PythonPath"
    }
    $pythonVersion = (& $PythonPath -c 'import sys; print(".".join(map(str, sys.version_info[:3])))').Trim()
    if ($LASTEXITCODE -ne 0 -or -not $pythonVersion.StartsWith('3.12.')) {
        throw "MHR requires the pinned Python 3.12 lane; found $pythonVersion."
    }
    $lockPath = Join-Path $PSScriptRoot 'runtime-locks\mhr-py312-cpu-requirements.txt'
    if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
        throw "Missing MHR wheel lock at $lockPath"
    }
    $wheelRoot = Join-Path $DownloadRoot 'mhr-wheels-py312'
    $requiredWheelHashes = @(
        '87dd94cf281e586d135fa51132b8e3d9a598b316e90377a288663c9321036c82',
        'b57ddbafedfaef7018c1ecab32aa200a9d7ca26b77965f64e48b70061249d279',
        '85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67',
        '26a5784ded40c9e318cfc2bdb30fe164bdb8665ded9cd64d500a34fb42067b1c',
        'a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c',
        'd47fbf302e7d9cbbb9e2555a0d267983d2aa476bac30e90dfbe5669bd57f3762',
        'b5f0362dc928a6ecd9db58868fca5e48485205e3855957bdedea308f8672ea4a',
        'fdd925d5c5d9f62e4b74b30d6dd7828ce236fd6ed998a08d81de62ce5a6310d6',
        'e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5',
        '51c6c6e26eaa0d64ed439ebdc9ce3b8cc2d5cfcc7cdd4e72f17831d80886b7f4',
        '481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8'
    )
    $wheels = @(Get-ChildItem -LiteralPath $wheelRoot -Filter '*.whl' -File -ErrorAction Stop)
    $actualWheelHashes = @($wheels | ForEach-Object { Get-LowerSha256 $_.FullName } | Sort-Object)
    if (@(Compare-Object ($requiredWheelHashes | Sort-Object) $actualWheelHashes).Count -ne 0) {
        throw 'The MHR offline wheel cache does not match the committed hash lock.'
    }

    $componentRoot = Join-Path $DestinationRoot $mhr.Name
    $final = Join-Path $componentRoot $mhr.Version
    if (Test-InstalledRuntime -Path $final -Version $mhr.Version) {
        return [pscustomobject]@{ Name = $mhr.Name; Version = $mhr.Version; Path = $final; Reused = $true; Backup = $null }
    }
    New-Item -ItemType Directory -Path $componentRoot -Force | Out-Null
    $staging = Join-Path $componentRoot ('.staging-' + [Guid]::NewGuid().ToString('N'))
    try {
        Expand-VerifiedZip -ArchivePath $archivePath -Destination $staging
        Assert-FileIdentity (Join-Path $staging $mhr.ModelRelativePath) $mhr.ModelBytes $mhr.ModelSha256 'MHR TorchScript model'
        Assert-FileIdentity (Join-Path $staging $mhr.LicenseRelativePath) $mhr.LicenseBytes $mhr.LicenseSha256 'MHR Apache license'

        $venv = Join-Path $staging '.venv'
        Invoke-CheckedProcess $PythonPath @('-m', 'venv', $venv) 'MHR virtual environment creation'
        $venvPython = Join-Path $venv 'Scripts\python.exe'
        Invoke-CheckedProcess $venvPython @(
            '-m', 'pip', 'install', '--disable-pip-version-check', '--no-index',
            '--find-links', $wheelRoot, '--require-hashes', '-r', $lockPath
        ) 'MHR offline dependency installation'
        $modelPath = Join-Path $staging $mhr.ModelRelativePath
        $smoke = @'
import json, pathlib, torch
model_path = pathlib.Path(__import__('sys').argv[1])
model = torch.jit.load(str(model_path), map_location='cpu')
model.eval()
identity = torch.zeros((1, 45), dtype=torch.float32)
pose = torch.zeros((1, 204), dtype=torch.float32)
face = torch.zeros((1, 72), dtype=torch.float32)
with torch.no_grad():
    vertices, _ = model(identity, pose, face, True)
if tuple(vertices.shape) != (1, 18439, 3):
    raise RuntimeError(f'Unexpected MHR output shape: {tuple(vertices.shape)}')
print(json.dumps({'torch': torch.__version__, 'shape': list(vertices.shape)}))
'@
        Invoke-CheckedProcess $venvPython @('-c', $smoke, $modelPath) 'MHR TorchScript smoke test'
        $packageList = & $venvPython -m pip list --format json --disable-pip-version-check | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0) {
            throw 'MHR package inventory failed.'
        }
        $entrypoints = [ordered]@{
            ($mhr.ModelRelativePath) = $mhr.ModelSha256
            ($mhr.LicenseRelativePath) = $mhr.LicenseSha256
            '.venv\Scripts\python.exe' = Get-LowerSha256 $venvPython
        }
        $manifest = [ordered]@{
            schemaVersion = 'patterna.challenger-runtime/1.0'
            name = $mhr.Name
            version = $mhr.Version
            installedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
            archive = [ordered]@{ uri = $mhr.ArchiveUri; bytes = $mhr.ArchiveBytes; sha256 = $mhr.ArchiveSha256 }
            python = [ordered]@{ baseVersion = $pythonVersion; packages = $packageList }
            wheelLockSha256 = Get-LowerSha256 $lockPath
            entrypoints = $entrypoints
        }
        Write-JsonAtomic $manifest (Join-Path $staging 'runtime-manifest.json')
        $promotion = Promote-StagedRuntime -Staging $staging -Final $final -Version $mhr.Version
        return [pscustomobject]@{ Name = $mhr.Name; Version = $mhr.Version; Path = $promotion.Path; Reused = $promotion.Reused; Backup = $promotion.Backup }
    }
    catch {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
        throw
    }
}

function Install-PpfRuntime {
    $archivePath = Join-Path $DownloadRoot $ppf.ArchiveName
    $licensePath = Join-Path $DownloadRoot $ppf.LicenseName
    Assert-FileIdentity $archivePath $ppf.ArchiveBytes $ppf.ArchiveSha256 'PPF Windows archive'
    Assert-FileIdentity $licensePath $ppf.LicenseBytes $ppf.LicenseSha256 'PPF tag license'
    $componentRoot = Join-Path $DestinationRoot $ppf.Name
    $final = Join-Path $componentRoot $ppf.Version
    if (Test-InstalledRuntime -Path $final -Version $ppf.Version) {
        return [pscustomobject]@{ Name = $ppf.Name; Version = $ppf.Version; Path = $final; Reused = $true; Backup = $null }
    }
    New-Item -ItemType Directory -Path $componentRoot -Force | Out-Null
    $staging = Join-Path $componentRoot ('.staging-' + [Guid]::NewGuid().ToString('N'))
    try {
        Expand-VerifiedZip -ArchivePath $archivePath -Destination $staging
        $licenseDestination = Join-Path $staging 'LICENSE-APACHE-2.0.txt'
        Copy-Item -LiteralPath $licensePath -Destination $licenseDestination
        Assert-FileHash (Join-Path $staging $ppf.SolverRelativePath) $ppf.SolverSha256 'PPF solver executable'
        Assert-FileHash (Join-Path $staging $ppf.ServerRelativePath) $ppf.ServerSha256 'PPF server executable'
        Assert-FileHash (Join-Path $staging $ppf.HeadlessRelativePath) $ppf.HeadlessSha256 'PPF headless example'
        Assert-FileHash (Join-Path $staging $ppf.ReadmeRelativePath) $ppf.ReadmeSha256 'PPF README'
        Assert-FileHash (Join-Path $staging $ppf.ThirdPartyLicenseRelativePath) $ppf.ThirdPartyLicenseSha256 'PPF third-party license inventory'
        Assert-FileHash $licenseDestination $ppf.LicenseSha256 'PPF Apache license copy'
        $embeddedPython = Join-Path $staging 'python\python.exe'
        $pythonVersion = (& $embeddedPython -c 'import platform; print(platform.python_version())').Trim()
        if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne '3.11.9') {
            throw "PPF embedded Python validation failed; expected 3.11.9 and reported $pythonVersion."
        }
        $frontendRoot = $staging
        $frontendSmoke = 'import os, sys; sys.path.insert(0, sys.argv[1]); import frontend; print(frontend.__file__)'
        Invoke-CheckedProcess $embeddedPython @('-c', $frontendSmoke, $frontendRoot) 'PPF frontend import smoke test'
        $entrypoints = [ordered]@{
            ($ppf.SolverRelativePath) = $ppf.SolverSha256
            ($ppf.ServerRelativePath) = $ppf.ServerSha256
            ($ppf.HeadlessRelativePath) = $ppf.HeadlessSha256
            ($ppf.ReadmeRelativePath) = $ppf.ReadmeSha256
            ($ppf.ThirdPartyLicenseRelativePath) = $ppf.ThirdPartyLicenseSha256
            'LICENSE-APACHE-2.0.txt' = $ppf.LicenseSha256
            'python\python.exe' = Get-LowerSha256 $embeddedPython
        }
        $manifest = [ordered]@{
            schemaVersion = 'patterna.challenger-runtime/1.0'
            name = $ppf.Name
            version = $ppf.Version
            installedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
            archive = [ordered]@{ uri = $ppf.ArchiveUri; bytes = $ppf.ArchiveBytes; sha256 = $ppf.ArchiveSha256 }
            license = [ordered]@{ uri = $ppf.LicenseUri; bytes = $ppf.LicenseBytes; sha256 = $ppf.LicenseSha256 }
            embeddedPythonVersion = $pythonVersion
            entrypoints = $entrypoints
        }
        Write-JsonAtomic $manifest (Join-Path $staging 'runtime-manifest.json')
        $promotion = Promote-StagedRuntime -Staging $staging -Final $final -Version $ppf.Version
        return [pscustomobject]@{ Name = $ppf.Name; Version = $ppf.Version; Path = $promotion.Path; Reused = $promotion.Reused; Backup = $promotion.Backup }
    }
    catch {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
        throw
    }
}

New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
$results = @()
if ($Component -in @('All', 'MHR')) {
    $results += Install-MhrRuntime
}
if ($Component -in @('All', 'PPF')) {
    $results += Install-PpfRuntime
}
$catalogEntries = @()
foreach ($componentDirectory in @(Get-ChildItem -LiteralPath $DestinationRoot -Directory -ErrorAction SilentlyContinue | Where-Object Name -in @('MHR', 'PPF'))) {
    foreach ($versionDirectory in @(Get-ChildItem -LiteralPath $componentDirectory.FullName -Directory -ErrorAction SilentlyContinue | Where-Object Name -notlike '.staging-*')) {
        $manifestPath = Join-Path $versionDirectory.FullName 'runtime-manifest.json'
        if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
            $manifestHash = Get-LowerSha256 $manifestPath
            $catalogEntries += [ordered]@{
                name = $componentDirectory.Name
                version = $versionDirectory.Name
                path = $versionDirectory.FullName
                manifestSha256 = $manifestHash
            }
        }
    }
}
$catalog = [ordered]@{
    schemaVersion = 'patterna.challenger-runtime-catalog/1.0'
    generatedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
    runtimes = $catalogEntries
}
Write-JsonAtomic $catalog (Join-Path $DestinationRoot 'challenger-runtime-catalog.json')
$results
