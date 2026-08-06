[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$PayloadZip,
    [Parameter(Mandatory)]
    [string]$PayloadManifest,
    [Parameter(Mandatory)]
    [uri]$RuntimeInstallerUri
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-DirectoryIdentity {
    param([string]$Path)

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $rootPrefix = $resolvedPath.TrimEnd('\') + '\'
    $lines = foreach ($file in Get-ChildItem -LiteralPath $resolvedPath -File -Recurse | Sort-Object FullName) {
        $relativePath = $file.FullName.Substring($rootPrefix.Length).Replace('\', '/')
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
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

Get-Process -Name Patternal -ErrorAction SilentlyContinue | Stop-Process -Force
if (Test-Path -LiteralPath $appxRoot) {
    if (-not $appxRoot.StartsWith($payloadBase.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean payload path outside its owned root: $appxRoot"
    }
    Remove-Item -LiteralPath $appxRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $appxRoot -Force | Out-Null
Expand-Archive -LiteralPath $PayloadZip -DestinationPath $appxRoot -Force

$actualIdentity = Get-DirectoryIdentity -Path $appxRoot
if ($actualIdentity -ne $manifest.payloadIdentity) {
    throw "Guest payload identity mismatch. Expected $($manifest.payloadIdentity), found $actualIdentity."
}

$requiredRuntime = [version]$manifest.windowsAppRuntime
$installedRuntime = Get-AppxPackage -Name 'Microsoft.WindowsAppRuntime.2' |
    Where-Object { $_.Architecture -eq 'X64' } |
    Sort-Object Version -Descending |
    Select-Object -First 1
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
        throw "Windows App Runtime installer failed with exit code $($runtimeProcess.ExitCode)."
    }
}

$existingPackage = Get-AppxPackage -Name $manifest.packageName
if ($existingPackage) {
    $existingPackage | Remove-AppxPackage
}

$appxManifest = Join-Path $appxRoot 'AppxManifest.xml'
Add-AppxPackage -Register $appxManifest -ForceApplicationShutdown
$registeredPackage = Get-AppxPackage -Name $manifest.packageName
if (-not $registeredPackage) {
    throw 'Patternal AppX registration did not appear for the guest test user.'
}

$taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\PatternalTest\Guest\Invoke-PatternalUiSmoke.ps1"'
$taskPrincipal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName 'Patternal Guest UI Smoke' -Action $taskAction -Principal $taskPrincipal -Settings $taskSettings -Force | Out-Null

$installResult = [ordered]@{
    schema = 'patternal.isolated-ui-install/1.0'
    installedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
    payloadIdentity = $manifest.payloadIdentity
    appxRoot = $appxRoot
    packageFullName = $registeredPackage.PackageFullName
    windowsAppRuntime = $requiredRuntime.ToString()
    runtimeInstallerUri = $RuntimeInstallerUri.AbsoluteUri
    scheduledTask = 'Patternal Guest UI Smoke'
    interactiveUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
}
$installResultPath = Join-Path $payloadRoot 'install-result.json'
$installResult | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $installResultPath -Encoding utf8
[pscustomobject]$installResult
