[CmdletBinding()]
param(
    [ValidateSet('All', 'MHR', 'PPF', 'Anny', 'LibUIPC')]
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

$anny = [ordered]@{
    Name = 'Anny'
    Version = 'v0.6.0-py312-torch2.13.0-cu126'
    WheelDirectoryName = 'anny-wheels-py312-cu126'
    LockName = 'anny-py312-cu126-requirements.txt'
    WheelName = 'anny-0.6.0-py3-none-any.whl'
    WheelBytes = 47705473L
    WheelSha256 = '050a0b24a3e7fdb89b46dc3581947ea84225305425ac9a1a97b65ea997fb2ad6'
    ReleaseTagCommit = '72104cac8242d1735ec06433b65bec5e26953ce7'
    WheelUri = 'https://files.pythonhosted.org/packages/67/a5/59594be242b7239d725ce982bacbe5fa6a7e37075cc62488396234f2c4f8/anny-0.6.0-py3-none-any.whl'
}
$libuipc = [ordered]@{
    Name = 'LibUIPC'
    Version = 'v0.0.25-py312-cuda'
    WheelDirectoryName = 'libuipc-wheels-py312'
    LockName = 'libuipc-py312-requirements.txt'
    WheelName = 'pyuipc-0.0.25-cp312-cp312-win_amd64.whl'
    WheelBytes = 32078944L
    WheelSha256 = 'b636a64689e1f63e58cef177dce6edd6cea2d454d534234d1f953d5b8ad5b074'
    WheelUri = 'https://files.pythonhosted.org/packages/85/11/999268750624872f57660ca7311ef10b755214af8664ff19528605fa6194/pyuipc-0.0.25-cp312-cp312-win_amd64.whl'
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

function Assert-PinnedPythonLane {
    param([Parameter(Mandatory)][string]$Description)
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw "Python 3.12 was not found at $PythonPath"
    }
    $pythonVersion = (& $PythonPath -c 'import sys; print(".".join(map(str, sys.version_info[:3])))').Trim()
    if ($LASTEXITCODE -ne 0 -or -not $pythonVersion.StartsWith('3.12.')) {
        throw "$Description requires the pinned Python 3.12 lane; found $pythonVersion."
    }
    return $pythonVersion
}

function Assert-WheelhouseMatchesLock {
    param(
        [Parameter(Mandatory)][string]$WheelRoot,
        [Parameter(Mandatory)][string]$LockPath,
        [Parameter(Mandatory)][string]$Description
    )
    if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) {
        throw "Missing $Description wheel lock at $LockPath"
    }
    $lockHashes = @(
        Select-String -LiteralPath $LockPath -Pattern '--hash=sha256:([0-9a-f]{64})' -AllMatches |
            ForEach-Object { $_.Matches } |
            ForEach-Object { $_.Groups[1].Value }
    )
    if ($lockHashes.Count -eq 0) {
        throw "$Description wheel lock declares no hashes: $LockPath"
    }
    $wheels = @(Get-ChildItem -LiteralPath $WheelRoot -Filter '*.whl' -File -ErrorAction Stop)
    if ($wheels.Count -ne $lockHashes.Count) {
        throw "$Description wheelhouse holds $($wheels.Count) wheels; the lock declares $($lockHashes.Count)."
    }
    $actualHashes = @($wheels | ForEach-Object { Get-LowerSha256 $_.FullName } | Sort-Object)
    if (@(Compare-Object ($lockHashes | Sort-Object) $actualHashes).Count -ne 0) {
        throw "The $Description offline wheel cache does not match the committed hash lock."
    }
    return @(
        $wheels | Sort-Object Name | ForEach-Object {
            [ordered]@{ filename = $_.Name; bytes = $_.Length; sha256 = Get-LowerSha256 $_.FullName }
        }
    )
}

function Install-AnnyRuntime {
    $pythonVersion = Assert-PinnedPythonLane -Description 'Anny'
    $wheelRoot = Join-Path $DownloadRoot $anny.WheelDirectoryName
    $lockPath = Join-Path $PSScriptRoot ('runtime-locks\' + $anny.LockName)
    $wheelInventory = Assert-WheelhouseMatchesLock -WheelRoot $wheelRoot -LockPath $lockPath -Description 'Anny'
    $annyWheelPath = Join-Path $wheelRoot $anny.WheelName
    Assert-FileIdentity $annyWheelPath $anny.WheelBytes $anny.WheelSha256 'Anny 0.6.0 release wheel'
    Invoke-CheckedProcess $PythonPath @(
        (Join-Path $PSScriptRoot 'verify_anny_release_wheel.py'), '--wheel', $annyWheelPath
    ) 'Anny release wheel verification'

    $componentRoot = Join-Path $DestinationRoot $anny.Name
    $final = Join-Path $componentRoot $anny.Version
    if (Test-InstalledRuntime -Path $final -Version $anny.Version) {
        return [pscustomobject]@{ Name = $anny.Name; Version = $anny.Version; Path = $final; Reused = $true; Backup = $null }
    }
    New-Item -ItemType Directory -Path $componentRoot -Force | Out-Null
    $staging = Join-Path $componentRoot ('.staging-' + [Guid]::NewGuid().ToString('N'))
    try {
        New-Item -ItemType Directory -Path $staging -Force | Out-Null
        $venv = Join-Path $staging '.venv'
        Invoke-CheckedProcess $PythonPath @('-m', 'venv', $venv) 'Anny virtual environment creation'
        $venvPython = Join-Path $venv 'Scripts\python.exe'
        Invoke-CheckedProcess $venvPython @(
            '-m', 'pip', 'install', '--disable-pip-version-check', '--no-index', '--no-deps',
            '--find-links', $wheelRoot, '--require-hashes', '-r', $lockPath
        ) 'Anny offline dependency installation'
        Invoke-CheckedProcess $venvPython @(
            '-m', 'pip', 'check', '--disable-pip-version-check'
        ) 'Anny installed dependency consistency check'

        $smokeTool = Join-Path $PSScriptRoot 'run_anny_install_smoke.py'
        $smokeReports = @()
        foreach ($runIndex in 1, 2) {
            $cacheDir = Join-Path $staging "anny-cache-run$runIndex"
            $reportPath = Join-Path $staging "anny-install-smoke-run$runIndex.json"
            Invoke-CheckedProcess $venvPython @(
                $smokeTool, '--cache-dir', $cacheDir, '--output', $reportPath
            ) "Anny offline neutral-body smoke test run $runIndex"
            $smokeReports += $reportPath
        }
        $firstRun = Get-Content -LiteralPath $smokeReports[0] -Raw | ConvertFrom-Json
        $secondRun = Get-Content -LiteralPath $smokeReports[1] -Raw | ConvertFrom-Json
        $firstDeterministic = $firstRun.deterministic | ConvertTo-Json -Depth 8
        $secondDeterministic = $secondRun.deterministic | ConvertTo-Json -Depth 8
        if ($firstDeterministic -ne $secondDeterministic) {
            throw 'Two clean Anny smoke runs produced different deterministic sections.'
        }
        $firstCacheNames = ($firstRun.cacheFileNames | ConvertTo-Json -Depth 4)
        $secondCacheNames = ($secondRun.cacheFileNames | ConvertTo-Json -Depth 4)
        if ($firstCacheNames -ne $secondCacheNames) {
            throw 'Two clean Anny smoke runs wrote different cache file sets.'
        }

        $packageList = & $venvPython -m pip list --format json --disable-pip-version-check | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0) {
            throw 'Anny package inventory failed.'
        }
        $entrypoints = [ordered]@{
            '.venv\Scripts\python.exe' = Get-LowerSha256 $venvPython
            'anny-install-smoke-run1.json' = Get-LowerSha256 $smokeReports[0]
            'anny-install-smoke-run2.json' = Get-LowerSha256 $smokeReports[1]
        }
        $manifest = [ordered]@{
            schemaVersion = 'patterna.challenger-runtime/1.0'
            name = $anny.Name
            version = $anny.Version
            installedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
            archive = [ordered]@{ uri = $anny.WheelUri; bytes = $anny.WheelBytes; sha256 = $anny.WheelSha256 }
            releaseTagCommit = $anny.ReleaseTagCommit
            python = [ordered]@{ baseVersion = $pythonVersion; packages = $packageList }
            wheelLockSha256 = Get-LowerSha256 $lockPath
            wheelhouse = $wheelInventory
            neutralVerticesSha256 = $firstRun.deterministic.verticesSha256
            entrypoints = $entrypoints
        }
        Write-JsonAtomic $manifest (Join-Path $staging 'runtime-manifest.json')
        $promotion = Promote-StagedRuntime -Staging $staging -Final $final -Version $anny.Version
        return [pscustomobject]@{ Name = $anny.Name; Version = $anny.Version; Path = $promotion.Path; Reused = $promotion.Reused; Backup = $promotion.Backup }
    }
    catch {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
        throw
    }
}

function Install-LibUipcRuntime {
    $pythonVersion = Assert-PinnedPythonLane -Description 'LibUIPC'
    $wheelRoot = Join-Path $DownloadRoot $libuipc.WheelDirectoryName
    $lockPath = Join-Path $PSScriptRoot ('runtime-locks\' + $libuipc.LockName)
    $wheelInventory = Assert-WheelhouseMatchesLock -WheelRoot $wheelRoot -LockPath $lockPath -Description 'LibUIPC'
    $pyuipcWheelPath = Join-Path $wheelRoot $libuipc.WheelName
    Assert-FileIdentity $pyuipcWheelPath $libuipc.WheelBytes $libuipc.WheelSha256 'pyuipc 0.0.25 CUDA wheel'

    $componentRoot = Join-Path $DestinationRoot $libuipc.Name
    $final = Join-Path $componentRoot $libuipc.Version
    if (Test-InstalledRuntime -Path $final -Version $libuipc.Version) {
        return [pscustomobject]@{ Name = $libuipc.Name; Version = $libuipc.Version; Path = $final; Reused = $true; Backup = $null }
    }
    New-Item -ItemType Directory -Path $componentRoot -Force | Out-Null
    $staging = Join-Path $componentRoot ('.staging-' + [Guid]::NewGuid().ToString('N'))
    try {
        New-Item -ItemType Directory -Path $staging -Force | Out-Null
        $venv = Join-Path $staging '.venv'
        Invoke-CheckedProcess $PythonPath @('-m', 'venv', $venv) 'LibUIPC virtual environment creation'
        $venvPython = Join-Path $venv 'Scripts\python.exe'
        Invoke-CheckedProcess $venvPython @(
            '-m', 'pip', 'install', '--disable-pip-version-check', '--no-index', '--no-deps',
            '--find-links', $wheelRoot, '--require-hashes', '-r', $lockPath
        ) 'LibUIPC offline dependency installation'
        Invoke-CheckedProcess $venvPython @(
            '-m', 'pip', 'check', '--disable-pip-version-check'
        ) 'LibUIPC installed dependency consistency check'

        $siteCustomize = @'
"""Patterna LibUIPC challenger runtime bootstrap.

Prepends the venv-local NVIDIA CUDA runtime DLL directories to the process
PATH so the libuipc CUDA backend's dependent DLLs (cudart, cuBLAS, cuSOLVER,
cuSPARSE, nvJitLink) resolve without a system CUDA toolkit installation or a
machine-level PATH change.
"""
import os
from pathlib import Path

_nvidia_root = Path(__file__).resolve().parent / "nvidia"
if _nvidia_root.is_dir():
    _dll_dirs = sorted({str(p.parent) for p in _nvidia_root.rglob("*.dll")})
    for _dir in _dll_dirs:
        try:
            os.add_dll_directory(_dir)
        except OSError:
            pass
    os.environ["PATH"] = os.pathsep.join(_dll_dirs + [os.environ.get("PATH", "")])
'@
        $siteCustomizePath = Join-Path $venv 'Lib\site-packages\sitecustomize.py'
        [System.IO.File]::WriteAllText($siteCustomizePath, $siteCustomize, [System.Text.UTF8Encoding]::new($false))

        $smokeTool = Join-Path $PSScriptRoot 'run_libuipc_install_smoke.py'
        $workspace = Join-Path $staging 'engine-probe-workspace'
        $reportPath = Join-Path $staging 'libuipc-install-smoke.json'
        Invoke-CheckedProcess $venvPython @(
            $smokeTool, '--workspace', $workspace, '--output', $reportPath
        ) 'LibUIPC offline import and CUDA engine smoke test'
        $smoke = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
        if ($smoke.pyuipcVersion -ne '0.0.25') {
            throw "The installed pyuipc version is $($smoke.pyuipcVersion); expected 0.0.25."
        }

        $packageList = & $venvPython -m pip list --format json --disable-pip-version-check | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0) {
            throw 'LibUIPC package inventory failed.'
        }
        $entrypoints = [ordered]@{
            '.venv\Scripts\python.exe' = Get-LowerSha256 $venvPython
            '.venv\Lib\site-packages\sitecustomize.py' = Get-LowerSha256 $siteCustomizePath
            'libuipc-install-smoke.json' = Get-LowerSha256 $reportPath
        }
        $manifest = [ordered]@{
            schemaVersion = 'patterna.challenger-runtime/1.0'
            name = $libuipc.Name
            version = $libuipc.Version
            installedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
            archive = [ordered]@{ uri = $libuipc.WheelUri; bytes = $libuipc.WheelBytes; sha256 = $libuipc.WheelSha256 }
            python = [ordered]@{ baseVersion = $pythonVersion; packages = $packageList }
            wheelLockSha256 = Get-LowerSha256 $lockPath
            wheelhouse = $wheelInventory
            licenseFindings = $smoke.pyuipcLicenseConflict
            entrypoints = $entrypoints
        }
        Write-JsonAtomic $manifest (Join-Path $staging 'runtime-manifest.json')
        $promotion = Promote-StagedRuntime -Staging $staging -Final $final -Version $libuipc.Version
        return [pscustomobject]@{ Name = $libuipc.Name; Version = $libuipc.Version; Path = $promotion.Path; Reused = $promotion.Reused; Backup = $promotion.Backup }
    }
    catch {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
        throw
    }
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
if ($Component -in @('All', 'Anny')) {
    $results += Install-AnnyRuntime
}
if ($Component -in @('All', 'LibUIPC')) {
    $results += Install-LibUipcRuntime
}
$catalogEntries = @()
foreach ($componentDirectory in @(Get-ChildItem -LiteralPath $DestinationRoot -Directory -ErrorAction SilentlyContinue | Where-Object Name -in @('MHR', 'PPF', 'Anny', 'LibUIPC'))) {
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
