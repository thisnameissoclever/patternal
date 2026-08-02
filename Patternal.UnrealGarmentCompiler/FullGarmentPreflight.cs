using System.Security.Cryptography;
using System.Text;
using Patterna;

namespace Patterna.UnrealGarmentCompiler;

public sealed record LiveBodySurfacePointDocument(
    double AngleRadians,
    double RadiusCm,
    double XCm,
    double YCm);

public sealed record LiveBodySectionDocument(
    double HeightCm,
    double WidthCm,
    double DepthCm,
    double CenterXCm,
    double CenterYCm,
    double EllipseCircumferenceCm,
    int SampleCount,
    int SurfacePointCount,
    IReadOnlyList<LiveBodySurfacePointDocument> SurfacePoints);

public sealed record LiveBodyProfileDocument(
    string SchemaVersion,
    string BodyAssetPath,
    double SampleHalfBandCm,
    double LowerPercentile,
    double UpperPercentile,
    string SurfaceSampling,
    IReadOnlyList<LiveBodySectionDocument> Sections,
    double? LowestSampleHeightCm = null,
    double? HighestSampleHeightCm = null,
    double? SampleHeightStepCm = null);

public sealed record FullGarmentPreflightIssue(
    string Severity,
    string Code,
    string Message,
    string? SourceId = null);

public sealed record FullGarmentPanelReport(
    string Id,
    string PieceId,
    string Placement,
    int VertexCount,
    int TriangleCount,
    double WidthCm,
    double HeightCm,
    double AreaCm2,
    double MinimumTriangleAreaCm2,
    double MaximumTriangleAspectRatio,
    int SewingRelationshipCount,
    bool HasStructuredRemesh);

public sealed record FullGarmentSeamReport(
    string Id,
    string PanelA,
    string PanelB,
    double LengthACm,
    double LengthBCm,
    double LengthMismatchCm,
    double LengthMismatchRatio,
    int CorrespondenceCount,
    bool Accepted);

public sealed record FullGarmentClosureReport(
    string Id,
    string Kind,
    string State,
    string PanelA,
    string PanelB,
    int ConstraintCount,
    double TargetDistanceCm,
    double Strength,
    bool Accepted);

public sealed record FullGarmentBodyProfileReport(
    string SamplingMethod,
    int SectionCount,
    double MinimumHeightCm,
    double MaximumHeightCm,
    int MinimumIntersectionCount,
    int MinimumSurfacePointCount,
    double MaximumAdjacentCircumferenceChangeRatio,
    bool Accepted);

public sealed record FullGarmentArrangementSummary(
    int PanelCount,
    int StitchCount,
    int ClosureCount,
    int ClosureConstraintCount,
    double MinimumTriangleAreaCm2,
    double MaximumSeamGapCm,
    double MaximumClosureGapCm,
    double MaximumEdgeStrainRatio,
    double NinetyFifthPercentileEdgeStrainRatio,
    double MinimumTorsoClearanceCm,
    bool Accepted);

public sealed record FullGarmentPreflightReport(
    string SchemaVersion,
    string GarmentId,
    string BridgeSha256,
    string BodyProfileSha256,
    bool IsAccepted,
    IReadOnlyList<FullGarmentPreflightIssue> Issues,
    IReadOnlyList<FullGarmentPanelReport> Panels,
    IReadOnlyList<FullGarmentSeamReport> Seams,
    IReadOnlyList<FullGarmentClosureReport> Closures,
    FullGarmentBodyProfileReport BodyProfile,
    FullGarmentArrangementSummary Arrangement);

public static class FullGarmentPreflight
{
    private const double MaximumAcceptedSeamMismatchRatio = 0.15;
    private const double MaximumAcceptedStructuredAspectRatio = 12.0;
    private const double MaximumAcceptedBoundaryDeviationCm = 0.001;
    private const double MinimumAcceptedArrangedTriangleAreaCm2 = 0.001;
    private const double MaximumAcceptedInitialSeamGapCm = 90.0;
    private const double MaximumAcceptedInitialClosureGapCm = 130.0;
    private const double MaximumAcceptedInitialEdgeStrainRatio = 2.0;
    private const double MaximumAcceptedNinetyFifthPercentileStrainRatio = 0.25;
    private const double MaximumAcceptedValidatedPrefitBroadStrainRatio = 0.35;
    private const double MaximumAcceptedValidatedPrefitPeakStrainRatio = 0.50;
    private const double MinimumAcceptedTorsoClearanceCm = 0.25;
    private const int MaximumAcceptedPrefitBodyIntersections = 64;
    private const string ExactMetaHumanBody = "patterna_metahuman_female";
    private const double MaximumAcceptedExactBodyCollisionRate = 0.10;
    private const double MaximumAcceptedExactSelfCollisionRate = 0.003;
    private const double MaximumAcceptedAdjacentCircumferenceChangeRatio = 0.20;
    private const double MaximumTorsoContinuityHeightCm = 137.0;
    private static readonly HashSet<string> RequiredSamplingMethods =
    [
        "torso-skin-weight-filtered-triangle-plane-intersection-above-109cm",
        "segmented-triangle-plane-intersection"
    ];

    public static FullGarmentPreflightReport Run(
        PatternaUnrealBridgeDocument bridge,
        LiveBodyProfileDocument bodyProfile,
        string bridgeJson,
        string bodyProfileJson,
        PatternAwareMeshDocument? patternAwareMesh = null,
        GarmentPrefitMeshDocument? prefitMesh = null)
    {
        ArgumentNullException.ThrowIfNull(bridge);
        ArgumentNullException.ThrowIfNull(bodyProfile);

        List<FullGarmentPreflightIssue> issues = [];
        if (!string.Equals(bridge.SchemaVersion, "patterna.unreal-bridge/1.0", StringComparison.Ordinal))
        {
            issues.Add(Error("bridge-schema", $"Unsupported bridge schema {bridge.SchemaVersion}."));
        }

        if (!string.Equals(bodyProfile.SchemaVersion, "patterna.live-body-profile/1.0", StringComparison.Ordinal) &&
            !string.Equals(bodyProfile.SchemaVersion, "patterna.live-body-profile/1.1", StringComparison.Ordinal))
        {
            issues.Add(Error("body-profile-schema", $"Unsupported body profile schema {bodyProfile.SchemaVersion}."));
        }

        PatternTopologyCompilation topology;
        try
        {
            topology = PatternTopologyCompiler.Compile(
                bridge.Garment,
                new PatternTopologyCompilerOptions(
                    MaximumCurveSegmentLengthCm: 0.75,
                    MaximumSeamLengthMismatchRatio: MaximumAcceptedSeamMismatchRatio));
        }
        catch (PatternTopologyException exception)
        {
            foreach (string error in exception.Errors)
            {
                issues.Add(Error("topology-invalid", error));
            }

            return EmptyReport(bridge, bodyProfile, bridgeJson, bodyProfileJson, issues);
        }

        Dictionary<string, int> sewingRelationshipCounts = topology.Panels
            .ToDictionary(panel => panel.Id, _ => 0, StringComparer.OrdinalIgnoreCase);
        foreach (CompiledPatternSeam seam in topology.Seams)
        {
            sewingRelationshipCounts[seam.PanelA]++;
            sewingRelationshipCounts[seam.PanelB]++;
        }

        List<FullGarmentPanelReport> panelReports = [];
        foreach (CompiledPatternPanel panel in topology.Panels)
        {
            double minimumX = panel.Vertices.Min(vertex => vertex.X);
            double maximumX = panel.Vertices.Max(vertex => vertex.X);
            double minimumY = panel.Vertices.Min(vertex => vertex.Y);
            double maximumY = panel.Vertices.Max(vertex => vertex.Y);
            int sewingRelationshipCount = sewingRelationshipCounts[panel.Id];
            if (sewingRelationshipCount == 0)
            {
                issues.Add(Error(
                    "unsewn-panel",
                    $"Panel {panel.Id} has no sewing relationship and cannot be part of a closed garment.",
                    panel.Id));
            }

            StructuredPanelMesh? structuredMesh = null;
            try
            {
                structuredMesh = StructuredPanelRemesher.Remesh(panel, patternAwareMesh);
                string[] missingEdges = panel.Edges
                    .Where(edge => !structuredMesh.EdgeVertexIndices.ContainsKey(edge.Id))
                    .Select(edge => edge.Id)
                    .ToArray();
                if (missingEdges.Length > 0)
                {
                    issues.Add(Error(
                        "structured-remesh-edge-map",
                        $"Panel {panel.Id} structured mesh omits named edges: {string.Join(", ", missingEdges)}.",
                        panel.Id));
                }
                if (structuredMesh.MaximumTriangleAspectRatio > MaximumAcceptedStructuredAspectRatio)
                {
                    issues.Add(Error(
                        "structured-remesh-aspect-ratio",
                        $"Panel {panel.Id} structured triangle aspect ratio is {structuredMesh.MaximumTriangleAspectRatio:F2}; the limit is {MaximumAcceptedStructuredAspectRatio:F0}:1.",
                        panel.Id));
                }
                if (structuredMesh.MaximumBoundaryDeviationCm > MaximumAcceptedBoundaryDeviationCm)
                {
                    issues.Add(Error(
                        "structured-remesh-boundary-deviation",
                        $"Panel {panel.Id} structured boundary deviates by {structuredMesh.MaximumBoundaryDeviationCm:F4} cm; the limit is {MaximumAcceptedBoundaryDeviationCm:F3} cm.",
                        panel.Id));
                }
            }
            catch (InvalidOperationException exception)
            {
                issues.Add(Error(
                    "structured-remesh-invalid",
                    exception.Message,
                    panel.Id));
            }

            panelReports.Add(new FullGarmentPanelReport(
                panel.Id,
                panel.PieceId,
                panel.Placement,
                structuredMesh?.Vertices.Count ?? panel.Vertices.Count,
                structuredMesh?.Triangles.Count ?? panel.Triangles.Count,
                maximumX - minimumX,
                maximumY - minimumY,
                Math.Abs(panel.SignedAreaCm2),
                structuredMesh?.MinimumTriangleAreaCm2 ?? panel.Triangles.Min(triangle => triangle.AreaCm2),
                structuredMesh?.MaximumTriangleAspectRatio ?? panel.Triangles.Max(triangle => TriangleAspectRatio(panel, triangle)),
                sewingRelationshipCount,
                structuredMesh is not null));
        }

        List<FullGarmentSeamReport> seamReports = [];
        foreach (CompiledPatternSeam seam in topology.Seams)
        {
            bool accepted = seam.LengthMismatchRatio <= MaximumAcceptedSeamMismatchRatio;
            if (!accepted)
            {
                issues.Add(Error(
                    "seam-length-mismatch",
                    $"Seam {seam.Id} differs by {seam.LengthMismatchCm:F2} cm ({seam.LengthMismatchRatio:P1}); the full-garment limit is {MaximumAcceptedSeamMismatchRatio:P0}.",
                    seam.Id));
            }

            seamReports.Add(new FullGarmentSeamReport(
                seam.Id,
                seam.PanelA,
                seam.PanelB,
                seam.LengthACm,
                seam.LengthBCm,
                seam.LengthMismatchCm,
                seam.LengthMismatchRatio,
                seam.VertexPairs.Count,
                accepted));
        }

        List<FullGarmentClosureReport> closureReports = [];
        foreach (CompiledPatternClosure closure in topology.Closures)
        {
            bool accepted = closure.Constraints.Count > 0 &&
                closure.TargetDistanceCm <= 0.000001 &&
                closure.Strength is > 0 and <= 1;
            if (!accepted)
            {
                issues.Add(Error(
                    "closure-invalid",
                    $"Closure {closure.Id} cannot be represented by the current zero-distance fastener constraint path.",
                    closure.Id));
            }
            closureReports.Add(new FullGarmentClosureReport(
                closure.Id,
                closure.Kind,
                closure.State,
                closure.AnchorA.PanelId,
                closure.AnchorB.PanelId,
                closure.Constraints.Count,
                closure.TargetDistanceCm,
                closure.Strength,
                accepted));
        }
        if (string.Equals(bridge.Garment.Id, "wrap-dress", StringComparison.OrdinalIgnoreCase) &&
            closureReports.All(closure => !string.Equals(
                closure.State,
                GarmentClosureStates.Closed,
                StringComparison.OrdinalIgnoreCase)))
        {
            issues.Add(Error(
                "wrap-closure-missing",
                "The wrap dress has no active closure and cannot be validated in its worn state.",
                bridge.Garment.Id));
        }

        if (prefitMesh?.FabricThicknessCm is double solverThicknessCm)
        {
            double sourceThicknessCm = bridge.Garment.Fabric.ThicknessMillimeters / 10.0;
            if (Math.Abs(solverThicknessCm - sourceThicknessCm) > 0.0005)
            {
                issues.Add(Error(
                    "prefit-fabric-thickness-mismatch",
                    $"The garment solver used {solverThicknessCm * 10.0:F3} mm cloth, but the garment source specifies {bridge.Garment.Fabric.ThicknessMillimeters:F3} mm."));
            }
        }

        FullGarmentBodyProfileReport bodyReport = ValidateBodyProfile(bodyProfile, issues);
        FullGarmentArrangementSummary arrangementSummary = EmptyArrangementSummary();
        if (issues.All(issue => !string.Equals(issue.Severity, "error", StringComparison.Ordinal)))
        {
            try
            {
                FullGarmentArrangementReport arrangement = FullGarmentArrangement.Arrange(
                    topology,
                    bodyProfile,
                    patternAwareMesh,
                    prefitMesh);
                bool arrangementAccepted = true;
                bool hasValidatedPrefit = HasValidatedPrefit(prefitMesh);
                bool peakStrainGateEnabled = !string.Equals(
                    prefitMesh?.SolverReportSchemaVersion,
                    "patterna.newton-style3d-report/1.0",
                    StringComparison.Ordinal);
                double peakStrainLimit = hasValidatedPrefit
                    ? Math.Min(
                        prefitMesh!.SolverMaximumEdgeStrainLimit!.Value,
                        MaximumAcceptedValidatedPrefitPeakStrainRatio)
                    : MaximumAcceptedInitialEdgeStrainRatio;
                double broadStrainLimit = hasValidatedPrefit
                    ? Math.Min(
                        prefitMesh!.SolverNinetyFifthPercentileEdgeStrainLimit!.Value,
                        MaximumAcceptedValidatedPrefitBroadStrainRatio)
                    : MaximumAcceptedNinetyFifthPercentileStrainRatio;
                if (arrangement.MinimumTriangleAreaCm2 < MinimumAcceptedArrangedTriangleAreaCm2)
                {
                    arrangementAccepted = false;
                    issues.Add(Error(
                        "arrangement-degenerate-triangle",
                        $"Full-garment arrangement minimum triangle area is {arrangement.MinimumTriangleAreaCm2:F6} cm2; at least {MinimumAcceptedArrangedTriangleAreaCm2:F3} cm2 is required."));
                }
                if (arrangement.MaximumSeamGapCm > MaximumAcceptedInitialSeamGapCm)
                {
                    arrangementAccepted = false;
                    issues.Add(Error(
                        "arrangement-seam-gap",
                        $"Full-garment arrangement maximum seam gap is {arrangement.MaximumSeamGapCm:F4} cm; the limit is {MaximumAcceptedInitialSeamGapCm:F3} cm."));
                }
                if (arrangement.MaximumClosureGapCm > MaximumAcceptedInitialClosureGapCm)
                {
                    arrangementAccepted = false;
                    issues.Add(Error(
                        "arrangement-closure-gap",
                        $"Full-garment arrangement maximum closure gap is {arrangement.MaximumClosureGapCm:F4} cm; the limit is {MaximumAcceptedInitialClosureGapCm:F3} cm."));
                }
                if (peakStrainGateEnabled && arrangement.MaximumEdgeStrainRatio > peakStrainLimit)
                {
                    ArrangedPanelQualityReport worstPanel = arrangement.PanelQuality
                        .MaxBy(panel => panel.MaximumEdgeStrainRatio)!;
                    arrangementAccepted = false;
                    issues.Add(Error(
                        "arrangement-peak-strain",
                        $"Full-garment arrangement peak edge strain is {arrangement.MaximumEdgeStrainRatio:P1} on panel {worstPanel.PanelId}; the {(hasValidatedPrefit ? "recorded solver pre-fit" : "initial arrangement")} limit is {peakStrainLimit:P1}."));
                }
                if (arrangement.NinetyFifthPercentileEdgeStrainRatio > broadStrainLimit)
                {
                    ArrangedPanelQualityReport worstBroadStrainPanel = arrangement.PanelQuality
                        .MaxBy(panel => panel.NinetyFifthPercentileEdgeStrainRatio)!;
                    arrangementAccepted = false;
                    issues.Add(Error(
                        "arrangement-broad-strain",
                        $"Full-garment arrangement 95th-percentile edge strain is {arrangement.NinetyFifthPercentileEdgeStrainRatio:P1}; the worst panel is {worstBroadStrainPanel.PanelId} at {worstBroadStrainPanel.NinetyFifthPercentileEdgeStrainRatio:P1}, and the {(hasValidatedPrefit ? "recorded solver pre-fit" : "initial arrangement")} limit is {broadStrainLimit:P1}."));
                }
                if (arrangement.MinimumTorsoClearanceCm < MinimumAcceptedTorsoClearanceCm)
                {
                    if (hasValidatedPrefit)
                    {
                        if (prefitMesh!.BodyCollisionCount > 0 || prefitMesh.SelfCollisionCount > 0)
                        {
                            issues.Add(Warning(
                                "prefit-body-contact",
                                $"{prefitMesh.SolverName ?? "Garment solver"} reports {prefitMesh.BodyCollisionCount} residual body edge intersections ({prefitMesh.BodyCollisionRate:P2}) and {prefitMesh.SelfCollisionCount} self-intersections ({prefitMesh.SelfCollisionRate:P2}) on {prefitMesh.SolverBody}; analytical clearance against the preview profile is {arrangement.MinimumTorsoClearanceCm:F3} cm.",
                                prefitMesh.SolverReportPath));
                        }
                    }
                    else
                    {
                        arrangementAccepted = false;
                        issues.Add(Error(
                            "arrangement-body-clearance",
                            $"Full-garment arrangement minimum measured torso clearance is {arrangement.MinimumTorsoClearanceCm:F3} cm; at least {MinimumAcceptedTorsoClearanceCm:F2} cm is required."));
                    }
                }
                arrangementSummary = new FullGarmentArrangementSummary(
                    arrangement.Panels.Count,
                    arrangement.Stitches.Count,
                    arrangement.Closures.Select(closure => closure.ClosureId).Distinct(StringComparer.OrdinalIgnoreCase).Count(),
                    arrangement.Closures.Count,
                    arrangement.MinimumTriangleAreaCm2,
                    arrangement.MaximumSeamGapCm,
                    arrangement.MaximumClosureGapCm,
                    arrangement.MaximumEdgeStrainRatio,
                    arrangement.NinetyFifthPercentileEdgeStrainRatio,
                    arrangement.MinimumTorsoClearanceCm,
                    arrangementAccepted);
            }
            catch (InvalidOperationException exception)
            {
                issues.Add(Error("arrangement-invalid", exception.Message));
            }
        }
        if (prefitMesh is null)
        {
            issues.Add(Warning(
                "upper-neck-collision-fallback",
                "The sectional placement profile ends near 139 cm; neckline collision requires the complete body surface in the downstream cloth solver.",
                bodyProfile.BodyAssetPath));
        }

        bool isAccepted = issues.All(issue => !string.Equals(issue.Severity, "error", StringComparison.Ordinal));
        return new FullGarmentPreflightReport(
            "patterna.full-garment-preflight/1.1",
            bridge.Garment.Id,
            Sha256(bridgeJson),
            Sha256(bodyProfileJson),
            isAccepted,
            issues,
            panelReports,
            seamReports,
            closureReports,
            bodyReport,
            arrangementSummary);
    }

    private static FullGarmentBodyProfileReport ValidateBodyProfile(
        LiveBodyProfileDocument profile,
        ICollection<FullGarmentPreflightIssue> issues)
    {
        LiveBodySectionDocument[] sections = profile.Sections
            .OrderBy(section => section.HeightCm)
            .ToArray();
        if (sections.Length == 0)
        {
            issues.Add(Error("body-profile-empty", "The live body profile has no surface sections."));
            return new FullGarmentBodyProfileReport(
                profile.SurfaceSampling,
                0,
                0,
                0,
                0,
                0,
                0,
                false);
        }

        double minimumHeight = sections[0].HeightCm;
        double maximumHeight = sections[^1].HeightCm;
        int minimumIntersectionCount = sections.Min(section => section.SampleCount);
        int minimumSurfacePointCount = sections.Min(section => section.SurfacePointCount);
        double maximumAdjacentChange = 0;
        for (int index = 1; index < sections.Length; index++)
        {
            // The uppermost section is the neck-root transition, not a torso
            // placement circuit. Preserve it for neckline placement and exact
            // downstream collision, but do not reject a real shoulder-to-neck
            // narrowing as a discontinuous torso surface.
            if (sections[index].HeightCm > MaximumTorsoContinuityHeightCm)
            {
                continue;
            }
            double previous = sections[index - 1].EllipseCircumferenceCm;
            double current = sections[index].EllipseCircumferenceCm;
            maximumAdjacentChange = Math.Max(
                maximumAdjacentChange,
                Math.Abs(current - previous) / Math.Max(current, previous));
        }

        if (!RequiredSamplingMethods.Contains(profile.SurfaceSampling))
        {
            issues.Add(Error(
                "body-profile-sampling",
                $"Full-garment placement requires a segmented triangle-plane profile; received {profile.SurfaceSampling}."));
        }
        if (sections.Length < 23 || minimumHeight > 95.0 || maximumHeight < 139.0)
        {
            issues.Add(Error(
                "body-profile-coverage",
                $"Body profile coverage is {minimumHeight:F1} to {maximumHeight:F1} cm across {sections.Length} sections; at least 95 to 139 cm across 23 sections is required."));
        }
        if (minimumIntersectionCount < 64)
        {
            issues.Add(Error(
                "body-profile-density",
                $"The sparsest section has only {minimumIntersectionCount} triangle-plane intersections; 64 are required."));
        }
        if (minimumSurfacePointCount < 24)
        {
            issues.Add(Error(
                "body-profile-angular-coverage",
                $"The sparsest section covers only {minimumSurfacePointCount} angular sectors; 24 are required."));
        }
        if (maximumAdjacentChange > MaximumAcceptedAdjacentCircumferenceChangeRatio)
        {
            issues.Add(Error(
                "body-profile-discontinuity",
                $"Adjacent torso sections through {MaximumTorsoContinuityHeightCm:F0} cm change circumference by as much as {maximumAdjacentChange:P1}; the limit is {MaximumAcceptedAdjacentCircumferenceChangeRatio:P0}."));
        }

        bool accepted = issues.All(issue =>
            !string.Equals(issue.Severity, "error", StringComparison.Ordinal) ||
            !issue.Code.StartsWith("body-profile-", StringComparison.Ordinal));
        return new FullGarmentBodyProfileReport(
            profile.SurfaceSampling,
            sections.Length,
            minimumHeight,
            maximumHeight,
            minimumIntersectionCount,
            minimumSurfacePointCount,
            maximumAdjacentChange,
            accepted);
    }

    private static bool HasValidatedPrefit(GarmentPrefitMeshDocument? prefitMesh)
    {
        if (prefitMesh is not
            {
                SolverAccepted: true,
                SolverFinitePositions: true,
                SolverEquilibriumGateEvaluated: true,
                SolverStaticEquilibriumReached: true,
                SolverCollisionGateEvaluated: true,
                SolverSeamClosureGateEvaluated: true,
                FabricThicknessCm: > 0 and <= 0.10,
                FabricDensity: > 0,
                FabricFriction: >= 0,
                FabricEdgeBendingStiffness: >= 0,
                SolverMaximumBodyCollisions: >= 0,
                SolverMaximumSelfCollisions: >= 0,
                SolverSeamLinkCount: > 0,
                SolverMaximumSeamSeparationCm: >= 0,
                SolverMeanSeamSeparationCm: >= 0,
                SolverNinetyFifthPercentileSeamSeparationCm: >= 0,
                SolverMaximumSeamSeparationLimitCm: > 0,
                SolverEvaluatedEdgeCount: > 0,
                SolverMaximumEdgeStrainRatio: >= 0,
                SolverNinetyFifthPercentileEdgeStrainRatio: >= 0,
                SolverNinetyNinthPointNinthPercentileEdgeStrainRatio: >= 0,
                SolverMaximumEdgeStrainLimit: >= 0,
                SolverNinetyFifthPercentileEdgeStrainLimit: >= 0,
                SolverNinetyNinthPointNinthPercentileEdgeStrainLimit: >= 0,
                SolverSimulationSubsteps: >= 10,
                SolverPhysicalIdentityVerified: true,
                BodyCollisionCount: >= 0,
                SelfCollisionCount: >= 0
            } ||
            prefitMesh.BodyCollisionCount > prefitMesh.SolverMaximumBodyCollisions ||
            prefitMesh.SelfCollisionCount > prefitMesh.SolverMaximumSelfCollisions ||
            prefitMesh.SolverMaximumSeamSeparationCm >
                prefitMesh.SolverMaximumSeamSeparationLimitCm ||
            prefitMesh.SolverNinetyFifthPercentileEdgeStrainRatio >
                prefitMesh.SolverNinetyFifthPercentileEdgeStrainLimit ||
            prefitMesh.SolverNinetyNinthPointNinthPercentileEdgeStrainRatio >
                prefitMesh.SolverNinetyNinthPointNinthPercentileEdgeStrainLimit)
        {
            return false;
        }

        bool isWarpSchema = string.Equals(
            prefitMesh.SolverReportSchemaVersion,
            "patterna.warp-prefit-report/2.6",
            StringComparison.Ordinal);
        bool isStyle3DSchema = string.Equals(
            prefitMesh.SolverReportSchemaVersion,
            "patterna.newton-style3d-report/1.0",
            StringComparison.Ordinal);
        if (!isWarpSchema && !isStyle3DSchema)
        {
            return false;
        }
        if (prefitMesh.SolverMaterialRestLengthEdgeCount is not > 0 ||
            prefitMesh.SolverReferenceGeometryEdgeCount is not >= 0 ||
            prefitMesh.SolverExcludedEdgeCount is not 0 ||
            prefitMesh.SolverEvaluatedEdgeCount !=
                prefitMesh.SolverMaterialRestLengthEdgeCount +
                prefitMesh.SolverReferenceGeometryEdgeCount)
        {
            return false;
        }

        if (isStyle3DSchema)
        {
            return string.Equals(
                    prefitMesh.SolverName,
                    "newton.solvers.SolverStyle3D",
                    StringComparison.Ordinal) &&
                prefitMesh.SolverNinetyNinthPointNinetyNinthPercentileEdgeStrainRatio is >= 0 &&
                prefitMesh.SolverNinetyNinthPointNinetyNinthPercentileEdgeStrainLimit is > 0 &&
                prefitMesh.SolverNinetyNinthPointNinetyNinthPercentileEdgeStrainRatio <=
                    prefitMesh.SolverNinetyNinthPointNinetyNinthPercentileEdgeStrainLimit &&
                prefitMesh.SolverHighStrainEdgeCount is >= 0 &&
                prefitMesh.SolverHighStrainEdgeFraction is >= 0 &&
                prefitMesh.SolverMaximumHighStrainEdgeFraction is > 0 &&
                prefitMesh.SolverHighStrainEdgeFraction <=
                    prefitMesh.SolverMaximumHighStrainEdgeFraction &&
                prefitMesh.BodyCollisionCount is 0 &&
                prefitMesh.SelfCollisionCount is 0;
        }

        if (prefitMesh.SolverConfigSha256 is not { Length: 64 } ||
            prefitMesh.SolverEdgeContactBufferSaturated is not false ||
            prefitMesh.SolverMaximumObservedEdgeContacts is not >= 0 ||
            prefitMesh.SolverEdgeContactCapacity is not > 0 ||
            prefitMesh.SolverEdgeContactsPerSpring is not > 0 ||
            prefitMesh.SolverMaximumObservedEdgeContacts >= prefitMesh.SolverEdgeContactCapacity ||
            prefitMesh.SolverMaximumEdgeStrainRatio > prefitMesh.SolverMaximumEdgeStrainLimit)
        {
            return false;
        }

        if (string.Equals(prefitMesh.SolverBody, ExactMetaHumanBody, StringComparison.Ordinal))
        {
            return prefitMesh.ClothVertexCount is > 0 &&
                prefitMesh.BodyFaceCount is > 0 &&
                prefitMesh.BodyCollisionRate is >= 0 and <= MaximumAcceptedExactBodyCollisionRate &&
                prefitMesh.SelfCollisionRate is >= 0 and <= MaximumAcceptedExactSelfCollisionRate;
        }

        return prefitMesh.BodyCollisionCount is <= MaximumAcceptedPrefitBodyIntersections &&
            prefitMesh.SelfCollisionCount is 0;
    }

    private static double TriangleAspectRatio(
        CompiledPatternPanel panel,
        CompiledPatternTriangle triangle)
    {
        CompiledPatternVertex a = panel.Vertices[triangle.A];
        CompiledPatternVertex b = panel.Vertices[triangle.B];
        CompiledPatternVertex c = panel.Vertices[triangle.C];
        double ab = Distance(a, b);
        double bc = Distance(b, c);
        double ca = Distance(c, a);
        double longest = Math.Max(ab, Math.Max(bc, ca));
        double shortestAltitude = 2.0 * triangle.AreaCm2 / Math.Max(longest, double.Epsilon);
        return longest / Math.Max(shortestAltitude, double.Epsilon);
    }

    private static double Distance(CompiledPatternVertex first, CompiledPatternVertex second)
        => Math.Sqrt(Math.Pow(second.X - first.X, 2) + Math.Pow(second.Y - first.Y, 2));

    private static FullGarmentPreflightReport EmptyReport(
        PatternaUnrealBridgeDocument bridge,
        LiveBodyProfileDocument bodyProfile,
        string bridgeJson,
        string bodyProfileJson,
        IReadOnlyList<FullGarmentPreflightIssue> issues)
        => new(
            "patterna.full-garment-preflight/1.1",
            bridge.Garment.Id,
            Sha256(bridgeJson),
            Sha256(bodyProfileJson),
            false,
            issues,
            [],
            [],
            [],
            new FullGarmentBodyProfileReport(
                bodyProfile.SurfaceSampling,
                bodyProfile.Sections.Count,
                bodyProfile.Sections.Count == 0 ? 0 : bodyProfile.Sections.Min(section => section.HeightCm),
                bodyProfile.Sections.Count == 0 ? 0 : bodyProfile.Sections.Max(section => section.HeightCm),
                bodyProfile.Sections.Count == 0 ? 0 : bodyProfile.Sections.Min(section => section.SampleCount),
                bodyProfile.Sections.Count == 0 ? 0 : bodyProfile.Sections.Min(section => section.SurfacePointCount),
                double.PositiveInfinity,
                false),
            EmptyArrangementSummary());

    private static FullGarmentArrangementSummary EmptyArrangementSummary()
        => new(
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            false);

    private static string Sha256(string source)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(source))).ToLowerInvariant();

    private static FullGarmentPreflightIssue Error(string code, string message, string? sourceId = null)
        => new("error", code, message, sourceId);

    private static FullGarmentPreflightIssue Warning(string code, string message, string? sourceId = null)
        => new("warning", code, message, sourceId);
}
