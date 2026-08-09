[CmdletBinding()]
param(
    [string]$RunnerRoot = 'C:\PatternalTest\Runner'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing

$schemaVersion = 'patternal.guest-runner-request/1.0'
$resultSchemaVersion = 'patternal.guest-runner-result/1.0'
$runnerVersion = '1.0.0'
$defaultAumid = 'C513E361-86E8-4FBD-9FF7-FABA0EAFA8FE_1z32rh13vfry6!App'
$defaultWindowTitle = 'Patternal'
$requestsDirectory = Join-Path $RunnerRoot 'requests'
$processingDirectory = Join-Path $RunnerRoot 'processing'
$resultsDirectory = Join-Path $RunnerRoot 'results'
$evidenceDirectory = Join-Path $RunnerRoot 'evidence'
$logsDirectory = Join-Path $RunnerRoot 'logs'
$statusPath = Join-Path $RunnerRoot 'runner-status.json'
$logPath = Join-Path $logsDirectory 'runner.log'
$mutex = [System.Threading.Mutex]::new($false, 'Local\PatternalGuestRunner')
$ownsMutex = $false

function Write-AtomicJson {
    param(
        [Parameter(Mandatory)]
        [object]$Value,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporaryPath = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    [IO.File]::WriteAllText(
        $temporaryPath,
        ($Value | ConvertTo-Json -Depth 12),
        [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
}

function Write-RunnerLog {
    param([string]$Message)

    $line = '{0} {1}' -f [DateTimeOffset]::UtcNow.ToString('O'), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding utf8
}

function Get-RequestProperty {
    param(
        [Parameter(Mandatory)]
        [object]$Request,
        [Parameter(Mandatory)]
        [string]$Name,
        [object]$DefaultValue = $null
    )

    if ($Request.PSObject.Properties.Name -contains $Name) {
        return $Request.$Name
    }
    return $DefaultValue
}

function Find-PatternalWindow {
    param([string]$ExpectedWindowTitle = $defaultWindowTitle)

    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        $ExpectedWindowTitle)
    $window = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
        [System.Windows.Automation.TreeScope]::Children,
        $condition)
    if (-not $window) {
        return $null
    }

    $process = Get-Process -Id $window.Current.ProcessId -ErrorAction SilentlyContinue
    if (-not $process -or $process.ProcessName -ne 'Patternal' -or $process.SessionId -ne [System.Diagnostics.Process]::GetCurrentProcess().SessionId) {
        return $null
    }
    return $window
}

function Get-WindowDetails {
    param([System.Windows.Automation.AutomationElement]$Window)

    if (-not $Window) {
        return $null
    }
    $process = Get-Process -Id $Window.Current.ProcessId -ErrorAction Stop
    $bounds = $Window.Current.BoundingRectangle
    return [ordered]@{
        processId = $process.Id
        sessionId = $process.SessionId
        title = $Window.Current.Name
        responsive = $process.Responding
        bounds = [ordered]@{
            left = [math]::Round($bounds.Left, 2)
            top = [math]::Round($bounds.Top, 2)
            width = [math]::Round($bounds.Width, 2)
            height = [math]::Round($bounds.Height, 2)
        }
    }
}

function Wait-ForPatternalWindow {
    param(
        [string]$ExpectedWindowTitle,
        [int]$TimeoutSeconds = 60
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $window = Find-PatternalWindow -ExpectedWindowTitle $ExpectedWindowTitle
        if ($window) {
            return $window
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "Patternal did not expose a '$ExpectedWindowTitle' top-level window within $TimeoutSeconds seconds."
}

function Get-WindowPattern {
    param([System.Windows.Automation.AutomationElement]$Window)

    $pattern = $null
    if (-not $Window.TryGetCurrentPattern(
        [System.Windows.Automation.WindowPattern]::Pattern,
        [ref]$pattern)) {
        throw 'The Patternal window does not expose WindowPattern.'
    }
    return [System.Windows.Automation.WindowPattern]$pattern
}

function Save-PatternalScreenshot {
    param(
        [System.Windows.Automation.AutomationElement]$Window,
        [string]$RequestId
    )

    $bounds = $Window.Current.BoundingRectangle
    $width = [int][math]::Round($bounds.Width)
    $height = [int][math]::Round($bounds.Height)
    if ($width -le 0 -or $height -le 0) {
        throw 'The Patternal window has no capturable bounds.'
    }

    $path = Join-Path $evidenceDirectory "$RequestId.png"
    $bitmap = [Drawing.Bitmap]::new($width, $height)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen(
            [int][math]::Round($bounds.Left),
            [int][math]::Round($bounds.Top),
            0,
            0,
            [Drawing.Size]::new($width, $height))
        $bitmap.Save($path, [Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }

    return [ordered]@{
        path = $path
        bytes = (Get-Item -LiteralPath $path).Length
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        width = $width
        height = $height
    }
}

function Remove-OldRunnerFiles {
    foreach ($retention in @(
        @{ Path = $resultsDirectory; Count = 200 },
        @{ Path = $evidenceDirectory; Count = 100 }
    )) {
        Get-ChildItem -LiteralPath $retention.Path -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -Skip $retention.Count |
            Remove-Item -Force
    }
}

function Invoke-RunnerCommand {
    param([object]$Request)

    $command = [string](Get-RequestProperty -Request $Request -Name 'command')
    $expectedWindowTitle = [string](Get-RequestProperty -Request $Request -Name 'expectedWindowTitle' -DefaultValue $defaultWindowTitle)
    $aumid = [string](Get-RequestProperty -Request $Request -Name 'aumid' -DefaultValue $defaultAumid)
    $requestId = [string]$Request.requestId
    $window = Find-PatternalWindow -ExpectedWindowTitle $expectedWindowTitle

    switch ($command) {
        'status' {
            $processes = @(Get-Process -Name Patternal -ErrorAction SilentlyContinue | Where-Object SessionId -eq ([System.Diagnostics.Process]::GetCurrentProcess().SessionId))
            return [ordered]@{
                command = $command
                running = [bool]$window
                processCount = $processes.Count
                window = Get-WindowDetails -Window $window
            }
        }
        'launch' {
            if (-not $window) {
                $headlessProcesses = @(Get-Process -Name Patternal -ErrorAction SilentlyContinue | Where-Object SessionId -eq ([System.Diagnostics.Process]::GetCurrentProcess().SessionId))
                if ($headlessProcesses.Count -gt 0) {
                    throw 'Patternal has a process in the interactive session but no top-level window. Close it explicitly before relaunching.'
                }
                Start-Process -FilePath explorer.exe -ArgumentList "shell:AppsFolder\$aumid"
                $window = Wait-ForPatternalWindow -ExpectedWindowTitle $expectedWindowTitle -TimeoutSeconds 60
            }
            $windowPattern = Get-WindowPattern -Window $window
            $windowPattern.SetWindowVisualState([System.Windows.Automation.WindowVisualState]::Maximized)
            $workspaceCondition = [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::NameProperty,
                'Pattern workspace views')
            $workspace = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $workspaceCondition)
            if (-not $workspace) {
                throw 'Patternal launched without the primary workspace automation surface.'
            }
            return [ordered]@{
                command = $command
                running = $true
                window = Get-WindowDetails -Window $window
            }
        }
        'screenshot' {
            if (-not $window) {
                throw 'Patternal is not open in the interactive guest session.'
            }
            return [ordered]@{
                command = $command
                window = Get-WindowDetails -Window $window
                screenshot = Save-PatternalScreenshot -Window $window -RequestId $requestId
            }
        }
        'close' {
            if ($window) {
                (Get-WindowPattern -Window $window).Close()
                $deadline = [DateTimeOffset]::UtcNow.AddSeconds(15)
                do {
                    Start-Sleep -Milliseconds 250
                    $window = Find-PatternalWindow -ExpectedWindowTitle $expectedWindowTitle
                } while ($window -and [DateTimeOffset]::UtcNow -lt $deadline)
                if ($window) {
                    throw 'Patternal did not close through its window contract within 15 seconds.'
                }
            }
            $terminateHeadless = [bool](Get-RequestProperty -Request $Request -Name 'terminateHeadless' -DefaultValue $false)
            $remaining = @(Get-Process -Name Patternal -ErrorAction SilentlyContinue | Where-Object SessionId -eq ([System.Diagnostics.Process]::GetCurrentProcess().SessionId))
            if ($remaining.Count -gt 0 -and -not $terminateHeadless) {
                $processExitDeadline = [DateTimeOffset]::UtcNow.AddSeconds(15)
                do {
                    Start-Sleep -Milliseconds 250
                    $remaining = @(Get-Process -Name Patternal -ErrorAction SilentlyContinue | Where-Object SessionId -eq ([System.Diagnostics.Process]::GetCurrentProcess().SessionId))
                } while ($remaining.Count -gt 0 -and [DateTimeOffset]::UtcNow -lt $processExitDeadline)
            }
            if ($remaining.Count -gt 0 -and $terminateHeadless) {
                $remaining | Stop-Process -Force
                $remaining = @()
            }
            if ($remaining.Count -gt 0) {
                throw 'Patternal has a headless process. Repeat close with terminateHeadless only if discarding that process is intended.'
            }
            return [ordered]@{ command = $command; running = $false }
        }
        'stop' {
            return [ordered]@{ command = $command; stopping = $true }
        }
        default {
            throw "Unsupported guest runner command: $command"
        }
    }
}

try {
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) {
        throw 'Another Patternal guest runner already owns this interactive session.'
    }

    foreach ($directory in @($RunnerRoot, $requestsDirectory, $processingDirectory, $resultsDirectory, $evidenceDirectory, $logsDirectory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    if ((Test-Path -LiteralPath $logPath) -and (Get-Item -LiteralPath $logPath).Length -gt 1MB) {
        $previousLogPath = Join-Path $logsDirectory 'runner.previous.log'
        if (Test-Path -LiteralPath $previousLogPath) {
            Remove-Item -LiteralPath $previousLogPath -Force
        }
        Move-Item -LiteralPath $logPath -Destination $previousLogPath
    }
    foreach ($staleRequest in Get-ChildItem -LiteralPath $processingDirectory -Filter '*.json' -File -ErrorAction SilentlyContinue) {
        Move-Item -LiteralPath $staleRequest.FullName -Destination (Join-Path $requestsDirectory $staleRequest.Name) -Force
    }

    Write-RunnerLog "Runner $runnerVersion started in session $([System.Diagnostics.Process]::GetCurrentProcess().SessionId)."
    $stopRequested = $false
    while (-not $stopRequested) {
        Write-AtomicJson -Path $statusPath -Value ([ordered]@{
            schema = 'patternal.guest-runner-status/1.0'
            runnerVersion = $runnerVersion
            processId = $PID
            sessionId = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
            userName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            state = 'ready'
            updatedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
        })

        $requestFile = Get-ChildItem -LiteralPath $requestsDirectory -Filter '*.json' -File -ErrorAction SilentlyContinue |
            Sort-Object CreationTimeUtc, Name |
            Select-Object -First 1
        if (-not $requestFile) {
            Start-Sleep -Milliseconds 250
            continue
        }

        $processingPath = Join-Path $processingDirectory $requestFile.Name
        try {
            Move-Item -LiteralPath $requestFile.FullName -Destination $processingPath -ErrorAction Stop
        }
        catch {
            continue
        }

        $startedAt = [DateTimeOffset]::UtcNow
        $request = $null
        $requestId = [IO.Path]::GetFileNameWithoutExtension($requestFile.Name)
        $accepted = $false
        $details = $null
        $errorMessage = $null
        $errorType = $null
        try {
            $request = Get-Content -LiteralPath $processingPath -Raw | ConvertFrom-Json
            if ($request.schema -ne $schemaVersion) {
                throw "Unsupported guest runner request schema: $($request.schema)"
            }
            if ([string]$request.requestId -notmatch '^[a-f0-9]{32}$' -or [string]$request.requestId -ne $requestId) {
                throw 'Guest runner request ID does not match its lowercase 32-character filename.'
            }
            $details = Invoke-RunnerCommand -Request $request
            $accepted = $true
            $stopRequested = [string]$request.command -eq 'stop'
        }
        catch {
            $errorMessage = $_.Exception.Message
            $errorType = $_.Exception.GetType().FullName
        }

        $resultPath = Join-Path $resultsDirectory "$requestId.json"
        Write-AtomicJson -Path $resultPath -Value ([ordered]@{
            schema = $resultSchemaVersion
            requestId = $requestId
            command = if ($request) { [string](Get-RequestProperty -Request $request -Name 'command') } else { $null }
            accepted = $accepted
            startedAtUtc = $startedAt.ToString('O')
            finishedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
            runnerVersion = $runnerVersion
            runnerProcessId = $PID
            sessionId = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
            hostInputInjected = $false
            vmConnectLaunched = $false
            details = $details
            error = $errorMessage
            errorType = $errorType
        })
        Remove-Item -LiteralPath $processingPath -Force -ErrorAction SilentlyContinue
        Write-RunnerLog "Request $requestId completed with accepted=$accepted."
        Remove-OldRunnerFiles
    }
}
finally {
    if ($ownsMutex) {
        try {
            Write-RunnerLog 'Runner stopped.'
        }
        catch {
        }
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
