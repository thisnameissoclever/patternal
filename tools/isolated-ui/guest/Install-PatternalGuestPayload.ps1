[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$PayloadZip,
    [Parameter(Mandatory)]
    [string]$PayloadManifest,
    [Parameter(Mandatory)]
    [uri]$RuntimeInstallerUri,
    [Parameter(Mandatory)]
    [uri]$RuntimeRedistributableUri,
    [Parameter(Mandatory)]
    [uri]$DotNetRuntimeInstallerUri,
    [Parameter(Mandatory)]
    [version]$DotNetRuntimeVersion
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-PatternalFileSha256 {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $stream = [System.IO.File]::OpenRead($resolvedPath)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha256.ComputeHash($stream)
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }

    return ([BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
}

function Get-DirectoryIdentity {
    param([string]$Path)

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $rootPrefix = $resolvedPath.TrimEnd('\') + '\'
    $lines = foreach ($file in Get-ChildItem -LiteralPath $resolvedPath -File -Recurse | Sort-Object FullName) {
        $relativePath = $file.FullName.Substring($rootPrefix.Length).Replace('\', '/')
        $hash = Get-PatternalFileSha256 -Path $file.FullName
        "$relativePath`t$($file.Length)`t$hash"
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($lines -join "`n"))
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $identity = $sha256.ComputeHash($bytes)
    }
    finally {
        $sha256.Dispose()
    }
    return ([BitConverter]::ToString($identity) -replace '-', '').ToLowerInvariant()
}

function Install-WindowsAppRuntimeMsixFallback {
    param(
        [Parameter(Mandatory)]
        [uri]$RedistributableUri,
        [Parameter(Mandatory)]
        [string]$CacheRoot,
        [Parameter(Mandatory)]
        [version]$RequiredRuntime
    )

    $redistributableZip = Join-Path $CacheRoot "Microsoft.WindowsAppRuntime.Redist-$RequiredRuntime.zip"
    if (-not (Test-Path -LiteralPath $redistributableZip)) {
        Invoke-WebRequest -Uri $RedistributableUri -OutFile $redistributableZip -UseBasicParsing
    }

    $redistributableRoot = Join-Path $CacheRoot "Microsoft.WindowsAppRuntime.Redist-$RequiredRuntime"
    if (Test-Path -LiteralPath $redistributableRoot) {
        if (-not $redistributableRoot.StartsWith($CacheRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean runtime path outside its owned cache: $redistributableRoot"
        }
        Remove-Item -LiteralPath $redistributableRoot -Recurse -Force
    }
    Expand-Archive -LiteralPath $redistributableZip -DestinationPath $redistributableRoot -Force

    $x64Root = Join-Path $redistributableRoot 'MSIX\win10-x64'
    $packages = @(
        'Microsoft.WindowsAppRuntime.2.msix',
        'Microsoft.WindowsAppRuntime.Main.2.msix',
        'Microsoft.WindowsAppRuntime.Singleton.2.msix',
        'Microsoft.WindowsAppRuntime.DDLM.2.msix'
    )
    foreach ($packageName in $packages) {
        $packagePath = Join-Path $x64Root $packageName
        if (-not (Test-Path -LiteralPath $packagePath -PathType Leaf)) {
            throw "Windows App Runtime redistributable is missing x64 package: $packageName"
        }

        $signature = Get-AuthenticodeSignature -LiteralPath $packagePath
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
            throw "Windows App Runtime package is not valid Microsoft code: $packageName $($signature.Status) $($signature.SignerCertificate.Subject)"
        }

        Add-AppxPackage -Path $packagePath -ForceApplicationShutdown
    }

    return [pscustomobject]@{
        Mode = 'DirectMsixFallback'
        RedistributableUri = $RedistributableUri.AbsoluteUri
        Packages = $packages
    }
}

function Get-CompatibleDotNetRuntime {
    param([Parameter(Mandatory)][version]$MinimumVersion)

    $sharedRuntimeRoot = 'C:\Program Files\dotnet\shared\Microsoft.NETCore.App'
    if (-not (Test-Path -LiteralPath $sharedRuntimeRoot -PathType Container)) {
        return $null
    }

    return Get-ChildItem -LiteralPath $sharedRuntimeRoot -Directory |
        ForEach-Object {
            $version = $null
            if ([version]::TryParse($_.Name, [ref]$version)) { $version }
        } |
        Where-Object {
            $_.Major -eq $MinimumVersion.Major -and
            $_.Minor -eq $MinimumVersion.Minor -and
            $_ -ge $MinimumVersion
        } |
        Sort-Object -Descending |
        Select-Object -First 1
}

function Stop-PatternalPackageProcesses {
    $processes = @(Get-Process -Name Patternal -ErrorAction SilentlyContinue)
    if ($processes.Count -eq 0) {
        return
    }
    $processes | Stop-Process -Force
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 250
        $processes = @(Get-Process -Name Patternal -ErrorAction SilentlyContinue)
    } while ($processes.Count -gt 0 -and [DateTimeOffset]::UtcNow -lt $deadline)
    if ($processes.Count -gt 0) {
        throw 'Patternal processes did not exit within 30 seconds before package replacement.'
    }
}

$manifest = Get-Content -LiteralPath $PayloadManifest -Raw | ConvertFrom-Json
if ($manifest.schema -ne 'patternal.isolated-ui-payload/1.0') {
    throw "Unsupported payload manifest schema: $($manifest.schema)"
}
if ([string]$manifest.payloadIdentity -notmatch '^[a-f0-9]{64}$') {
    throw "Payload identity is not a lowercase SHA-256 value: $($manifest.payloadIdentity)"
}

$root = 'C:\PatternalTest'
$payloadBase = [System.IO.Path]::GetFullPath((Join-Path $root 'Payloads'))
$payloadRoot = [System.IO.Path]::GetFullPath((Join-Path $payloadBase ([string]$manifest.payloadIdentity)))
if (-not $payloadRoot.StartsWith($payloadBase.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Payload path escaped its owned root: $payloadRoot"
}
$appxRoot = Join-Path $payloadRoot 'AppX'
$cacheRoot = Join-Path $root 'Cache'
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null
New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null

$appxReused = $false
if (Test-Path -LiteralPath $appxRoot -PathType Container) {
    try {
        $appxReused = (Get-DirectoryIdentity -Path $appxRoot) -eq [string]$manifest.payloadIdentity
    }
    catch {
        $appxReused = $false
    }
}
if (-not $appxReused -and (Test-Path -LiteralPath $appxRoot)) {
    if (-not $appxRoot.StartsWith($payloadBase.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean payload path outside its owned root: $appxRoot"
    }
    Stop-PatternalPackageProcesses
    $registeredForReplacement = Get-AppxPackage -Name $manifest.packageName
    if ($registeredForReplacement) {
        $registeredForReplacement | Remove-AppxPackage
    }
    Remove-Item -LiteralPath $appxRoot -Recurse -Force
}
if (-not $appxReused) {
    New-Item -ItemType Directory -Path $appxRoot -Force | Out-Null
    Expand-Archive -LiteralPath $PayloadZip -DestinationPath $appxRoot -Force
}

$actualIdentity = Get-DirectoryIdentity -Path $appxRoot
if ($actualIdentity -ne $manifest.payloadIdentity) {
    throw "Guest payload identity mismatch. Expected $($manifest.payloadIdentity), found $actualIdentity."
}

$dotNetRuntimeMinimum = [version]$manifest.dotNetRuntimeMinimum
if ($DotNetRuntimeVersion.ToString() -ne [string]$manifest.dotNetRuntimeInstallerVersion) {
    throw "Requested .NET runtime $DotNetRuntimeVersion does not match payload pin $($manifest.dotNetRuntimeInstallerVersion)."
}
$installedDotNetRuntime = Get-CompatibleDotNetRuntime -MinimumVersion $dotNetRuntimeMinimum
$dotNetDeployment = [pscustomobject]@{ Mode = 'AlreadyInstalled'; InstallerExitCode = $null }
if (-not $installedDotNetRuntime) {
    $dotNetInstaller = Join-Path $cacheRoot "dotnet-runtime-$DotNetRuntimeVersion-win-x64.exe"
    if (-not (Test-Path -LiteralPath $dotNetInstaller)) {
        Invoke-WebRequest -Uri $DotNetRuntimeInstallerUri -OutFile $dotNetInstaller -UseBasicParsing
    }

    $dotNetSignature = Get-AuthenticodeSignature -LiteralPath $dotNetInstaller
    if ($dotNetSignature.Status -ne 'Valid' -or $dotNetSignature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
        throw ".NET runtime installer signature is not valid Microsoft code: $($dotNetSignature.Status) $($dotNetSignature.SignerCertificate.Subject)"
    }

    $dotNetProcess = Start-Process -FilePath $dotNetInstaller -ArgumentList '/install', '/quiet', '/norestart' -Wait -PassThru
    if ($dotNetProcess.ExitCode -notin @(0, 3010)) {
        throw ".NET runtime installer failed with exit code $($dotNetProcess.ExitCode)."
    }
    $dotNetDeployment = [pscustomobject]@{ Mode = 'Installer'; InstallerExitCode = $dotNetProcess.ExitCode }
    $installedDotNetRuntime = Get-CompatibleDotNetRuntime -MinimumVersion $dotNetRuntimeMinimum
}
if (-not $installedDotNetRuntime) {
    throw ".NET runtime Microsoft.NETCore.App $dotNetRuntimeMinimum or newer compatible patch is still missing after deployment."
}

$requiredRuntime = [version]$manifest.windowsAppRuntime
$installedRuntime = Get-AppxPackage -Name 'Microsoft.WindowsAppRuntime.2' |
    Where-Object { $_.Architecture -eq 'X64' } |
    Sort-Object Version -Descending |
    Select-Object -First 1
$runtimeDeployment = [pscustomobject]@{ Mode = 'AlreadyInstalled'; InstallerExitCode = $null }
if (-not $installedRuntime -or [version]$installedRuntime.Version -lt $requiredRuntime) {
    $runtimeInstaller = Join-Path $cacheRoot "WindowsAppRuntimeInstall-$requiredRuntime-x64.exe"
    if (-not (Test-Path -LiteralPath $runtimeInstaller)) {
        Invoke-WebRequest -Uri $RuntimeInstallerUri -OutFile $runtimeInstaller -UseBasicParsing
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $runtimeInstaller
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
        throw "Windows App Runtime installer signature is not valid Microsoft code: $($signature.Status) $($signature.SignerCertificate.Subject)"
    }

    $runtimeProcess = Start-Process -FilePath $runtimeInstaller -ArgumentList '--quiet' -Wait -PassThru
    if ($runtimeProcess.ExitCode -ne 0) {
        $runtimeDeployment = Install-WindowsAppRuntimeMsixFallback `
            -RedistributableUri $RuntimeRedistributableUri `
            -CacheRoot $cacheRoot `
            -RequiredRuntime $requiredRuntime
        $runtimeDeployment | Add-Member -NotePropertyName InstallerExitCode -NotePropertyValue $runtimeProcess.ExitCode
    }
    else {
        $runtimeDeployment = [pscustomobject]@{ Mode = 'Installer'; InstallerExitCode = 0 }
    }
}

$installedRuntime = Get-AppxPackage -Name 'Microsoft.WindowsAppRuntime.2' |
    Where-Object { $_.Architecture -eq 'X64' } |
    Sort-Object Version -Descending |
    Select-Object -First 1
if (-not $installedRuntime -or [version]$installedRuntime.Version -lt $requiredRuntime) {
    $installedVersion = if ($installedRuntime) { [string]$installedRuntime.Version } else { 'missing' }
    throw "Windows App Runtime x64 framework package is still below $requiredRuntime after deployment: $installedVersion."
}

$existingPackage = Get-AppxPackage -Name $manifest.packageName
$registrationReused = $existingPackage -and
    [string]::Equals(
        [IO.Path]::GetFullPath([string]$existingPackage.InstallLocation).TrimEnd('\'),
        [IO.Path]::GetFullPath($appxRoot).TrimEnd('\'),
        [StringComparison]::OrdinalIgnoreCase)
if (-not $registrationReused) {
    Stop-PatternalPackageProcesses
    if ($existingPackage) {
        $existingPackage | Remove-AppxPackage
    }
    $appxManifest = Join-Path $appxRoot 'AppxManifest.xml'
    Add-AppxPackage -Register $appxManifest -ForceApplicationShutdown
}
$registeredPackage = Get-AppxPackage -Name $manifest.packageName
if (-not $registeredPackage) {
    throw 'Patternal AppX registration did not appear for the guest test user.'
}

$taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\PatternalTest\Guest\Invoke-PatternalUiSmoke.ps1"'
$taskPrincipal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName 'Patternal Guest UI Smoke' -Action $taskAction -Principal $taskPrincipal -Settings $taskSettings -Force | Out-Null

$runnerScriptPath = 'C:\PatternalTest\Guest\Start-PatternalGuestRunner.ps1'
if (-not (Test-Path -LiteralPath $runnerScriptPath -PathType Leaf)) {
    throw "Persistent guest runner is missing: $runnerScriptPath"
}
$runnerRoot = 'C:\PatternalTest\Runner'
foreach ($runnerDirectory in @('requests', 'processing', 'results', 'evidence', 'logs', 'staging')) {
    New-Item -ItemType Directory -Path (Join-Path $runnerRoot $runnerDirectory) -Force | Out-Null
}
$existingRunnerTask = Get-ScheduledTask -TaskName 'Patternal Guest Runner' -ErrorAction SilentlyContinue
if ($existingRunnerTask -and $existingRunnerTask.State -eq 'Running') {
    Stop-ScheduledTask -TaskName 'Patternal Guest Runner'
    $runnerStopDeadline = [DateTimeOffset]::UtcNow.AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 250
        $existingRunnerTask = Get-ScheduledTask -TaskName 'Patternal Guest Runner'
    } while ($existingRunnerTask.State -eq 'Running' -and [DateTimeOffset]::UtcNow -lt $runnerStopDeadline)
    if ($existingRunnerTask.State -eq 'Running') {
        throw 'The previous persistent guest runner did not stop within 15 seconds.'
    }
}
$runnerAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\PatternalTest\Guest\Start-PatternalGuestRunner.ps1"'
$runnerTrigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$runnerSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'Patternal Guest Runner' -Action $runnerAction -Principal $taskPrincipal -Trigger $runnerTrigger -Settings $runnerSettings -Force | Out-Null
Start-ScheduledTask -TaskName 'Patternal Guest Runner'

$installResult = [ordered]@{
    schema = 'patternal.isolated-ui-install/1.0'
    installedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
    payloadIdentity = $manifest.payloadIdentity
    appxRoot = $appxRoot
    packageFullName = $registeredPackage.PackageFullName
    appxReused = $appxReused
    registrationReused = $registrationReused
    windowsAppRuntime = $requiredRuntime.ToString()
    dotNetRuntimeMinimum = $dotNetRuntimeMinimum.ToString()
    dotNetRuntimeInstalled = $installedDotNetRuntime.ToString()
    dotNetRuntimeInstallerVersion = $DotNetRuntimeVersion.ToString()
    dotNetRuntimeInstallerUri = $DotNetRuntimeInstallerUri.AbsoluteUri
    dotNetDeployment = $dotNetDeployment
    runtimeInstallerUri = $RuntimeInstallerUri.AbsoluteUri
    runtimeRedistributableUri = $RuntimeRedistributableUri.AbsoluteUri
    runtimeDeployment = $runtimeDeployment
    scheduledTask = 'Patternal Guest UI Smoke'
    persistentRunnerTask = 'Patternal Guest Runner'
    persistentRunnerSchema = 'patternal.guest-runner-request/1.0'
    interactiveUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
}
$installResultPath = Join-Path $payloadRoot 'install-result.json'
$installResult | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $installResultPath -Encoding utf8
[pscustomobject]$installResult
