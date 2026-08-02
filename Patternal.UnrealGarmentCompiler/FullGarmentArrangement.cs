using Patterna;

namespace Patterna.UnrealGarmentCompiler;

public readonly record struct ArrangedPoint3(double X, double Y, double Z)
{
    public static ArrangedPoint3 operator +(ArrangedPoint3 first, ArrangedPoint3 second)
        => new(first.X + second.X, first.Y + second.Y, first.Z + second.Z);

    public static ArrangedPoint3 operator -(ArrangedPoint3 first, ArrangedPoint3 second)
        => new(first.X - second.X, first.Y - second.Y, first.Z - second.Z);

    public static ArrangedPoint3 operator *(ArrangedPoint3 point, double scale)
        => new(point.X * scale, point.Y * scale, point.Z * scale);

    public static ArrangedPoint3 operator /(ArrangedPoint3 point, double divisor)
        => new(point.X / divisor, point.Y / divisor, point.Z / divisor);
}

public sealed record ArrangedPanelVertex(
    int Index,
    double RestX,
    double RestY,
    double U,
    double V,
    double X,
    double Y,
    double Z);

public sealed record ArrangedPanelMesh(
    string PanelId,
    string PieceId,
    string Placement,
    bool ReverseWinding,
    int Columns,
    int Rows,
    IReadOnlyList<ArrangedPanelVertex> Vertices,
    IReadOnlyList<StructuredPanelTriangle> Triangles,
    IReadOnlyDictionary<string, IReadOnlyList<int>> EdgeVertexIndices);

public sealed record ArrangedSeamStitch(
    string SeamId,
    string PanelA,
    int VertexA,
    string PanelB,
    int VertexB,
    double NormalizedPosition,
    double GapCm);

public sealed record ArrangedClosureConstraint(
    string ClosureId,
    string Kind,
    string PanelA,
    int VertexA,
    string PanelB,
    int VertexB,
    double NormalizedPosition,
    double TargetDistanceCm,
    double Strength,
    double InitialGapCm);

public sealed record ArrangedPanelQualityReport(
    string PanelId,
    double MinimumTriangleAreaCm2,
    double MaximumEdgeStrainRatio,
    double NinetyFifthPercentileEdgeStrainRatio);

public sealed record ArrangedSeamDirectionReport(
    string SeamId,
    bool WasAutoReversed,
    double SelectedEndpointGapCm,
    double OppositeEndpointGapCm);

public sealed record FullGarmentArrangementReport(
    string SchemaVersion,
    IReadOnlyList<ArrangedPanelMesh> Panels,
    IReadOnlyList<ArrangedSeamStitch> Stitches,
    IReadOnlyList<ArrangedClosureConstraint> Closures,
    IReadOnlyList<ArrangedSeamDirectionReport> SeamDirections,
    IReadOnlyList<ArrangedPanelQualityReport> PanelQuality,
    double MinimumTriangleAreaCm2,
    double MaximumSeamGapCm,
    double MaximumClosureGapCm,
    double MaximumEdgeStrainRatio,
    double NinetyFifthPercentileEdgeStrainRatio,
    double MinimumTorsoClearanceCm);

public static class FullGarmentArrangement
{
    private const double TorsoClearanceCm = 1.20;
    private const double SkirtClearanceCm = 1.35;
    private const double WaistHeightCm = 107.0;
    private const double ShoulderHeightCm = 149.0;
    private const double ShoulderBreadthCm = 39.0;

    private sealed record SurfaceSample(double CenterX, double CenterY, double Radius);
    private sealed record SurfacePointSample(double CenterX, double CenterY, double X, double Y);
    private sealed record EllipseArcMap(
        IReadOnlyList<double> Distances,
        IReadOnlyList<StructuredPoint2> Points);

    private sealed class DisjointSet
    {
        private readonly int[] parent;
        private readonly byte[] rank;

        public DisjointSet(int count)
        {
            parent = Enumerable.Range(0, count).ToArray();
            rank = new byte[count];
        }

        public int Find(int item)
        {
            if (parent[item] != item)
            {
                parent[item] = Find(parent[item]);
            }
            return parent[item];
        }

        public void Union(int first, int second)
        {
            int rootA = Find(first);
            int rootB = Find(second);
            if (rootA == rootB)
            {
                return;
            }

            if (rank[rootA] < rank[rootB])
            {
                parent[rootA] = rootB;
            }
            else if (rank[rootA] > rank[rootB])
            {
                parent[rootB] = rootA;
            }
            else
            {
                parent[rootB] = rootA;
                rank[rootA]++;
            }
        }
    }

    public static FullGarmentArrangementReport Arrange(
        PatternTopologyCompilation topology,
        LiveBodyProfileDocument bodyProfile,
        PatternAwareMeshDocument? patternAwareMesh = null,
        GarmentPrefitMeshDocument? prefitMesh = null,
        bool prepareSewnSimulationShell = false)
    {
        ArgumentNullException.ThrowIfNull(topology);
        ArgumentNullException.ThrowIfNull(bodyProfile);
        if (bodyProfile.Sections.Count == 0)
        {
            throw new InvalidOperationException("Full-garment arrangement requires a nonempty body profile.");
        }

        Dictionary<string, CompiledPatternPanel> compiledPanels = topology.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        StructuredPanelMesh[] structuredMeshes = topology.Panels
            .Select(panel => StructuredPanelRemesher.Remesh(panel, patternAwareMesh))
            .ToArray();
        Dictionary<string, StructuredPanelMesh> structuredByPanel = structuredMeshes
            .ToDictionary(panel => panel.PanelId, StringComparer.OrdinalIgnoreCase);

        Dictionary<string, int> panelOffsets = new(StringComparer.OrdinalIgnoreCase);
        int totalVertexCount = 0;
        foreach (StructuredPanelMesh mesh in structuredMeshes)
        {
            panelOffsets[mesh.PanelId] = totalVertexCount;
            totalVertexCount += mesh.Vertices.Count;
        }

        string[] placementByGlobalVertex = new string[totalVertexCount];

        if (prefitMesh is not null && patternAwareMesh is null)
        {
            throw new InvalidOperationException("A pre-fit mesh requires its pattern-aware mesh sidecar.");
        }

        ArrangedPoint3[] points = new ArrangedPoint3[totalVertexCount];
        foreach (StructuredPanelMesh mesh in structuredMeshes)
        {
            CompiledPatternPanel panel = compiledPanels[mesh.PanelId];
            ArrangedPoint3[] panelPoints = prefitMesh is null
                ? ArrangePanel(mesh, panel, bodyProfile)
                : RequirePrefitPanel(prefitMesh, mesh);
            int offset = panelOffsets[mesh.PanelId];
            Array.Copy(panelPoints, 0, points, offset, panelPoints.Length);
            Array.Fill(placementByGlobalVertex, panel.Placement, offset, panelPoints.Length);
        }
        bool hasCompleteSourcePlacement = compiledPanels.Values.All(panel =>
            panel.SourcePlacement is not null);
        bool isImportedUpperBodyGarment = hasCompleteSourcePlacement &&
            compiledPanels.Values.Any(panel => panel.Placement.StartsWith(
                "torso",
                StringComparison.OrdinalIgnoreCase)) &&
            !compiledPanels.Values.Any(panel => panel.Placement.StartsWith(
                "skirt",
                StringComparison.OrdinalIgnoreCase));
        if (prefitMesh is null && isImportedUpperBodyGarment)
        {
            AlignImportedUpperGarmentToShoulderLandmark(
                points,
                structuredMeshes,
                compiledPanels,
                panelOffsets);
        }
        if (prefitMesh is not null)
        {
            // GarmentCode Warp already assembled seams and resolved body collisions.
        }
        else
        {
            WrapImportedBodyPanelsForSewing(
                structuredMeshes,
                compiledPanels,
                panelOffsets,
                bodyProfile,
                points);
            BendPanelsForSewing(
                structuredMeshes,
                compiledPanels,
                panelOffsets,
                bodyProfile,
                points);
            FoldImportedSleevePanelsForSewing(
                structuredMeshes,
                compiledPanels,
                panelOffsets,
                bodyProfile,
                points);
            AlignSleeveCapsToArmholes(
                topology,
                structuredByPanel,
                compiledPanels,
                panelOffsets,
                points);
        }

        List<(CompiledPatternSeam Seam, int LocalA, int LocalB, double Normalized)> stitchDefinitions = [];
        List<ArrangedSeamDirectionReport> seamDirections = [];
        foreach (CompiledPatternSeam seam in topology.Seams)
        {
            StructuredPanelMesh panelA = structuredByPanel[seam.PanelA];
            StructuredPanelMesh panelB = structuredByPanel[seam.PanelB];
            int[] chainA = BuildSeamChain(panelA, seam.EdgeIdsA, seam.ReverseA);
            int[] chainB = BuildSeamChain(panelB, seam.EdgeIdsB, seam.ReverseB);
            int pairCount = Math.Min(chainA.Length, chainB.Length);
            if (pairCount < 2)
            {
                throw new InvalidOperationException($"Seam {seam.Id} has fewer than two unique structured stitches.");
            }

            double selectedEndpointGap = EndpointPairGap(
                seam,
                chainA,
                chainB,
                panelOffsets,
                points);
            int[] oppositeChainB = chainB.Reverse().ToArray();
            double oppositeEndpointGap = EndpointPairGap(
                seam,
                chainA,
                oppositeChainB,
                panelOffsets,
                points);
            bool hasAuthoredConstructionDirection = patternAwareMesh is not null || seam.Id.Contains(
                "patterna-",
                StringComparison.OrdinalIgnoreCase);
            bool wasAutoReversed = !hasAuthoredConstructionDirection &&
                oppositeEndpointGap + 0.01 < selectedEndpointGap;
            if (wasAutoReversed)
            {
                chainB = oppositeChainB;
                (selectedEndpointGap, oppositeEndpointGap) =
                    (oppositeEndpointGap, selectedEndpointGap);
            }
            seamDirections.Add(new ArrangedSeamDirectionReport(
                seam.Id,
                wasAutoReversed,
                selectedEndpointGap,
                oppositeEndpointGap));

            for (int pairIndex = 0; pairIndex < pairCount; pairIndex++)
            {
                double normalized = pairIndex / (double)(pairCount - 1);
                int localA = chainA[(int)Math.Round(normalized * (chainA.Length - 1))];
                int localB = chainB[(int)Math.Round(normalized * (chainB.Length - 1))];
                stitchDefinitions.Add((seam, localA, localB, normalized));
            }
        }

        if (prefitMesh is null && !prepareSewnSimulationShell)
        {
            AlignPanelsToConstructionFrames(
                structuredMeshes,
                panelOffsets,
                stitchDefinitions,
                points);
            if (hasCompleteSourcePlacement)
            {
                List<(CompiledPatternSeam Seam, int LocalA, int LocalB, double Normalized)> assemblyStitches =
                    patternAwareMesh is null
                        ? stitchDefinitions.Where(IsSafeInitialAssemblyConstraint).ToList()
                        : stitchDefinitions;
                DisjointSet seamGroups = new(totalVertexCount);
                foreach ((CompiledPatternSeam seam, int localA, int localB, _) in assemblyStitches)
                {
                    seamGroups.Union(
                        panelOffsets[seam.PanelA] + localA,
                        panelOffsets[seam.PanelB] + localB);
                }
                RelaxEdgeStrainBeforeSimulation(
                    points,
                    structuredMeshes,
                    panelOffsets,
                    assemblyStitches,
                    placementByGlobalVertex,
                    seamGroups,
                    bodyProfile);
                AlignImportedGarmentToWaistLandmark(
                    points,
                    structuredMeshes,
                    compiledPanels,
                    panelOffsets);
                ProjectAllTorsoVerticesOutsideBody(
                    points,
                    placementByGlobalVertex,
                    bodyProfile);
                ProjectSewnTorsoGroupsOutsideBody(
                    points,
                    placementByGlobalVertex,
                    seamGroups,
                    bodyProfile);
            }
            BendTiePanelsTowardFrontClosure(
                structuredMeshes,
                compiledPanels,
                panelOffsets,
                bodyProfile,
                points);
        }

        List<ArrangedPanelMesh> arrangedPanels = [];
        foreach (StructuredPanelMesh mesh in structuredMeshes)
        {
            int offset = panelOffsets[mesh.PanelId];
            CompiledPatternPanel compiled = compiledPanels[mesh.PanelId];
            ArrangedPanelVertex[] vertices = mesh.Vertices
                .Select(vertex =>
                {
                    ArrangedPoint3 point = points[offset + vertex.Index];
                    return new ArrangedPanelVertex(
                        vertex.Index,
                        vertex.X,
                        vertex.Y,
                        vertex.U,
                        vertex.V,
                        point.X,
                        point.Y,
                        point.Z);
                })
                .ToArray();
            arrangedPanels.Add(new ArrangedPanelMesh(
                mesh.PanelId,
                mesh.PieceId,
                compiled.Placement,
                compiled.ReverseWinding,
                mesh.Columns,
                mesh.Rows,
                vertices,
                mesh.Triangles,
                mesh.EdgeVertexIndices));
        }

        List<ArrangedSeamStitch> stitches = [];
        Dictionary<string, HashSet<int>> sewnVerticesByPanel = new(StringComparer.OrdinalIgnoreCase);
        foreach ((CompiledPatternSeam seam, int localA, int localB, double normalized) in stitchDefinitions)
        {
            ArrangedPoint3 pointA = points[panelOffsets[seam.PanelA] + localA];
            ArrangedPoint3 pointB = points[panelOffsets[seam.PanelB] + localB];
            stitches.Add(new ArrangedSeamStitch(
                seam.Id,
                seam.PanelA,
                localA,
                seam.PanelB,
                localB,
                normalized,
                Distance(pointA, pointB)));
            sewnVerticesByPanel.TryAdd(seam.PanelA, []);
            sewnVerticesByPanel.TryAdd(seam.PanelB, []);
            sewnVerticesByPanel[seam.PanelA].Add(localA);
            sewnVerticesByPanel[seam.PanelB].Add(localB);
        }

        List<ArrangedClosureConstraint> closures = [];
        foreach (CompiledPatternClosure closure in topology.Closures.Where(closure =>
            string.Equals(closure.State, GarmentClosureStates.Closed, StringComparison.OrdinalIgnoreCase)))
        {
            StructuredPanelMesh panelA = structuredByPanel[closure.AnchorA.PanelId];
            StructuredPanelMesh panelB = structuredByPanel[closure.AnchorB.PanelId];
            int[] chainA = BuildSeamChain(panelA, closure.AnchorA.EdgeIds, closure.AnchorA.Reverse);
            int[] chainB = BuildSeamChain(panelB, closure.AnchorB.EdgeIds, closure.AnchorB.Reverse);
            for (int index = 0; index < closure.Constraints.Count; index++)
            {
                CompiledClosureConstraint sourceConstraint = closure.Constraints[index];
                double normalized = sourceConstraint.NormalizedPosition;
                double positionA = Lerp(
                    closure.AnchorA.StartPosition,
                    closure.AnchorA.EndPosition,
                    normalized);
                double positionB = Lerp(
                    closure.AnchorB.StartPosition,
                    closure.AnchorB.EndPosition,
                    normalized);
                int localA = chainA[(int)Math.Round(positionA * (chainA.Length - 1))];
                int localB = chainB[(int)Math.Round(positionB * (chainB.Length - 1))];
                ArrangedPoint3 pointA = points[panelOffsets[panelA.PanelId] + localA];
                ArrangedPoint3 pointB = points[panelOffsets[panelB.PanelId] + localB];
                closures.Add(new ArrangedClosureConstraint(
                    closure.Id,
                    closure.Kind,
                    panelA.PanelId,
                    localA,
                    panelB.PanelId,
                    localB,
                    normalized,
                    closure.TargetDistanceCm,
                    closure.Strength,
                    Distance(pointA, pointB)));
            }
        }

        double minimumTriangleArea = double.PositiveInfinity;
        List<double> edgeStrains = [];
        HashSet<(string PanelId, int A, int B)> visitedEdges = [];
        List<ArrangedPanelQualityReport> panelQuality = [];
        foreach (ArrangedPanelMesh panel in arrangedPanels)
        {
            double panelMinimumTriangleArea = double.PositiveInfinity;
            List<double> panelEdgeStrains = [];
            ISet<int>? excludedVertices = prefitMesh is not null &&
                sewnVerticesByPanel.TryGetValue(panel.PanelId, out HashSet<int>? sewnVertices)
                ? sewnVertices
                : null;
            foreach (StructuredPanelTriangle triangle in panel.Triangles)
            {
                ArrangedPoint3 a = ToPoint(panel.Vertices[triangle.A]);
                ArrangedPoint3 b = ToPoint(panel.Vertices[triangle.B]);
                ArrangedPoint3 c = ToPoint(panel.Vertices[triangle.C]);
                double area = TriangleArea(a, b, c);
                minimumTriangleArea = Math.Min(minimumTriangleArea, area);
                panelMinimumTriangleArea = Math.Min(panelMinimumTriangleArea, area);
                AddEdgeStrain(panel, triangle.A, triangle.B, visitedEdges, edgeStrains, panelEdgeStrains, excludedVertices);
                AddEdgeStrain(panel, triangle.B, triangle.C, visitedEdges, edgeStrains, panelEdgeStrains, excludedVertices);
                AddEdgeStrain(panel, triangle.C, triangle.A, visitedEdges, edgeStrains, panelEdgeStrains, excludedVertices);
            }
            panelEdgeStrains.Sort();
            panelQuality.Add(new ArrangedPanelQualityReport(
                panel.PanelId,
                panelMinimumTriangleArea,
                panelEdgeStrains.Max(),
                Percentile(panelEdgeStrains, 0.95)));
        }

        edgeStrains.Sort();
        double minimumTorsoClearance = MeasureMinimumTorsoClearance(arrangedPanels, bodyProfile);
        return new FullGarmentArrangementReport(
            "patterna.full-garment-arrangement/1.1",
            arrangedPanels,
            stitches,
            closures,
            seamDirections,
            panelQuality,
            minimumTriangleArea,
            stitches.Max(stitch => stitch.GapCm),
            closures.Count == 0 ? 0 : closures.Max(closure => closure.InitialGapCm),
            edgeStrains.Max(),
            Percentile(edgeStrains, 0.95),
            minimumTorsoClearance);
    }

    private static double EndpointPairGap(
        CompiledPatternSeam seam,
        IReadOnlyList<int> chainA,
        IReadOnlyList<int> chainB,
        IReadOnlyDictionary<string, int> panelOffsets,
        IReadOnlyList<ArrangedPoint3> points)
    {
        ArrangedPoint3 firstA = points[panelOffsets[seam.PanelA] + chainA[0]];
        ArrangedPoint3 lastA = points[panelOffsets[seam.PanelA] + chainA[^1]];
        ArrangedPoint3 firstB = points[panelOffsets[seam.PanelB] + chainB[0]];
        ArrangedPoint3 lastB = points[panelOffsets[seam.PanelB] + chainB[^1]];
        return Distance(firstA, firstB) + Distance(lastA, lastB);
    }

    private static ArrangedPoint3[] RequirePrefitPanel(
        GarmentPrefitMeshDocument prefitMesh,
        StructuredPanelMesh mesh)
    {
        GarmentPrefitPanel source = prefitMesh.RequirePanel(mesh.PanelId);
        if (source.Vertices.Count != mesh.Vertices.Count)
        {
            throw new InvalidOperationException(
                $"Pre-fit panel {mesh.PanelId} has {source.Vertices.Count} vertices; " +
                $"the pattern-aware mesh has {mesh.Vertices.Count}.");
        }
        return source.Vertices
            .Select(vertex => new ArrangedPoint3(vertex.X, vertex.Z, vertex.Y))
            .ToArray();
    }

    private static ArrangedPoint3[] ArrangePanel(
        StructuredPanelMesh mesh,
        CompiledPatternPanel panel,
        LiveBodyProfileDocument bodyProfile)
        => panel.SourcePlacement is null
            ? ArrangeFlatSewingStage(mesh, panel.Placement, bodyProfile)
            : ArrangeFromSourcePlacement(mesh, panel.SourcePlacement);

    private static ArrangedPoint3[] ArrangeFromSourcePlacement(
        StructuredPanelMesh mesh,
        PatternPlacement3DDocument placement)
    {
        double xAngle = placement.RotationXDegrees * Math.PI / 180.0;
        double yAngle = placement.RotationYDegrees * Math.PI / 180.0;
        double zAngle = placement.RotationZDegrees * Math.PI / 180.0;
        double cx = Math.Cos(xAngle);
        double sx = Math.Sin(xAngle);
        double cy = Math.Cos(yAngle);
        double sy = Math.Sin(yAngle);
        double cz = Math.Cos(zAngle);
        double sz = Math.Sin(zAngle);
        ArrangedPoint3[] result = new ArrangedPoint3[mesh.Vertices.Count];
        foreach (StructuredPanelVertex vertex in mesh.Vertices)
        {
            double afterXx = vertex.X;
            double afterXy = vertex.Y * cx;
            double afterXz = vertex.Y * sx;
            double afterYx = afterXx * cy + afterXz * sy;
            double afterYy = afterXy;
            double afterYz = -afterXx * sy + afterXz * cy;
            double worldX = afterYx * cz - afterYy * sz + placement.X;
            double worldVertical = afterYx * sz + afterYy * cz + placement.Y;
            double worldDepth = afterYz + placement.Z;
            result[vertex.Index] = new ArrangedPoint3(worldX, worldDepth, worldVertical);
        }
        return result;
    }

    private static void WrapImportedBodyPanelsForSewing(
        IReadOnlyList<StructuredPanelMesh> panels,
        IReadOnlyDictionary<string, CompiledPatternPanel> compiledPanels,
        IReadOnlyDictionary<string, int> panelOffsets,
        LiveBodyProfileDocument bodyProfile,
        ArrangedPoint3[] points)
    {
        string[] supportedPlacements = ["torsoFront", "torsoBack", "skirtFront", "skirtBack"];
        foreach (string placement in supportedPlacements)
        {
            StructuredPanelMesh[] group = panels.Where(panel =>
                compiledPanels[panel.PanelId].SourcePlacement is not null &&
                compiledPanels[panel.PanelId].Placement.Equals(
                    placement,
                    StringComparison.OrdinalIgnoreCase)).ToArray();
            if (group.Length == 0)
            {
                continue;
            }

            bool isFront = placement.EndsWith("Front", StringComparison.OrdinalIgnoreCase);
            double clearance = placement.StartsWith("torso", StringComparison.OrdinalIgnoreCase)
                ? TorsoClearanceCm
                : SkirtClearanceCm;
            double minimumSourceX = group.Min(panel =>
                panel.Vertices.Min(vertex => points[panelOffsets[panel.PanelId] + vertex.Index].X));
            double maximumSourceX = group.Max(panel =>
                panel.Vertices.Max(vertex => points[panelOffsets[panel.PanelId] + vertex.Index].X));
            double groupWidth = maximumSourceX - minimumSourceX;

            foreach (StructuredPanelMesh panel in group)
            {
                int offset = panelOffsets[panel.PanelId];
                foreach (StructuredPanelVertex vertex in panel.Vertices)
                {
                    int globalIndex = offset + vertex.Index;
                    ArrangedPoint3 source = points[globalIndex];
                    double fraction = Math.Clamp(
                        (source.X - minimumSourceX) / Math.Max(groupWidth, 0.000001),
                        0,
                        1);
                    SurfacePointSample surface = SampleHalfSurfacePoint(
                        bodyProfile,
                        source.Z,
                        fraction,
                        isFront);
                    double deltaX = surface.X - surface.CenterX;
                    double deltaY = surface.Y - surface.CenterY;
                    double radial = Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
                    double scale = (radial + clearance) / Math.Max(radial, 0.000001);
                    points[globalIndex] = new ArrangedPoint3(
                        surface.CenterX + deltaX * scale,
                        surface.CenterY + deltaY * scale,
                        source.Z);
                }
            }
        }
    }

    private static void AlignImportedUpperGarmentToShoulderLandmark(
        ArrangedPoint3[] points,
        IReadOnlyList<StructuredPanelMesh> panels,
        IReadOnlyDictionary<string, CompiledPatternPanel> compiledPanels,
        IReadOnlyDictionary<string, int> panelOffsets)
    {
        StructuredPanelMesh[] torsoPanels = panels.Where(panel =>
            compiledPanels[panel.PanelId].SourcePlacement is not null &&
            compiledPanels[panel.PanelId].Placement.StartsWith(
                "torso",
                StringComparison.OrdinalIgnoreCase)).ToArray();
        if (torsoPanels.Length == 0)
        {
            return;
        }

        double stagedShoulderHeight = torsoPanels.Max(panel =>
            panel.Vertices.Max(vertex => points[panelOffsets[panel.PanelId] + vertex.Index].Z));
        double verticalOffset = ShoulderHeightCm - 3.0 - stagedShoulderHeight;
        for (int index = 0; index < points.Length; index++)
        {
            points[index] += new ArrangedPoint3(0, 0, verticalOffset);
        }
    }

    private static void FoldImportedSleevePanelsForSewing(
        IReadOnlyList<StructuredPanelMesh> panels,
        IReadOnlyDictionary<string, CompiledPatternPanel> compiledPanels,
        IReadOnlyDictionary<string, int> panelOffsets,
        LiveBodyProfileDocument bodyProfile,
        ArrangedPoint3[] points)
    {
        double armCenterDepth = bodyProfile.Sections
            .Where(section => section.HeightCm >= 120)
            .DefaultIfEmpty(bodyProfile.Sections[^1])
            .Average(section => section.CenterYCm);
        const double targetHalfDepthCm = 4.8;
        foreach (string placement in new[] { "sleeveLeft", "sleeveRight" })
        {
            StructuredPanelMesh[] group = panels.Where(panel =>
                compiledPanels[panel.PanelId].SourcePlacement is not null &&
                compiledPanels[panel.PanelId].Placement.Equals(
                    placement,
                    StringComparison.OrdinalIgnoreCase)).ToArray();
            if (group.Length == 0)
            {
                continue;
            }

            double maximumDepthOffset = group
                .SelectMany(panel => panel.Vertices.Select(vertex =>
                    Math.Abs(points[panelOffsets[panel.PanelId] + vertex.Index].Y - armCenterDepth)))
                .DefaultIfEmpty(targetHalfDepthCm)
                .Max();
            double depthScale = Math.Min(
                1,
                targetHalfDepthCm / Math.Max(maximumDepthOffset, targetHalfDepthCm));
            foreach (StructuredPanelMesh panel in group)
            {
                int offset = panelOffsets[panel.PanelId];
                foreach (StructuredPanelVertex vertex in panel.Vertices)
                {
                    int globalIndex = offset + vertex.Index;
                    ArrangedPoint3 point = points[globalIndex];
                    points[globalIndex] = point with
                    {
                        Y = armCenterDepth + (point.Y - armCenterDepth) * depthScale
                    };
                }
            }
        }
    }

    private static void AlignImportedGarmentToWaistLandmark(
        ArrangedPoint3[] points,
        IReadOnlyList<StructuredPanelMesh> panels,
        IReadOnlyDictionary<string, CompiledPatternPanel> compiledPanels,
        IReadOnlyDictionary<string, int> panelOffsets)
    {
        StructuredPanelMesh[] skirtPanels = panels.Where(panel =>
            compiledPanels[panel.PanelId].SourcePlacement is not null &&
            compiledPanels[panel.PanelId].Placement.StartsWith(
                "skirt",
                StringComparison.OrdinalIgnoreCase)).ToArray();
        if (skirtPanels.Length == 0)
        {
            return;
        }

        double stagedWaistHeight = skirtPanels.Max(panel =>
            panel.Vertices.Max(vertex => points[panelOffsets[panel.PanelId] + vertex.Index].Z));
        double verticalOffset = WaistHeightCm - stagedWaistHeight;
        for (int index = 0; index < points.Length; index++)
        {
            points[index] += new ArrangedPoint3(0, 0, verticalOffset);
        }
    }

    private static void BendPanelsForSewing(
        IReadOnlyList<StructuredPanelMesh> panels,
        IReadOnlyDictionary<string, CompiledPatternPanel> compiledPanels,
        IReadOnlyDictionary<string, int> panelOffsets,
        LiveBodyProfileDocument bodyProfile,
        ArrangedPoint3[] points)
    {
        double centerX = bodyProfile.Sections.Average(section => section.CenterXCm);
        double centerY = bodyProfile.Sections.Average(section => section.CenterYCm);
        LiveBodySectionDocument[] torsoSections = bodyProfile.Sections
            .Where(section => section.HeightCm >= WaistHeightCm)
            .DefaultIfEmpty(bodyProfile.Sections[^1])
            .ToArray();
        double radiusX = torsoSections.Max(section => section.WidthCm) * 0.5 + TorsoClearanceCm + 2.2;
        double radiusY = torsoSections.Max(section => section.DepthCm) * 0.5 + TorsoClearanceCm + 2.2;
        double maximumPanelWidth = panels
            .Where(panel => compiledPanels[panel.PanelId].Placement.StartsWith("torso", StringComparison.Ordinal))
            .Max(panel => panel.Vertices.Max(vertex => vertex.X) - panel.Vertices.Min(vertex => vertex.X));
        EllipseArcMap leftFrontArc = BuildEllipseArcMap(
            centerX,
            centerY,
            radiusX,
            radiusY,
            Math.PI,
            -1,
            maximumPanelWidth);
        EllipseArcMap rightFrontArc = BuildEllipseArcMap(
            centerX,
            centerY,
            radiusX,
            radiusY,
            0,
            1,
            maximumPanelWidth);
        EllipseArcMap backArc = BuildEllipseArcMap(
            centerX,
            centerY,
            radiusX,
            radiusY,
            Math.PI,
            1,
            maximumPanelWidth);
        double backHalfArcLength = EllipsePerimeter(radiusX, radiusY) * 0.5;

        foreach (StructuredPanelMesh panel in panels)
        {
            CompiledPatternPanel compiledPanel = compiledPanels[panel.PanelId];
            if (compiledPanel.SourcePlacement is not null)
            {
                continue;
            }
            string placement = compiledPanel.Placement;
            bool isBack = placement.Equals("torsoBack", StringComparison.OrdinalIgnoreCase) ||
                placement.Equals("skirtBack", StringComparison.OrdinalIgnoreCase);
            bool isLeftFront = placement.Equals("torsoFrontWrapLeft", StringComparison.OrdinalIgnoreCase);
            bool isRightFront = placement.Equals("torsoFrontWrapRight", StringComparison.OrdinalIgnoreCase);
            if (!isBack && !isLeftFront && !isRightFront)
            {
                continue;
            }

            int offset = panelOffsets[panel.PanelId];
            double minimumX = panel.Vertices.Min(vertex => vertex.X);
            double maximumX = panel.Vertices.Max(vertex => vertex.X);
            for (int vertexIndex = 0; vertexIndex < panel.Vertices.Count; vertexIndex++)
            {
                StructuredPanelVertex sourceVertex = panel.Vertices[vertexIndex];
                ArrangedPoint3 point = points[offset + vertexIndex];
                double panelWidth = maximumX - minimumX;
                double distance = isBack
                    ? sourceVertex.X - minimumX + Math.Max(0, backHalfArcLength - panelWidth) * 0.5
                    : maximumX - sourceVertex.X;
                StructuredPoint2 surfacePoint = SampleEllipseArc(
                    isBack ? backArc : isLeftFront ? leftFrontArc : rightFrontArc,
                    distance);
                double y = surfacePoint.Y;
                double z = point.Z;
                if (placement.StartsWith("torso", StringComparison.Ordinal))
                {
                    const double shoulderShiftCm = 12.0;
                    const double shoulderFoldLengthCm = 18.0;
                    const double shoulderFoldHeightCm = 135.0;
                    double slope = shoulderShiftCm / shoulderFoldLengthCm;
                    double distanceAboveFold = Math.Max(0, point.Z - shoulderFoldHeightCm);
                    y += (isBack ? 1.0 : -1.0) * slope * distanceAboveFold;
                    z = point.Z <= shoulderFoldHeightCm
                        ? point.Z
                        : shoulderFoldHeightCm + distanceAboveFold * Math.Sqrt(1.0 - slope * slope);
                }
                points[offset + vertexIndex] = new ArrangedPoint3(
                    surfacePoint.X,
                    y,
                    z);
            }
        }
    }

    private static EllipseArcMap BuildEllipseArcMap(
        double centerX,
        double centerY,
        double radiusX,
        double radiusY,
        double startAngle,
        double direction,
        double maximumDistance)
    {
        const int sampleCount = 4096;
        double maximumSweep = maximumDistance / Math.Max(Math.Min(radiusX, radiusY), 0.001) + 0.35;
        double[] distances = new double[sampleCount + 1];
        StructuredPoint2[] points = new StructuredPoint2[sampleCount + 1];
        for (int index = 0; index <= sampleCount; index++)
        {
            double angle = startAngle + direction * maximumSweep * index / sampleCount;
            points[index] = new StructuredPoint2(
                centerX + radiusX * Math.Cos(angle),
                centerY + radiusY * Math.Sin(angle));
            if (index > 0)
            {
                distances[index] = distances[index - 1] + Distance2(points[index - 1], points[index]);
            }
        }
        if (distances[^1] < maximumDistance)
        {
            throw new InvalidOperationException(
                $"Ellipse staging arc covers {distances[^1]:F2} cm; {maximumDistance:F2} cm is required.");
        }
        return new EllipseArcMap(distances, points);
    }

    private static StructuredPoint2 SampleEllipseArc(EllipseArcMap map, double distance)
    {
        distance = Math.Clamp(distance, 0, map.Distances[^1]);
        int lowerBound = 0;
        int upperBound = map.Distances.Count - 1;
        while (lowerBound < upperBound)
        {
            int middle = lowerBound + (upperBound - lowerBound) / 2;
            if (map.Distances[middle] < distance)
            {
                lowerBound = middle + 1;
            }
            else
            {
                upperBound = middle;
            }
        }
        int upper = lowerBound;
        if (Math.Abs(map.Distances[upper] - distance) <= 0.0000001)
        {
            return map.Points[upper];
        }
        if (upper <= 0)
        {
            return map.Points[0];
        }
        if (upper >= map.Distances.Count)
        {
            return map.Points[^1];
        }
        int lower = upper - 1;
        double span = map.Distances[upper] - map.Distances[lower];
        double alpha = (distance - map.Distances[lower]) / Math.Max(span, 0.000001);
        return map.Points[lower] * (1 - alpha) + map.Points[upper] * alpha;
    }

    private static double Distance2(StructuredPoint2 first, StructuredPoint2 second)
        => Math.Sqrt(
            Math.Pow(second.X - first.X, 2) +
            Math.Pow(second.Y - first.Y, 2));

    private static double EllipsePerimeter(double radiusX, double radiusY)
    {
        double sum = radiusX + radiusY;
        double difference = radiusX - radiusY;
        double h = difference * difference / Math.Max(sum * sum, 0.000001);
        return Math.PI * sum * (1.0 + 3.0 * h / (10.0 + Math.Sqrt(4.0 - 3.0 * h)));
    }

    private static void AlignPanelsToConstructionFrames(
        IReadOnlyList<StructuredPanelMesh> panels,
        IReadOnlyDictionary<string, int> panelOffsets,
        IReadOnlyList<(CompiledPatternSeam Seam, int LocalA, int LocalB, double Normalized)> stitches,
        ArrangedPoint3[] points)
    {
        Dictionary<string, StructuredPanelMesh> panelsById = panels.ToDictionary(
            panel => panel.PanelId,
            StringComparer.OrdinalIgnoreCase);
        string[] wrapConstructionPanels =
        [
            "bodice-back-panel",
            "bodice-left-wrap-panel",
            "bodice-right-wrap-panel",
            "skirt-back-panel",
            "skirt-left-wrap-panel",
            "skirt-right-wrap-panel",
            "tie-left-panel",
            "tie-right-panel"
        ];
        if (!wrapConstructionPanels.All(panelsById.ContainsKey))
        {
            return;
        }

        AlignPanelToReferences(
            "skirt-back-panel",
            ["bodice-back-panel"],
            panelsById,
            panelOffsets,
            stitches,
            points);
        AlignPanelToReferences(
            "skirt-left-wrap-panel",
            ["bodice-left-wrap-panel", "skirt-back-panel"],
            panelsById,
            panelOffsets,
            stitches,
            points);
        AlignPanelToReferences(
            "skirt-right-wrap-panel",
            ["bodice-right-wrap-panel", "skirt-back-panel"],
            panelsById,
            panelOffsets,
            stitches,
            points);
        AlignPanelToReferences(
            "tie-left-panel",
            ["bodice-left-wrap-panel"],
            panelsById,
            panelOffsets,
            stitches,
            points);
        AlignPanelToReferences(
            "tie-right-panel",
            ["bodice-right-wrap-panel"],
            panelsById,
            panelOffsets,
            stitches,
            points);
    }

    private static void AlignPanelToReferences(
        string panelId,
        IReadOnlyCollection<string> referencePanelIds,
        IReadOnlyDictionary<string, StructuredPanelMesh> panelsById,
        IReadOnlyDictionary<string, int> panelOffsets,
        IReadOnlyList<(CompiledPatternSeam Seam, int LocalA, int LocalB, double Normalized)> stitches,
        ArrangedPoint3[] points)
    {
        List<(ArrangedPoint3 Source, ArrangedPoint3 Target)> correspondences = [];
        foreach ((CompiledPatternSeam seam, int localA, int localB, _) in stitches)
        {
            if (seam.PanelA.Equals(panelId, StringComparison.OrdinalIgnoreCase) &&
                referencePanelIds.Contains(seam.PanelB, StringComparer.OrdinalIgnoreCase))
            {
                correspondences.Add((
                    points[panelOffsets[seam.PanelA] + localA],
                    points[panelOffsets[seam.PanelB] + localB]));
            }
            else if (seam.PanelB.Equals(panelId, StringComparison.OrdinalIgnoreCase) &&
                referencePanelIds.Contains(seam.PanelA, StringComparer.OrdinalIgnoreCase))
            {
                correspondences.Add((
                    points[panelOffsets[seam.PanelB] + localB],
                    points[panelOffsets[seam.PanelA] + localA]));
            }
        }

        if (correspondences.Count < 2)
        {
            throw new InvalidOperationException(
                $"Panel {panelId} has too few construction-frame correspondences.");
        }

        double sourceCenterX = correspondences.Average(pair => pair.Source.X);
        double sourceCenterZ = correspondences.Average(pair => pair.Source.Z);
        double targetCenterX = correspondences.Average(pair => pair.Target.X);
        double targetCenterZ = correspondences.Average(pair => pair.Target.Z);
        double dot = 0;
        double cross = 0;
        foreach ((ArrangedPoint3 source, ArrangedPoint3 target) in correspondences)
        {
            double sourceX = source.X - sourceCenterX;
            double sourceZ = source.Z - sourceCenterZ;
            double targetX = target.X - targetCenterX;
            double targetZ = target.Z - targetCenterZ;
            dot += sourceX * targetX + sourceZ * targetZ;
            cross += sourceX * targetZ - sourceZ * targetX;
        }

        double angle = Math.Atan2(cross, dot);
        double cosine = Math.Cos(angle);
        double sine = Math.Sin(angle);
        StructuredPanelMesh panel = panelsById[panelId];
        int offset = panelOffsets[panelId];
        for (int vertexIndex = 0; vertexIndex < panel.Vertices.Count; vertexIndex++)
        {
            ArrangedPoint3 point = points[offset + vertexIndex];
            double centeredX = point.X - sourceCenterX;
            double centeredZ = point.Z - sourceCenterZ;
            points[offset + vertexIndex] = new ArrangedPoint3(
                targetCenterX + cosine * centeredX - sine * centeredZ,
                point.Y,
                targetCenterZ + sine * centeredX + cosine * centeredZ);
        }
    }

    private static void BendTiePanelsTowardFrontClosure(
        IReadOnlyList<StructuredPanelMesh> panels,
        IReadOnlyDictionary<string, CompiledPatternPanel> compiledPanels,
        IReadOnlyDictionary<string, int> panelOffsets,
        LiveBodyProfileDocument bodyProfile,
        ArrangedPoint3[] points)
    {
        double bodyCenterX = bodyProfile.Sections.Average(section => section.CenterXCm);
        double bodyCenterY = bodyProfile.Sections.Average(section => section.CenterYCm);
        foreach (StructuredPanelMesh panel in panels)
        {
            string placement = compiledPanels[panel.PanelId].Placement;
            bool isLeft = placement.Equals("tieLeft", StringComparison.OrdinalIgnoreCase);
            bool isRight = placement.Equals("tieRight", StringComparison.OrdinalIgnoreCase);
            if (!isLeft && !isRight)
            {
                continue;
            }

            int offset = panelOffsets[panel.PanelId];
            int[] innerEdge = panel.EdgeVertexIndices["inner-end"].Distinct().ToArray();
            ArrangedPoint3 innerCenter = innerEdge
                .Select(index => points[offset + index])
                .Aggregate(new ArrangedPoint3(0, 0, 0), (sum, point) => sum + point) /
                innerEdge.Length;
            double deltaX = innerCenter.X - bodyCenterX;
            double deltaY = innerCenter.Y - bodyCenterY;
            double radius = Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
            double startAngle = Math.Atan2(deltaY, deltaX);
            double minimumRestX = panel.Vertices.Min(vertex => vertex.X);
            double maximumRestX = panel.Vertices.Max(vertex => vertex.X);
            double centerRestY = (panel.Vertices.Min(vertex => vertex.Y) +
                panel.Vertices.Max(vertex => vertex.Y)) * 0.5;
            double direction = isLeft ? -1.0 : 1.0;
            foreach (StructuredPanelVertex vertex in panel.Vertices)
            {
                double distanceFromInner = vertex.X - minimumRestX;
                double angle = startAngle + direction * distanceFromInner / Math.Max(radius, 0.000001);
                points[offset + vertex.Index] = new ArrangedPoint3(
                    bodyCenterX + radius * Math.Cos(angle),
                    bodyCenterY + radius * Math.Sin(angle),
                    innerCenter.Z + centerRestY - vertex.Y);
            }
        }
    }

    private static ArrangedPoint3[] ArrangeFlatSewingStage(
        StructuredPanelMesh mesh,
        string placement,
        LiveBodyProfileDocument bodyProfile)
    {
        double minimumX = mesh.Vertices.Min(vertex => vertex.X);
        double maximumX = mesh.Vertices.Max(vertex => vertex.X);
        double minimumY = mesh.Vertices.Min(vertex => vertex.Y);
        double maximumY = mesh.Vertices.Max(vertex => vertex.Y);
        double centerX = (minimumX + maximumX) * 0.5;
        double frontDepth = bodyProfile.Sections.Max(section => section.DepthCm) * 0.5 + 3.5;
        double backDepth = -bodyProfile.Sections.Max(section => section.DepthCm) * 0.5 - 3.5;
        double bodyCenterX = bodyProfile.Sections.Average(section => section.CenterXCm);
        double bodyCenterY = bodyProfile.Sections.Average(section => section.CenterYCm);
        double lateralRadius = bodyProfile.Sections.Max(section => section.WidthCm) * 0.5 + 5.5;

        (double StageX, double StageY, bool Bodice, bool Skirt, bool Tie, bool MirrorX) stage = placement switch
        {
            "torsoFront" => (0, frontDepth, true, false, false, false),
            "torsoBack" => (0, backDepth, true, false, false, false),
            "torsoFrontWrapLeft" => (-9, frontDepth, true, false, false, true),
            "torsoFrontWrapRight" => (9, frontDepth + 1.2, true, false, false, false),
            "skirtFront" => (0, frontDepth, false, true, false, false),
            "skirtBack" => (0, backDepth, false, true, false, false),
            "skirtFrontWrapLeft" => (-12, frontDepth, false, true, false, true),
            "skirtFrontWrapRight" => (12, frontDepth + 1.2, false, true, false, false),
            "sleeveLeft" => (-45, 0, false, false, false, false),
            "sleeveRight" => (45, 0, false, false, false, false),
            "tieLeft" => (-56, frontDepth + 2.4, false, false, true, true),
            "tieRight" => (56, frontDepth + 3.6, false, false, true, false),
            _ => throw new InvalidOperationException(
                $"Panel {mesh.PanelId} uses unsupported arrangement placement {placement}.")
        };

        ArrangedPoint3[] result = new ArrangedPoint3[mesh.Vertices.Count];
        foreach (StructuredPanelVertex vertex in mesh.Vertices)
        {
            double localX = vertex.X - centerX;
            double physicalLocalX = stage.MirrorX ? -localX : localX;
            double x = stage.StageX + physicalLocalX;
            double y = stage.StageY;
            if (placement.Equals("torsoFrontWrapLeft", StringComparison.OrdinalIgnoreCase) ||
                placement.Equals("torsoFrontWrapRight", StringComparison.OrdinalIgnoreCase))
            {
                const double diagonalCosine = 0.7071067811865476;
                const double diagonalSine = 0.7071067811865476;
                double halfPanelWidth = (maximumX - minimumX) * 0.5;
                bool isLeft = placement.Equals("torsoFrontWrapLeft", StringComparison.OrdinalIgnoreCase);
                double distanceFromSide = isLeft
                    ? physicalLocalX + halfPanelWidth
                    : halfPanelWidth - physicalLocalX;
                x = bodyCenterX + (isLeft ? -lateralRadius : lateralRadius) +
                    (isLeft ? 1.0 : -1.0) * distanceFromSide * diagonalCosine;
                y = bodyCenterY + distanceFromSide * diagonalSine + (isLeft ? 0.0 : 1.2);
            }
            double z = stage.Bodice
                ? WaistHeightCm + maximumY - vertex.Y
                : stage.Skirt
                    ? WaistHeightCm - (vertex.Y - minimumY)
                    : stage.Tie
                        ? WaistHeightCm + 4.0 - (vertex.Y - minimumY)
                        : ShoulderHeightCm - 4.0 - (vertex.Y - minimumY);
            result[vertex.Index] = new ArrangedPoint3(x, y, z);
        }
        return result;
    }

    private static ArrangedPoint3[] ArrangeTorso(
        StructuredPanelMesh mesh,
        LiveBodyProfileDocument profile,
        bool front)
    {
        ArrangedPoint3[] result = new ArrangedPoint3[mesh.Vertices.Count];
        foreach (StructuredPanelVertex vertex in mesh.Vertices)
        {
            int row = (int)Math.Round(vertex.V * mesh.Rows);
            int column = (int)Math.Round(vertex.U * mesh.Columns);
            StructuredPanelVertex bottom = mesh.Vertices[mesh.Rows * (mesh.Columns + 1) + column];
            double height = WaistHeightCm + bottom.Y - vertex.Y;
            double surfaceFraction = RowCumulativeLength(mesh, row, column) /
                Math.Max(RowPolylineLength(mesh, row), 0.000001);
            double upperBodyInset = Math.Clamp(
                (height - 135.0) / (ShoulderHeightCm - 135.0),
                0,
                1);
            double insetSurfaceFraction = Lerp(0.10, 0.90, surfaceFraction);
            surfaceFraction = Lerp(surfaceFraction, insetSurfaceFraction, upperBodyInset);
            SurfacePointSample body = SampleHalfSurfacePoint(profile, height, surfaceFraction, front);
            double deltaX = body.X - body.CenterX;
            double deltaY = body.Y - body.CenterY;
            double radial = Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
            double scale = (radial + TorsoClearanceCm) / Math.Max(radial, 0.000001);
            result[vertex.Index] = new ArrangedPoint3(
                body.CenterX + deltaX * scale,
                body.CenterY + deltaY * scale,
                height);
        }
        return result;
    }

    private static ArrangedPoint3[] ArrangeWrapTorso(
        StructuredPanelMesh mesh,
        LiveBodyProfileDocument profile,
        bool left)
    {
        ArrangedPoint3[] result = new ArrangedPoint3[mesh.Vertices.Count];
        double clearance = TorsoClearanceCm + 0.18;
        foreach (StructuredPanelVertex vertex in mesh.Vertices)
        {
            int column = (int)Math.Round(vertex.U * mesh.Columns);
            StructuredPanelVertex bottom = mesh.Vertices[mesh.Rows * (mesh.Columns + 1) + column];
            double height = WaistHeightCm + bottom.Y - vertex.Y;
            double necklineBlend = Math.Clamp(vertex.V / 0.48, 0, 1);
            necklineBlend = necklineBlend * necklineBlend * (3.0 - 2.0 * necklineBlend);
            double wrapEdgeFraction = left
                ? Lerp(0.38, 0.50, necklineBlend)
                : Lerp(0.62, 0.50, necklineBlend);
            double sideFraction = left
                ? Lerp(0.10, 0.0, vertex.V)
                : Lerp(0.90, 1.0, vertex.V);
            double surfaceFraction = Lerp(wrapEdgeFraction, sideFraction, vertex.U);
            SurfacePointSample body = SampleHalfSurfacePoint(profile, height, surfaceFraction, true);
            double deltaX = body.X - body.CenterX;
            double deltaY = body.Y - body.CenterY;
            double radial = Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
            double scale = (radial + clearance) / Math.Max(radial, 0.000001);
            result[vertex.Index] = new ArrangedPoint3(
                body.CenterX + deltaX * scale,
                body.CenterY + deltaY * scale,
                height);
        }
        return result;
    }

    private static ArrangedPoint3[] ArrangeSkirt(
        StructuredPanelMesh mesh,
        LiveBodyProfileDocument profile,
        bool front)
    {
        ArrangedPoint3[] result = new ArrangedPoint3[mesh.Vertices.Count];
        double topWidth = RowPolylineLength(mesh, 0);
        double minimumProfileHeight = profile.Sections.Min(section => section.HeightCm);
        foreach (StructuredPanelVertex vertex in mesh.Vertices)
        {
            double height = WaistHeightCm - vertex.Y;
            int row = (int)Math.Round(vertex.V * mesh.Rows);
            int column = (int)Math.Round(vertex.U * mesh.Columns);
            double surfaceFraction = RowCumulativeLength(mesh, row, column) /
                Math.Max(RowPolylineLength(mesh, row), 0.000001);
            SurfacePointSample body = SampleHalfSurfacePoint(
                profile,
                Math.Max(height, minimumProfileHeight),
                surfaceFraction,
                front);
            double deltaX = body.X - body.CenterX;
            double deltaY = body.Y - body.CenterY;
            double radial = Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
            double rowWidth = RowPolylineLength(mesh, row);
            double flare = Math.Max(0, rowWidth - topWidth) / Math.PI;
            double scale = (radial + SkirtClearanceCm + flare) / Math.Max(radial, 0.000001);
            result[vertex.Index] = new ArrangedPoint3(
                body.CenterX + deltaX * scale,
                body.CenterY + deltaY * scale,
                height);
        }
        return result;
    }

    private static ArrangedPoint3[] ArrangeWrapSkirt(
        StructuredPanelMesh mesh,
        LiveBodyProfileDocument profile,
        bool left)
    {
        ArrangedPoint3[] result = new ArrangedPoint3[mesh.Vertices.Count];
        double topWidth = RowPolylineLength(mesh, 0);
        double minimumProfileHeight = profile.Sections.Min(section => section.HeightCm);
        double clearance = left ? SkirtClearanceCm + 0.18 : SkirtClearanceCm + 0.52;
        foreach (StructuredPanelVertex vertex in mesh.Vertices)
        {
            double height = WaistHeightCm - vertex.Y;
            int row = (int)Math.Round(vertex.V * mesh.Rows);
            double wrapEdgeFraction = left ? 0.96 : 0.04;
            double sideFraction = left ? 0.0 : 1.0;
            double surfaceFraction = Lerp(wrapEdgeFraction, sideFraction, vertex.U);
            SurfacePointSample body = SampleHalfSurfacePoint(
                profile,
                Math.Max(height, minimumProfileHeight),
                surfaceFraction,
                true);
            double deltaX = body.X - body.CenterX;
            double deltaY = body.Y - body.CenterY;
            double radial = Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
            double rowWidth = RowPolylineLength(mesh, row);
            double flare = Math.Max(0, rowWidth - topWidth) / Math.PI;
            double scale = (radial + clearance + flare) / Math.Max(radial, 0.000001);
            result[vertex.Index] = new ArrangedPoint3(
                body.CenterX + deltaX * scale,
                body.CenterY + deltaY * scale,
                height);
        }
        return result;
    }

    private static ArrangedPoint3[] ArrangeSleeve(StructuredPanelMesh mesh, bool left)
    {
        double side = left ? -1.0 : 1.0;
        ArrangedPoint3 shoulder = new(side * ShoulderBreadthCm * 0.50, 0, ShoulderHeightCm - 3.0);
        ArrangedPoint3 axis = Normalize(new ArrangedPoint3(side * 0.88, 0, -0.475));
        ArrangedPoint3 depthBasis = new(0, 1, 0);
        ArrangedPoint3 radialBasis = Normalize(new ArrangedPoint3(-axis.Z, 0, axis.X));
        double capRadius = BoundaryLength(mesh, "cap-front", "cap-back") / (2.0 * Math.PI);
        double cuffRadius = BoundaryLength(mesh, "hem") / (2.0 * Math.PI);
        ArrangedPoint3[] result = new ArrangedPoint3[mesh.Vertices.Count];
        foreach (StructuredPanelVertex vertex in mesh.Vertices)
        {
            int row = (int)Math.Round(vertex.V * mesh.Rows);
            int column = (int)Math.Round(vertex.U * mesh.Columns);
            StructuredPanelVertex top = mesh.Vertices[column];
            double longitudinalDistance = Math.Max(0, vertex.Y - top.Y);
            double rowLength = RowPolylineLength(mesh, row);
            double rowRadius = rowLength / (2.0 * Math.PI);
            double radius = Math.Max(Lerp(capRadius, cuffRadius, vertex.V), rowRadius) + 0.35;
            double angle = 2.0 * Math.PI *
                RowCumulativeLength(mesh, row, column) /
                Math.Max(rowLength, 0.000001);
            ArrangedPoint3 center = shoulder + axis * longitudinalDistance;
            ArrangedPoint3 point = center +
                depthBasis * (radius * Math.Cos(angle)) +
                radialBasis * (radius * Math.Sin(angle));
            result[vertex.Index] = point;
        }
        return result;
    }

    private static ArrangedPoint3[] ArrangeTie(
        StructuredPanelMesh mesh,
        LiveBodyProfileDocument profile,
        bool left)
    {
        double startAngle = left ? Math.PI : 0.0;
        double direction = left ? 1.0 : -1.0;
        double tieLength = Math.Max(1.0, BoundaryLength(mesh, "top"));
        double tieWidth = Math.Max(1.0, BoundaryLength(mesh, "inner-end"));
        SurfaceSample waist = SampleTorsoSurface(profile, WaistHeightCm + tieWidth * 0.5, startAngle);
        double wrapRadius = waist.Radius + TorsoClearanceCm + (left ? 1.25 : 1.75);
        double wrapLength = Math.Min(tieLength * 0.58, 48.0);
        double centerHeight = WaistHeightCm + tieWidth * 0.5;
        double wrapEndAngle = startAngle + direction * wrapLength / wrapRadius;
        ArrangedPoint3 wrapEnd = new(
            waist.CenterX + wrapRadius * Math.Cos(wrapEndAngle),
            waist.CenterY + wrapRadius * Math.Sin(wrapEndAngle),
            centerHeight);
        ArrangedPoint3 tangent = new(
            direction * -Math.Sin(wrapEndAngle),
            direction * Math.Cos(wrapEndAngle),
            0);

        ArrangedPoint3[] result = new ArrangedPoint3[mesh.Vertices.Count];
        foreach (StructuredPanelVertex vertex in mesh.Vertices)
        {
            int row = (int)Math.Round(vertex.V * mesh.Rows);
            int column = (int)Math.Round(vertex.U * mesh.Columns);
            StructuredPanelVertex top = mesh.Vertices[column];
            double distance = RowCumulativeLength(mesh, row, column);
            ArrangedPoint3 center;
            if (distance <= wrapLength)
            {
                double angle = startAngle + direction * distance / wrapRadius;
                center = new ArrangedPoint3(
                    waist.CenterX + wrapRadius * Math.Cos(angle),
                    waist.CenterY + wrapRadius * Math.Sin(angle),
                    centerHeight);
            }
            else
            {
                double tailDistance = distance - wrapLength;
                center = wrapEnd + tangent * (tailDistance * 0.55) +
                    new ArrangedPoint3(0, 0, -tailDistance * 0.835);
            }
            result[vertex.Index] = center + new ArrangedPoint3(
                0,
                0,
                tieWidth * 0.5 - Math.Max(0, vertex.Y - top.Y));
        }
        return result;
    }

    private static int[] BuildSeamChain(
        StructuredPanelMesh panel,
        IReadOnlyList<string> edgeIds,
        bool reverse)
    {
        List<int> result = [];
        foreach (string edgeId in edgeIds)
        {
            if (!panel.EdgeVertexIndices.TryGetValue(edgeId, out IReadOnlyList<int>? edge))
            {
                throw new InvalidOperationException($"Panel {panel.PanelId} is missing structured edge {edgeId}.");
            }
            if (result.Count > 0 && result[^1] != edge[0])
            {
                throw new InvalidOperationException(
                    $"Panel {panel.PanelId} seam chain is discontinuous before edge {edgeId}.");
            }
            result.AddRange(edge.Skip(result.Count == 0 ? 0 : 1));
        }
        if (reverse)
        {
            result.Reverse();
        }
        return result.ToArray();
    }

    private static void AddContinuousSeamTargets(
        IReadOnlyList<ArrangedPoint3> points,
        int offsetA,
        IReadOnlyList<int> chainA,
        int offsetB,
        IReadOnlyList<int> chainB,
        IDictionary<int, List<ArrangedPoint3>> destination)
    {
        for (int index = 0; index < chainA.Count; index++)
        {
            double normalized = index / (double)Math.Max(chainA.Count - 1, 1);
            int globalIndex = offsetA + chainA[index];
            ArrangedPoint3 target = (points[globalIndex] +
                SampleChainPoint(points, offsetB, chainB, normalized)) * 0.5;
            AddTargetContribution(destination, globalIndex, target);
        }
        for (int index = 0; index < chainB.Count; index++)
        {
            double normalized = index / (double)Math.Max(chainB.Count - 1, 1);
            int globalIndex = offsetB + chainB[index];
            ArrangedPoint3 target = (SampleChainPoint(points, offsetA, chainA, normalized) +
                points[globalIndex]) * 0.5;
            AddTargetContribution(destination, globalIndex, target);
        }
    }

    private static ArrangedPoint3 SampleChainPoint(
        IReadOnlyList<ArrangedPoint3> points,
        int offset,
        IReadOnlyList<int> chain,
        double normalized)
    {
        double position = Math.Clamp(normalized, 0, 1) * (chain.Count - 1);
        int lowerIndex = (int)Math.Floor(position);
        int upperIndex = Math.Min(lowerIndex + 1, chain.Count - 1);
        double blend = position - lowerIndex;
        return points[offset + chain[lowerIndex]] * (1.0 - blend) +
            points[offset + chain[upperIndex]] * blend;
    }

    private static void AddTargetContribution(
        IDictionary<int, List<ArrangedPoint3>> destination,
        int vertexIndex,
        ArrangedPoint3 target)
    {
        if (!destination.TryGetValue(vertexIndex, out List<ArrangedPoint3>? contributions))
        {
            contributions = [];
            destination.Add(vertexIndex, contributions);
        }
        contributions.Add(target);
    }

    private static void AlignSleeveCapsToArmholes(
        PatternTopologyCompilation topology,
        IReadOnlyDictionary<string, StructuredPanelMesh> panels,
        IReadOnlyDictionary<string, CompiledPatternPanel> compiledPanels,
        IReadOnlyDictionary<string, int> panelOffsets,
        ArrangedPoint3[] points)
    {
        Dictionary<int, List<ArrangedPoint3>> capTargets = [];
        Dictionary<string, HashSet<string>> sleevePanelIdsByPlacement =
            new(StringComparer.OrdinalIgnoreCase);
        foreach (CompiledPatternSeam seam in topology.Seams)
        {
            string placementA = compiledPanels[seam.PanelA].Placement;
            string placementB = compiledPanels[seam.PanelB].Placement;
            bool aIsSleeve = IsSleevePlacement(placementA);
            bool bIsSleeve = IsSleevePlacement(placementB);
            bool aIsTorso = placementA.StartsWith("torso", StringComparison.OrdinalIgnoreCase);
            bool bIsTorso = placementB.StartsWith("torso", StringComparison.OrdinalIgnoreCase);
            if (!(aIsSleeve && bIsTorso) && !(bIsSleeve && aIsTorso))
            {
                continue;
            }

            string sleevePanelId = aIsSleeve ? seam.PanelA : seam.PanelB;
            string bodicePanelId = aIsSleeve ? seam.PanelB : seam.PanelA;
            string sleevePlacement = aIsSleeve ? placementA : placementB;
            StructuredPanelMesh sleeve = panels[sleevePanelId];
            StructuredPanelMesh bodice = panels[bodicePanelId];
            int[] sleeveChain = BuildSeamChain(
                sleeve,
                aIsSleeve ? seam.EdgeIdsA : seam.EdgeIdsB,
                aIsSleeve ? seam.ReverseA : seam.ReverseB);
            int[] bodiceChain = BuildSeamChain(
                bodice,
                aIsSleeve ? seam.EdgeIdsB : seam.EdgeIdsA,
                aIsSleeve ? seam.ReverseB : seam.ReverseA);
            if (EndpointChainGap(
                    sleevePanelId,
                    sleeveChain,
                    bodicePanelId,
                    bodiceChain,
                    panelOffsets,
                    points) >
                EndpointChainGap(
                    sleevePanelId,
                    sleeveChain,
                    bodicePanelId,
                    bodiceChain.Reverse().ToArray(),
                    panelOffsets,
                    points))
            {
                bodiceChain = bodiceChain.Reverse().ToArray();
            }

            if (!sleevePanelIdsByPlacement.TryGetValue(
                    sleevePlacement,
                    out HashSet<string>? sleevePanelIds))
            {
                sleevePanelIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                sleevePanelIdsByPlacement.Add(sleevePlacement, sleevePanelIds);
            }
            sleevePanelIds.Add(sleevePanelId);
            for (int index = 0; index < sleeveChain.Length; index++)
            {
                double normalized = index / (double)Math.Max(sleeveChain.Length - 1, 1);
                int globalSleeveVertex = panelOffsets[sleevePanelId] + sleeveChain[index];
                ArrangedPoint3 target = SampleChainPoint(
                    points,
                    panelOffsets[bodicePanelId],
                    bodiceChain,
                    normalized);
                AddTargetContribution(capTargets, globalSleeveVertex, target);
            }
        }

        if (capTargets.Count == 0)
        {
            return;
        }

        foreach ((string sleevePlacement, HashSet<string> sleevePanelIds) in
            sleevePanelIdsByPlacement)
        {
            ArrangedPoint3 displacementSum = new(0, 0, 0);
            int displacementCount = 0;
            foreach (string sleevePanelId in sleevePanelIds)
            {
                StructuredPanelMesh sleeve = panels[sleevePanelId];
                int offset = panelOffsets[sleevePanelId];
                foreach (StructuredPanelVertex vertex in sleeve.Vertices)
                {
                    int globalVertex = offset + vertex.Index;
                    if (!capTargets.TryGetValue(globalVertex, out List<ArrangedPoint3>? targets))
                    {
                        continue;
                    }
                    ArrangedPoint3 target = targets.Aggregate(
                        new ArrangedPoint3(0, 0, 0),
                        (sum, current) => sum + current) / targets.Count;
                    displacementSum += target - points[globalVertex];
                    displacementCount++;
                }
            }

            if (displacementCount == 0)
            {
                throw new InvalidOperationException(
                    $"Sleeve placement {sleevePlacement} has no armhole target vertices.");
            }

            ArrangedPoint3 groupDisplacement = displacementSum / displacementCount;
            foreach (string sleevePanelId in sleevePanelIds)
            {
                StructuredPanelMesh sleeve = panels[sleevePanelId];
                int offset = panelOffsets[sleevePanelId];
                foreach (StructuredPanelVertex vertex in sleeve.Vertices)
                {
                    points[offset + vertex.Index] += groupDisplacement;
                }
            }
        }

        Dictionary<int, ArrangedPoint3> boundaryTargets = capTargets.ToDictionary(
            pair => pair.Key,
            pair => pair.Value.Aggregate(
                new ArrangedPoint3(0, 0, 0),
                (sum, current) => sum + current) / pair.Value.Count);
        StructuredPanelMesh[] sleevePanels = panels.Values.Where(panel =>
            IsSleevePlacement(compiledPanels[panel.PanelId].Placement)).ToArray();
        SmoothPanelSeamDisplacements(
            points,
            sleevePanels,
            panelOffsets,
            boundaryTargets);
    }

    private static double EndpointChainGap(
        string panelA,
        IReadOnlyList<int> chainA,
        string panelB,
        IReadOnlyList<int> chainB,
        IReadOnlyDictionary<string, int> panelOffsets,
        IReadOnlyList<ArrangedPoint3> points)
        => Distance(
                points[panelOffsets[panelA] + chainA[0]],
                points[panelOffsets[panelB] + chainB[0]]) +
            Distance(
                points[panelOffsets[panelA] + chainA[^1]],
                points[panelOffsets[panelB] + chainB[^1]]);

    private static bool IsSleevePlacement(string placement)
        => placement.Equals("sleeveLeft", StringComparison.OrdinalIgnoreCase) ||
            placement.Equals("sleeveRight", StringComparison.OrdinalIgnoreCase);

    private static SurfaceSample SampleTorsoSurface(
        LiveBodyProfileDocument profile,
        double height,
        double angle)
    {
        LiveBodySectionDocument[] sections = profile.Sections
            .OrderBy(section => section.HeightCm)
            .ToArray();
        const double measuredUpperHeight = 135.0;
        if (height > measuredUpperHeight)
        {
            LiveBodySectionDocument baseSection = sections
                .Where(section => section.HeightCm <= measuredUpperHeight)
                .DefaultIfEmpty(sections[^1])
                .Last();
            double blend = Math.Clamp(
                (height - baseSection.HeightCm) / Math.Max(ShoulderHeightCm - baseSection.HeightCm, 0.001),
                0,
                1);
            double width = Lerp(baseSection.WidthCm, ShoulderBreadthCm - 4.5, blend);
            double depth = Lerp(baseSection.DepthCm, 19.0, blend);
            double centerX = Lerp(baseSection.CenterXCm, 0, blend);
            double centerY = Lerp(baseSection.CenterYCm, -2.5, blend);
            return new SurfaceSample(centerX, centerY, EllipseRadius(width * 0.5, depth * 0.5, angle));
        }

        LiveBodySectionDocument lower = sections[0];
        LiveBodySectionDocument upper = sections[^1];
        for (int index = 1; index < sections.Length; index++)
        {
            if (sections[index].HeightCm >= height)
            {
                lower = sections[index - 1];
                upper = sections[index];
                break;
            }
        }
        if (height <= sections[0].HeightCm)
        {
            lower = upper = sections[0];
        }
        else if (height >= sections[^1].HeightCm)
        {
            lower = upper = sections[^1];
        }

        double blendHeight = Math.Abs(upper.HeightCm - lower.HeightCm) <= 0.000001
            ? 0
            : (height - lower.HeightCm) / (upper.HeightCm - lower.HeightCm);
        double lowerRadius = SurfaceRadiusAtAngle(lower, angle);
        double upperRadius = SurfaceRadiusAtAngle(upper, angle);
        return new SurfaceSample(
            Lerp(lower.CenterXCm, upper.CenterXCm, blendHeight),
            Lerp(lower.CenterYCm, upper.CenterYCm, blendHeight),
            Lerp(lowerRadius, upperRadius, blendHeight));
    }

    private static SurfacePointSample SampleHalfSurfacePoint(
        LiveBodyProfileDocument profile,
        double height,
        double fraction,
        bool front)
    {
        const int curveSegments = 64;
        ArrangedPoint3[] samples = new ArrangedPoint3[curveSegments + 1];
        double[] cumulativeLengths = new double[curveSegments + 1];
        for (int index = 0; index <= curveSegments; index++)
        {
            double curveFraction = index / (double)curveSegments;
            double angle = front
                ? Math.PI * (1.0 - curveFraction)
                : Math.PI * (1.0 + curveFraction);
            SurfaceSample surface = SampleTorsoSurface(profile, height, angle);
            samples[index] = new ArrangedPoint3(
                surface.CenterX + surface.Radius * Math.Cos(angle),
                surface.CenterY + surface.Radius * Math.Sin(angle),
                0);
            if (index > 0)
            {
                cumulativeLengths[index] = cumulativeLengths[index - 1] +
                    Distance(samples[index - 1], samples[index]);
            }
        }

        double targetLength = cumulativeLengths[^1] * fraction;
        int segment = 0;
        while (segment + 1 < cumulativeLengths.Length - 1 &&
            cumulativeLengths[segment + 1] < targetLength)
        {
            segment++;
        }
        double segmentLength = cumulativeLengths[segment + 1] - cumulativeLengths[segment];
        double blend = (targetLength - cumulativeLengths[segment]) /
            Math.Max(segmentLength, 0.000001);
        ArrangedPoint3 point = samples[segment] * (1.0 - blend) + samples[segment + 1] * blend;
        double angleAtPoint = Math.Atan2(point.Y, point.X);
        SurfaceSample center = SampleTorsoSurface(profile, height, angleAtPoint);
        return new SurfacePointSample(center.CenterX, center.CenterY, point.X, point.Y);
    }

    private static double SurfaceRadiusAtAngle(LiveBodySectionDocument section, double angle)
    {
        if (section.SurfacePoints.Count < 2)
        {
            return EllipseRadius(section.WidthCm * 0.5, section.DepthCm * 0.5, angle);
        }

        double normalized = NormalizeAngle(angle);
        IReadOnlyList<LiveBodySurfacePointDocument> points = section.SurfacePoints;
        for (int index = 0; index < points.Count; index++)
        {
            LiveBodySurfacePointDocument current = points[index];
            LiveBodySurfacePointDocument next = points[(index + 1) % points.Count];
            double currentAngle = current.AngleRadians;
            double nextAngle = index == points.Count - 1
                ? next.AngleRadians + 2.0 * Math.PI
                : next.AngleRadians;
            double candidate = normalized < currentAngle ? normalized + 2.0 * Math.PI : normalized;
            if (candidate >= currentAngle && candidate <= nextAngle)
            {
                double blend = (candidate - currentAngle) / Math.Max(nextAngle - currentAngle, 0.000001);
                return Lerp(current.RadiusCm, next.RadiusCm, blend);
            }
        }
        return points[0].RadiusCm;
    }

    private static double MeasureMinimumTorsoClearance(
        IEnumerable<ArrangedPanelMesh> panels,
        LiveBodyProfileDocument profile)
    {
        double minimum = double.PositiveInfinity;
        foreach (ArrangedPanelMesh panel in panels.Where(panel =>
            panel.Placement.StartsWith("torso", StringComparison.OrdinalIgnoreCase) ||
            panel.Placement.StartsWith("skirt", StringComparison.OrdinalIgnoreCase)))
        {
            foreach (ArrangedPanelVertex vertex in panel.Vertices.Where(vertex =>
                vertex.Z >= profile.Sections.Min(section => section.HeightCm) &&
                vertex.Z <= 135.0))
            {
                double angle = Math.Atan2(vertex.Y, vertex.X);
                SurfaceSample body = SampleTorsoSurface(profile, vertex.Z, angle);
                double radial = Math.Sqrt(
                    Math.Pow(vertex.X - body.CenterX, 2) +
                    Math.Pow(vertex.Y - body.CenterY, 2));
                minimum = Math.Min(minimum, radial - body.Radius);
            }
        }
        return minimum;
    }

    private static void ProjectSewnTorsoGroupsOutsideBody(
        ArrangedPoint3[] points,
        IReadOnlyList<string> placementByVertex,
        DisjointSet seamGroups,
        LiveBodyProfileDocument profile)
    {
        Dictionary<int, List<int>> membersByRoot = [];
        for (int index = 0; index < points.Length; index++)
        {
            int root = seamGroups.Find(index);
            if (!membersByRoot.TryGetValue(root, out List<int>? members))
            {
                members = [];
                membersByRoot.Add(root, members);
            }
            members.Add(index);
        }

        foreach (List<int> members in membersByRoot.Values)
        {
            if (members.Count < 2)
            {
                continue;
            }
            bool touchesTorso = members.Any(index =>
                placementByVertex[index].StartsWith("torso", StringComparison.Ordinal) ||
                placementByVertex[index].StartsWith("skirt", StringComparison.Ordinal));
            if (!touchesTorso)
            {
                continue;
            }

            ArrangedPoint3 point = members
                .Select(index => points[index])
                .Aggregate(new ArrangedPoint3(0, 0, 0), (sum, current) => sum + current) /
                members.Count;
            double angle = Math.Atan2(point.Y, point.X);
            SurfaceSample body = SampleTorsoSurface(profile, point.Z, angle);
            double deltaX = point.X - body.CenterX;
            double deltaY = point.Y - body.CenterY;
            double radial = Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
            double upperBodyBlend = Math.Clamp((point.Z - 135.0) / 14.0, 0, 1);
            double requiredClearance = Lerp(TorsoClearanceCm, 0.10, upperBodyBlend);
            double requiredRadius = body.Radius + requiredClearance;
            ArrangedPoint3 projected = point;
            if (radial < requiredRadius)
            {
                double scale = requiredRadius / Math.Max(radial, 0.000001);
                projected = new ArrangedPoint3(
                    body.CenterX + deltaX * scale,
                    body.CenterY + deltaY * scale,
                    point.Z);
            }
            foreach (int index in members)
            {
                points[index] = projected;
            }
        }
    }

    private static bool IsSafeInitialAssemblyConstraint(
        (CompiledPatternSeam Seam, int LocalA, int LocalB, double Normalized) stitch)
    {
        if (stitch.Seam.PanelA.Equals(
                stitch.Seam.PanelB,
                StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        const double endpointTolerance = 0.000001;
        return stitch.Normalized > endpointTolerance &&
            stitch.Normalized < 1.0 - endpointTolerance;
    }

    private static void SmoothPanelSeamDisplacements(
        ArrangedPoint3[] points,
        IReadOnlyList<StructuredPanelMesh> panels,
        IReadOnlyDictionary<string, int> panelOffsets,
        IReadOnlyDictionary<int, ArrangedPoint3> boundaryTargets)
    {
        ArrangedPoint3[] basePoints = points.ToArray();
        foreach (StructuredPanelMesh panel in panels)
        {
            int offset = panelOffsets[panel.PanelId];
            int vertexCount = panel.Vertices.Count;
            ArrangedPoint3[] current = new ArrangedPoint3[vertexCount];
            ArrangedPoint3[] next = new ArrangedPoint3[vertexCount];
            bool[] constrained = new bool[vertexCount];
            for (int localIndex = 0; localIndex < vertexCount; localIndex++)
            {
                int globalIndex = offset + localIndex;
                if (boundaryTargets.TryGetValue(globalIndex, out ArrangedPoint3 target))
                {
                    constrained[localIndex] = true;
                    current[localIndex] = target - basePoints[globalIndex];
                }
            }

            for (int iteration = 0; iteration < 1600; iteration++)
            {
                for (int row = 0; row <= panel.Rows; row++)
                {
                    for (int column = 0; column <= panel.Columns; column++)
                    {
                        int localIndex = row * (panel.Columns + 1) + column;
                        if (constrained[localIndex])
                        {
                            next[localIndex] = current[localIndex];
                            continue;
                        }

                        ArrangedPoint3 sum = new(0, 0, 0);
                        int neighborCount = 0;
                        if (column > 0)
                        {
                            sum += current[localIndex - 1];
                            neighborCount++;
                        }
                        if (column < panel.Columns)
                        {
                            sum += current[localIndex + 1];
                            neighborCount++;
                        }
                        if (row > 0)
                        {
                            sum += current[localIndex - panel.Columns - 1];
                            neighborCount++;
                        }
                        if (row < panel.Rows)
                        {
                            sum += current[localIndex + panel.Columns + 1];
                            neighborCount++;
                        }
                        next[localIndex] = sum / Math.Max(neighborCount, 1);
                    }
                }
                (current, next) = (next, current);
            }

            for (int localIndex = 0; localIndex < vertexCount; localIndex++)
            {
                points[offset + localIndex] = basePoints[offset + localIndex] + current[localIndex];
            }
        }
    }

    private static void ProjectAllTorsoVerticesOutsideBody(
        ArrangedPoint3[] points,
        IReadOnlyList<string> placementByVertex,
        LiveBodyProfileDocument profile)
    {
        for (int index = 0; index < points.Length; index++)
        {
            if (!IsBodyPlacement(placementByVertex[index]))
            {
                continue;
            }
            points[index] = ProjectPointOutsideBody(points[index], profile);
        }
    }

    private static bool IsBodyPlacement(string placement)
        => placement.StartsWith("torso", StringComparison.Ordinal) ||
            placement.StartsWith("skirt", StringComparison.Ordinal);

    private static ArrangedPoint3 ProjectPointOutsideBody(
        ArrangedPoint3 point,
        LiveBodyProfileDocument profile)
    {
        double angle = Math.Atan2(point.Y, point.X);
        SurfaceSample body = SampleTorsoSurface(profile, point.Z, angle);
        double deltaX = point.X - body.CenterX;
        double deltaY = point.Y - body.CenterY;
        double radial = Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
        double upperBodyBlend = Math.Clamp((point.Z - 135.0) / 14.0, 0, 1);
        double requiredClearance = Lerp(TorsoClearanceCm, 0.10, upperBodyBlend);
        double requiredRadius = body.Radius + requiredClearance;
        if (radial >= requiredRadius)
        {
            return point;
        }

        double scale = requiredRadius / Math.Max(radial, 0.000001);
        return new ArrangedPoint3(
            body.CenterX + deltaX * scale,
            body.CenterY + deltaY * scale,
            point.Z);
    }

    private static void RelaxEdgeStrainBeforeSimulation(
        ArrangedPoint3[] points,
        IReadOnlyList<StructuredPanelMesh> panels,
        IReadOnlyDictionary<string, int> panelOffsets,
        IReadOnlyList<(CompiledPatternSeam Seam, int LocalA, int LocalB, double Normalized)> stitches,
        IReadOnlyList<string> placementByVertex,
        DisjointSet seamGroups,
        LiveBodyProfileDocument profile)
    {
        List<(int A, int B, double RestLength)> edges = [];
        foreach (StructuredPanelMesh panel in panels)
        {
            int offset = panelOffsets[panel.PanelId];
            HashSet<(int A, int B)> visited = [];
            foreach (StructuredPanelTriangle triangle in panel.Triangles)
            {
                AddRelaxationEdge(panel, offset, triangle.A, triangle.B, visited, edges);
                AddRelaxationEdge(panel, offset, triangle.B, triangle.C, visited, edges);
                AddRelaxationEdge(panel, offset, triangle.C, triangle.A, visited, edges);
            }
        }

        ArrangedPoint3[] anchors = points.ToArray();
        const int iterations = 1200;
        const double edgeStiffness = 0.82;
        const double anchorStrength = 0.00015;
        for (int iteration = 0; iteration < iterations; iteration++)
        {
            foreach ((int a, int b, double restLength) in edges)
            {
                ArrangedPoint3 delta = points[b] - points[a];
                double length = Math.Sqrt(
                    delta.X * delta.X + delta.Y * delta.Y + delta.Z * delta.Z);
                if (length <= 0.000001)
                {
                    continue;
                }
                ArrangedPoint3 correction = delta *
                    (edgeStiffness * 0.5 * (length - restLength) / length);
                points[a] += correction;
                points[b] -= correction;
            }

            for (int index = 0; index < points.Length; index++)
            {
                points[index] = points[index] * (1.0 - anchorStrength) +
                    anchors[index] * anchorStrength;
            }

            foreach ((CompiledPatternSeam seam, int localA, int localB, _) in stitches)
            {
                int globalA = panelOffsets[seam.PanelA] + localA;
                int globalB = panelOffsets[seam.PanelB] + localB;
                ArrangedPoint3 midpoint = (points[globalA] + points[globalB]) * 0.5;
                if (IsBodyPlacement(placementByVertex[globalA]) ||
                    IsBodyPlacement(placementByVertex[globalB]))
                {
                    midpoint = ProjectPointOutsideBody(midpoint, profile);
                }
                points[globalA] = midpoint;
                points[globalB] = midpoint;
            }

            if ((iteration + 1) % 10 == 0)
            {
                ProjectAllTorsoVerticesOutsideBody(points, placementByVertex, profile);
                ProjectSewnTorsoGroupsOutsideBody(
                    points,
                    placementByVertex,
                    seamGroups,
                    profile);
            }
        }

        ProjectAllTorsoVerticesOutsideBody(points, placementByVertex, profile);
        ProjectSewnTorsoGroupsOutsideBody(
            points,
            placementByVertex,
            seamGroups,
            profile);
    }

    private static void AddRelaxationEdge(
        StructuredPanelMesh panel,
        int offset,
        int firstIndex,
        int secondIndex,
        ISet<(int A, int B)> visited,
        ICollection<(int A, int B, double RestLength)> destination)
    {
        int localA = Math.Min(firstIndex, secondIndex);
        int localB = Math.Max(firstIndex, secondIndex);
        if (!visited.Add((localA, localB)))
        {
            return;
        }
        StructuredPanelVertex first = panel.Vertices[localA];
        StructuredPanelVertex second = panel.Vertices[localB];
        double restLength = Math.Sqrt(
            Math.Pow(second.X - first.X, 2) +
            Math.Pow(second.Y - first.Y, 2));
        destination.Add((offset + localA, offset + localB, restLength));
    }

    private static void AddEdgeStrain(
        ArrangedPanelMesh panel,
        int firstIndex,
        int secondIndex,
        ISet<(string PanelId, int A, int B)> visited,
        ICollection<double> destination,
        ICollection<double> panelDestination,
        ISet<int>? excludedVertices = null)
    {
        int a = Math.Min(firstIndex, secondIndex);
        int b = Math.Max(firstIndex, secondIndex);
        if (excludedVertices is not null &&
            (excludedVertices.Contains(a) || excludedVertices.Contains(b)))
        {
            return;
        }
        if (!visited.Add((panel.PanelId, a, b)))
        {
            return;
        }
        ArrangedPanelVertex first = panel.Vertices[a];
        ArrangedPanelVertex second = panel.Vertices[b];
        double restLength = Math.Sqrt(
            Math.Pow(second.RestX - first.RestX, 2) +
            Math.Pow(second.RestY - first.RestY, 2));
        double arrangedLength = Distance(ToPoint(first), ToPoint(second));
        double strain = Math.Abs(arrangedLength - restLength) / Math.Max(restLength, 0.000001);
        destination.Add(strain);
        panelDestination.Add(strain);
    }

    private static double Percentile(IReadOnlyList<double> sortedValues, double percentile)
    {
        int index = Math.Clamp(
            (int)Math.Ceiling(sortedValues.Count * percentile) - 1,
            0,
            sortedValues.Count - 1);
        return sortedValues[index];
    }

    private static double RowPolylineLength(StructuredPanelMesh mesh, int row)
    {
        double length = 0;
        for (int column = 1; column <= mesh.Columns; column++)
        {
            StructuredPanelVertex previous = mesh.Vertices[row * (mesh.Columns + 1) + column - 1];
            StructuredPanelVertex current = mesh.Vertices[row * (mesh.Columns + 1) + column];
            length += Math.Sqrt(
                Math.Pow(current.X - previous.X, 2) +
                Math.Pow(current.Y - previous.Y, 2));
        }
        return length;
    }

    private static double RowCumulativeLength(StructuredPanelMesh mesh, int row, int column)
    {
        double length = 0;
        for (int currentColumn = 1; currentColumn <= column; currentColumn++)
        {
            StructuredPanelVertex previous = mesh.Vertices[
                row * (mesh.Columns + 1) + currentColumn - 1];
            StructuredPanelVertex current = mesh.Vertices[
                row * (mesh.Columns + 1) + currentColumn];
            length += Math.Sqrt(
                Math.Pow(current.X - previous.X, 2) +
                Math.Pow(current.Y - previous.Y, 2));
        }
        return length;
    }

    private static double BoundaryLength(StructuredPanelMesh mesh, params string[] edgeIds)
    {
        double length = 0;
        foreach (string edgeId in edgeIds)
        {
            IReadOnlyList<int> edge = mesh.EdgeVertexIndices[edgeId];
            for (int index = 1; index < edge.Count; index++)
            {
                StructuredPanelVertex previous = mesh.Vertices[edge[index - 1]];
                StructuredPanelVertex current = mesh.Vertices[edge[index]];
                length += Math.Sqrt(
                    Math.Pow(current.X - previous.X, 2) +
                    Math.Pow(current.Y - previous.Y, 2));
            }
        }
        return length;
    }

    private static double EllipseRadius(double radiusX, double radiusY, double angle)
        => radiusX * radiusY / Math.Sqrt(
            Math.Pow(radiusY * Math.Cos(angle), 2) +
            Math.Pow(radiusX * Math.Sin(angle), 2));

    private static double NormalizeAngle(double angle)
    {
        double normalized = angle % (2.0 * Math.PI);
        if (normalized < -Math.PI)
        {
            normalized += 2.0 * Math.PI;
        }
        else if (normalized >= Math.PI)
        {
            normalized -= 2.0 * Math.PI;
        }
        return normalized;
    }

    private static ArrangedPoint3 Normalize(ArrangedPoint3 vector)
    {
        double length = Math.Sqrt(vector.X * vector.X + vector.Y * vector.Y + vector.Z * vector.Z);
        return vector / Math.Max(length, 0.000001);
    }

    private static ArrangedPoint3 ToPoint(ArrangedPanelVertex vertex)
        => new(vertex.X, vertex.Y, vertex.Z);

    private static double TriangleArea(ArrangedPoint3 a, ArrangedPoint3 b, ArrangedPoint3 c)
    {
        ArrangedPoint3 first = b - a;
        ArrangedPoint3 second = c - a;
        ArrangedPoint3 cross = new(
            first.Y * second.Z - first.Z * second.Y,
            first.Z * second.X - first.X * second.Z,
            first.X * second.Y - first.Y * second.X);
        return 0.5 * Math.Sqrt(cross.X * cross.X + cross.Y * cross.Y + cross.Z * cross.Z);
    }

    private static double Distance(ArrangedPoint3 first, ArrangedPoint3 second)
        => Math.Sqrt(
            Math.Pow(second.X - first.X, 2) +
            Math.Pow(second.Y - first.Y, 2) +
            Math.Pow(second.Z - first.Z, 2));

    private static double Lerp(double first, double second, double blend)
        => first + (second - first) * blend;
}
