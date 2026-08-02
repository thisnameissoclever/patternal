[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$BridgeDocumentPath,
    [string]$BodyProfilePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolvedBridgePath = [System.IO.Path]::GetFullPath($BridgeDocumentPath)
if (-not [System.IO.File]::Exists($resolvedBridgePath)) {
    throw "Bridge document does not exist: $resolvedBridgePath"
}

$resolvedBodyProfilePath = $null
if (-not [string]::IsNullOrWhiteSpace($BodyProfilePath)) {
    $resolvedBodyProfilePath = [System.IO.Path]::GetFullPath($BodyProfilePath)
    if (-not [System.IO.File]::Exists($resolvedBodyProfilePath)) {
        throw "Body profile does not exist: $resolvedBodyProfilePath"
    }
}

$generatorPath = Join-Path $PSScriptRoot 'Generate-PatternaUnrealGarment.ps1'
$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase ("PatternaUnrealBridgeTest-" + [Guid]::NewGuid().ToString('N'))
[System.IO.Directory]::CreateDirectory($testRoot) | Out-Null

function Assert-Equal {
    param(
        [string]$Name,
        $Actual,
        $Expected
    )

    if ($Actual -ne $Expected) {
        throw "$Name mismatch. Expected '$Expected'; received '$Actual'."
    }
}

function Assert-Rejected {
    param(
        [string]$Name,
        [string]$InputPath,
        [string]$ExpectedMessage,
        [string]$ProfilePath
    )

    $rejected = $false
    try {
        & $generatorPath `
            -BridgeDocumentPath $InputPath `
            -BodyProfilePath $ProfilePath `
            -OutputDirectory (Join-Path $testRoot $Name) | Out-Null
    }
    catch {
        if ($_.Exception.Message -notlike "*$ExpectedMessage*") {
            throw "$Name failed for the wrong reason: $($_.Exception.Message)"
        }
        $rejected = $true
    }

    if (-not $rejected) {
        throw "$Name was accepted when it should have been rejected."
    }
}

try {
    $bridge = Get-Content -Raw -LiteralPath $resolvedBridgePath | ConvertFrom-Json
    Assert-Equal 'Bridge schema' $bridge.schemaVersion 'patterna.unreal-bridge/1.0'

    if ($bridge.body.measurements.Count -lt 145) {
        throw "Bridge contains only $($bridge.body.measurements.Count) measurements; at least 145 are required."
    }
    if ($bridge.garment.panels.Count -lt 1 -or $bridge.garment.seams.Count -lt 1) {
        throw 'Bridge garment must contain panels and seams.'
    }

    $firstRun = & $generatorPath `
        -BridgeDocumentPath $resolvedBridgePath `
        -BodyProfilePath $resolvedBodyProfilePath `
        -OutputDirectory (Join-Path $testRoot 'run-one')
    $secondRun = & $generatorPath `
        -BridgeDocumentPath $resolvedBridgePath `
        -BodyProfilePath $resolvedBodyProfilePath `
        -OutputDirectory (Join-Path $testRoot 'run-two')
    $denseRun = & $generatorPath `
        -BridgeDocumentPath $resolvedBridgePath `
        -BodyProfilePath $resolvedBodyProfilePath `
        -PanelColumns 72 `
        -VerticalRows 48 `
        -OutputDirectory (Join-Path $testRoot 'run-dense')

    $firstUsdHash = (Get-FileHash -LiteralPath $firstRun.UsdPath -Algorithm SHA256).Hash
    $secondUsdHash = (Get-FileHash -LiteralPath $secondRun.UsdPath -Algorithm SHA256).Hash
    $firstManifestHash = (Get-FileHash -LiteralPath $firstRun.ManifestPath -Algorithm SHA256).Hash
    $secondManifestHash = (Get-FileHash -LiteralPath $secondRun.ManifestPath -Algorithm SHA256).Hash
    Assert-Equal 'Deterministic USD hash' $firstUsdHash $secondUsdHash
    Assert-Equal 'Deterministic manifest hash' $firstManifestHash $secondManifestHash

    $manifest = Get-Content -Raw -LiteralPath $firstRun.ManifestPath | ConvertFrom-Json
    $verification = Get-Content -Raw -LiteralPath $firstRun.VerificationPath | ConvertFrom-Json
    $denseManifest = Get-Content -Raw -LiteralPath $denseRun.ManifestPath | ConvertFrom-Json
    Assert-Equal 'Explicit dense panel column override' $denseManifest.panels[0].columns 72
    Assert-Equal 'Explicit dense vertical row override' $denseManifest.panels[0].rows 48
    Assert-Equal 'Waist mapping' $manifest.bodyReference.waistCircumference $bridge.unrealGeneration.bodyWaistCircumferenceCm
    Assert-Equal 'Hip mapping' $manifest.bodyReference.hipCircumference $bridge.unrealGeneration.bodyHipCircumferenceCm
    Assert-Equal 'Requested waist height mapping' $manifest.bodyReference.requestedWaistHeight $bridge.unrealGeneration.waistHeightCm
    if ($null -ne $resolvedBodyProfilePath) {
        $profile = Get-Content -Raw -LiteralPath $resolvedBodyProfilePath | ConvertFrom-Json
        Assert-Equal 'Body profile schema mapping' $manifest.bodyReference.liveProfile.schemaVersion 'patterna.live-body-profile/1.0'
        Assert-Equal 'Body profile hash mapping' `
            $manifest.bodyReference.liveProfile.sha256 `
            ((Get-FileHash -LiteralPath $resolvedBodyProfilePath -Algorithm SHA256).Hash.ToLowerInvariant())
        Assert-Equal 'Geometry-derived waist placement reason' `
            $manifest.bodyReference.waistPlacementReason `
            'closest-live-body-circumference'
        Assert-Equal 'Effective waist height consistency' `
            $manifest.bodyReference.waistHeight `
            $manifest.bodyReference.effectiveWaistHeight
        if ($manifest.bodyReference.effectiveWaistHeight -eq $manifest.bodyReference.requestedWaistHeight) {
            throw 'The live body profile did not override the deliberately mismatched requested waist height.'
        }
        if ($manifest.dressing.bodyConformedRowCount -lt 2) {
            throw "Only $($manifest.dressing.bodyConformedRowCount) garment rows were conformed to the measured body."
        }
        if ($null -ne $profile.PSObject.Properties['surfaceSampling']) {
            Assert-Equal 'Body surface sampling mapping' `
                $manifest.bodyReference.liveProfile.surfaceSampling `
                $profile.surfaceSampling
            if ($manifest.bodyReference.liveProfile.minimumSurfacePointCount -lt 16) {
                throw "The live body profile retained only $($manifest.bodyReference.liveProfile.minimumSurfacePointCount) surface points in its sparsest section."
            }
            if ($profile.surfaceSampling -eq 'torso-skin-weight-filtered-triangle-plane-intersection-above-109cm') {
                if ($profile.sections.Count -lt 23) {
                    throw "The expanded live body profile retained only $($profile.sections.Count) sections; at least 23 are required."
                }
                $lowestProfileHeight = ($profile.sections.heightCm | Measure-Object -Minimum).Minimum
                $highestProfileHeight = ($profile.sections.heightCm | Measure-Object -Maximum).Maximum
                if ($lowestProfileHeight -gt 95.0 -or $highestProfileHeight -lt 139.0) {
                    throw "The expanded live body profile covers only $lowestProfileHeight to $highestProfileHeight cm."
                }
                $minimumIntersectionCount = ($profile.sections.sampleCount | Measure-Object -Minimum).Minimum
                if ($minimumIntersectionCount -lt 64) {
                    throw "The sparsest body-plane section contains only $minimumIntersectionCount contour intersections."
                }

                $orderedProfileSections = @($profile.sections | Sort-Object heightCm)
                for ($sectionIndex = 1; $sectionIndex -lt $orderedProfileSections.Count; $sectionIndex++) {
                    $previousCircumference = [double]$orderedProfileSections[$sectionIndex - 1].ellipseCircumferenceCm
                    $currentCircumference = [double]$orderedProfileSections[$sectionIndex].ellipseCircumferenceCm
                    $relativeChange = [Math]::Abs($currentCircumference - $previousCircumference) /
                        [Math]::Max($previousCircumference, $currentCircumference)
                    if ($relativeChange -gt 0.20) {
                        throw "Adjacent body-plane sections change circumference by $([Math]::Round($relativeChange * 100.0, 1)) percent."
                    }
                }
            }
            if ($manifest.dressing.measuredBodySurfaceRowCount -lt 2) {
                throw "Only $($manifest.dressing.measuredBodySurfaceRowCount) garment rows used the measured body surface."
            }
            Assert-Equal 'Verification measured body surface row count' `
                $verification.measuredBodySurfaceRowCount `
                $manifest.dressing.measuredBodySurfaceRowCount
        }
        Assert-Equal 'Verification effective waist height' `
            $verification.effectiveWaistHeightCm `
            $manifest.bodyReference.effectiveWaistHeight
    }
    else {
        Assert-Equal 'Waist height mapping without profile' $manifest.bodyReference.waistHeight $bridge.unrealGeneration.waistHeightCm
    }
    Assert-Equal 'Two-dimensional waist rest circumference' `
        $manifest.garmentMeasurements.waistCircumference `
        ([double]$bridge.unrealGeneration.bodyWaistCircumferenceCm + [double]$bridge.unrealGeneration.waistEaseCm)
    $expectedDressingClearance = if ($null -ne $bridge.unrealGeneration.PSObject.Properties['dressingClearanceCm']) {
        [double]$bridge.unrealGeneration.dressingClearanceCm
    } else {
        8.0
    }
    Assert-Equal 'Requested dressing clearance mapping' $manifest.dressing.requestedMaximumRadialClearance $expectedDressingClearance
    Assert-Equal 'Hip dressing clearance mapping' $manifest.dressing.hipAndBelowRadialClearance 0.0
    Assert-Equal 'Waist dressing clearance mapping' $manifest.dressing.waistRadialClearance 0.0
    Assert-Equal 'Hem dressing clearance mapping' $manifest.dressing.hemRadialClearance 0.0
    Assert-Equal 'Balanced editable pattern hem enabled' $verification.balancedHem $true
    Assert-Equal 'Balanced hem manifest profile' `
        $manifest.dressing.balancedHem.profile `
        'Patterna editable skirt cubic hem'
    Assert-Equal 'Balanced hem center length mapping' `
        $manifest.dressing.balancedHem.centerLengthCm `
        $bridge.unrealGeneration.skirtLengthCm
    Assert-Equal 'Balanced hem verification center length' `
        $verification.centerPatternLengthCm `
        $manifest.dressing.balancedHem.centerLengthCm
    Assert-Equal 'Balanced hem verification side length' `
        $verification.sidePatternVerticalLengthCm `
        $manifest.dressing.balancedHem.sideVerticalLengthCm
    Assert-Equal 'Balanced hem center curve position' $manifest.dressing.balancedHem.centerHemY 224.5
    Assert-Equal 'Balanced hem side curve position' $manifest.dressing.balancedHem.sideHemY 214.0
    Assert-Equal 'Balanced hem control curve position' $manifest.dressing.balancedHem.controlHemY 228.0
    if ($manifest.dressing.balancedHem.sideVerticalLengthCm -ge $manifest.dressing.balancedHem.centerLengthCm) {
        throw 'The balanced skirt hem must shorten the vertical side seam relative to center front.'
    }
    if ($manifest.dressing.balancedHem.sideVerticalLengthCm -lt (0.9 * $manifest.dressing.balancedHem.centerLengthCm)) {
        throw 'The balanced skirt hem shortened the side seam by an implausibly large amount.'
    }
    Assert-Equal 'Waist dressing depth ratio' $manifest.dressing.waistDepthToWidthRatio 0.82
    Assert-Equal 'Hip dressing depth ratio' $manifest.dressing.hipAndHemDepthToWidthRatio 0.78
    Assert-Equal 'Measured body width axis' $manifest.dressing.coordinateAxes.bodyWidth 'X'
    Assert-Equal 'Measured body depth axis' $manifest.dressing.coordinateAxes.forwardDepth 'Y'
    Assert-Equal 'Dressing clearance preserves 2D measurements' $manifest.dressing.preservesTwoDimensionalRestMeasurements $true
    Assert-Equal 'Fabric mass mapping' $manifest.fabric.source.massGsm $bridge.unrealGeneration.fabric.massGramsPerSquareMeter
    Assert-Equal 'Fabric thickness mapping' $manifest.fabric.source.thicknessMm $bridge.unrealGeneration.fabric.thicknessMillimeters
    Assert-Equal 'Separate simulation and render meshes' $verification.separateSimulationAndRenderMeshes $true
    Assert-Equal 'Independent render mesh per panel' $verification.independentRenderMeshPerPanel $true
    Assert-Equal 'Render mesh count' $verification.renderMeshCount 2
    Assert-Equal 'Render pattern count' $verification.renderPatternCount 2
    Assert-Equal 'Raised construction ribbon count' $manifest.renderConstruction.ribbonCount 6
    Assert-Equal 'Raised construction remains render-only' $manifest.renderConstruction.affectsSimulation $false
    Assert-Equal 'Verification construction ribbon count' `
        $verification.constructionRibbonCount `
        $manifest.renderConstruction.ribbonCount
    Assert-Equal 'Verification construction ribbon simulation isolation' `
        $verification.constructionRibbonsAffectSimulation `
        $false
    $expectedConstructionVertices =
        (8 * ([int]$manifest.panels[0].columns + 1)) +
        (4 * ([int]$manifest.panels[0].rows + 1))
    $expectedConstructionTriangles =
        (8 * [int]$manifest.panels[0].columns) +
        (4 * [int]$manifest.panels[0].rows)
    Assert-Equal 'Raised construction vertex count' `
        $manifest.renderConstruction.ribbonVertexCount `
        $expectedConstructionVertices
    Assert-Equal 'Raised construction triangle count' `
        $manifest.renderConstruction.ribbonTriangleCount `
        $expectedConstructionTriangles
    Assert-Equal 'Render-only construction vertex delta' `
        ($verification.renderVertices - $verification.simulationVertices) `
        $expectedConstructionVertices
    Assert-Equal 'Render-only construction triangle delta' `
        ($verification.renderTriangles - $verification.simulationTriangles) `
        $expectedConstructionTriangles

    $renderMeshDefinitions = @(Select-String -Path $firstRun.UsdPath -Pattern '^    def Mesh "RenderMesh(Front|Back)"')
    Assert-Equal 'Independent USD render mesh definitions' $renderMeshDefinitions.Count 2
    $renderColorPrimvars = @(Select-String -Path $firstRun.UsdPath -Pattern 'color3f\[\] primvars:displayColor')
    Assert-Equal 'Render mesh vertex color primvars' $renderColorPrimvars.Count 2
    $usdSource = Get-Content -Raw -LiteralPath $firstRun.UsdPath
    if ($usdSource -notmatch '\(0\.58, 0\.58, 0\.58\)') {
        throw 'The render construction ribbons do not contain their restrained thread tint.'
    }

    $gravityLine = (Select-String -Path $firstRun.UsdPath -Pattern 'float3 gravity').Line.Trim()
    Assert-Equal 'Stage-unit gravity' $gravityLine 'float3 gravity = (0, 0, -981)'

    $invalidSchemaPath = Join-Path $testRoot 'invalid-schema.json'
    $invalidSchema = Get-Content -Raw -LiteralPath $resolvedBridgePath | ConvertFrom-Json
    $invalidSchema.schemaVersion = 'patterna.unreal-bridge/999.0'
    [System.IO.File]::WriteAllText(
        $invalidSchemaPath,
        ($invalidSchema | ConvertTo-Json -Depth 100),
        [System.Text.UTF8Encoding]::new($false))
    Assert-Rejected 'invalid-schema' $invalidSchemaPath 'Unsupported bridge schema' $resolvedBodyProfilePath

    $invalidWaistPath = Join-Path $testRoot 'invalid-waist.json'
    $invalidWaist = Get-Content -Raw -LiteralPath $resolvedBridgePath | ConvertFrom-Json
    $invalidWaist.unrealGeneration.bodyWaistCircumferenceCm = 10.0
    [System.IO.File]::WriteAllText(
        $invalidWaistPath,
        ($invalidWaist | ConvertTo-Json -Depth 100),
        [System.Text.UTF8Encoding]::new($false))
    Assert-Rejected 'invalid-waist' $invalidWaistPath 'BodyWaistCircumferenceCm must be between' $resolvedBodyProfilePath

    $invalidBodyProfileRejected = $false
    if ($null -ne $resolvedBodyProfilePath) {
        $invalidBodyProfilePath = Join-Path $testRoot 'invalid-body-profile.json'
        $invalidBodyProfile = Get-Content -Raw -LiteralPath $resolvedBodyProfilePath | ConvertFrom-Json
        $invalidBodyProfile.schemaVersion = 'patterna.live-body-profile/999.0'
        [System.IO.File]::WriteAllText(
            $invalidBodyProfilePath,
            ($invalidBodyProfile | ConvertTo-Json -Depth 100),
            [System.Text.UTF8Encoding]::new($false))
        Assert-Rejected 'invalid-body-profile' $resolvedBridgePath 'Unsupported body profile schema' $invalidBodyProfilePath
        $invalidBodyProfileRejected = $true
    }

    [pscustomobject]@{
        BridgeSchema = $bridge.schemaVersion
        MeasurementCount = $bridge.body.measurements.Count
        GarmentPanelCount = $bridge.garment.panels.Count
        GarmentSeamCount = $bridge.garment.seams.Count
        UsdSha256 = $firstUsdHash.ToLowerInvariant()
        ManifestSha256 = $firstManifestHash.ToLowerInvariant()
        InvalidSchemaRejected = $true
        InvalidWaistRejected = $true
        InvalidBodyProfileRejected = $invalidBodyProfileRejected
        Result = 'Passed'
    }
}
finally {
    $resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
    if ($resolvedTestRoot.StartsWith($temporaryBase, [StringComparison]::OrdinalIgnoreCase) -and
        [System.IO.Path]::GetFileName($resolvedTestRoot).StartsWith('PatternaUnrealBridgeTest-', [StringComparison]::Ordinal)) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
