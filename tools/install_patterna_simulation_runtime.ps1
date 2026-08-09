[CmdletBinding()]
param(
    [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DestinationRoot = (Join-Path $env:LOCALAPPDATA 'Patterna\SimulationRuntime'),
    [string]$RuntimeVersion = '2026.07.23-style3d-v2',
    [switch]$Replace
)

$ErrorActionPreference = 'Stop'

function Require-File {
    param([string]$Path, [string]$Description)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing $Description at $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Require-Directory {
    param([string]$Path, [string]$Description)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Missing $Description at $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Copy-RuntimeTree {
    param([string]$Source, [string]$Destination, [string]$Label)
    Write-Host "Copying $Label"
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $arguments = @(
        $Source,
        $Destination,
        '/E',
        '/COPY:DAT',
        '/DCOPY:DAT',
        '/R:2',
        '/W:1',
        '/NFL',
        '/NDL',
        '/NJH',
        '/NJS',
        '/NP',
        '/XD',
        '.git',
        '__pycache__',
        '.pytest_cache'
    )
    & robocopy @arguments | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "Robocopy failed for $Label with exit code $LASTEXITCODE"
    }
}

function Write-VenvConfiguration {
    param([string]$ConfigurationPath, [string]$FinalPythonHome)
    $updated = foreach ($line in Get-Content -LiteralPath $ConfigurationPath) {
        if ($line -match '^home\s*=') {
            "home = $FinalPythonHome"
        }
        elseif ($line -match '^executable\s*=') {
            "executable = $(Join-Path $FinalPythonHome 'python.exe')"
        }
        elseif ($line -match '^command\s*=') {
            "command = Patterna installed simulation runtime"
        }
        else {
            $line
        }
    }
    [System.IO.File]::WriteAllLines(
        $ConfigurationPath,
        [string[]]$updated,
        [System.Text.UTF8Encoding]::new($false))
}

function Rewrite-RuntimeReference {
    param([string]$Path, [string]$OldRoot, [string]$NewRoot)
    $content = [System.IO.File]::ReadAllText($Path)
    $updated = $content.Replace($OldRoot, $NewRoot).Replace(
        $OldRoot.Replace('\', '/'),
        $NewRoot.Replace('\', '/'))
    if ($updated -ne $content) {
        [System.IO.File]::WriteAllText(
            $Path,
            $updated,
            [System.Text.UTF8Encoding]::new($false))
    }
}

function Relative-RuntimePath {
    param([string]$Root, [string]$Path)
    return [System.IO.Path]::GetRelativePath($Root, $Path).Replace('\', '/')
}

$source = Require-Directory $SourceRoot 'Patterna source root'
$destination = [System.IO.Path]::GetFullPath($DestinationRoot)
$current = Join-Path $destination 'current'
$staging = Join-Path $destination ('.staging-' + [Guid]::NewGuid().ToString('N'))

if (Test-Path -LiteralPath $current) {
    if (-not $Replace) {
        throw "A Patterna simulation runtime already exists at $current. Use -Replace to preserve it as a backup and install a new runtime."
    }
    $backup = Join-Path $destination ('backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Move-Item -LiteralPath $current -Destination $backup
    Write-Host "Preserved the previous runtime at $backup"
}

New-Item -ItemType Directory -Path $staging -Force | Out-Null

$garmentVenvSource = Require-Directory (Join-Path $source '.venv-garmentcode') 'GarmentCode Python environment'
$newtonVenvSource = Require-Directory (Join-Path $source '.venv-newton') 'Newton Style3D Python environment'
$garmentConfiguration = Require-File (Join-Path $garmentVenvSource 'pyvenv.cfg') 'GarmentCode Python configuration'
$pythonHomeLine = Get-Content -LiteralPath $garmentConfiguration | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
if (-not $pythonHomeLine) {
    throw 'The GarmentCode Python environment does not declare its base Python home.'
}
$pythonHomeSource = Require-Directory (($pythonHomeLine -split '=', 2)[1].Trim()) 'base Python runtime'

$compilerCandidates = @(
    (Join-Path $source 'Patternal.UnrealGarmentCompiler\bin\x64\Release\net10.0'),
    (Join-Path $source 'Patternal.UnrealGarmentCompiler\bin\x64\Debug\net10.0'),
    (Join-Path $source 'Patternal.UnrealGarmentCompiler\bin\Release\net10.0'),
    (Join-Path $source 'Patternal.UnrealGarmentCompiler\bin\Debug\net10.0')
) | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'Patternal.UnrealGarmentCompiler.exe') }
if ($compilerCandidates.Count -eq 0) {
    throw 'The Patterna garment compiler has not been built.'
}
$compilerSource = $compilerCandidates |
    Sort-Object { (Get-Item -LiteralPath (Join-Path $_ 'Patternal.UnrealGarmentCompiler.dll')).LastWriteTimeUtc } -Descending |
    Select-Object -First 1

$blenderSource = Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Patterna\Tools') -Filter blender.exe -File -Recurse -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1 -ExpandProperty DirectoryName
if (-not $blenderSource) {
    $blenderSource = Get-ChildItem -LiteralPath (Join-Path $source '.runtime\blender') -Filter blender.exe -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1 -ExpandProperty DirectoryName
}
$blenderSource = Require-Directory $blenderSource 'managed Blender runtime'

Copy-RuntimeTree $pythonHomeSource (Join-Path $staging 'python-base') 'base Python runtime'
Copy-RuntimeTree $garmentVenvSource (Join-Path $staging '.venv-garmentcode') 'GarmentCode Python environment'
Copy-RuntimeTree $newtonVenvSource (Join-Path $staging '.venv-newton') 'Newton Style3D Python environment'
Copy-RuntimeTree (Require-Directory (Join-Path $source 'third_party\GarmentCode') 'GarmentCode source') (Join-Path $staging 'third_party\GarmentCode') 'GarmentCode source and assets'
Copy-RuntimeTree (Require-Directory (Join-Path $source 'third_party\NvidiaWarp-GarmentCode') 'GarmentCode Warp source') (Join-Path $staging 'third_party\NvidiaWarp-GarmentCode') 'GarmentCode Warp runtime'
Copy-RuntimeTree (Require-Directory (Join-Path $source 'third_party\MPFB2') 'MPFB source') (Join-Path $staging 'third_party\MPFB2') 'MPFB body system'
Copy-RuntimeTree (Require-Directory (Join-Path $source 'third_party\MakeHumanAssets') 'MakeHuman assets') (Join-Path $staging 'third_party\MakeHumanAssets') 'MakeHuman body and appearance assets'
Copy-RuntimeTree (Require-Directory (Join-Path $source 'third_party\CharMorph-db\characters\mb_female') 'CharMorph female character data') (Join-Path $staging 'third_party\CharMorph-db\characters\mb_female') 'CharMorph female body system'
Copy-RuntimeTree $blenderSource (Join-Path $staging 'blender') 'Blender runtime'
Copy-RuntimeTree $compilerSource (Join-Path $staging 'compiler') 'Patterna garment compiler'

$toolsDestination = Join-Path $staging 'tools'
New-Item -ItemType Directory -Path $toolsDestination -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $source 'tools') -Filter '*.py' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $toolsDestination $_.Name)
}

$finalPythonHome = Join-Path $current 'python-base'
Write-VenvConfiguration (Join-Path $staging '.venv-garmentcode\pyvenv.cfg') $finalPythonHome
Write-VenvConfiguration (Join-Path $staging '.venv-newton\pyvenv.cfg') $finalPythonHome

$runtimeReferenceFiles = @(
    Get-ChildItem -LiteralPath (Join-Path $staging '.venv-garmentcode\Lib\site-packages') -Filter '__editable__*.pth' -File -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath (Join-Path $staging '.venv-newton\Lib\site-packages') -Filter '__editable__*.pth' -File -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath (Join-Path $staging '.venv-garmentcode\Lib\site-packages') -Filter '__editable___warp_lang*_finder.py' -File -ErrorAction SilentlyContinue
)
foreach ($referenceFile in $runtimeReferenceFiles) {
    Rewrite-RuntimeReference $referenceFile.FullName $source $current
}

$sourceRevisions = [ordered]@{}
foreach ($sourceDirectoryName in @('MPFB2', 'GarmentCode', 'MakeHumanAssets', 'NvidiaWarp-GarmentCode', 'CharMorph-db')) {
    $sourceDirectory = Join-Path $source "third_party\$sourceDirectoryName"
    $revision = (& git -C $sourceDirectory rev-parse HEAD 2>$null)
    if ($LASTEXITCODE -eq 0 -and $revision -match '^[0-9a-fA-F]{40}$') {
        $sourceRevisions[$sourceDirectoryName] = $revision.ToLowerInvariant()
    }
}
if (-not $sourceRevisions.Contains('MPFB2')) {
    throw 'The installer could not record the exact MPFB source revision.'
}
if (-not $sourceRevisions.Contains('CharMorph-db')) {
    throw 'The installer could not record the exact CharMorph character-data revision.'
}
$sourceRevisionPath = Join-Path $staging 'runtime-source-revisions.json'
[System.IO.File]::WriteAllText(
    $sourceRevisionPath,
    ($sourceRevisions | ConvertTo-Json),
    [System.Text.UTF8Encoding]::new($false))

$requiredScripts = @(
    'fit_charmorph_profile.py',
    'generate_charmorph_avatar.py',
    'prepare_charmorph_garmentcode_body.py',
    'charmorph_collision.py',
    'charmorph_character.py',
    'charmorph_glb.py',
    'verify_charmorph_glb.py',
    'charmorph_morphs.py',
    'charmorph_profile_controls.py',
    'mesh_torso_arcs.py',
    'generate_body_profile_from_mesh.py',
    'export_garmentcode_pattern_mesh.py',
    'build_style3d_source.py',
    'prefit_newton_style3d.py',
    'patterna_style3d_sewing.py',
    'render_product_acceptance.py',
    'product_registration.py'
)
$integrityFiles = @(
    (Join-Path $staging '.venv-garmentcode\Scripts\python.exe'),
    (Join-Path $staging '.venv-newton\Scripts\python.exe'),
    (Join-Path $staging 'blender\blender.exe'),
    (Join-Path $staging 'compiler\Patternal.UnrealGarmentCompiler.exe'),
    (Join-Path $staging '.venv-garmentcode\pyvenv.cfg'),
    (Join-Path $staging '.venv-newton\pyvenv.cfg'),
    $sourceRevisionPath,
    (Join-Path $staging 'third_party\GarmentCode\assets\img\fabric_texture.png')
)
$integrityFiles += $requiredScripts | ForEach-Object { Join-Path $toolsDestination $_ }
$integrityFiles += $runtimeReferenceFiles | Select-Object -ExpandProperty FullName
$integrityFiles += Get-ChildItem -LiteralPath (Join-Path $staging 'compiler') -File | Select-Object -ExpandProperty FullName
$integrityFiles += @(
    (Join-Path $staging 'third_party\GarmentCode\pygarment\__init__.py'),
    (Join-Path $staging '.venv-newton\Lib\site-packages\newton\__init__.py'),
    (Join-Path $staging '.venv-newton\Lib\site-packages\warp\__init__.py'),
    (Join-Path $staging 'third_party\CharMorph-db\characters\mb_female\license.txt')
) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
$integrityFiles = $integrityFiles | Sort-Object -Unique

$hashes = [ordered]@{}
foreach ($file in $integrityFiles) {
    $relative = Relative-RuntimePath $staging $file
    $hashes[$relative] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
}

$manifest = [ordered]@{
    schemaVersion = 'patterna.simulation-runtime/1.0'
    runtimeVersion = $RuntimeVersion
    garmentCodePython = '.venv-garmentcode/Scripts/python.exe'
    style3dPython = '.venv-newton/Scripts/python.exe'
    blender = 'blender/blender.exe'
    compiler = 'compiler/Patternal.UnrealGarmentCompiler.exe'
    toolsDirectory = 'tools'
    avatarBackend = 'CharMorph mb_female'
    avatarOutputLicense = 'AGPL-3.0'
    avatarLicenseFile = 'third_party/CharMorph-db/characters/mb_female/license.txt'
    entrypointSha256 = $hashes
}
$manifestPath = Join-Path $staging 'runtime-manifest.json'
[System.IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 6),
    [System.Text.UTF8Encoding]::new($false))

New-Item -ItemType Directory -Path $destination -Force | Out-Null
Move-Item -LiteralPath $staging -Destination $current

try {
    $env:PATTERNA_SIMULATION_RUNTIME_ROOT = $current
    & (Join-Path $current '.venv-garmentcode\Scripts\python.exe') -c 'import os, sys; sys.path.insert(0, os.path.join(os.environ["PATTERNA_SIMULATION_RUNTIME_ROOT"], "third_party", "GarmentCode")); import numpy, trimesh, pygarment; print("GarmentCode runtime accepted")'
    if ($LASTEXITCODE -ne 0) {
        throw "GarmentCode Python validation exited with code $LASTEXITCODE"
    }
    & (Join-Path $current '.venv-newton\Scripts\python.exe') -c 'import newton, warp, trimesh; print("Newton Style3D runtime accepted")'
    if ($LASTEXITCODE -ne 0) {
        throw "Newton Style3D Python validation exited with code $LASTEXITCODE"
    }
    & (Join-Path $current 'blender\blender.exe') --version | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) {
        throw "Blender validation exited with code $LASTEXITCODE"
    }
}
catch {
    $failed = Join-Path $destination ('failed-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Move-Item -LiteralPath $current -Destination $failed
    throw "The staged runtime failed validation and was preserved at $failed. $($_.Exception.Message)"
}
finally {
    Remove-Item Env:PATTERNA_SIMULATION_RUNTIME_ROOT -ErrorAction SilentlyContinue
}

Write-Host "Patterna simulation runtime installed at $current"
Write-Host "Runtime version: $RuntimeVersion"
