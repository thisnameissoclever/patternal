[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$VmName = 'Patternal-UI',
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',
    [ValidateSet('x64')]
    [string]$Platform = 'x64',
    [string]$RuntimeInstallerUri = 'https://aka.ms/windowsappsdk/2.3/2.3.1/windowsappruntimeinstall-x64.exe',
    [switch]$PrepareOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Patternal.IsolatedUi.psm1') -Force
$repositoryRoot = Get-PatternalRepositoryRoot
$projectPath = Join-Path $repositoryRoot 'Patternal\Patternal.csproj'
& dotnet build $projectPath "-p:Platform=$Platform" "-p:Configuration=$Configuration"
if ($LASTEXITCODE -ne 0) {
    throw "Patternal build failed with exit code $LASTEXITCODE."
}

$outputRoot = Get-ChildItem -LiteralPath (Join-Path $repositoryRoot "Patternal\bin\$Platform\$Configuration") -Directory -Recurse |
    Where-Object { $_.FullName -match 'net10\.0-windows10\.0\.26100\.0\\win-x64$' } |
    Select-Object -First 1
if (-not $outputRoot) {
    throw 'Could not locate the x64 Patternal output directory.'
}

$recipePath = Join-Path $outputRoot.FullName 'Patternal.build.appxrecipe'
if (-not (Test-Path -LiteralPath $recipePath)) {
    throw "The build did not produce an AppX recipe: $recipePath"
}

$stagingBase = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot 'artifacts\isolated-ui\.staging'))
$stagingRoot = [System.IO.Path]::GetFullPath((Join-Path $stagingBase ([Guid]::NewGuid().ToString('N'))))
if (-not $stagingRoot.StartsWith($stagingBase.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Staging path escaped its owned root: $stagingRoot"
}
$appxRoot = Join-Path $stagingRoot 'AppX'
New-Item -ItemType Directory -Path $appxRoot -Force | Out-Null
try {
    [xml]$recipe = Get-Content -LiteralPath $recipePath -Raw
    $namespace = [System.Xml.XmlNamespaceManager]::new($recipe.NameTable)
    $namespace.AddNamespace('msb', 'http://schemas.microsoft.com/developer/msbuild/2003')
    $recipeItems = @($recipe.SelectNodes('//msb:AppXManifest | //msb:AppxPackagedFile', $namespace))
    if ($recipeItems.Count -eq 0) {
        throw 'The AppX recipe contains no payload files.'
    }

    $packagePaths = @{}
    foreach ($item in $recipeItems) {
        $sourcePath = [Environment]::ExpandEnvironmentVariables([string]$item.Include)
        $packagePathNode = $item.SelectSingleNode('msb:PackagePath', $namespace)
        if (-not $packagePathNode -or [string]::IsNullOrWhiteSpace($packagePathNode.InnerText)) {
            throw "Recipe item has no PackagePath: $sourcePath"
        }
        $packagePath = $packagePathNode.InnerText
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Recipe source is missing: $sourcePath"
        }

        $key = $packagePath.ToLowerInvariant()
        if ($packagePaths.ContainsKey($key)) {
            $existingHash = (Get-FileHash -LiteralPath $packagePaths[$key] -Algorithm SHA256).Hash
            $incomingHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
            if ($existingHash -ine $incomingHash) {
                throw "Recipe maps different files to the same package path: $packagePath"
            }
            continue
        }
        $packagePaths[$key] = $sourcePath

        $destinationPath = Join-Path $appxRoot $packagePath
        $destinationDirectory = Split-Path -Parent $destinationPath
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        Copy-Item -LiteralPath $sourcePath -Destination $destinationPath
    }

    if (-not (Test-Path -LiteralPath (Join-Path $appxRoot 'AppxManifest.xml'))) {
        throw 'The materialized AppX layout has no manifest.'
    }

$identityFiles = @(
    'Patternal.dll',
    'resources.pri',
    'Assets\avatar3d.html',
    'Assets\Production\patterna-production-crew-neck.obj',
    'Assets\Production\fabric-texture.png'
)

    $identityComparisons = foreach ($relativePath in $identityFiles) {
        $buildPath = Join-Path $outputRoot.FullName $relativePath
        $stagedPath = Join-Path $appxRoot $relativePath
        if (-not (Test-Path -LiteralPath $buildPath) -or -not (Test-Path -LiteralPath $stagedPath)) {
            throw "Required package identity file is missing: $relativePath"
        }

        $buildHash = (Get-FileHash -LiteralPath $buildPath -Algorithm SHA256).Hash
        $stagedHash = (Get-FileHash -LiteralPath $stagedPath -Algorithm SHA256).Hash
        if ($buildHash -ine $stagedHash) {
            throw "Materialized AppX file does not match current build output: $relativePath"
        }

        [pscustomobject]@{
            Path = $relativePath.Replace('\', '/')
            Sha256 = $stagedHash.ToLowerInvariant()
            Bytes = (Get-Item -LiteralPath $stagedPath).Length
        }
    }

    $payloadIdentity = Get-PatternalDirectoryIdentity -Path $appxRoot
    $artifactRoot = Join-Path $repositoryRoot "artifacts\isolated-ui\payloads\$payloadIdentity"
    New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
    $payloadZip = Join-Path $artifactRoot 'Patternal-AppX.zip'
    $manifestPath = Join-Path $artifactRoot 'payload-manifest.json'
    if (Test-Path -LiteralPath $payloadZip) {
        Remove-Item -LiteralPath $payloadZip -Force
    }

    Compress-Archive -Path (Join-Path $appxRoot '*') -DestinationPath $payloadZip -CompressionLevel Optimal
    $sourceCommit = (& git -C $repositoryRoot rev-parse HEAD).Trim()
    $sourceDirty = [bool](& git -C $repositoryRoot status --porcelain)
    $manifest = [ordered]@{
        schema = 'patternal.isolated-ui-payload/1.0'
        payloadIdentity = $payloadIdentity
        sourceCommit = $sourceCommit
        sourceDirty = $sourceDirty
        configuration = $Configuration
        platform = $Platform
        stagedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
        materializedFromRecipe = [IO.Path]::GetFileName($recipePath)
        recipeItemCount = $recipeItems.Count
        appxRelativePath = 'Patternal-AppX.zip'
        aumid = 'C513E361-86E8-4FBD-9FF7-FABA0EAFA8FE_1z32rh13vfry6!App'
        packageName = 'C513E361-86E8-4FBD-9FF7-FABA0EAFA8FE'
        windowsAppRuntime = '2.3.1'
        identityFiles = @($identityComparisons)
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8

    $installResult = $null
    if (-not $PrepareOnly) {
        $vm = Assert-PatternalHyperVAccess -VmName $VmName
        if ($vm.State -ne 'Running') {
            Start-VM -Name $VmName | Out-Null
        }

        $credential = Get-PatternalGuestCredential -VmName $VmName
        $session = New-PatternalVmSession -VmName $VmName -Credential $credential
        try {
            $guestTransferRoot = "C:\PatternalTest\Transfers\$payloadIdentity"
            Invoke-Command -Session $session -ScriptBlock {
                param($Path)
                New-Item -ItemType Directory -Path $Path -Force | Out-Null
                New-Item -ItemType Directory -Path 'C:\PatternalTest\Guest' -Force | Out-Null
            } -ArgumentList $guestTransferRoot

            Copy-Item -ToSession $session -LiteralPath $payloadZip -Destination (Join-Path $guestTransferRoot 'Patternal-AppX.zip')
            Copy-Item -ToSession $session -LiteralPath $manifestPath -Destination (Join-Path $guestTransferRoot 'payload-manifest.json')
            Copy-Item -ToSession $session -LiteralPath (Join-Path $PSScriptRoot 'guest\Install-PatternalGuestPayload.ps1') -Destination 'C:\PatternalTest\Guest\Install-PatternalGuestPayload.ps1'
            Copy-Item -ToSession $session -LiteralPath (Join-Path $PSScriptRoot 'guest\Invoke-PatternalUiSmoke.ps1') -Destination 'C:\PatternalTest\Guest\Invoke-PatternalUiSmoke.ps1'

            $installResult = Invoke-Command -Session $session -ScriptBlock {
                param($TransferRoot, $RuntimeUri)
                & 'C:\PatternalTest\Guest\Install-PatternalGuestPayload.ps1' `
                    -PayloadZip (Join-Path $TransferRoot 'Patternal-AppX.zip') `
                    -PayloadManifest (Join-Path $TransferRoot 'payload-manifest.json') `
                    -RuntimeInstallerUri $RuntimeUri
            } -ArgumentList $guestTransferRoot, $RuntimeInstallerUri
        }
        finally {
            Remove-PSSession -Session $session
        }
    }

    [pscustomobject]@{
        VmName = $VmName
        PayloadIdentity = $payloadIdentity
        SourceCommit = $sourceCommit
        SourceDirty = $sourceDirty
        RecipePath = $recipePath
        RecipeItemCount = $recipeItems.Count
        PayloadZip = $payloadZip
        ArtifactRoot = $artifactRoot
        IdentityFiles = @($identityComparisons)
        PreparedOnly = $PrepareOnly.IsPresent
        GuestInstall = $installResult
    }
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        if (-not $stagingRoot.StartsWith($stagingBase.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean staging path outside its owned root: $stagingRoot"
        }
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
