[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$VmName = 'Patternal-UI',
    [ValidateRange(60, 1800)]
    [int]$TimeoutSeconds = 600,
    [ValidateSet('full', 'persistence-only')]
    [string]$Mode = 'full',
    [ValidateRange(1280, 3840)]
    [int]$DisplayWidth = 1920,
    [ValidateRange(720, 2160)]
    [int]$DisplayHeight = 1080,
    [ValidateRange(100, 225)]
    [int]$TextScalePercent = 100,
    [switch]$KeepAppOpen
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Patternal.IsolatedUi.psm1') -Force
$repositoryRoot = Get-PatternalRepositoryRoot
$vm = Assert-PatternalHyperVAccess -VmName $VmName
if ($vm.State -ne 'Running') {
    Start-VM -Name $VmName | Out-Null
}

$runId = [DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$guestRequestPath = 'C:\PatternalTest\run-request.json'
$guestStagedRequestPath = "C:\PatternalTest\run-request-$runId.json"
$guestEvidenceRoot = 'C:\PatternalTest\Evidence'
$localEvidenceParent = Join-Path $repositoryRoot 'artifacts\isolated-ui\runs'
$localRequestPath = Join-Path $env:TEMP "Patternal-$runId-request.json"
$localEvidencePath = Join-Path $localEvidenceParent $runId

$request = [ordered]@{
    schema = 'patternal.isolated-ui-request/1.0'
    runId = $runId
    aumid = 'C513E361-86E8-4FBD-9FF7-FABA0EAFA8FE_1z32rh13vfry6!App'
    expectedWindowTitle = 'Patternal'
    evidenceRoot = $guestEvidenceRoot
    keepAppOpen = $KeepAppOpen.IsPresent
    mode = $Mode
    displayWidth = $DisplayWidth
    displayHeight = $DisplayHeight
    textScalePercent = $TextScalePercent
    requestedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
}
$request | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $localRequestPath -Encoding utf8

$credential = Get-PatternalGuestCredential -VmName $VmName
$session = New-PatternalVmSession -VmName $VmName -Credential $credential
try {
    Copy-Item -ToSession $session -LiteralPath $localRequestPath -Destination $guestStagedRequestPath
    Invoke-Command -Session $session -ScriptBlock {
        param($StagedRequestPath, $RequestPath)
        $task = Get-ScheduledTask -TaskName 'Patternal Guest UI Smoke' -ErrorAction Stop
        if ($task.State -eq 'Running') {
            Remove-Item -LiteralPath $StagedRequestPath -Force -ErrorAction SilentlyContinue
            throw 'The guest UI smoke task is already running.'
        }

        Move-Item -LiteralPath $StagedRequestPath -Destination $RequestPath -Force
        Start-ScheduledTask -TaskName 'Patternal Guest UI Smoke'
    } -ArgumentList $guestStagedRequestPath, $guestRequestPath

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    $taskStartRequestedAt = Get-Date
    $guestResultPath = "$guestEvidenceRoot\$runId\result.json"
    do {
        $guestStatus = Invoke-Command -Session $session -ScriptBlock {
            param($Path)
            $task = Get-ScheduledTask -TaskName 'Patternal Guest UI Smoke' -ErrorAction Stop
            $taskInfo = Get-ScheduledTaskInfo -TaskName 'Patternal Guest UI Smoke' -ErrorAction Stop
            [pscustomobject]@{
                ResultExists = Test-Path -LiteralPath $Path
                TaskState = $task.State.ToString()
                LastRunTime = $taskInfo.LastRunTime
                LastTaskResult = $taskInfo.LastTaskResult
            }
        } -ArgumentList $guestResultPath
        $complete = $guestStatus.ResultExists
        if ($complete) {
            break
        }
        if ($guestStatus.TaskState -ne 'Running' -and
            $guestStatus.LastRunTime -ge $taskStartRequestedAt.AddSeconds(-2)) {
            throw "Guest UI smoke task exited before writing result.json. Task state was $($guestStatus.TaskState); last task result was $($guestStatus.LastTaskResult)."
        }
        Start-Sleep -Seconds 5
    } while ([DateTimeOffset]::UtcNow -lt $deadline)

    if (-not $complete) {
        throw "Guest UI smoke test did not finish within $TimeoutSeconds seconds."
    }

    New-Item -ItemType Directory -Path $localEvidenceParent -Force | Out-Null
    if (Test-Path -LiteralPath $localEvidencePath) {
        throw "Refusing to overwrite evidence directory: $localEvidencePath"
    }
    Copy-Item -FromSession $session -Path "$guestEvidenceRoot\$runId" -Destination $localEvidenceParent -Recurse
}
finally {
    Remove-PSSession -Session $session
    if (Test-Path -LiteralPath $localRequestPath) {
        Remove-Item -LiteralPath $localRequestPath -Force
    }
}

$resultPath = Join-Path $localEvidencePath 'result.json'
$result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
if (-not $result.passed) {
    throw "Guest UI smoke test failed. Evidence is preserved at $localEvidencePath"
}

[pscustomobject]@{
    VmName = $VmName
    RunId = $runId
    Passed = $result.passed
    ActionCount = @($result.actions).Count
    ScreenshotCount = @($result.screenshots).Count
    EvidencePath = $localEvidencePath
    ResultPath = $resultPath
    HostInputInjected = $false
    VmConnectLaunched = $false
}
