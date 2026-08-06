[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$VmName = 'Patternal-UI'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Patternal.IsolatedUi.psm1') -Force
$repositoryRoot = Get-PatternalRepositoryRoot
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$hyperVAdministratorsSid = 'S-1-5-32-578'
$hasHyperVGroupToken = [bool]($identity.Groups | Where-Object { $_.Value -eq $hyperVAdministratorsSid })
$hyperVService = Get-Service -Name vmms -ErrorAction SilentlyContinue
$sandboxCommand = Get-Command WindowsSandbox.exe -ErrorAction SilentlyContinue
$credentialPath = Get-PatternalVmCredentialPath -VmName $VmName

$hyperVAccess = $false
$vmState = 'Missing or inaccessible'
$vmPath = $null
if (Get-Command Get-VM -ErrorAction SilentlyContinue) {
    try {
        $vm = Get-VM -Name $VmName -ErrorAction Stop
        $hyperVAccess = $true
        $vmState = $vm.State.ToString()
        $vmPath = $vm.Path
    }
    catch {
        try {
            $null = Get-VM -ErrorAction Stop
            $hyperVAccess = $true
            $vmState = 'Missing'
        }
        catch {
            $vmState = 'Inaccessible'
        }
    }
}

$latestManifest = Get-ChildItem -LiteralPath (Join-Path $repositoryRoot 'artifacts\isolated-ui\payloads') -Filter 'payload-manifest.json' -File -Recurse -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
$payload = if ($latestManifest) {
    $manifest = Get-Content -LiteralPath $latestManifest.FullName -Raw | ConvertFrom-Json
    [ordered]@{
        identity = $manifest.payloadIdentity
        sourceCommit = $manifest.sourceCommit
        sourceDirty = $manifest.sourceDirty
        recipeItemCount = $manifest.recipeItemCount
        manifestPath = $latestManifest.FullName
        archivePath = Join-Path $latestManifest.DirectoryName $manifest.appxRelativePath
    }
}
else {
    $null
}

$nextStep = if (-not $hyperVService -or $hyperVService.Status -ne 'Running') {
    'Run Initialize-PatternalHyperVHost.ps1 from an elevated PowerShell window.'
}
elseif (-not $hasHyperVGroupToken) {
    'Run the elevated host bootstrap, then sign out and back in to refresh Hyper-V permissions.'
}
elseif (-not $hyperVAccess) {
    'Confirm Hyper-V Administrators membership and refresh the Windows logon token.'
}
elseif ($vmState -eq 'Missing') {
    'Download and verify an official Windows ISO, then run New-PatternalHyperVGuest.ps1 from an elevated PowerShell window.'
}
elseif (-not $payload) {
    'Run Sync-PatternalGuestPayload.ps1 to build and install the current AppX payload.'
}
else {
    'Run Invoke-PatternalGuestUiSmoke.ps1 and inspect the JSON and PNG evidence.'
}

[pscustomobject]@{
    ComputerName = $env:COMPUTERNAME
    UserName = $identity.Name
    HyperVService = if ($hyperVService) { $hyperVService.Status.ToString() } else { 'Missing' }
    HyperVGroupInCurrentToken = $hasHyperVGroupToken
    HyperVManagementAccess = $hyperVAccess
    VmName = $VmName
    VmState = $vmState
    VmPath = $vmPath
    CredentialPresent = Test-Path -LiteralPath $credentialPath
    CredentialPath = $credentialPath
    WindowsSandboxPresent = [bool]$sandboxCommand
    LatestPayload = $payload
    ContractTest = Join-Path $PSScriptRoot 'Test-PatternalIsolatedUiHarness.ps1'
    Documentation = Join-Path $repositoryRoot 'docs\isolated-windows-ui-testing.md'
    NextStep = $nextStep
}
