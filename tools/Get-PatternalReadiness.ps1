<#
.SYNOPSIS
    Gather every gate this project can evaluate into one status.

.DESCRIPTION
    Readiness is spread across a packaged-asset report, a renderer contract
    check, a product acceptance gate, an isolated guest run, and two live
    control sweeps. Answering "where does this stand" meant opening five files
    and knowing which were current, which is how a stale blocker survived being
    repeated for a whole working session.

    This reads the newest of each and prints them together, separating what is
    still failing into what more work can close and what needs a person or an
    instrument. It evaluates nothing itself and accepts nothing; every line is
    read from evidence another tool wrote.
#>
[CmdletBinding()]
param(
    [string]$OutputPath = 'artifacts/patternal-readiness.json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Read-Json {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $text = [System.Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xFEFF)
    try { return $text | ConvertFrom-Json } catch { return $null }
}

function Newest {
    param([string]$Pattern)
    $match = Get-ChildItem -Path $Pattern -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    return $match
}

$report = [ordered]@{
    schemaVersion = 'patterna.readiness/1.0'
    claims        = [ordered]@{ accepted = $false }
    note          = 'Every line here is read from evidence another tool wrote. Nothing is evaluated or accepted here.'
    gatheredAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
}

# ---- What the packaged application ships ----
$shipped = Read-Json 'Patternal/Assets/SolvedDrape/packaged-drape-assets.json'
if ($null -ne $shipped) {
    $report.shippedAsset = [ordered]@{
        identity  = $shipped.garmentArchetype
        claims    = $shipped.claims
        openGates = $shipped.openGates
    }
}

# ---- The isolated packaged gate ----
$run = Newest 'artifacts/isolated-ui/runs/*/result.json'
if ($null -ne $run) {
    $result = Read-Json $run.FullName
    if ($null -ne $result) {
        $failed = @($result.actions | Where-Object { -not $_.passed })
        $report.isolatedPackagedGate = [ordered]@{
            run               = Split-Path -Leaf (Split-Path -Parent $run.FullName)
            passed            = $result.passed
            actions           = @($result.actions).Count
            actionsPassed     = @($result.actions | Where-Object { $_.passed }).Count
            failedActions     = @($failed | ForEach-Object { $_.name })
            hostInputInjected = $result.hostInputInjected
            screenshots       = @($result.screenshots).Count
        }
    }
}

# ---- Live control behaviour ----
$sweep = Newest 'artifacts/control-sweep/control-sweep*.json'
if ($null -ne $sweep) {
    $s = (Read-Json $sweep.FullName).summary
    if ($null -ne $s) {
        $report.controlSweep = [ordered]@{
            source              = $sweep.Name
            slidersFound        = $s.slidersFound
            slidersMoved        = $s.slidersMovedToProbe
            numberBoxesFound    = $s.numberBoxesFound
            numberBoxesMoved    = $s.numberBoxesMovedToProbe
            togglesResponded    = $s.togglesResponded
            nothingFailedToRestore =
                (@($s.slidersNotRestored).Count -eq 0 -and @($s.numberBoxesNotRestored).Count -eq 0)
        }
    }
}
$workspace = Read-Json 'artifacts/control-sweep/workspace-sweep.json'
if ($null -ne $workspace) {
    $report.workspaceSweep = [ordered]@{
        cameraButtonsFound          = $workspace.summary.cameraButtonsFound
        cameraButtonsChangingTheView = $workspace.summary.cameraButtonsThatChangedTheView
        assemblyTogglesEnabled      = $workspace.summary.assemblyTogglesEnabled
    }
}

# ---- Fabric ----
$fabric = Read-Json 'artifacts/fabric-coherence-shipped-v1.json'
if ($null -ne $fabric) {
    $report.fabric = [ordered]@{
        physicallyCoherent = $fabric.claims.physicallyCoherent
        calibrated         = $fabric.claims.calibratedFabric
        failedRelations    = $fabric.failedRelations
    }
}

# ---- What is left, split by who can close it ----
$softwareCanClose = @()
$needsAPersonOrInstrument = @()
if ($null -ne $shipped) {
    foreach ($gate in $shipped.openGates) {
        if ($gate -match 'reviewed|accepted these six views') {
            $needsAPersonOrInstrument += "$gate (a person must judge the images)"
        }
        elseif ($gate -match 'swatch|calibrat') {
            $needsAPersonOrInstrument += "$gate (an instrument must measure real cloth)"
        }
        else {
            $softwareCanClose += $gate
        }
    }
}
if ($null -ne $report.isolatedPackagedGate -and $report.isolatedPackagedGate.failedActions.Count -gt 0) {
    $softwareCanClose += $report.isolatedPackagedGate.failedActions
}
$report.remaining = [ordered]@{
    softwareCanClose         = $softwareCanClose
    needsAPersonOrInstrument = $needsAPersonOrInstrument
}

$outputFile = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
$directory = Split-Path -Parent $outputFile
if (-not (Test-Path -LiteralPath $directory)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
[System.IO.File]::WriteAllText(
    $outputFile,
    (($report | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
    [System.Text.UTF8Encoding]::new($false))

Write-Output "Readiness written to $outputFile"
$report | ConvertTo-Json -Depth 8
