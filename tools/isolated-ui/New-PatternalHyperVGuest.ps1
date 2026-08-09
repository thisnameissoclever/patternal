#Requires -RunAsAdministrator
#Requires -Modules Hyper-V

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$IsoPath,

    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Fa-f0-9]{64}$')]
    [string]$ExpectedIsoSha256,

    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$VmName = 'Patternal-UI',
    [string]$VmRoot = 'D:\VMs\Patternal-UI',
    [string]$GuestUser = 'PatternalTest',
    [string]$SwitchName = 'Default Switch',

    [ValidateRange(8, 32)]
    [int]$MemoryGb = 12,

    [ValidateRange(4, 16)]
    [int]$ProcessorCount = 8,

    [ValidateRange(96, 512)]
    [int]$DiskGb = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Patternal.IsolatedUi.psm1') -Force

$resolvedIsoPath = (Resolve-Path -LiteralPath $IsoPath).Path
$actualIsoHash = Get-PatternalFileSha256 -Path $resolvedIsoPath
if ($actualIsoHash -ine $ExpectedIsoSha256) {
    throw "Windows ISO hash mismatch. Expected $ExpectedIsoSha256 but found $actualIsoHash."
}

if (Get-VM -Name $VmName -ErrorAction SilentlyContinue) {
    throw "Refusing to replace existing VM '$VmName'. Remove it manually only after preserving any evidence you need."
}

if (Test-Path -LiteralPath $VmRoot) {
    $existingItems = Get-ChildItem -LiteralPath $VmRoot -Force -ErrorAction Stop
    if ($existingItems.Count -gt 0) {
        throw "Refusing to use non-empty VM root: $VmRoot"
    }
}

if (-not (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
    throw "Hyper-V switch '$SwitchName' does not exist."
}

$credentialPath = Get-PatternalVmCredentialPath -VmName $VmName
if (Test-Path -LiteralPath $credentialPath) {
    $guestCredential = Get-PatternalGuestCredential -VmName $VmName -CredentialPath $credentialPath
    if ($guestCredential.UserName -ne $GuestUser) {
        throw "Existing credential belongs to '$($guestCredential.UserName)', not '$GuestUser'."
    }
}
else {
    $guestCredential = New-PatternalGuestCredential -VmName $VmName -UserName $GuestUser -CredentialPath $credentialPath
}
Export-PatternalGuestCredentialNote -VmName $VmName -Credential $guestCredential | Out-Null

$mountedImage = $null
$provisioned = $false
$temporaryRoot = Join-Path $env:TEMP "Patternal-$VmName-setup"
$answerIsoPath = Join-Path $temporaryRoot 'Patternal-Unattend.iso'
try {
    New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null

    $mountedImage = Mount-DiskImage -ImagePath $resolvedIsoPath -PassThru
    $isoVolume = $mountedImage | Get-Volume
    if (-not $isoVolume.DriveLetter) {
        throw 'The Windows ISO mounted without a drive letter.'
    }

    $sourceRoot = "$($isoVolume.DriveLetter):\"
    $installImagePath = @(
        (Join-Path $sourceRoot 'sources\install.wim'),
        (Join-Path $sourceRoot 'sources\install.esd')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

    if (-not $installImagePath) {
        throw 'The ISO does not contain sources\install.wim or sources\install.esd.'
    }

    $windowsImages = @(Get-WindowsImage -ImagePath $installImagePath)
    if ($windowsImages.Count -eq 0) {
        throw 'No Windows images were found in the ISO.'
    }

    $selectedImage = $windowsImages |
        Where-Object { $_.ImageName -match 'Windows 11 Enterprise' -and $_.ImageName -notmatch ' LTSC| N$' } |
        Select-Object -First 1
    if (-not $selectedImage) {
        $selectedImage = $windowsImages | Select-Object -First 1
    }

    $plainPassword = $guestCredential.GetNetworkCredential().Password
    $escapedPassword = [System.Security.SecurityElement]::Escape($plainPassword)
    $escapedUser = [System.Security.SecurityElement]::Escape($GuestUser)
    $imageIndex = $selectedImage.ImageIndex
    $computerName = (($VmName -replace '[^A-Za-z0-9-]', '-') + '-GUEST').ToUpperInvariant()
    if ($computerName.Length -gt 15) {
        $computerName = $computerName.Substring(0, 15).TrimEnd('-')
    }

    $answerDirectory = Join-Path $temporaryRoot 'answer-media'
    New-Item -ItemType Directory -Path $answerDirectory -Force | Out-Null
    $answerPath = Join-Path $answerDirectory 'Autounattend.xml'
    $answerXml = @"
<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
  <settings pass="windowsPE">
    <component name="Microsoft-Windows-International-Core-WinPE" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <SetupUILanguage><UILanguage>en-US</UILanguage></SetupUILanguage>
      <InputLocale>0409:00000409</InputLocale>
      <SystemLocale>en-US</SystemLocale>
      <UILanguage>en-US</UILanguage>
      <UserLocale>en-US</UserLocale>
    </component>
    <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <DiskConfiguration>
        <Disk wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
          <DiskID>0</DiskID>
          <WillWipeDisk>true</WillWipeDisk>
          <CreatePartitions>
            <CreatePartition wcm:action="add"><Order>1</Order><Type>EFI</Type><Size>260</Size></CreatePartition>
            <CreatePartition wcm:action="add"><Order>2</Order><Type>MSR</Type><Size>16</Size></CreatePartition>
            <CreatePartition wcm:action="add"><Order>3</Order><Type>Primary</Type><Extend>true</Extend></CreatePartition>
          </CreatePartitions>
          <ModifyPartitions>
            <ModifyPartition wcm:action="add"><Order>1</Order><PartitionID>1</PartitionID><Label>System</Label><Format>FAT32</Format></ModifyPartition>
            <ModifyPartition wcm:action="add"><Order>2</Order><PartitionID>3</PartitionID><Label>Windows</Label><Letter>C</Letter><Format>NTFS</Format></ModifyPartition>
          </ModifyPartitions>
        </Disk>
        <WillShowUI>OnError</WillShowUI>
      </DiskConfiguration>
      <ImageInstall>
        <OSImage>
          <InstallFrom><MetaData wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"><Key>/IMAGE/INDEX</Key><Value>$imageIndex</Value></MetaData></InstallFrom>
          <InstallTo><DiskID>0</DiskID><PartitionID>3</PartitionID></InstallTo>
          <WillShowUI>OnError</WillShowUI>
        </OSImage>
      </ImageInstall>
      <UserData><AcceptEula>true</AcceptEula><FullName>Patternal UI Test</FullName><Organization>Patternal</Organization></UserData>
    </component>
  </settings>
  <settings pass="specialize">
    <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <ComputerName>$computerName</ComputerName>
      <RegisteredOwner>Patternal UI Test</RegisteredOwner>
      <TimeZone>Pacific Standard Time</TimeZone>
    </component>
    <component name="Microsoft-Windows-Deployment" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <RunSynchronous>
        <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"><Order>1</Order><Path>reg.exe add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock" /v AllowDevelopmentWithoutDevLicense /t REG_DWORD /d 1 /f</Path></RunSynchronousCommand>
      </RunSynchronous>
    </component>
  </settings>
  <settings pass="oobeSystem">
    <component name="Microsoft-Windows-International-Core" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <InputLocale>0409:00000409</InputLocale><SystemLocale>en-US</SystemLocale><UILanguage>en-US</UILanguage><UserLocale>en-US</UserLocale>
    </component>
    <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <OOBE><HideEULAPage>true</HideEULAPage><HideOEMRegistrationScreen>true</HideOEMRegistrationScreen><HideOnlineAccountScreens>true</HideOnlineAccountScreens><HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE><ProtectYourPC>3</ProtectYourPC></OOBE>
      <UserAccounts><LocalAccounts><LocalAccount wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"><Name>$escapedUser</Name><Group>Administrators</Group><DisplayName>Patternal UI Test</DisplayName><Password><Value>$escapedPassword</Value><PlainText>true</PlainText></Password></LocalAccount></LocalAccounts></UserAccounts>
      <AutoLogon><Enabled>true</Enabled><LogonCount>999</LogonCount><Username>$escapedUser</Username><Password><Value>$escapedPassword</Value><PlainText>true</PlainText></Password></AutoLogon>
      <FirstLogonCommands>
        <SynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"><Order>1</Order><Description>Create Patternal test root</Description><CommandLine>cmd.exe /c mkdir C:\PatternalTest</CommandLine></SynchronousCommand>
        <SynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"><Order>2</Order><Description>Disable AC display timeout</Description><CommandLine>powercfg.exe /change monitor-timeout-ac 0</CommandLine></SynchronousCommand>
        <SynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"><Order>3</Order><Description>Disable AC standby timeout</Description><CommandLine>powercfg.exe /change standby-timeout-ac 0</CommandLine></SynchronousCommand>
      </FirstLogonCommands>
    </component>
  </settings>
</unattend>
"@
    [System.IO.File]::WriteAllText($answerPath, $answerXml, [Text.UTF8Encoding]::new($false))
    New-PatternalDataIso -SourceDirectory $answerDirectory -DestinationPath $answerIsoPath

    New-Item -ItemType Directory -Path $VmRoot -Force | Out-Null
    $vhdPath = Join-Path $VmRoot "$VmName.vhdx"
    $vm = New-VM -Name $VmName -Generation 2 -MemoryStartupBytes ($MemoryGb * 1GB) -NewVHDPath $vhdPath -NewVHDSizeBytes ($DiskGb * 1GB) -SwitchName $SwitchName -Path $VmRoot
    Set-VM -Name $VmName -ProcessorCount $ProcessorCount -AutomaticCheckpointsEnabled $false -CheckpointType Production
    Set-VMMemory -VMName $VmName -DynamicMemoryEnabled $true -MinimumBytes 8GB -StartupBytes ($MemoryGb * 1GB) -MaximumBytes 24GB
    Set-VMFirmware -VMName $VmName -EnableSecureBoot On -SecureBootTemplate MicrosoftWindows
    Set-VMKeyProtector -VMName $VmName -NewLocalKeyProtector
    Enable-VMTPM -VMName $VmName

    $windowsDvd = Add-VMDvdDrive -VMName $VmName -Path $resolvedIsoPath -Passthru
    Add-VMDvdDrive -VMName $VmName -Path $answerIsoPath | Out-Null
    Set-VMFirmware -VMName $VmName -FirstBootDevice $windowsDvd
    Start-VM -Name $VmName | Out-Null
    Start-Sleep -Seconds 3
    Send-PatternalVmEnterKey -VmName $VmName

    $session = New-PatternalVmSession -VmName $VmName -Credential $guestCredential -TimeoutSeconds 2700
    try {
        $guestState = Invoke-Command -Session $session -ScriptBlock {
            [pscustomobject]@{
                ComputerName = $env:COMPUTERNAME
                UserName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
                OsVersion = [Environment]::OSVersion.Version.ToString()
            }
        }
    }
    finally {
        Remove-PSSession -Session $session
    }

    Get-VMDvdDrive -VMName $VmName | Set-VMDvdDrive -Path $null
    Checkpoint-VM -Name $VmName -SnapshotName "clean-windows-$([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))"
    $provisioned = $true

    [pscustomobject]@{
        VmName = $VmName
        VmRoot = $VmRoot
        Guest = $guestState
        WindowsImage = $selectedImage.ImageName
        IsoSha256 = $actualIsoHash.ToLowerInvariant()
        CredentialPath = $credentialPath
        PowerShellDirectReady = $true
        VmConnectLaunched = $false
    }
}
catch {
    if (Get-VM -Name $VmName -ErrorAction SilentlyContinue) {
        Write-Warning "VM '$VmName' was created but provisioning did not finish. It was not deleted. Error: $($_.Exception.Message)"
    }
    throw
}
finally {
    if ($mountedImage) {
        Dismount-DiskImage -ImagePath $resolvedIsoPath -ErrorAction SilentlyContinue
    }

    if ($provisioned -and (Test-Path -LiteralPath $temporaryRoot)) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
    elseif ((Test-Path -LiteralPath $temporaryRoot) -and (Get-VM -Name $VmName -ErrorAction SilentlyContinue)) {
        Write-Warning "Provisioning media remains at '$temporaryRoot' so the incomplete VM can be diagnosed or resumed. It contains the generated guest password and must be deleted after recovery."
    }
}
