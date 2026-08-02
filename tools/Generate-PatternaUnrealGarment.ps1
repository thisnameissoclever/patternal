[CmdletBinding()]
param(
    [string]$BridgeDocumentPath,
    [string]$BodyProfilePath,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\PatternaUnreal\SourceAssets\PatternaFlaredSkirt'),
    [string]$GarmentId = 'PatternaFlaredSkirt',
    [double]$BodyWaistCircumferenceCm = 74.0,
    [double]$BodyHipCircumferenceCm = 98.0,
    [double]$WaistEaseCm = 2.0,
    [double]$HipEaseCm = 5.0,
    [double]$HemCircumferenceCm = 190.0,
    [double]$SkirtLengthCm = 62.0,
    [double]$WaistHeightCm = 108.0,
    [double]$DressingClearanceCm = 8.0,
    [double]$RenderThicknessCm = 0.16,
    [double]$FabricMassGsm = 180.0,
    [double]$FabricThicknessMm = 1.6,
    [double]$FabricWarpStretchPercent = 5.0,
    [double]$FabricWeftStretchPercent = 9.0,
    [double]$FabricBiasStretchPercent = 12.6,
    [double]$FabricBendResistance = 38.0,
    [double]$FabricShearResistance = 79.1,
    [double]$FabricStaticFriction = 0.52,
    [double]$FabricDynamicFriction = 0.45,
    [ValidateRange(8, 96)]
    [int]$PanelColumns = 48,
    [ValidateRange(6, 64)]
    [int]$VerticalRows = 32
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:InvariantCulture = [System.Globalization.CultureInfo]::InvariantCulture
$panelColumnsWereExplicit = $PSBoundParameters.ContainsKey('PanelColumns')
$verticalRowsWereExplicit = $PSBoundParameters.ContainsKey('VerticalRows')
$bridgeDocument = $null
$bridgeDocumentSha256 = $null
$bodyProfile = $null
$bodyProfileSha256 = $null
$resolvedBodyProfilePath = $null
$bodyProfileSurfaceSampling = $null
$bodyProfileMinimumSurfacePointCount = 0

if (-not [string]::IsNullOrWhiteSpace($BridgeDocumentPath)) {
    $resolvedBridgeDocumentPath = [System.IO.Path]::GetFullPath($BridgeDocumentPath)
    if (-not [System.IO.File]::Exists($resolvedBridgeDocumentPath)) {
        throw "Bridge document does not exist: $resolvedBridgeDocumentPath"
    }

    $bridgeDocument = Get-Content -Raw -LiteralPath $resolvedBridgeDocumentPath | ConvertFrom-Json
    if ($bridgeDocument.schemaVersion -ne 'patterna.unreal-bridge/1.0') {
        throw "Unsupported bridge schema: $($bridgeDocument.schemaVersion)"
    }

    $generation = $bridgeDocument.unrealGeneration
    if ($generation.profile -ne 'flared-skirt-v1') {
        throw "Unsupported Unreal generation profile: $($generation.profile)"
    }

    $GarmentId = [string]$generation.garmentId
    $BodyWaistCircumferenceCm = [double]$generation.bodyWaistCircumferenceCm
    $BodyHipCircumferenceCm = [double]$generation.bodyHipCircumferenceCm
    $WaistEaseCm = [double]$generation.waistEaseCm
    $HipEaseCm = [double]$generation.hipEaseCm
    $HemCircumferenceCm = [double]$generation.hemCircumferenceCm
    $SkirtLengthCm = [double]$generation.skirtLengthCm
    $WaistHeightCm = [double]$generation.waistHeightCm
    if ($null -ne $generation.PSObject.Properties['dressingClearanceCm']) {
        $DressingClearanceCm = [double]$generation.dressingClearanceCm
    }
    $RenderThicknessCm = [double]$generation.renderThicknessCm
    if (-not $panelColumnsWereExplicit) {
        $PanelColumns = [int]$generation.panelColumns
    }
    if (-not $verticalRowsWereExplicit) {
        $VerticalRows = [int]$generation.verticalRows
    }

    $FabricMassGsm = [double]$generation.fabric.massGramsPerSquareMeter
    $FabricThicknessMm = [double]$generation.fabric.thicknessMillimeters
    $FabricWarpStretchPercent = [double]$generation.fabric.warpStretchPercent
    $FabricWeftStretchPercent = [double]$generation.fabric.weftStretchPercent
    $FabricBiasStretchPercent = [double]$generation.fabric.biasStretchPercent
    $FabricBendResistance = [double]$generation.fabric.bendResistance
    $FabricShearResistance = [double]$generation.fabric.shearResistance
    $FabricStaticFriction = [double]$generation.fabric.staticFriction
    $FabricDynamicFriction = [double]$generation.fabric.dynamicFriction
    $bridgeDocumentSha256 = (Get-FileHash -LiteralPath $resolvedBridgeDocumentPath -Algorithm SHA256).Hash.ToLowerInvariant()
}

if (-not [string]::IsNullOrWhiteSpace($BodyProfilePath)) {
    $resolvedBodyProfilePath = [System.IO.Path]::GetFullPath($BodyProfilePath)
    if (-not [System.IO.File]::Exists($resolvedBodyProfilePath)) {
        throw "Body profile does not exist: $resolvedBodyProfilePath"
    }

    $bodyProfile = Get-Content -Raw -LiteralPath $resolvedBodyProfilePath | ConvertFrom-Json
    if ($bodyProfile.schemaVersion -ne 'patterna.live-body-profile/1.0') {
        throw "Unsupported body profile schema: $($bodyProfile.schemaVersion)"
    }
    if ($null -eq $bodyProfile.sections -or $bodyProfile.sections.Count -lt 2) {
        throw 'Body profile must contain at least two cross sections.'
    }

    $bodyProfileSha256 = (Get-FileHash -LiteralPath $resolvedBodyProfilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($null -ne $bodyProfile.PSObject.Properties['surfaceSampling']) {
        $bodyProfileSurfaceSampling = [string]$bodyProfile.surfaceSampling
    }
    $surfacePointCounts = @(
        $bodyProfile.sections |
            Where-Object { $null -ne $_.PSObject.Properties['surfacePointCount'] } |
            ForEach-Object { [int]$_.surfacePointCount }
    )
    if ($surfacePointCounts.Count -gt 0) {
        $bodyProfileMinimumSurfacePointCount = [int](
            $surfacePointCounts |
                Measure-Object -Minimum |
                Select-Object -ExpandProperty Minimum)
    }
}

function Assert-InRange {
    param(
        [string]$Name,
        [double]$Value,
        [double]$Minimum,
        [double]$Maximum
    )

    if ($Value -lt $Minimum -or $Value -gt $Maximum) {
        throw "$Name must be between $Minimum and $Maximum. Received $Value."
    }
}

function Format-Number {
    param([double]$Value)

    if ([Math]::Abs($Value) -lt 0.0000005) {
        $Value = 0.0
    }

    return $Value.ToString('0.######', $script:InvariantCulture)
}

function Format-Vector2 {
    param($Value)

    return "($(Format-Number $Value.X), $(Format-Number $Value.Y))"
}

function Format-Vector3 {
    param($Value)

    return "($(Format-Number $Value.X), $(Format-Number $Value.Y), $(Format-Number $Value.Z))"
}

function Format-NumberList {
    param([System.Collections.IEnumerable]$Values)

    $formatted = [System.Collections.Generic.List[string]]::new()
    foreach ($value in $Values) {
        $formatted.Add((Format-Number ([double]$value)))
    }
    return [string]::Join(', ', $formatted)
}

function Format-IntegerList {
    param([System.Collections.IEnumerable]$Values)

    $formatted = [System.Collections.Generic.List[string]]::new()
    foreach ($value in $Values) {
        $formatted.Add(([int]$value).ToString($script:InvariantCulture))
    }
    return [string]::Join(', ', $formatted)
}

function Format-Vector2List {
    param([System.Collections.IEnumerable]$Values)

    $formatted = [System.Collections.Generic.List[string]]::new()
    foreach ($value in $Values) {
        $formatted.Add((Format-Vector2 $value))
    }
    return [string]::Join(', ', $formatted)
}

function Format-Vector3List {
    param([System.Collections.IEnumerable]$Values)

    $formatted = [System.Collections.Generic.List[string]]::new()
    foreach ($value in $Values) {
        $formatted.Add((Format-Vector3 $value))
    }
    return [string]::Join(', ', $formatted)
}

function Get-EllipseRadii {
    param(
        [double]$Circumference,
        [double]$DepthToWidthRatio
    )

    $a = 1.0
    $b = $DepthToWidthRatio
    $h = [Math]::Pow(($a - $b) / ($a + $b), 2)
    $baseCircumference = [Math]::PI * ($a + $b) * (1.0 + ((3.0 * $h) / (10.0 + [Math]::Sqrt(4.0 - (3.0 * $h)))))
    $scale = $Circumference / $baseCircumference

    return [pscustomobject]@{
        X = $scale
        Y = $scale * $DepthToWidthRatio
    }
}

function Get-RowCircumference {
    param([double]$T)

    $waistCircumference = $BodyWaistCircumferenceCm + $WaistEaseCm
    $hipCircumference = $BodyHipCircumferenceCm + $HipEaseCm
    $hipT = 0.34

    if ($T -le $hipT) {
        $blend = $T / $hipT
        $smooth = $blend * $blend * (3.0 - (2.0 * $blend))
        return $waistCircumference + (($hipCircumference - $waistCircumference) * $smooth)
    }

    $blend = ($T - $hipT) / (1.0 - $hipT)
    $smooth = $blend * $blend * (3.0 - (2.0 * $blend))
    return $hipCircumference + (($HemCircumferenceCm - $hipCircumference) * $smooth)
}

function Get-BodyProfileSectionAtHeight {
    param([double]$HeightCm)

    if ($null -eq $bodyProfile) {
        return $null
    }

    $sections = @($bodyProfile.sections | Sort-Object { [double]$_.heightCm })
    $minimumHeight = [double]$sections[0].heightCm
    $maximumHeight = [double]$sections[-1].heightCm
    if ($HeightCm -lt $minimumHeight -or $HeightCm -gt $maximumHeight) {
        return $null
    }

    for ($index = 0; $index -lt $sections.Count; $index++) {
        $upper = $sections[$index]
        $upperHeight = [double]$upper.heightCm
        if ([Math]::Abs($HeightCm - $upperHeight) -le 0.000001) {
            return [pscustomobject]@{
                HeightCm = $HeightCm
                WidthCm = [double]$upper.widthCm
                DepthCm = [double]$upper.depthCm
                CenterXCm = [double]$upper.centerXCm
                CenterYCm = [double]$upper.centerYCm
                EllipseCircumferenceCm = [double]$upper.ellipseCircumferenceCm
                LowerSourceSection = $upper
                UpperSourceSection = $upper
                HeightBlend = 0.0
            }
        }
        if ($upperHeight -gt $HeightCm) {
            $lower = $sections[$index - 1]
            $lowerHeight = [double]$lower.heightCm
            $blend = ($HeightCm - $lowerHeight) / ($upperHeight - $lowerHeight)
            return [pscustomobject]@{
                HeightCm = $HeightCm
                WidthCm = ([double]$lower.widthCm) + (([double]$upper.widthCm - [double]$lower.widthCm) * $blend)
                DepthCm = ([double]$lower.depthCm) + (([double]$upper.depthCm - [double]$lower.depthCm) * $blend)
                CenterXCm = ([double]$lower.centerXCm) + (([double]$upper.centerXCm - [double]$lower.centerXCm) * $blend)
                CenterYCm = ([double]$lower.centerYCm) + (([double]$upper.centerYCm - [double]$lower.centerYCm) * $blend)
                EllipseCircumferenceCm = ([double]$lower.ellipseCircumferenceCm) + (([double]$upper.ellipseCircumferenceCm - [double]$lower.ellipseCircumferenceCm) * $blend)
                LowerSourceSection = $lower
                UpperSourceSection = $upper
                HeightBlend = $blend
            }
        }
    }

    return $null
}

$bodySurfacePointCache = @{}

function Get-BodySurfaceRadiusAtAngle {
    param(
        $Section,
        [double]$AngleRadians
    )

    if ($null -eq $Section -or
        $null -eq $Section.PSObject.Properties['surfacePoints'] -or
        $null -eq $Section.surfacePoints -or
        $Section.surfacePoints.Count -lt 3) {
        return $null
    }

    $cacheKey = [string]$Section.heightCm
    if (-not $bodySurfacePointCache.ContainsKey($cacheKey)) {
        $normalizedPoints = @(
            $Section.surfacePoints |
                ForEach-Object {
                    $normalizedAngle = [double]$_.angleRadians
                    while ($normalizedAngle -lt 0.0) {
                        $normalizedAngle += 2.0 * [Math]::PI
                    }
                    while ($normalizedAngle -ge 2.0 * [Math]::PI) {
                        $normalizedAngle -= 2.0 * [Math]::PI
                    }
                    [pscustomobject]@{
                        Angle = $normalizedAngle
                        Radius = [double]$_.radiusCm
                    }
                } |
                Sort-Object Angle
        )
        $bodySurfacePointCache[$cacheKey] = $normalizedPoints
    }

    $points = @($bodySurfacePointCache[$cacheKey])
    if ($points.Count -lt 3) {
        return $null
    }

    $targetAngle = $AngleRadians
    while ($targetAngle -lt 0.0) {
        $targetAngle += 2.0 * [Math]::PI
    }
    while ($targetAngle -ge 2.0 * [Math]::PI) {
        $targetAngle -= 2.0 * [Math]::PI
    }

    $upperIndex = 0
    while ($upperIndex -lt $points.Count -and [double]$points[$upperIndex].Angle -lt $targetAngle) {
        $upperIndex++
    }

    if ($upperIndex -eq 0) {
        $lowerPoint = $points[-1]
        $upperPoint = $points[0]
        $lowerAngle = [double]$lowerPoint.Angle - (2.0 * [Math]::PI)
        $upperAngle = [double]$upperPoint.Angle
    }
    elseif ($upperIndex -ge $points.Count) {
        $lowerPoint = $points[-1]
        $upperPoint = $points[0]
        $lowerAngle = [double]$lowerPoint.Angle
        $upperAngle = [double]$upperPoint.Angle + (2.0 * [Math]::PI)
    }
    else {
        $lowerPoint = $points[$upperIndex - 1]
        $upperPoint = $points[$upperIndex]
        $lowerAngle = [double]$lowerPoint.Angle
        $upperAngle = [double]$upperPoint.Angle
    }

    $angleSpan = $upperAngle - $lowerAngle
    if ($angleSpan -le 0.000001) {
        return [double]$lowerPoint.Radius
    }
    $blend = ($targetAngle - $lowerAngle) / $angleSpan
    if ($blend -lt 0.0) {
        $blend = (($targetAngle + (2.0 * [Math]::PI)) - $lowerAngle) / $angleSpan
    }
    return ([double]$lowerPoint.Radius) + (([double]$upperPoint.Radius - [double]$lowerPoint.Radius) * $blend)
}

function Add-Triangle {
    param(
        [System.Collections.Generic.List[int]]$FaceVertexCounts,
        [System.Collections.Generic.List[int]]$FaceVertexIndices,
        [System.Collections.Generic.List[object]]$FaceTriples,
        [int]$A,
        [int]$B,
        [int]$C
    )

    $FaceVertexCounts.Add(3)
    $FaceVertexIndices.Add($A)
    $FaceVertexIndices.Add($B)
    $FaceVertexIndices.Add($C)
    $FaceTriples.Add([pscustomobject]@{ A = $A; B = $B; C = $C })
    return $FaceVertexCounts.Count - 1
}

function Get-CrossProduct {
    param($A, $B, $C)

    $abX = $B.X - $A.X
    $abY = $B.Y - $A.Y
    $abZ = $B.Z - $A.Z
    $acX = $C.X - $A.X
    $acY = $C.Y - $A.Y
    $acZ = $C.Z - $A.Z

    return [pscustomobject]@{
        X = ($abY * $acZ) - ($abZ * $acY)
        Y = ($abZ * $acX) - ($abX * $acZ)
        Z = ($abX * $acY) - ($abY * $acX)
    }
}

function Add-RaisedRenderRibbon {
    param(
        [System.Collections.Generic.List[object]]$Points,
        [System.Collections.Generic.List[object]]$Uvs,
        [System.Collections.Generic.List[object]]$Colors,
        [System.Collections.Generic.List[int]]$FaceCounts,
        [System.Collections.Generic.List[int]]$FaceIndices,
        [System.Collections.Generic.List[object]]$FaceTriples,
        [System.Collections.Generic.List[int]]$PatternFaces,
        [int[]]$OuterIndices,
        [int[]]$InteriorIndices,
        [double]$WidthCm,
        [double]$SurfaceOffsetCm
    )

    if ($OuterIndices.Count -ne $InteriorIndices.Count -or $OuterIndices.Count -lt 2) {
        throw 'A raised render ribbon requires matching outer and interior point chains.'
    }

    $ribbonStart = $Points.Count
    for ($index = 0; $index -lt $OuterIndices.Count; $index++) {
        $outerPoint = $Points[$OuterIndices[$index]]
        $interiorPoint = $Points[$InteriorIndices[$index]]
        $insetX = [double]$interiorPoint.X - [double]$outerPoint.X
        $insetY = [double]$interiorPoint.Y - [double]$outerPoint.Y
        $insetZ = [double]$interiorPoint.Z - [double]$outerPoint.Z
        $insetLength = [Math]::Sqrt(($insetX * $insetX) + ($insetY * $insetY) + ($insetZ * $insetZ))
        if ($insetLength -le 0.000001) {
            throw 'A raised render ribbon encountered coincident outer and interior points.'
        }
        $insetScale = [Math]::Min(1.0, $WidthCm / $insetLength)

        $radialLength = [Math]::Sqrt(
            ([double]$outerPoint.X * [double]$outerPoint.X) +
            ([double]$outerPoint.Y * [double]$outerPoint.Y))
        $radialX = if ($radialLength -gt 0.000001) { [double]$outerPoint.X / $radialLength } else { 1.0 }
        $radialY = if ($radialLength -gt 0.000001) { [double]$outerPoint.Y / $radialLength } else { 0.0 }

        $raisedOuter = [pscustomobject]@{
            X = [double]$outerPoint.X + ($radialX * $SurfaceOffsetCm)
            Y = [double]$outerPoint.Y + ($radialY * $SurfaceOffsetCm)
            Z = [double]$outerPoint.Z
        }
        $raisedInner = [pscustomobject]@{
            X = [double]$outerPoint.X + ($insetX * $insetScale) + ($radialX * $SurfaceOffsetCm)
            Y = [double]$outerPoint.Y + ($insetY * $insetScale) + ($radialY * $SurfaceOffsetCm)
            Z = [double]$outerPoint.Z + ($insetZ * $insetScale)
        }
        $outerUv = $Uvs[$OuterIndices[$index]]
        $interiorUv = $Uvs[$InteriorIndices[$index]]
        $innerUv = [pscustomobject]@{
            X = [double]$outerUv.X + (([double]$interiorUv.X - [double]$outerUv.X) * $insetScale)
            Y = [double]$outerUv.Y + (([double]$interiorUv.Y - [double]$outerUv.Y) * $insetScale)
        }

        $Points.Add($raisedOuter)
        $Points.Add($raisedInner)
        $Uvs.Add([pscustomobject]@{ X = [double]$outerUv.X; Y = [double]$outerUv.Y })
        $Uvs.Add($innerUv)
        $Colors.Add([pscustomobject]@{ X = 0.58; Y = 0.58; Z = 0.58 })
        $Colors.Add([pscustomobject]@{ X = 0.58; Y = 0.58; Z = 0.58 })
    }

    $triangleCount = 0
    for ($segmentIndex = 0; $segmentIndex -lt $OuterIndices.Count - 1; $segmentIndex++) {
        $outerA = $ribbonStart + ($segmentIndex * 2)
        $innerA = $outerA + 1
        $outerB = $outerA + 2
        $innerB = $outerA + 3
        $cross = Get-CrossProduct $Points[$outerA] $Points[$innerA] $Points[$outerB]
        $centerX = ([double]$Points[$outerA].X + [double]$Points[$innerA].X + [double]$Points[$outerB].X) / 3.0
        $centerY = ([double]$Points[$outerA].Y + [double]$Points[$innerA].Y + [double]$Points[$outerB].Y) / 3.0
        $outwardDot = ($cross.X * $centerX) + ($cross.Y * $centerY)

        if ($outwardDot -ge 0.0) {
            $PatternFaces.Add((Add-Triangle $FaceCounts $FaceIndices $FaceTriples $outerA $innerA $outerB))
            $PatternFaces.Add((Add-Triangle $FaceCounts $FaceIndices $FaceTriples $innerA $innerB $outerB))
        }
        else {
            $PatternFaces.Add((Add-Triangle $FaceCounts $FaceIndices $FaceTriples $outerA $outerB $innerA))
            $PatternFaces.Add((Add-Triangle $FaceCounts $FaceIndices $FaceTriples $innerA $outerB $innerB))
        }
        $triangleCount += 2
    }

    return [pscustomobject]@{
        VertexCount = $OuterIndices.Count * 2
        TriangleCount = $triangleCount
    }
}

Assert-InRange 'BodyWaistCircumferenceCm' $BodyWaistCircumferenceCm 45.0 180.0
Assert-InRange 'BodyHipCircumferenceCm' $BodyHipCircumferenceCm 55.0 220.0
Assert-InRange 'WaistEaseCm' $WaistEaseCm -8.0 30.0
Assert-InRange 'HipEaseCm' $HipEaseCm -8.0 40.0
Assert-InRange 'HemCircumferenceCm' $HemCircumferenceCm 70.0 500.0
Assert-InRange 'SkirtLengthCm' $SkirtLengthCm 20.0 160.0
Assert-InRange 'WaistHeightCm' $WaistHeightCm 60.0 160.0
Assert-InRange 'DressingClearanceCm' $DressingClearanceCm 0.0 10.0
Assert-InRange 'RenderThicknessCm' $RenderThicknessCm 0.02 1.0
Assert-InRange 'FabricMassGsm' $FabricMassGsm 5.0 2000.0
Assert-InRange 'FabricThicknessMm' $FabricThicknessMm 0.01 20.0
Assert-InRange 'FabricWarpStretchPercent' $FabricWarpStretchPercent 0.1 300.0
Assert-InRange 'FabricWeftStretchPercent' $FabricWeftStretchPercent 0.1 300.0
Assert-InRange 'FabricBiasStretchPercent' $FabricBiasStretchPercent 0.1 500.0
Assert-InRange 'FabricBendResistance' $FabricBendResistance 0.0 100.0
Assert-InRange 'FabricShearResistance' $FabricShearResistance 0.0 200.0
Assert-InRange 'FabricStaticFriction' $FabricStaticFriction 0.01 5.0
Assert-InRange 'FabricDynamicFriction' $FabricDynamicFriction 0.01 5.0

$requestedWaistHeightCm = $WaistHeightCm
$effectiveWaistHeightCm = $WaistHeightCm
$waistPlacementReason = 'requested-measurement'
$matchedWaistSection = $null
if ($null -ne $bodyProfile) {
    $validBodySections = @(
        $bodyProfile.sections |
            Where-Object {
                [double]$_.widthCm -gt 5.0 -and
                [double]$_.widthCm -lt 40.0 -and
                [double]$_.depthCm -gt 5.0 -and
                [double]$_.depthCm -lt 40.0 -and
                [double]$_.ellipseCircumferenceCm -gt 30.0 -and
                [double]$_.ellipseCircumferenceCm -lt 180.0 -and
                [int]$_.sampleCount -ge 8
            } |
            Sort-Object `
                @{ Expression = { [Math]::Abs([double]$_.ellipseCircumferenceCm - $BodyWaistCircumferenceCm) } },
                @{ Expression = { [Math]::Abs([double]$_.heightCm - $requestedWaistHeightCm) } }
    )
    if ($validBodySections.Count -eq 0) {
        throw 'Body profile contains no valid torso cross sections.'
    }

    $matchedWaistSection = $validBodySections[0]
    $waistCircumferenceErrorCm = [Math]::Abs(
        [double]$matchedWaistSection.ellipseCircumferenceCm - $BodyWaistCircumferenceCm)
    if ($waistCircumferenceErrorCm -gt 10.0) {
        throw "Body profile does not contain a plausible waist section. Closest circumference error: $waistCircumferenceErrorCm cm."
    }

    $effectiveWaistHeightCm = [double]$matchedWaistSection.heightCm
    $WaistHeightCm = $effectiveWaistHeightCm
    $waistPlacementReason = 'closest-live-body-circumference'
}

if ($PanelColumns -lt 8 -or $PanelColumns -gt 96) {
    throw "PanelColumns must be between 8 and 96. Received $PanelColumns."
}
if ($VerticalRows -lt 6 -or $VerticalRows -gt 64) {
    throw "VerticalRows must be between 6 and 64. Received $VerticalRows."
}

if ([Math]::Abs($RenderThicknessCm - ($FabricThicknessMm / 10.0)) -gt 0.0001) {
    throw 'RenderThicknessCm must match FabricThicknessMm converted to centimeters.'
}

$fabricDensityKgPerSquareCm = $FabricMassGsm / 10000000.0
$stretchWarpStiffness = 120000.0 / (1.0 + ($FabricWarpStretchPercent / 10.0))
$stretchWeftStiffness = 120000.0 / (1.0 + ($FabricWeftStretchPercent / 10.0))
$shearStiffness = 3000.0 + ($FabricShearResistance * 150.0)
# Map the fabric controls into Chaos' practical low bending range. Values near
# two resisted the distributed buckling that a lightweight woven skirt needs
# and concentrated the excess hem length into a few oversized waves.
$bendWarpStiffness = 0.05 + ($FabricBendResistance * 0.006)
$bendWeftStiffness = 0.03 + ($FabricBendResistance * 0.003)
$bendBiasStiffness = 0.04 + ($FabricBendResistance * 0.0045)
$internalDamping = [Math]::Clamp(0.08 + ($FabricMassGsm / 2000.0), 0.08, 0.35)

$waistGarmentCircumferenceCm = $BodyWaistCircumferenceCm + $WaistEaseCm
$hipGarmentCircumferenceCm = $BodyHipCircumferenceCm + $HipEaseCm
$waistDressingClearanceCm = 0.0
$hipDressingClearanceCm = 0.0
$hemDressingClearanceCm = 0.0
$waistDepthToWidthRatio = 0.82
$hipAndHemDepthToWidthRatio = 0.78
$hipTransitionT = 0.34
$bodySupportCollisionOffsetCm = [Math]::Max(0.15, ($RenderThicknessCm * 0.5) + 0.05)
$bodyConformedRowCount = 0
$measuredBodySurfaceRowCount = 0
if ($hipGarmentCircumferenceCm -lt $waistGarmentCircumferenceCm) {
    throw 'The hip garment circumference must not be smaller than the waist garment circumference.'
}
if ($HemCircumferenceCm -lt $hipGarmentCircumferenceCm) {
    throw 'The hem circumference must not be smaller than the hip garment circumference for this flared-skirt generator.'
}

$resolvedOutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($resolvedOutputDirectory) | Out-Null

$simPoints = [System.Collections.Generic.List[object]]::new()
$simUvs = [System.Collections.Generic.List[object]]::new()
$simFaceCounts = [System.Collections.Generic.List[int]]::new()
$simFaceIndices = [System.Collections.Generic.List[int]]::new()
$simFaceTriples = [System.Collections.Generic.List[object]]::new()
$frontFaces = [System.Collections.Generic.List[int]]::new()
$backFaces = [System.Collections.Generic.List[int]]::new()
$panelVertexCount = ($VerticalRows + 1) * ($PanelColumns + 1)
$maximumPanelWidth = $HemCircumferenceCm / 2.0
# Match the editable Patterna skirt panel's cubic hem. The center-front grain
# remains the requested skirt length while the side seam is raised enough to
# account for its diagonal flare and the body path over the hip.
$patternHemSideY = 214.0
$patternHemControlY = 228.0
$patternHemCenterY = 224.5

for ($panelIndex = 0; $panelIndex -lt 2; $panelIndex++) {
    for ($row = 0; $row -le $VerticalRows; $row++) {
        $t = $row / [double]$VerticalRows
        $circumference = Get-RowCircumference $t
        $depthRatioBlend = [Math]::Min(1.0, $t / $hipTransitionT)
        $depthRatioBlend = $depthRatioBlend * $depthRatioBlend * (3.0 - (2.0 * $depthRatioBlend))
        $depthRatio = $waistDepthToWidthRatio +
            (($hipAndHemDepthToWidthRatio - $waistDepthToWidthRatio) * $depthRatioBlend)
        $radii = Get-EllipseRadii $circumference $depthRatio
        $panelWidth = $circumference / 2.0
        $z = $WaistHeightCm - ($SkirtLengthCm * $t)
        $bodySection = Get-BodyProfileSectionAtHeight $z
        $rowCenterX = 0.0
        $rowCenterY = 0.0
        $useMeasuredBodySurface = $false
        $bodySurfaceRadialOffsetCm = 0.0
        if ($null -ne $bodySection) {
            $lowerSurfacePoints = $bodySection.LowerSourceSection.PSObject.Properties['surfacePoints']
            $upperSurfacePoints = $bodySection.UpperSourceSection.PSObject.Properties['surfacePoints']
            if ($null -ne $lowerSurfacePoints -and
                $null -ne $upperSurfacePoints -and
                $bodySection.LowerSourceSection.surfacePoints.Count -ge 3 -and
                $bodySection.UpperSourceSection.surfacePoints.Count -ge 3) {
                $useMeasuredBodySurface = $true
                $bodySurfaceRadialOffsetCm =
                    (($circumference - [double]$bodySection.EllipseCircumferenceCm) / (2.0 * [Math]::PI)) +
                    $bodySupportCollisionOffsetCm
                $rowCenterX = [double]$bodySection.CenterXCm
                $rowCenterY = [double]$bodySection.CenterYCm
                if ($panelIndex -eq 0) {
                    $bodyConformedRowCount++
                    $measuredBodySurfaceRowCount++
                }
            }
            else {
                $bodyClearanceCircumference = [double]$bodySection.EllipseCircumferenceCm +
                    (2.0 * [Math]::PI * $bodySupportCollisionOffsetCm)
            }
            if (-not $useMeasuredBodySurface -and $circumference -lt $bodyClearanceCircumference) {
                $scale = $bodyClearanceCircumference / [double]$bodySection.EllipseCircumferenceCm
                $radii = [pscustomobject]@{
                    X = ([double]$bodySection.WidthCm * 0.5) * $scale
                    Y = ([double]$bodySection.DepthCm * 0.5) * $scale
                }
                $rowCenterX = [double]$bodySection.CenterXCm
                $rowCenterY = [double]$bodySection.CenterYCm
                if ($panelIndex -eq 0) {
                    $bodyConformedRowCount++
                }
            }
        }

        for ($column = 0; $column -le $PanelColumns; $column++) {
            $u = $column / [double]$PanelColumns
            if ($panelIndex -eq 0) {
                $angle = (-0.5 * [Math]::PI) + ([Math]::PI * $u)
            }
            else {
                $angle = (0.5 * [Math]::PI) + ([Math]::PI * $u)
            }

            if ($t -le $hipTransitionT) {
                $clearanceBlend = $t / $hipTransitionT
                $clearanceBlend = $clearanceBlend * $clearanceBlend * (3.0 - (2.0 * $clearanceBlend))
                $rowDressingClearanceCm = $waistDressingClearanceCm +
                    (($hipDressingClearanceCm - $waistDressingClearanceCm) * $clearanceBlend)
            }
            else {
                $clearanceBlend = ($t - $hipTransitionT) / (1.0 - $hipTransitionT)
                $clearanceBlend = $clearanceBlend * $clearanceBlend * (3.0 - (2.0 * $clearanceBlend))
                $rowDressingClearanceCm = $hipDressingClearanceCm +
                    (($hemDressingClearanceCm - $hipDressingClearanceCm) * $clearanceBlend)
            }
            $dressingRadiusX = $radii.X + $rowDressingClearanceCm
            $dressingRadiusY = $radii.Y + $rowDressingClearanceCm
            # A perfectly rotationally symmetric dressing pose makes the
            # numerical solve choose one or two arbitrary large buckling modes.
            # This sub-millimeter seed breaks that symmetry without changing
            # the two-dimensional rest pattern or the sewn seam locations.
            $foldSeedBlend = [Math]::Clamp(($t - $hipTransitionT) / (1.0 - $hipTransitionT), 0.0, 1.0)
            $foldSeedBlend = $foldSeedBlend * $foldSeedBlend * (3.0 - (2.0 * $foldSeedBlend))
            $foldSeedCm = 0.08 * $foldSeedBlend * [Math]::Sin(12.0 * $angle)
            if ($useMeasuredBodySurface) {
                $bodyPolarAngle = $angle + (0.5 * [Math]::PI)
                $lowerSurfaceRadius = Get-BodySurfaceRadiusAtAngle `
                    $bodySection.LowerSourceSection `
                    $bodyPolarAngle
                $upperSurfaceRadius = Get-BodySurfaceRadiusAtAngle `
                    $bodySection.UpperSourceSection `
                    $bodyPolarAngle
                if ($null -eq $lowerSurfaceRadius -or $null -eq $upperSurfaceRadius) {
                    throw "Measured body surface sampling failed at height $z cm and angle $bodyPolarAngle radians."
                }
                $bodySurfaceRadius = [double]$lowerSurfaceRadius +
                    (([double]$upperSurfaceRadius - [double]$lowerSurfaceRadius) * [double]$bodySection.HeightBlend)
                $dressingRadius = [Math]::Max(
                    0.5,
                    $bodySurfaceRadius + $bodySurfaceRadialOffsetCm + $rowDressingClearanceCm + $foldSeedCm)
                $x = $rowCenterX + ($dressingRadius * [Math]::Cos($bodyPolarAngle))
                $y = $rowCenterY + ($dressingRadius * [Math]::Sin($bodyPolarAngle))
            }
            else {
                $dressingRadiusX += $foldSeedCm
                $dressingRadiusY += $foldSeedCm
                # This MetaHuman faces along Y, with body width along X. The
                # ellipse helper returns its wide radius as X and depth as Y,
                # so map those dimensions onto the measured live body axes.
                $x = $rowCenterX - ($dressingRadiusX * [Math]::Sin($angle))
                $y = $rowCenterY + ($dressingRadiusY * [Math]::Cos($angle))
            }
            $flatX = (-0.5 * $panelWidth) + ($panelWidth * $u)
            $uvX = 0.5 + ($flatX / $maximumPanelWidth)
            $inverseU = 1.0 - $u
            $hemCurveY =
                ($patternHemSideY * [Math]::Pow($inverseU, 3.0)) +
                (3.0 * $patternHemControlY * [Math]::Pow($inverseU, 2.0) * $u) +
                (3.0 * $patternHemControlY * $inverseU * [Math]::Pow($u, 2.0)) +
                ($patternHemSideY * [Math]::Pow($u, 3.0))
            $columnPatternLengthCm = $SkirtLengthCm * ($hemCurveY / $patternHemCenterY)
            $flatPatternYCm = $columnPatternLengthCm * $t
            $uvY = 1.0 - ($flatPatternYCm / $SkirtLengthCm)

            $simPoints.Add([pscustomobject]@{ X = $x; Y = $y; Z = $z })
            $simUvs.Add([pscustomobject]@{ X = $uvX; Y = $uvY })
        }
    }

    $panelVertexStart = $panelIndex * $panelVertexCount
    if ($panelIndex -eq 0) {
        $destinationFaces = $frontFaces
    }
    else {
        $destinationFaces = $backFaces
    }

    for ($row = 0; $row -lt $VerticalRows; $row++) {
        for ($column = 0; $column -lt $PanelColumns; $column++) {
            $v00 = $panelVertexStart + ($row * ($PanelColumns + 1)) + $column
            $v01 = $v00 + 1
            $v10 = $v00 + ($PanelColumns + 1)
            $v11 = $v10 + 1

            $destinationFaces.Add((Add-Triangle $simFaceCounts $simFaceIndices $simFaceTriples $v00 $v10 $v01))
            $destinationFaces.Add((Add-Triangle $simFaceCounts $simFaceIndices $simFaceTriples $v01 $v10 $v11))
        }
    }
}

$frontVertexStart = 0
$backVertexStart = $panelVertexCount
$leftSideSeam = [System.Collections.Generic.List[int]]::new()
$rightSideSeam = [System.Collections.Generic.List[int]]::new()

for ($row = 0; $row -le $VerticalRows; $row++) {
    $rowOffset = $row * ($PanelColumns + 1)

    $leftSideSeam.Add($frontVertexStart + $rowOffset)
    $leftSideSeam.Add($backVertexStart + $rowOffset + $PanelColumns)

    $rightSideSeam.Add($frontVertexStart + $rowOffset + $PanelColumns)
    $rightSideSeam.Add($backVertexStart + $rowOffset)
}

$renderFrontPoints = [System.Collections.Generic.List[object]]::new()
$renderFrontUvs = [System.Collections.Generic.List[object]]::new()
$renderFrontColors = [System.Collections.Generic.List[object]]::new()
$renderFrontFaceCounts = [System.Collections.Generic.List[int]]::new()
$renderFrontFaceIndices = [System.Collections.Generic.List[int]]::new()
$renderFrontFaceTriples = [System.Collections.Generic.List[object]]::new()
$renderFrontPatternFaces = [System.Collections.Generic.List[int]]::new()
$renderBackPoints = [System.Collections.Generic.List[object]]::new()
$renderBackUvs = [System.Collections.Generic.List[object]]::new()
$renderBackColors = [System.Collections.Generic.List[object]]::new()
$renderBackFaceCounts = [System.Collections.Generic.List[int]]::new()
$renderBackFaceIndices = [System.Collections.Generic.List[int]]::new()
$renderBackFaceTriples = [System.Collections.Generic.List[object]]::new()
$renderBackPatternFaces = [System.Collections.Generic.List[int]]::new()
$constructionRibbonCount = 0
$constructionRibbonVertexCount = 0
$constructionRibbonTriangleCount = 0
$constructionRibbonWidthCm = 0.22
$constructionRibbonSurfaceOffsetCm = [Math]::Max(0.045, $RenderThicknessCm * 1.25)

for ($panelIndex = 0; $panelIndex -lt 2; $panelIndex++) {
    $panelVertexStart = $panelIndex * $panelVertexCount
    if ($panelIndex -eq 0) {
        $sourceFaces = $frontFaces
        $destinationPoints = $renderFrontPoints
        $destinationUvs = $renderFrontUvs
        $destinationColors = $renderFrontColors
        $destinationFaceCounts = $renderFrontFaceCounts
        $destinationFaceIndices = $renderFrontFaceIndices
        $destinationFaceTriples = $renderFrontFaceTriples
        $destinationPatternFaces = $renderFrontPatternFaces
    }
    else {
        $sourceFaces = $backFaces
        $destinationPoints = $renderBackPoints
        $destinationUvs = $renderBackUvs
        $destinationColors = $renderBackColors
        $destinationFaceCounts = $renderBackFaceCounts
        $destinationFaceIndices = $renderBackFaceIndices
        $destinationFaceTriples = $renderBackFaceTriples
        $destinationPatternFaces = $renderBackPatternFaces
    }

    for ($localVertexIndex = 0; $localVertexIndex -lt $panelVertexCount; $localVertexIndex++) {
        $sourceVertexIndex = $panelVertexStart + $localVertexIndex
        $point = $simPoints[$sourceVertexIndex]
        $destinationPoints.Add([pscustomobject]@{
            X = $point.X
            Y = $point.Y
            Z = $point.Z
        })
        $destinationUvs.Add($simUvs[$sourceVertexIndex])
        $destinationColors.Add([pscustomobject]@{ X = 1.0; Y = 1.0; Z = 1.0 })
    }

    foreach ($faceIndex in $sourceFaces) {
        $triangle = $simFaceTriples[$faceIndex]
        $destinationPatternFaces.Add((Add-Triangle `
            $destinationFaceCounts `
            $destinationFaceIndices `
            $destinationFaceTriples `
            ($triangle.A - $panelVertexStart) `
            ($triangle.B - $panelVertexStart) `
            ($triangle.C - $panelVertexStart)))
    }

    $waistRibbonRow = [Math]::Min(2, $VerticalRows - 1)
    $hemRibbonRow = [Math]::Max(1, $VerticalRows - 1)
    foreach ($ribbonDefinition in @(
        [pscustomobject]@{
            Outer = @(
                for ($column = 0; $column -le $PanelColumns; $column++) {
                    ($waistRibbonRow * ($PanelColumns + 1)) + $column
                })
            Interior = @(
                for ($column = 0; $column -le $PanelColumns; $column++) {
                    (($waistRibbonRow + 1) * ($PanelColumns + 1)) + $column
                })
        },
        [pscustomobject]@{
            Outer = @(
                for ($column = 0; $column -le $PanelColumns; $column++) {
                    ($hemRibbonRow * ($PanelColumns + 1)) + $column
                })
            Interior = @(
                for ($column = 0; $column -le $PanelColumns; $column++) {
                    (($hemRibbonRow - 1) * ($PanelColumns + 1)) + $column
                })
        }
    )) {
        $ribbonResult = Add-RaisedRenderRibbon `
            $destinationPoints `
            $destinationUvs `
            $destinationColors `
            $destinationFaceCounts `
            $destinationFaceIndices `
            $destinationFaceTriples `
            $destinationPatternFaces `
            ([int[]]$ribbonDefinition.Outer) `
            ([int[]]$ribbonDefinition.Interior) `
            $constructionRibbonWidthCm `
            $constructionRibbonSurfaceOffsetCm
        $constructionRibbonCount++
        $constructionRibbonVertexCount += $ribbonResult.VertexCount
        $constructionRibbonTriangleCount += $ribbonResult.TriangleCount
    }

    if ($panelIndex -eq 0) {
        foreach ($sideColumn in @(0, $PanelColumns)) {
            $interiorColumn = if ($sideColumn -eq 0) { 1 } else { $PanelColumns - 1 }
            $outerIndices = @(
                for ($row = 0; $row -le $VerticalRows; $row++) {
                    ($row * ($PanelColumns + 1)) + $sideColumn
                })
            $interiorIndices = @(
                for ($row = 0; $row -le $VerticalRows; $row++) {
                    ($row * ($PanelColumns + 1)) + $interiorColumn
                })
            $ribbonResult = Add-RaisedRenderRibbon `
                $destinationPoints `
                $destinationUvs `
                $destinationColors `
                $destinationFaceCounts `
                $destinationFaceIndices `
                $destinationFaceTriples `
                $destinationPatternFaces `
                ([int[]]$outerIndices) `
                ([int[]]$interiorIndices) `
                $constructionRibbonWidthCm `
                $constructionRibbonSurfaceOffsetCm
            $constructionRibbonCount++
            $constructionRibbonVertexCount += $ribbonResult.VertexCount
            $constructionRibbonTriangleCount += $ribbonResult.TriangleCount
        }
    }
}

$renderVertexCount = $renderFrontPoints.Count + $renderBackPoints.Count
$renderTriangleCount = $renderFrontFaceCounts.Count + $renderBackFaceCounts.Count

$minimumTriangleArea2 = [double]::PositiveInfinity
$minimumOutwardDot = [double]::PositiveInfinity
for ($faceIndex = 0; $faceIndex -lt $simFaceTriples.Count; $faceIndex++) {
    $triangle = $simFaceTriples[$faceIndex]
    $pointA = $simPoints[$triangle.A]
    $pointB = $simPoints[$triangle.B]
    $pointC = $simPoints[$triangle.C]
    $cross = Get-CrossProduct $pointA $pointB $pointC
    $area2 = [Math]::Sqrt(($cross.X * $cross.X) + ($cross.Y * $cross.Y) + ($cross.Z * $cross.Z))
    $centerX = ($pointA.X + $pointB.X + $pointC.X) / 3.0
    $centerY = ($pointA.Y + $pointB.Y + $pointC.Y) / 3.0
    $outwardDot = ($cross.X * $centerX) + ($cross.Y * $centerY)

    $minimumTriangleArea2 = [Math]::Min($minimumTriangleArea2, $area2)
    $minimumOutwardDot = [Math]::Min($minimumOutwardDot, $outwardDot)
}

if ($minimumTriangleArea2 -le 0.0001) {
    throw "The generated simulation mesh contains a degenerate triangle. Minimum doubled area: $minimumTriangleArea2"
}
if ($minimumOutwardDot -le 0.0) {
    throw "The generated simulation mesh contains an inward-facing triangle. Minimum outward dot: $minimumOutwardDot"
}

for ($pairIndex = 0; $pairIndex -lt $leftSideSeam.Count; $pairIndex += 2) {
    foreach ($seam in @($leftSideSeam, $rightSideSeam)) {
        $pointA = $simPoints[$seam[$pairIndex]]
        $pointB = $simPoints[$seam[$pairIndex + 1]]
        $distance = [Math]::Sqrt(
            [Math]::Pow($pointA.X - $pointB.X, 2) +
            [Math]::Pow($pointA.Y - $pointB.Y, 2) +
            [Math]::Pow($pointA.Z - $pointB.Z, 2)
        )
        if ($distance -gt 0.001) {
            throw "A generated seam pair does not share the same draped position. Distance: $distance"
        }
    }
}

$fabricAttributes = @"
            float[] primvars:clo:bendingBiasLeft = [$(Format-Number $bendBiasStiffness)]
            float[] primvars:clo:bendingBiasRight = [$(Format-Number $bendBiasStiffness)]
            float[] primvars:clo:bendingWarp = [$(Format-Number $bendWarpStiffness)]
            float[] primvars:clo:bendingWeft = [$(Format-Number $bendWeftStiffness)]
            float[] primvars:clo:bucklingRatioBiasLeft = [0.35]
            float[] primvars:clo:bucklingRatioBiasRight = [0.35]
            float[] primvars:clo:bucklingRatioWarp = [0.4]
            float[] primvars:clo:bucklingRatioWeft = [0.3]
            float[] primvars:clo:bucklingStiffnessBiasLeft = [0.5]
            float[] primvars:clo:bucklingStiffnessBiasRight = [0.5]
            float[] primvars:clo:bucklingStiffnessWarp = [0.55]
            float[] primvars:clo:bucklingStiffnessWeft = [0.45]
            float[] primvars:clo:density = [$(Format-Number $fabricDensityKgPerSquareCm)]
            float[] primvars:clo:friction = [$(Format-Number $FabricDynamicFriction)]
            float[] primvars:clo:internalDamping = [$(Format-Number $internalDamping)]
            float[] primvars:clo:shearLeft = [$(Format-Number $shearStiffness)]
            float[] primvars:clo:shearRight = [$(Format-Number $shearStiffness)]
            float2[] primvars:clo:shrinkage = [(1, 1)]
            float[] primvars:clo:stretchWarp = [$(Format-Number $stretchWarpStiffness)]
            float[] primvars:clo:stretchWeft = [$(Format-Number $stretchWeftStiffness)]
            float[] primvars:clo:thickness = [$(Format-Number ($RenderThicknessCm * 10.0))]
"@
$fabricAttributes += [Environment]::NewLine

$usd = @"
#usda 1.0
(
    defaultPrim = "$GarmentId"
    metersPerUnit = 0.01
    upAxis = "Z"
)

def Scope "$GarmentId" (
    kind = "component"
    prepend apiSchemas = ["ClothRootAPI", "ClothSolverAPI:clo"]
)
{
    rel solver:clo:properties = </$GarmentId/CloSolverProperties>

    def Scope "CloSolverProperties" (
        prepend apiSchemas = ["CloSolverPropertiesAPI"]
    )
    {
        float airDamping = 0.12
        float3 gravity = (0, 0, -981)
        uint subStepCount = 4
        float timeStep = 0.016667
    }

    def Mesh "SimulationMesh" (
        prepend apiSchemas = ["SimMeshDataAPI"]
    )
    {
        uniform token purpose = "guide"
        float2 restPositionScale = ($(Format-Number $maximumPanelWidth), $(Format-Number $SkirtLengthCm))
        point3f[] points = [$(Format-Vector3List $simPoints)]
        int[] faceVertexCounts = [$(Format-IntegerList $simFaceCounts)]
        int[] faceVertexIndices = [$(Format-IntegerList $simFaceIndices)]
        texCoord2f[] primvars:st = [$(Format-Vector2List $simUvs)]
        uniform token primvars:st:interpolation = "vertex"

        def GeomSubset "FrontPanel" (
            prepend apiSchemas = ["SimPatternAPI"]
        )
        {
            uniform token elementType = "face"
            uniform token familyName = "pattern"
            int[] indices = [$(Format-IntegerList $frontFaces)]
$fabricAttributes        }

        def GeomSubset "BackPanel" (
            prepend apiSchemas = ["SimPatternAPI"]
        )
        {
            uniform token elementType = "face"
            uniform token familyName = "pattern"
            int[] indices = [$(Format-IntegerList $backFaces)]
$fabricAttributes        }

        def GeomSubset "LeftSideSeam" (
            prepend apiSchemas = ["SewingAPI"]
        )
        {
            uniform token elementType = "edge"
            uniform token familyName = "sewing"
            int[] indices = [$(Format-IntegerList $leftSideSeam)]
            rel patternA = </$GarmentId/SimulationMesh/FrontPanel>
            rel patternB = </$GarmentId/SimulationMesh/BackPanel>
        }

        def GeomSubset "RightSideSeam" (
            prepend apiSchemas = ["SewingAPI"]
        )
        {
            uniform token elementType = "edge"
            uniform token familyName = "sewing"
            int[] indices = [$(Format-IntegerList $rightSideSeam)]
            rel patternA = </$GarmentId/SimulationMesh/FrontPanel>
            rel patternB = </$GarmentId/SimulationMesh/BackPanel>
        }
    }

    def Mesh "RenderMeshFront" (
        prepend apiSchemas = ["MaterialBindingAPI"]
    )
    {
        bool doubleSided = 1
        point3f[] points = [$(Format-Vector3List $renderFrontPoints)]
        int[] faceVertexCounts = [$(Format-IntegerList $renderFrontFaceCounts)]
        int[] faceVertexIndices = [$(Format-IntegerList $renderFrontFaceIndices)]
        texCoord2f[] primvars:st = [$(Format-Vector2List $renderFrontUvs)]
        uniform token primvars:st:interpolation = "vertex"
        color3f[] primvars:displayColor = [$(Format-Vector3List $renderFrontColors)]
        uniform token primvars:displayColor:interpolation = "vertex"
        rel material:binding = </$GarmentId/Materials/PatternaFabric>

        def GeomSubset "FrontPanelRender" (
            prepend apiSchemas = ["RenderPatternAPI"]
        )
        {
            uniform token elementType = "face"
            uniform token familyName = "pattern"
            int[] indices = [$(Format-IntegerList $renderFrontPatternFaces)]
            rel simPattern = </$GarmentId/SimulationMesh/FrontPanel>
        }
    }

    def Mesh "RenderMeshBack" (
        prepend apiSchemas = ["MaterialBindingAPI"]
    )
    {
        bool doubleSided = 1
        point3f[] points = [$(Format-Vector3List $renderBackPoints)]
        int[] faceVertexCounts = [$(Format-IntegerList $renderBackFaceCounts)]
        int[] faceVertexIndices = [$(Format-IntegerList $renderBackFaceIndices)]
        texCoord2f[] primvars:st = [$(Format-Vector2List $renderBackUvs)]
        uniform token primvars:st:interpolation = "vertex"
        color3f[] primvars:displayColor = [$(Format-Vector3List $renderBackColors)]
        uniform token primvars:displayColor:interpolation = "vertex"
        rel material:binding = </$GarmentId/Materials/PatternaFabric>

        def GeomSubset "BackPanelRender" (
            prepend apiSchemas = ["RenderPatternAPI"]
        )
        {
            uniform token elementType = "face"
            uniform token familyName = "pattern"
            int[] indices = [$(Format-IntegerList $renderBackPatternFaces)]
            rel simPattern = </$GarmentId/SimulationMesh/BackPanel>
        }
    }

    def Scope "Materials"
    {
        def Material "PatternaFabric"
        {
            token outputs:surface.connect = </$GarmentId/Materials/PatternaFabric/Surface.outputs:surface>

            def Shader "Surface"
            {
                uniform token info:id = "UsdPreviewSurface"
                color3f inputs:diffuseColor = (0.19, 0.028, 0.075)
                float inputs:metallic = 0
                float inputs:roughness = 0.72
                float inputs:clearcoat = 0.05
                token outputs:surface
            }
        }
    }
}
"@

$manifest = [ordered]@{
    schemaVersion = 1
    garmentId = $GarmentId
    units = 'centimeters'
    generator = 'tools/Generate-PatternaUnrealGarment.ps1'
    bridgeInput = if ($null -ne $bridgeDocument) {
        [ordered]@{
            schemaVersion = [string]$bridgeDocument.schemaVersion
            sha256 = $bridgeDocumentSha256
        }
    } else {
        $null
    }
    bodyReference = [ordered]@{
        waistCircumference = $BodyWaistCircumferenceCm
        hipCircumference = $BodyHipCircumferenceCm
        waistHeight = $effectiveWaistHeightCm
        requestedWaistHeight = $requestedWaistHeightCm
        effectiveWaistHeight = $effectiveWaistHeightCm
        waistPlacementReason = $waistPlacementReason
        matchedWaistSectionCircumference = if ($null -ne $matchedWaistSection) {
            [double]$matchedWaistSection.ellipseCircumferenceCm
        } else {
            $null
        }
        liveProfile = if ($null -ne $bodyProfile) {
            [ordered]@{
                schemaVersion = [string]$bodyProfile.schemaVersion
                bodyAssetPath = [string]$bodyProfile.bodyAssetPath
                sha256 = $bodyProfileSha256
                surfaceSampling = $bodyProfileSurfaceSampling
                minimumSurfacePointCount = $bodyProfileMinimumSurfacePointCount
            }
        } else {
            $null
        }
    }
    garmentMeasurements = [ordered]@{
        waistEase = $WaistEaseCm
        hipEase = $HipEaseCm
        waistCircumference = $waistGarmentCircumferenceCm
        hipCircumference = $hipGarmentCircumferenceCm
        hemCircumference = $HemCircumferenceCm
        length = $SkirtLengthCm
        renderThickness = $RenderThicknessCm
    }
    renderConstruction = [ordered]@{
        technique = 'raised render-only ribbons bound to cloth simulation'
        ribbonCount = $constructionRibbonCount
        ribbonVertexCount = $constructionRibbonVertexCount
        ribbonTriangleCount = $constructionRibbonTriangleCount
        ribbonWidthCm = $constructionRibbonWidthCm
        surfaceOffsetCm = $constructionRibbonSurfaceOffsetCm
        features = @('front-left-side-seam', 'front-right-side-seam', 'front-waistband-seam', 'back-waistband-seam', 'front-hem-stitch', 'back-hem-stitch')
        affectsSimulation = $false
    }
    dressing = [ordered]@{
        requestedMaximumRadialClearance = $DressingClearanceCm
        waistRadialClearance = $waistDressingClearanceCm
        hipAndBelowRadialClearance = $hipDressingClearanceCm
        hemRadialClearance = $hemDressingClearanceCm
        waistDepthToWidthRatio = $waistDepthToWidthRatio
        hipAndHemDepthToWidthRatio = $hipAndHemDepthToWidthRatio
        bodySupportCollisionOffset = $bodySupportCollisionOffsetCm
        bodyConformedRowCount = $bodyConformedRowCount
        measuredBodySurfaceRowCount = $measuredBodySurfaceRowCount
        preservesTwoDimensionalRestMeasurements = $true
        balancedHem = [ordered]@{
            profile = 'Patterna editable skirt cubic hem'
            centerLengthCm = $SkirtLengthCm
            sideVerticalLengthCm = $SkirtLengthCm * ($patternHemSideY / $patternHemCenterY)
            centerHemY = $patternHemCenterY
            sideHemY = $patternHemSideY
            controlHemY = $patternHemControlY
        }
        coordinateAxes = [ordered]@{
            forwardDepth = 'Y'
            bodyWidth = 'X'
            vertical = 'Z'
        }
    }
    panels = @(
        [ordered]@{ id = 'FrontPanel'; columns = $PanelColumns; rows = $VerticalRows; faceCount = $frontFaces.Count },
        [ordered]@{ id = 'BackPanel'; columns = $PanelColumns; rows = $VerticalRows; faceCount = $backFaces.Count }
    )
    namedSeams = @(
        [ordered]@{ id = 'LeftSideSeam'; panelA = 'FrontPanel'; edgeA = 'left'; panelB = 'BackPanel'; edgeB = 'right'; stitchCount = $VerticalRows + 1 },
        [ordered]@{ id = 'RightSideSeam'; panelA = 'FrontPanel'; edgeA = 'right'; panelB = 'BackPanel'; edgeB = 'left'; stitchCount = $VerticalRows + 1 }
    )
    fabric = [ordered]@{
        source = [ordered]@{
            massGsm = $FabricMassGsm
            thicknessMm = $FabricThicknessMm
            warpStretchPercent = $FabricWarpStretchPercent
            weftStretchPercent = $FabricWeftStretchPercent
            biasStretchPercent = $FabricBiasStretchPercent
            bendResistance = $FabricBendResistance
            shearResistance = $FabricShearResistance
            staticFriction = $FabricStaticFriction
            dynamicFriction = $FabricDynamicFriction
        }
        chaos = [ordered]@{
            densityKgPerSquareCm = $fabricDensityKgPerSquareCm
            stretchWarp = $stretchWarpStiffness
            stretchWeft = $stretchWeftStiffness
            shearLeft = $shearStiffness
            shearRight = $shearStiffness
            bendWarp = $bendWarpStiffness
            bendWeft = $bendWeftStiffness
            bendBias = $bendBiasStiffness
            damping = $internalDamping
            friction = $FabricDynamicFriction
        }
    }
}

$verification = [ordered]@{
    schemaVersion = 1
    garmentId = $GarmentId
    simulationVertices = $simPoints.Count
    simulationTriangles = $simFaceCounts.Count
    renderVertices = $renderVertexCount
    renderTriangles = $renderTriangleCount
    renderMeshCount = 2
    renderPatternCount = 2
    constructionRibbonCount = $constructionRibbonCount
    constructionRibbonVertexCount = $constructionRibbonVertexCount
    constructionRibbonTriangleCount = $constructionRibbonTriangleCount
    constructionRibbonsAffectSimulation = $false
    panelCount = 2
    namedSeamCount = 2
    stitchesPerSeam = $VerticalRows + 1
    minimumDoubledTriangleArea = $minimumTriangleArea2
    minimumOutwardWindingDot = $minimumOutwardDot
    seamCoincidenceToleranceCm = 0.001
    separateSimulationAndRenderMeshes = $true
    independentRenderMeshPerPanel = $true
    waistDressingClearanceCm = $waistDressingClearanceCm
    hipAndBelowDressingClearanceCm = $hipDressingClearanceCm
    hemDressingClearanceCm = $hemDressingClearanceCm
    waistDepthToWidthRatio = $waistDepthToWidthRatio
    hipAndHemDepthToWidthRatio = $hipAndHemDepthToWidthRatio
    bodySupportCollisionOffsetCm = $bodySupportCollisionOffsetCm
    bodyConformedRowCount = $bodyConformedRowCount
    measuredBodySurfaceRowCount = $measuredBodySurfaceRowCount
    requestedWaistHeightCm = $requestedWaistHeightCm
    effectiveWaistHeightCm = $effectiveWaistHeightCm
    preservesTwoDimensionalRestMeasurements = $true
    balancedHem = $true
    centerPatternLengthCm = $SkirtLengthCm
    sidePatternVerticalLengthCm = $SkirtLengthCm * ($patternHemSideY / $patternHemCenterY)
    coordinateAxes = [ordered]@{
        forwardDepth = 'Y'
        bodyWidth = 'X'
        vertical = 'Z'
    }
    renderThicknessCm = $RenderThicknessCm
}

$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
$usdPath = Join-Path $resolvedOutputDirectory "$GarmentId.usda"
$manifestPath = Join-Path $resolvedOutputDirectory "$GarmentId.garment.json"
$verificationPath = Join-Path $resolvedOutputDirectory "$GarmentId.verification.json"

[System.IO.File]::WriteAllText($usdPath, $usd, $utf8WithoutBom)
[System.IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), $utf8WithoutBom)
[System.IO.File]::WriteAllText($verificationPath, ($verification | ConvertTo-Json -Depth 8), $utf8WithoutBom)

[pscustomobject]@{
    UsdPath = $usdPath
    ManifestPath = $manifestPath
    VerificationPath = $verificationPath
    SimulationVertices = $simPoints.Count
    SimulationTriangles = $simFaceCounts.Count
    RenderVertices = $renderVertexCount
    RenderTriangles = $renderTriangleCount
    RenderMeshes = 2
    NamedSeams = 2
}
