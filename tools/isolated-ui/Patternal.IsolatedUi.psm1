Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:DefaultVmName = 'Patternal-UI'
$script:DefaultGuestRoot = 'C:\PatternalTest'

function Get-PatternalRepositoryRoot {
    return [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
}

function Get-PatternalVmCredentialPath {
    param(
        [string]$VmName = $script:DefaultVmName
    )

    $credentialRoot = Join-Path $env:LOCALAPPDATA 'Patternal\VirtualMachine'
    return Join-Path $credentialRoot "$VmName.credential.xml"
}

function New-PatternalGuestCredential {
    param(
        [string]$VmName = $script:DefaultVmName,
        [string]$UserName = 'PatternalTest',
        [string]$CredentialPath = (Get-PatternalVmCredentialPath -VmName $VmName)
    )

    if (Test-Path -LiteralPath $CredentialPath) {
        throw "Credential file already exists: $CredentialPath"
    }

    $randomBytes = New-Object byte[] 30
    $randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $randomGenerator.GetBytes($randomBytes)
    }
    finally {
        $randomGenerator.Dispose()
    }
    $password = 'Pt1!' + [Convert]::ToBase64String($randomBytes)
    $securePassword = ConvertTo-SecureString -String $password -AsPlainText -Force
    $credential = [pscredential]::new($UserName, $securePassword)

    $credentialDirectory = Split-Path -Parent $CredentialPath
    New-Item -ItemType Directory -Path $credentialDirectory -Force | Out-Null
    $credential | Export-Clixml -LiteralPath $CredentialPath

    return $credential
}

function Get-PatternalGuestCredential {
    param(
        [string]$VmName = $script:DefaultVmName,
        [string]$CredentialPath = (Get-PatternalVmCredentialPath -VmName $VmName)
    )

    if (-not (Test-Path -LiteralPath $CredentialPath)) {
        throw "Guest credential does not exist: $CredentialPath"
    }

    return Import-Clixml -LiteralPath $CredentialPath
}

function Assert-PatternalHyperVAccess {
    param(
        [string]$VmName,
        [switch]$AllowMissingVm
    )

    if (-not (Get-Command Get-VM -ErrorAction SilentlyContinue)) {
        throw 'The Hyper-V PowerShell module is not installed.'
    }

    try {
        $vm = Get-VM -Name $VmName -ErrorAction Stop
        return $vm
    }
    catch {
        if ($AllowMissingVm -and $_.Exception.Message -match 'not found|could not be found') {
            return $null
        }

        throw "Hyper-V access failed for '$VmName'. Run the host bootstrap as administrator, then sign out and back in. $($_.Exception.Message)"
    }
}

function New-PatternalVmSession {
    param(
        [string]$VmName = $script:DefaultVmName,
        [pscredential]$Credential = (Get-PatternalGuestCredential -VmName $VmName),
        [ValidateRange(10, 3600)]
        [int]$TimeoutSeconds = 600
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastError = $null
    do {
        try {
            return New-PSSession -VMName $VmName -Credential $Credential -ErrorAction Stop
        }
        catch {
            $lastError = $_
            Start-Sleep -Seconds 5
        }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)

    throw "PowerShell Direct did not become available for '$VmName' within $TimeoutSeconds seconds. Last error: $($lastError.Exception.Message)"
}

function New-PatternalDataIso {
    param(
        [Parameter(Mandatory)]
        [string]$SourceDirectory,
        [Parameter(Mandatory)]
        [string]$DestinationPath,
        [string]$VolumeName = 'PATTERNAL_CFG'
    )

    if (-not (Test-Path -LiteralPath $SourceDirectory -PathType Container)) {
        throw "ISO source directory does not exist: $SourceDirectory"
    }

    if (Test-Path -LiteralPath $DestinationPath) {
        throw "Refusing to overwrite ISO: $DestinationPath"
    }

    if (-not ('PatternalIsoWriter' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public static class PatternalIsoWriter
{
    public static void Write(string path, object stream, int blockSize, int totalBlocks)
    {
        var input = stream as IStream;
        if (input == null)
        {
            throw new ArgumentException("The image stream does not implement IStream.");
        }

        var bytesReadPointer = Marshal.AllocCoTaskMem(sizeof(int));
        try
        {
            using (var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                var buffer = new byte[blockSize];
                for (var block = 0; block < totalBlocks; block++)
                {
                    input.Read(buffer, blockSize, bytesReadPointer);
                    var bytesRead = Marshal.ReadInt32(bytesReadPointer);
                    if (bytesRead <= 0)
                    {
                        break;
                    }

                    output.Write(buffer, 0, bytesRead);
                }
            }
        }
        finally
        {
            Marshal.FreeCoTaskMem(bytesReadPointer);
        }
    }
}
'@
    }

    $image = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
    $image.VolumeName = $VolumeName
    $image.ChooseImageDefaultsForMediaType(12)
    $image.FileSystemsToCreate = 3
    $image.Root.AddTree((Resolve-Path -LiteralPath $SourceDirectory).Path, $false)
    $result = $image.CreateResultImage()
    [PatternalIsoWriter]::Write(
        [System.IO.Path]::GetFullPath($DestinationPath),
        $result.ImageStream,
        $result.BlockSize,
        $result.TotalBlocks)
}

function Send-PatternalVmEnterKey {
    param(
        [Parameter(Mandatory)]
        [string]$VmName
    )

    $escapedName = $VmName.Replace("'", "''")
    $vmSystem = Get-CimInstance -Namespace 'root\virtualization\v2' -ClassName Msvm_ComputerSystem -Filter "ElementName='$escapedName'"
    if (-not $vmSystem) {
        throw "Could not locate Hyper-V computer system '$VmName'."
    }

    $keyboard = Get-CimAssociatedInstance -InputObject $vmSystem -ResultClassName Msvm_Keyboard | Select-Object -First 1
    if (-not $keyboard) {
        throw "Could not locate the synthetic keyboard for '$VmName'."
    }

    $result = Invoke-CimMethod -InputObject $keyboard -MethodName TypeKey -Arguments @{ keyCode = [uint32]13 }
    if ($result.ReturnValue -ne 0) {
        throw "Hyper-V rejected the guest-local Enter key with return value $($result.ReturnValue)."
    }
}

function Get-PatternalDirectoryIdentity {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $lines = foreach ($file in Get-ChildItem -LiteralPath $resolvedPath -File -Recurse | Sort-Object FullName) {
        $rootPrefix = $resolvedPath.TrimEnd('\') + '\'
        $relativePath = $file.FullName.Substring($rootPrefix.Length).Replace('\', '/')
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$relativePath`t$($file.Length)`t$hash"
    }

    $content = [Text.Encoding]::UTF8.GetBytes(($lines -join "`n"))
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $identity = $sha256.ComputeHash($content)
    }
    finally {
        $sha256.Dispose()
    }

    return ([BitConverter]::ToString($identity) -replace '-', '').ToLowerInvariant()
}

Export-ModuleMember -Function @(
    'Assert-PatternalHyperVAccess',
    'Get-PatternalDirectoryIdentity',
    'Get-PatternalGuestCredential',
    'Get-PatternalRepositoryRoot',
    'Get-PatternalVmCredentialPath',
    'New-PatternalDataIso',
    'New-PatternalGuestCredential',
    'New-PatternalVmSession',
    'Send-PatternalVmEnterKey'
)
