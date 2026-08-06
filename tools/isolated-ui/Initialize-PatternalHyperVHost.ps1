#Requires -RunAsAdministrator

[CmdletBinding()]
param(
    [string]$UserName = "$env:USERDOMAIN\$env:USERNAME",
    [switch]$EnableHyperV
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$feature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
$restartRequired = $false
if ($feature.State -ne 'Enabled') {
    if (-not $EnableHyperV) {
        throw 'Hyper-V is not enabled. Rerun with -EnableHyperV to enable it without an automatic restart.'
    }

    $result = Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All -NoRestart
    $restartRequired = $result.RestartNeeded
}

$groupName = 'Hyper-V Administrators'
$isMember = Get-LocalGroupMember -Group $groupName -ErrorAction Stop |
    Where-Object { $_.Name -ieq $UserName }

if (-not $isMember) {
    Add-LocalGroupMember -Group $groupName -Member $UserName
}

[pscustomobject]@{
    HyperVEnabled = $true
    HyperVAdministratorsMember = $true
    UserName = $UserName
    RestartRequired = $restartRequired
    NewLogonRequired = -not $isMember
    NextStep = if ($restartRequired) {
        'Restart Windows, then rerun the non-mutating host audit.'
    }
    elseif (-not $isMember) {
        'Sign out and back in so new processes receive Hyper-V permissions.'
    }
    else {
        'The host is ready for Patternal VM provisioning.'
    }
}
