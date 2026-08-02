using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Patterna;

namespace Patterna.UnrealGarmentCompiler;

public sealed record FullGarmentUsdExport(
    string GarmentId,
    string Usd,
    string RenderObj,
    string ManifestJson,
    string UsdSha256,
    string RenderObjSha256,
    int SimulationVertexCount,
    int SimulationTriangleCount,
    int RenderMeshCount,
    int SeamCount,
    int StitchCount,
    int ClosureCount,
    int ClosureConstraintCount);

public static class FullGarmentUsdExporter
{
    public static FullGarmentUsdExport Export(
        FullGarmentArrangementReport arrangement,
        GarmentDocument garment,
        string garmentId = "PatternaWrapDress")
    {
        ArgumentNullException.ThrowIfNull(arrangement);
        ArgumentNullException.ThrowIfNull(garment);
        if (arrangement.Panels.Count != garment.Panels.Count)
        {
            throw new InvalidOperationException(
                $"USD export received {arrangement.Panels.Count} arranged panels for {garment.Panels.Count} garment panels.");
        }
        if (arrangement.Stitches.Count == 0)
        {
            throw new InvalidOperationException("USD export requires explicit sewing constraints.");
        }
        if (arrangement.MaximumSeamGapCm > 90.0)
        {
            throw new InvalidOperationException(
                $"USD export refuses a staged sewing gap of {arrangement.MaximumSeamGapCm:F4} cm because it exceeds 90 cm.");
        }
        if (arrangement.Closures.Any(closure => closure.TargetDistanceCm > 0.000001))
        {
            throw new InvalidOperationException(
                "USD SewingAPI closure export currently supports zero-distance fasteners only.");
        }

        WeldedRenderSurface renderSurface = WeldedRenderSurfaceBuilder.Build(
            arrangement,
            subdivisionLevel: 1);

        string rootName = UsdIdentifier(garmentId);
        Dictionary<string, int> vertexOffsets = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, int> faceOffsets = new(StringComparer.OrdinalIgnoreCase);
        int vertexOffset = 0;
        int faceOffset = 0;
        foreach (ArrangedPanelMesh panel in arrangement.Panels)
        {
            vertexOffsets[panel.PanelId] = vertexOffset;
            faceOffsets[panel.PanelId] = faceOffset;
            vertexOffset += panel.Vertices.Count;
            faceOffset += panel.Triangles.Count;
        }

        double restScaleX = arrangement.Panels.Max(panel =>
            panel.Vertices.Max(vertex => vertex.RestX) - panel.Vertices.Min(vertex => vertex.RestX));
        double restScaleY = arrangement.Panels.Max(panel =>
            panel.Vertices.Max(vertex => vertex.RestY) - panel.Vertices.Min(vertex => vertex.RestY));
        List<string> simulationPoints = [];
        List<string> simulationUvs = [];
        List<string> simulationFaceIndices = [];
        foreach (ArrangedPanelMesh panel in arrangement.Panels)
        {
            double minimumX = panel.Vertices.Min(vertex => vertex.RestX);
            double minimumY = panel.Vertices.Min(vertex => vertex.RestY);
            foreach (ArrangedPanelVertex vertex in panel.Vertices)
            {
                simulationPoints.Add(FormatUsdPointFromUnreal(vertex.X, vertex.Y, vertex.Z));
                simulationUvs.Add(FormatVector2(
                    (vertex.RestX - minimumX) / Math.Max(restScaleX, 0.000001),
                    1.0 - (vertex.RestY - minimumY) / Math.Max(restScaleY, 0.000001)));
            }
            int offset = vertexOffsets[panel.PanelId];
            foreach (StructuredPanelTriangle triangle in panel.Triangles)
            {
                int a = offset + triangle.A;
                int b = offset + triangle.B;
                int c = offset + triangle.C;
                if (!panel.ReverseWinding)
                {
                    (b, c) = (c, b);
                }
                simulationFaceIndices.Add(a.ToString(CultureInfo.InvariantCulture));
                simulationFaceIndices.Add(b.ToString(CultureInfo.InvariantCulture));
                simulationFaceIndices.Add(c.ToString(CultureInfo.InvariantCulture));
            }
        }

        StringBuilder usd = new();
        usd.AppendLine("#usda 1.0");
        usd.AppendLine("(");
        usd.AppendLine($"    defaultPrim = \"{rootName}\"");
        usd.AppendLine("    metersPerUnit = 0.01");
        usd.AppendLine("    upAxis = \"Z\"");
        usd.AppendLine(")");
        usd.AppendLine();
        usd.AppendLine($"def Scope \"{rootName}\" (");
        usd.AppendLine("    kind = \"component\"");
        usd.AppendLine("    prepend apiSchemas = [\"ClothRootAPI\", \"ClothSolverAPI:clo\"]");
        usd.AppendLine(")");
        usd.AppendLine("{");
        usd.AppendLine($"    rel solver:clo:properties = </{rootName}/CloSolverProperties>");
        usd.AppendLine();
        usd.AppendLine("    def Scope \"CloSolverProperties\" (");
        usd.AppendLine("        prepend apiSchemas = [\"CloSolverPropertiesAPI\"]");
        usd.AppendLine("    )");
        usd.AppendLine("    {");
        usd.AppendLine("        float airDamping = 0.12");
        usd.AppendLine("        float3 gravity = (0, 0, -981)");
        usd.AppendLine("        uint subStepCount = 6");
        usd.AppendLine("        float timeStep = 0.016667");
        usd.AppendLine("    }");
        usd.AppendLine();
        usd.AppendLine("    def Mesh \"SimulationMesh\" (");
        usd.AppendLine("        prepend apiSchemas = [\"SimMeshDataAPI\"]");
        usd.AppendLine("    )");
        usd.AppendLine("    {");
        usd.AppendLine("        uniform token purpose = \"guide\"");
        usd.AppendLine($"        float2 restPositionScale = ({Format(restScaleX)}, {Format(restScaleY)})");
        AppendArray(usd, "        point3f[] points", simulationPoints);
        AppendRepeatedIntegerArray(usd, "        int[] faceVertexCounts", 3, faceOffset);
        AppendArray(usd, "        int[] faceVertexIndices", simulationFaceIndices);
        AppendArray(usd, "        texCoord2f[] primvars:st", simulationUvs);
        usd.AppendLine("        uniform token primvars:st:interpolation = \"vertex\"");

        string fabricAttributes = BuildFabricAttributes(garment.Fabric);
        foreach (ArrangedPanelMesh panel in arrangement.Panels)
        {
            string panelName = UsdIdentifier(panel.PanelId);
            int startFace = faceOffsets[panel.PanelId];
            string faces = string.Join(", ", Enumerable.Range(startFace, panel.Triangles.Count));
            usd.AppendLine();
            usd.AppendLine($"        def GeomSubset \"{panelName}\" (");
            usd.AppendLine("            prepend apiSchemas = [\"SimPatternAPI\"]");
            usd.AppendLine("        )");
            usd.AppendLine("        {");
            usd.AppendLine("            uniform token elementType = \"face\"");
            usd.AppendLine("            uniform token familyName = \"pattern\"");
            usd.AppendLine($"            int[] indices = [{faces}]");
            usd.Append(fabricAttributes);
            usd.AppendLine("        }");
        }

        foreach (IGrouping<string, ArrangedSeamStitch> seamGroup in arrangement.Stitches
            .GroupBy(stitch => stitch.SeamId, StringComparer.OrdinalIgnoreCase))
        {
            ArrangedSeamStitch first = seamGroup.First();
            string seamName = UsdIdentifier(seamGroup.Key);
            List<string> stitchIndices = [];
            foreach (ArrangedSeamStitch stitch in seamGroup.OrderBy(stitch => stitch.NormalizedPosition))
            {
                stitchIndices.Add((vertexOffsets[stitch.PanelA] + stitch.VertexA)
                    .ToString(CultureInfo.InvariantCulture));
                stitchIndices.Add((vertexOffsets[stitch.PanelB] + stitch.VertexB)
                    .ToString(CultureInfo.InvariantCulture));
            }
            usd.AppendLine();
            usd.AppendLine($"        def GeomSubset \"{seamName}\" (");
            usd.AppendLine("            prepend apiSchemas = [\"SewingAPI\"]");
            usd.AppendLine("        )");
            usd.AppendLine("        {");
            usd.AppendLine("            uniform token elementType = \"edge\"");
            usd.AppendLine("            uniform token familyName = \"sewing\"");
            AppendArray(usd, "            int[] indices", stitchIndices);
            usd.AppendLine($"            rel patternA = </{rootName}/SimulationMesh/{UsdIdentifier(first.PanelA)}>");
            usd.AppendLine($"            rel patternB = </{rootName}/SimulationMesh/{UsdIdentifier(first.PanelB)}>");
            usd.AppendLine("        }");
        }
        foreach (IGrouping<string, ArrangedClosureConstraint> closureGroup in arrangement.Closures
            .GroupBy(closure => closure.ClosureId, StringComparer.OrdinalIgnoreCase))
        {
            ArrangedClosureConstraint first = closureGroup.First();
            string closureName = $"Closure{UsdIdentifier(closureGroup.Key)}";
            List<string> constraintIndices = [];
            foreach (ArrangedClosureConstraint closure in closureGroup.OrderBy(closure => closure.NormalizedPosition))
            {
                constraintIndices.Add((vertexOffsets[closure.PanelA] + closure.VertexA)
                    .ToString(CultureInfo.InvariantCulture));
                constraintIndices.Add((vertexOffsets[closure.PanelB] + closure.VertexB)
                    .ToString(CultureInfo.InvariantCulture));
            }
            usd.AppendLine();
            usd.AppendLine($"        def GeomSubset \"{closureName}\" (");
            usd.AppendLine("            prepend apiSchemas = [\"SewingAPI\"]");
            usd.AppendLine("        )");
            usd.AppendLine("        {");
            usd.AppendLine("            uniform token elementType = \"edge\"");
            usd.AppendLine("            uniform token familyName = \"sewing\"");
            usd.AppendLine("            custom string patterna:constraintSemantic = \"closure\"");
            usd.AppendLine($"            custom string patterna:closureKind = \"{first.Kind}\"");
            usd.AppendLine($"            custom float patterna:strength = {Format(first.Strength)}");
            AppendArray(usd, "            int[] indices", constraintIndices);
            usd.AppendLine($"            rel patternA = </{rootName}/SimulationMesh/{UsdIdentifier(first.PanelA)}>");
            usd.AppendLine($"            rel patternB = </{rootName}/SimulationMesh/{UsdIdentifier(first.PanelB)}>");
            usd.AppendLine("        }");
        }
        usd.AppendLine("    }");

        AppendRenderSurface(usd, rootName, renderSurface);
        AppendMaterial(usd, rootName);
        usd.AppendLine("}");

        string usdText = usd.ToString().Replace("\r\n", "\n", StringComparison.Ordinal);
        string usdHash = Sha256(usdText);
        string renderObj = BuildRenderObj(renderSurface, arrangement, garment);
        string renderObjHash = Sha256(renderObj);
        int constructionLineCount = arrangement.Stitches
            .Select(stitch => stitch.SeamId)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Count();
        int openBoundaryLineCount = CountOpenBoundaryLines(arrangement, garment);
        var manifest = new
        {
            schemaVersion = "patterna.full-garment-usd/1.1",
            garmentId = rootName,
            units = "centimeters",
            usdSha256 = usdHash,
            simulation = new
            {
                panelCount = arrangement.Panels.Count,
                vertexCount = vertexOffset,
                triangleCount = faceOffset,
                seamCount = arrangement.Stitches.Select(stitch => stitch.SeamId).Distinct(StringComparer.OrdinalIgnoreCase).Count(),
                stitchCount = arrangement.Stitches.Count,
                closureCount = arrangement.Closures.Select(closure => closure.ClosureId).Distinct(StringComparer.OrdinalIgnoreCase).Count(),
                closureConstraintCount = arrangement.Closures.Count,
                arrangement.MinimumTriangleAreaCm2,
                arrangement.MaximumSeamGapCm,
                arrangement.MaximumClosureGapCm,
                arrangement.MaximumEdgeStrainRatio,
                arrangement.NinetyFifthPercentileEdgeStrainRatio,
                arrangement.MinimumTorsoClearanceCm
            },
            panels = arrangement.Panels.Select(panel => new
            {
                id = panel.PanelId,
                pieceId = panel.PieceId,
                panel.Placement,
                panel.ReverseWinding,
                vertexCount = panel.Vertices.Count,
                triangleCount = panel.Triangles.Count
            }),
            seams = arrangement.Stitches
                .GroupBy(stitch => stitch.SeamId, StringComparer.OrdinalIgnoreCase)
                .Select(group => new
                {
                    id = group.Key,
                    panelA = group.First().PanelA,
                    panelB = group.First().PanelB,
                    stitchCount = group.Count(),
                    maximumGapCm = group.Max(stitch => stitch.GapCm)
                }),
            closures = arrangement.Closures
                .GroupBy(closure => closure.ClosureId, StringComparer.OrdinalIgnoreCase)
                .Select(group => new
                {
                    id = group.Key,
                    kind = group.First().Kind,
                    state = GarmentClosureStates.Closed,
                    panelA = group.First().PanelA,
                    panelB = group.First().PanelB,
                    constraintCount = group.Count(),
                    targetDistanceCm = group.First().TargetDistanceCm,
                    strength = group.First().Strength,
                    maximumInitialGapCm = group.Max(closure => closure.InitialGapCm)
                }),
            fabric = new
            {
                source = garment.Fabric,
                chaos = BuildChaosFabricManifest(garment.Fabric)
            },
            render = new
            {
                meshCount = 1,
                topology = "welded boundary-constrained fairing and Loop render surface",
                sourceVertexCount = renderSurface.SourceVertexCount,
                weldedBaseVertexCount = renderSurface.WeldedBaseVertexCount,
                vertexCount = renderSurface.Vertices.Count,
                triangleCount = renderSurface.Triangles.Count,
                subdivisionLevel = renderSurface.SubdivisionLevel,
                refinementAlgorithm = renderSurface.RefinementAlgorithm,
                protectedBoundaryVertexCount = renderSurface.ProtectedBoundaryVertexCount,
                protectedNonManifoldVertexCount = renderSurface.ProtectedNonManifoldVertexCount,
                maximumBaseVertexDisplacementCm = renderSurface.MaximumBaseVertexDisplacementCm,
                averageBaseVertexDisplacementCm = renderSurface.AverageBaseVertexDisplacementCm,
                weldedConstructionStitchCount = renderSurface.WeldedConstructionStitchCount,
                unweldedConstructionStitchCount = renderSurface.UnweldedConstructionStitchCount,
                maximumWeldedGapCm = renderSurface.MaximumWeldedGapCm,
                material = "PatternaFabric",
                doubleSided = true,
                objSha256 = renderObjHash,
                uvCoordinateSource = "authoritative 2D panel rest coordinates",
                uvInterpolation = "face-varying",
                constructionLineCount,
                openBoundaryLineCount
            },
            coordinateSystem = new
            {
                source = "Unreal left-handed Z-up",
                interchange = "OpenUSD right-handed Z-up",
                reflectedAxis = "Y",
                windingReversed = true
            }
        };
        string manifestJson = JsonSerializer.Serialize(manifest, new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = true
        });
        return new FullGarmentUsdExport(
            rootName,
            usdText,
            renderObj,
            manifestJson,
            usdHash,
            renderObjHash,
            vertexOffset,
            faceOffset,
            1,
            arrangement.Stitches.Select(stitch => stitch.SeamId).Distinct(StringComparer.OrdinalIgnoreCase).Count(),
            arrangement.Stitches.Count,
            arrangement.Closures.Select(closure => closure.ClosureId).Distinct(StringComparer.OrdinalIgnoreCase).Count(),
            arrangement.Closures.Count);
    }

    private sealed record ObjLineStrip(string Group, IReadOnlyList<ArrangedPoint3> Points);

    private static string BuildRenderObj(
        WeldedRenderSurface surface,
        FullGarmentArrangementReport arrangement,
        GarmentDocument garment)
    {
        List<ObjLineStrip> lineStrips = BuildConstructionLineStrips(arrangement, garment);
        StringBuilder vertices = new();
        StringBuilder textureCoordinates = new();
        StringBuilder faces = new();
        StringBuilder lines = new();

        vertices.AppendLine("# Patterna welded thin-cloth render surface");
        vertices.AppendLine("# Coordinates are centimeters in OBJ Y-up space");
        vertices.AppendLine("o PatternaGarment");
        foreach (RenderSurfaceVertex vertex in surface.Vertices)
        {
            vertices.AppendLine($"v {Format(vertex.X)} {Format(vertex.Z)} {Format(vertex.Y)}");
        }

        List<(string Group, int[] Indices)> objLines = [];
        int nextVertexIndex = surface.Vertices.Count + 1;
        foreach (ObjLineStrip strip in lineStrips)
        {
            int[] indices = new int[strip.Points.Count];
            for (int index = 0; index < strip.Points.Count; ++index)
            {
                ArrangedPoint3 point = strip.Points[index];
                vertices.AppendLine($"v {Format(point.X)} {Format(point.Z)} {Format(point.Y)}");
                indices[index] = nextVertexIndex++;
            }
            objLines.Add((strip.Group, indices));
        }

        int textureIndex = 1;
        foreach (RenderSurfaceTriangle triangle in surface.Triangles)
        {
            textureCoordinates.AppendLine($"vt {Format(triangle.UvA.X)} {Format(triangle.UvA.Y)}");
            textureCoordinates.AppendLine($"vt {Format(triangle.UvB.X)} {Format(triangle.UvB.Y)}");
            textureCoordinates.AppendLine($"vt {Format(triangle.UvC.X)} {Format(triangle.UvC.Y)}");
            faces.AppendLine(
                $"f {triangle.A + 1}/{textureIndex} " +
                $"{triangle.B + 1}/{textureIndex + 1} " +
                $"{triangle.C + 1}/{textureIndex + 2}");
            textureIndex += 3;
        }

        string? activeGroup = null;
        foreach ((string group, int[] indices) in objLines)
        {
            if (!string.Equals(activeGroup, group, StringComparison.Ordinal))
            {
                lines.AppendLine($"g {group}");
                activeGroup = group;
            }
            lines.AppendLine($"l {string.Join(' ', indices)}");
        }

        StringBuilder result = new();
        result.Append(vertices);
        result.Append(textureCoordinates);
        result.AppendLine("g patterna_surface");
        result.Append(faces);
        result.Append(lines);
        return result.ToString().Replace("\r\n", "\n", StringComparison.Ordinal);
    }

    private static List<ObjLineStrip> BuildConstructionLineStrips(
        FullGarmentArrangementReport arrangement,
        GarmentDocument garment)
    {
        Dictionary<string, ArrangedPanelMesh> panels = arrangement.Panels.ToDictionary(
            panel => panel.PanelId,
            StringComparer.OrdinalIgnoreCase);
        List<ObjLineStrip> result = [];

        foreach (IGrouping<string, ArrangedSeamStitch> seam in arrangement.Stitches
            .GroupBy(stitch => stitch.SeamId, StringComparer.OrdinalIgnoreCase)
            .OrderBy(group => group.Key, StringComparer.OrdinalIgnoreCase))
        {
            ArrangedPoint3[] points = seam
                .OrderBy(stitch => stitch.NormalizedPosition)
                .Select(stitch =>
                {
                    ArrangedPanelVertex a = panels[stitch.PanelA].Vertices[stitch.VertexA];
                    ArrangedPanelVertex b = panels[stitch.PanelB].Vertices[stitch.VertexB];
                    return new ArrangedPoint3(
                        (a.X + b.X) * 0.5,
                        (a.Y + b.Y) * 0.5,
                        (a.Z + b.Z) * 0.5);
                })
                .ToArray();
            if (points.Length >= 2)
            {
                result.Add(new ObjLineStrip("patterna_seams", points));
            }
        }

        Dictionary<string, HashSet<string>> sewnEdges = arrangement.Panels.ToDictionary(
            panel => panel.PanelId,
            _ => new HashSet<string>(StringComparer.OrdinalIgnoreCase),
            StringComparer.OrdinalIgnoreCase);
        foreach (GarmentSeamDocument seam in garment.Seams)
        {
            AddEdges(sewnEdges, seam.SideA);
            AddEdges(sewnEdges, seam.SideB);
        }

        foreach (ArrangedPanelMesh panel in arrangement.Panels.OrderBy(
            panel => panel.PanelId,
            StringComparer.OrdinalIgnoreCase))
        {
            foreach ((string edgeId, IReadOnlyList<int> vertexIndices) in panel.EdgeVertexIndices
                .OrderBy(edge => edge.Key, StringComparer.OrdinalIgnoreCase))
            {
                if (sewnEdges[panel.PanelId].Contains(edgeId) || vertexIndices.Count < 2)
                {
                    continue;
                }
                ArrangedPoint3[] points = vertexIndices
                    .Select(vertexIndex => panel.Vertices[vertexIndex])
                    .Select(vertex => new ArrangedPoint3(vertex.X, vertex.Y, vertex.Z))
                    .ToArray();
                result.Add(new ObjLineStrip("patterna_edges", points));
            }
        }
        return result;
    }

    private static int CountOpenBoundaryLines(
        FullGarmentArrangementReport arrangement,
        GarmentDocument garment)
        => BuildConstructionLineStrips(arrangement, garment)
            .Count(strip => strip.Group == "patterna_edges");

    private static void AddEdges(
        IReadOnlyDictionary<string, HashSet<string>> destination,
        SeamSideDocument side)
    {
        if (!destination.TryGetValue(side.PanelId, out HashSet<string>? edges))
        {
            throw new InvalidOperationException(
                $"Construction seam references unknown panel {side.PanelId}.");
        }
        foreach (string edgeId in side.EdgeIds)
        {
            edges.Add(edgeId);
        }
    }

    private static object BuildChaosFabricManifest(FabricPhysicsDocument fabric)
    {
        double density = fabric.MassGramsPerSquareMeter / 10_000_000.0;
        double stretchWarp = 120_000.0 / (1.0 + fabric.WarpStretchPercent / 10.0);
        double stretchWeft = 120_000.0 / (1.0 + fabric.WeftStretchPercent / 10.0);
        double shear = 3_000.0 + fabric.ShearResistance * 150.0;
        double bendWarp = 0.05 + fabric.BendResistance * 0.006;
        double bendWeft = 0.03 + fabric.BendResistance * 0.003;
        double bendBias = 0.04 + fabric.BendResistance * 0.0045;
        double damping = Math.Clamp(0.08 + fabric.MassGramsPerSquareMeter / 2_000.0, 0.08, 0.35);
        return new
        {
            densityKgPerSquareCm = density,
            stretchWarp,
            stretchWeft,
            shearLeft = shear,
            shearRight = shear,
            bendWarp,
            bendWeft,
            bendBias,
            damping,
            friction = fabric.DynamicFriction
        };
    }

    private static void AppendRenderSurface(
        StringBuilder usd,
        string rootName,
        WeldedRenderSurface surface)
    {
        usd.AppendLine();
        usd.AppendLine("    def Mesh \"RenderSurface\" (");
        usd.AppendLine("        prepend apiSchemas = [\"MaterialBindingAPI\"]");
        usd.AppendLine("    )");
        usd.AppendLine("    {");
        usd.AppendLine("        bool doubleSided = 1");
        AppendArray(usd, "        point3f[] points", surface.Vertices.Select(vertex =>
            FormatUsdPointFromUnreal(vertex.X, vertex.Y, vertex.Z)));
        AppendRepeatedIntegerArray(usd, "        int[] faceVertexCounts", 3, surface.Triangles.Count);
        List<string> indices = [];
        List<string> faceVaryingUvs = [];
        foreach (RenderSurfaceTriangle triangle in surface.Triangles)
        {
            indices.Add(triangle.A.ToString(CultureInfo.InvariantCulture));
            indices.Add(triangle.B.ToString(CultureInfo.InvariantCulture));
            indices.Add(triangle.C.ToString(CultureInfo.InvariantCulture));
            faceVaryingUvs.Add(FormatVector2(triangle.UvA.X, triangle.UvA.Y));
            faceVaryingUvs.Add(FormatVector2(triangle.UvB.X, triangle.UvB.Y));
            faceVaryingUvs.Add(FormatVector2(triangle.UvC.X, triangle.UvC.Y));
        }
        AppendArray(usd, "        int[] faceVertexIndices", indices);
        AppendArray(usd, "        texCoord2f[] primvars:st", faceVaryingUvs);
        usd.AppendLine("        uniform token primvars:st:interpolation = \"faceVarying\"");
        usd.AppendLine("        rel material:binding = <" + $"/{rootName}/Materials/PatternaFabric" + ">");
        usd.AppendLine();
        usd.AppendLine("        def GeomSubset \"GarmentRender\" (");
        usd.AppendLine("            prepend apiSchemas = [\"RenderPatternAPI\"]");
        usd.AppendLine("        )");
        usd.AppendLine("        {");
        usd.AppendLine("            uniform token elementType = \"face\"");
        usd.AppendLine("            uniform token familyName = \"pattern\"");
        usd.AppendLine($"            int[] indices = [{string.Join(", ", Enumerable.Range(0, surface.Triangles.Count))}]");
        usd.AppendLine("        }");
        usd.AppendLine("    }");
    }

    private static string BuildFabricAttributes(FabricPhysicsDocument fabric)
    {
        double density = fabric.MassGramsPerSquareMeter / 10_000_000.0;
        double stretchWarp = 120_000.0 / (1.0 + fabric.WarpStretchPercent / 10.0);
        double stretchWeft = 120_000.0 / (1.0 + fabric.WeftStretchPercent / 10.0);
        double shear = 3_000.0 + fabric.ShearResistance * 150.0;
        double bendWarp = 0.05 + fabric.BendResistance * 0.006;
        double bendWeft = 0.03 + fabric.BendResistance * 0.003;
        double bendBias = 0.04 + fabric.BendResistance * 0.0045;
        double damping = Math.Clamp(0.08 + fabric.MassGramsPerSquareMeter / 2_000.0, 0.08, 0.35);
        StringBuilder result = new();
        void Attribute(string name, double value)
            => result.AppendLine($"            float[] primvars:clo:{name} = [{Format(value)}]");
        Attribute("bendingBiasLeft", bendBias);
        Attribute("bendingBiasRight", bendBias);
        Attribute("bendingWarp", bendWarp);
        Attribute("bendingWeft", bendWeft);
        Attribute("bucklingRatioBiasLeft", 0.35);
        Attribute("bucklingRatioBiasRight", 0.35);
        Attribute("bucklingRatioWarp", 0.4);
        Attribute("bucklingRatioWeft", 0.3);
        Attribute("bucklingStiffnessBiasLeft", 0.5);
        Attribute("bucklingStiffnessBiasRight", 0.5);
        Attribute("bucklingStiffnessWarp", 0.55);
        Attribute("bucklingStiffnessWeft", 0.45);
        Attribute("density", density);
        Attribute("friction", fabric.DynamicFriction);
        Attribute("internalDamping", damping);
        Attribute("shearLeft", shear);
        Attribute("shearRight", shear);
        result.AppendLine("            float2[] primvars:clo:shrinkage = [(1, 1)]");
        Attribute("stretchWarp", stretchWarp);
        Attribute("stretchWeft", stretchWeft);
        Attribute("thickness", fabric.ThicknessMillimeters);
        return result.ToString();
    }

    private static void AppendMaterial(StringBuilder usd, string rootName)
    {
        usd.AppendLine();
        usd.AppendLine("    def Scope \"Materials\"");
        usd.AppendLine("    {");
        usd.AppendLine("        def Material \"PatternaFabric\"");
        usd.AppendLine("        {");
        usd.AppendLine($"            token outputs:surface.connect = </{rootName}/Materials/PatternaFabric/Surface.outputs:surface>");
        usd.AppendLine("            def Shader \"Surface\"");
        usd.AppendLine("            {");
        usd.AppendLine("                uniform token info:id = \"UsdPreviewSurface\"");
        usd.AppendLine("                color3f inputs:diffuseColor = (0.31, 0.035, 0.075)");
        usd.AppendLine("                float inputs:metallic = 0");
        usd.AppendLine("                float inputs:roughness = 0.76");
        usd.AppendLine("                float inputs:clearcoat = 0.02");
        usd.AppendLine("                token outputs:surface");
        usd.AppendLine("            }");
        usd.AppendLine("        }");
        usd.AppendLine("    }");
    }

    private static void AppendRepeatedIntegerArray(
        StringBuilder destination,
        string declaration,
        int value,
        int count)
        => AppendArray(
            destination,
            declaration,
            Enumerable.Repeat(value.ToString(CultureInfo.InvariantCulture), count));

    private static void AppendArray(
        StringBuilder destination,
        string declaration,
        IEnumerable<string> values)
    {
        destination.Append(declaration);
        destination.Append(" = [");
        destination.Append(string.Join(", ", values));
        destination.AppendLine("]");
    }

    private static string UsdIdentifier(string source)
    {
        StringBuilder result = new();
        bool capitalize = true;
        foreach (char character in source)
        {
            if (!char.IsLetterOrDigit(character))
            {
                capitalize = true;
                continue;
            }
            result.Append(capitalize ? char.ToUpperInvariant(character) : character);
            capitalize = false;
        }
        if (result.Length == 0 || char.IsDigit(result[0]))
        {
            result.Insert(0, 'P');
        }
        return result.ToString();
    }

    private static string FormatVector3(double x, double y, double z)
        => $"({Format(x)}, {Format(y)}, {Format(z)})";

    private static string FormatUsdPointFromUnreal(double x, double y, double z)
        => FormatVector3(x, -y, z);

    private static string FormatVector2(double x, double y)
        => $"({Format(x)}, {Format(y)})";

    private static string Format(double value)
        => value.ToString("0.######", CultureInfo.InvariantCulture);

    private static string Sha256(string source)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(source))).ToLowerInvariant();
}
