[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$VmName = 'Patternal-UI',
    [Parameter(Mandatory)]
    [ValidateSet('status', 'launch', 'screenshot', 'close', 'stop')]
    [string]$Command,
    [ValidateRange(10, 180)]
    [int]$TimeoutSeconds = 90,
    [switch]$TerminateHeadless
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Patternal.IsolatedUi.psm1') -Force
$repositoryRoot = Get-PatternalRepositoryRoot
$requestId = [Guid]::NewGuid().ToString('N')
$runnerRoot = 'C:\PatternalTest\Runner'
$stagingPath = "$runnerRoot\staging\$requestId.json"
$requestPath = "$runnerRoot\requests\$requestId.json"
$resultPath = "$runnerRoot\results\$requestId.json"
$localRequestPath = Join-Path $env:TEMP "Patternal-runner-$requestId.json"
$localArtifactRoot = Join-Path $repositoryRoot "artifacts\isolated-ui\runner\$requestId"
$localResultPath = Join-Path $localArtifactRoot 'result.json'
$request = [ordered]@{
    schema = 'patternal.guest-runner-request/1.0'
    requestId = $requestId
    command = $Command
    requestedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
    aumid = 'C513E361-86E8-4FBD-9FF7-FABA0EAFA8FE_1z32rh13vfry6!App'
    expectedWindowTitle = 'Patternal'
    terminateHeadless = $TerminateHeadless.IsPresent
}
[IO.File]::WriteAllText($localRequestPath, ($request | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))

$vm = Start-PatternalVmForAutomation -VmName $VmName

$credential = Get-PatternalGuestCredential -VmName $VmName
$session = New-PatternalVmSession -VmName $VmName -Credential $credential
try {
    $taskState = Invoke-Command -Session $session -ScriptBlock {
        $task = Get-ScheduledTask -TaskName 'Patternal Guest Runner' -ErrorAction Stop
        if ($task.State -ne 'Running') {
            Start-ScheduledTask -TaskName 'Patternal Guest Runner'
        }
        return $task.State.ToString()
    }

    $runnerDeadline = [DateTimeOffset]::UtcNow.AddSeconds(30)
    $runnerStatus = $null
    $updatedAt = [DateTimeOffset]::MinValue
    do {
        $runnerStatusEnvelope = Invoke-Command -Session $session -ScriptBlock {
            $path = 'C:\PatternalTest\Runner\runner-status.json'
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                return $null
            }
            $statusJson = Get-Content -LiteralPath $path -Raw
            $status = $statusJson | ConvertFrom-Json
            $runnerProcess = Get-Process -Id ([int]$status.processId) -ErrorAction SilentlyContinue
            [pscustomobject]@{
                StatusJson = $statusJson
                ProcessExists = [bool]$runnerProcess
                TaskState = (Get-ScheduledTask -TaskName 'Patternal Guest Runner').State.ToString()
            }
        }
        if ($runnerStatusEnvelope -and $runnerStatusEnvelope.ProcessExists -and $runnerStatusEnvelope.TaskState -eq 'Running') {
            $runnerStatus = [string]$runnerStatusEnvelope.StatusJson
            $parsedStatus = $runnerStatus | ConvertFrom-Json
            $updatedAt = [DateTimeOffset]::Parse([string]$parsedStatus.updatedAtUtc)
            if ([DateTimeOffset]::UtcNow - $updatedAt -lt [TimeSpan]::FromSeconds(10)) {
                break
            }
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $runnerDeadline)
    if (-not $runnerStatus -or [DateTimeOffset]::UtcNow - $updatedAt -ge [TimeSpan]::FromSeconds(10)) {
        throw "Patternal guest runner did not publish a fresh heartbeat. Initial task state: $taskState"
    }

    Invoke-Command -Session $session -ScriptBlock {
        param($Root)
        New-Item -ItemType Directory -Path (Join-Path $Root 'staging') -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $Root 'requests') -Force | Out-Null
    } -ArgumentList $runnerRoot
    Copy-Item -ToSession $session -LiteralPath $localRequestPath -Destination $stagingPath
    Invoke-Command -Session $session -ScriptBlock {
        param($StagingPath, $RequestPath)
        Move-Item -LiteralPath $StagingPath -Destination $RequestPath -ErrorAction Stop
    } -ArgumentList $stagingPath, $requestPath

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    $resultExists = $false
    do {
        $resultExists = Invoke-Command -Session $session -ScriptBlock {
            param($Path)
            Test-Path -LiteralPath $Path -PathType Leaf
        } -ArgumentList $resultPath
        if ($resultExists) {
            break
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    if (-not $resultExists) {
        throw "Guest runner command '$Command' did not finish within $TimeoutSeconds seconds. Request: $requestId"
    }

    New-Item -ItemType Directory -Path $localArtifactRoot -Force | Out-Null
    Copy-Item -FromSession $session -LiteralPath $resultPath -Destination $localResultPath
    $result = Get-Content -LiteralPath $localResultPath -Raw | ConvertFrom-Json
    if ($result.requestId -ne $requestId -or $result.schema -ne 'patternal.guest-runner-result/1.0') {
        throw 'Guest runner result identity or schema is invalid.'
    }
    $hasScreenshot = $result.details -and
        $result.details.PSObject.Properties.Name -contains 'screenshot' -and
        $result.details.screenshot -and
        $result.details.screenshot.path
    if ($hasScreenshot) {
        $guestEvidenceRoot = [IO.Path]::GetFullPath("$runnerRoot\evidence")
        $guestScreenshotPath = [IO.Path]::GetFullPath([string]$result.details.screenshot.path)
        if (-not $guestScreenshotPath.StartsWith($guestEvidenceRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Guest runner screenshot escaped its evidence root: $guestScreenshotPath"
        }
        Copy-Item -FromSession $session -LiteralPath $guestScreenshotPath -Destination (Join-Path $localArtifactRoot 'screenshot.png')
        $localScreenshotHash = (Get-FileHash -LiteralPath (Join-Path $localArtifactRoot 'screenshot.png') -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($localScreenshotHash -ne [string]$result.details.screenshot.sha256) {
            throw 'Copied guest runner screenshot does not match its recorded SHA-256.'
        }
    }
    if (-not [bool]$result.accepted) {
        throw "Guest runner command '$Command' failed: $($result.error). Evidence: $localArtifactRoot"
    }
    $result | Add-Member -NotePropertyName localArtifactRoot -NotePropertyValue $localArtifactRoot
    $result
}
finally {
    Remove-PSSession -Session $session
    if (Test-Path -LiteralPath $localRequestPath) {
        Remove-Item -LiteralPath $localRequestPath -Force
    }
}
