using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json.Serialization;

namespace Patterna.UnrealGarmentCompiler;

public sealed record GarmentPrefitPoint(double X, double Y, double Z);

public sealed record GarmentPrefitPanel(
    string PanelId,
    IReadOnlyList<GarmentPrefitPoint> Vertices);

public sealed record GarmentPrefitMeshDocument(
    string SourcePath,
    IReadOnlyList<GarmentPrefitPanel> Panels,
    int TriangleCount,
    string? SolverReportPath,
    bool SolverAccepted,
    string? SolverBody,
    string? SolverConfigPath,
    string? SolverConfigSha256,
    double? FabricThicknessCm,
    double? FabricDensity,
    double? FabricFriction,
    double? FabricEdgeBendingStiffness,
    int? ClothVertexCount,
    int? BodyVertexCount,
    int? BodyFaceCount,
    int? BodyCollisionCount,
    int? SelfCollisionCount,
    double? BodyCollisionRate,
    double? SelfCollisionRate,
    string? SolverReportSchemaVersion,
    string? SolverName,
    bool SolverFinitePositions,
    bool SolverEquilibriumGateEvaluated,
    bool SolverStaticEquilibriumReached,
    bool SolverCollisionGateEvaluated,
    bool SolverSeamClosureGateEvaluated,
    int? SolverMaximumBodyCollisions,
    int? SolverMaximumSelfCollisions,
    int? SolverSeamLinkCount,
    double? SolverMaximumSeamSeparationCm,
    double? SolverMeanSeamSeparationCm,
    double? SolverNinetyFifthPercentileSeamSeparationCm,
    double? SolverMaximumSeamSeparationLimitCm,
    int? SolverEvaluatedEdgeCount,
    int? SolverMaterialRestLengthEdgeCount,
    int? SolverReferenceGeometryEdgeCount,
    int? SolverExcludedEdgeCount,
    double? SolverMaximumEdgeStrainRatio,
    double? SolverNinetyFifthPercentileEdgeStrainRatio,
    double? SolverNinetyNinthPointNinthPercentileEdgeStrainRatio,
    double? SolverNinetyNinthPointNinetyNinthPercentileEdgeStrainRatio,
    double? SolverMaximumEdgeStrainLimit,
    double? SolverNinetyFifthPercentileEdgeStrainLimit,
    double? SolverNinetyNinthPointNinthPercentileEdgeStrainLimit,
    double? SolverNinetyNinthPointNinetyNinthPercentileEdgeStrainLimit,
    int? SolverHighStrainEdgeCount,
    double? SolverHighStrainEdgeFraction,
    double? SolverMaximumHighStrainEdgeFraction,
    bool? SolverEdgeContactBufferSaturated,
    int? SolverMaximumObservedEdgeContacts,
    int? SolverEdgeContactCapacity,
    int? SolverEdgeContactsPerSpring,
    int? SolverSimulationSubsteps,
    bool SolverPhysicalIdentityVerified,
    IReadOnlyList<string> SolverRejectionReasons)
{
    private sealed record WarpFabricReport(
        [property: JsonPropertyName("thickness_cm")] double ThicknessCm,
        double Density,
        double Friction,
        [property: JsonPropertyName("edge_bending_stiffness")] double EdgeBendingStiffness);

    private sealed record WarpPrefitReport(
        [property: JsonPropertyName("schema_version")] string? SchemaVersion,
        [property: JsonPropertyName("garment_topology_mode")] string? GarmentTopologyMode,
        [property: JsonPropertyName("pattern_specification_path")] string? PatternSpecificationPath,
        [property: JsonPropertyName("pattern_specification_sha256")] string? PatternSpecificationSha256,
        [property: JsonPropertyName("mesh_resolution_cm")] double? MeshResolutionCm,
        [property: JsonPropertyName("physical_mesh_path")] string? PhysicalMeshPath,
        [property: JsonPropertyName("physical_mesh_sha256")] string? PhysicalMeshSha256,
        [property: JsonPropertyName("physical_topology_sha256")] string? PhysicalTopologySha256,
        [property: JsonPropertyName("physical_vertex_count")] int? PhysicalVertexCount,
        [property: JsonPropertyName("physical_face_count")] int? PhysicalFaceCount,
        [property: JsonPropertyName("texture_vertex_count")] int? TextureVertexCount,
        [property: JsonPropertyName("welded_vertex_reduction")] int? WeldedVertexReduction,
        [property: JsonPropertyName("surface_corner_mapping_sha256")] string? SurfaceCornerMappingSha256,
        [property: JsonPropertyName("panel_ownership_path")] string? PanelOwnershipPath,
        [property: JsonPropertyName("panel_ownership_sha256")] string? PanelOwnershipSha256,
        [property: JsonPropertyName("panel_ownership_vertex_count")] int? PanelOwnershipVertexCount,
        [property: JsonPropertyName("seam_constraint_graph_sha256")] string? SeamConstraintGraphSha256,
        [property: JsonPropertyName("material_rest_graph_sha256")] string? MaterialRestGraphSha256,
        [property: JsonPropertyName("material_rest_graph_edge_count")] int? MaterialRestGraphEdgeCount,
        [property: JsonPropertyName("mesher_implementation_sha256")] string? MesherImplementationSha256,
        [property: JsonPropertyName("solver_implementation_sha256")] string? SolverImplementationSha256,
        [property: JsonPropertyName("solver_implementation_files")] IReadOnlyDictionary<string, string>? SolverImplementationFiles,
        bool Accepted,
        [property: JsonPropertyName("finite_positions")] bool FinitePositions,
        [property: JsonPropertyName("equilibrium_gate_evaluated")] bool EquilibriumGateEvaluated,
        [property: JsonPropertyName("static_equilibrium_reached")] bool StaticEquilibriumReached,
        [property: JsonPropertyName("collision_gate_evaluated")] bool CollisionGateEvaluated,
        [property: JsonPropertyName("seam_closure_gate_evaluated")] bool SeamClosureGateEvaluated,
        [property: JsonPropertyName("rejection_reasons")] IReadOnlyList<string>? RejectionReasons,
        string Body,
        [property: JsonPropertyName("solver_config_path")] string? SolverConfigPath,
        [property: JsonPropertyName("solver_config_sha256")] string? SolverConfigSha256,
        [property: JsonPropertyName("rest_lengths_path")] string? RestLengthsPath,
        [property: JsonPropertyName("rest_lengths_sha256")] string? RestLengthsSha256,
        WarpFabricReport? Fabric,
        [property: JsonPropertyName("cloth_vertices")] int ClothVertices,
        [property: JsonPropertyName("body_vertices")] int BodyVertices,
        [property: JsonPropertyName("body_faces")] int BodyFaces,
        [property: JsonPropertyName("body_collisions")] int BodyCollisions,
        [property: JsonPropertyName("self_collisions")] int SelfCollisions,
        [property: JsonPropertyName("max_body_collisions")] int? MaximumBodyCollisions,
        [property: JsonPropertyName("max_self_collisions")] int? MaximumSelfCollisions,
        [property: JsonPropertyName("seam_link_count")] int? SeamLinkCount,
        [property: JsonPropertyName("maximum_seam_separation_cm")] double? MaximumSeamSeparationCm,
        [property: JsonPropertyName("mean_seam_separation_cm")] double? MeanSeamSeparationCm,
        [property: JsonPropertyName("ninety_fifth_percentile_seam_separation_cm")] double? NinetyFifthPercentileSeamSeparationCm,
        [property: JsonPropertyName("max_seam_separation_cm")] double? MaximumSeamSeparationLimitCm,
        [property: JsonPropertyName("evaluated_edge_count")] int? EvaluatedEdgeCount,
        [property: JsonPropertyName("material_rest_length_edge_count")] int? MaterialRestLengthEdgeCount,
        [property: JsonPropertyName("reference_geometry_edge_count")] int? ReferenceGeometryEdgeCount,
        [property: JsonPropertyName("excluded_edge_count")] int? ExcludedEdgeCount,
        [property: JsonPropertyName("maximum_edge_strain_ratio")] double? MaximumEdgeStrainRatio,
        [property: JsonPropertyName("ninety_fifth_percentile_edge_strain_ratio")] double? NinetyFifthPercentileEdgeStrainRatio,
        [property: JsonPropertyName("ninety_ninth_point_ninth_percentile_edge_strain_ratio")] double? NinetyNinthPointNinthPercentileEdgeStrainRatio,
        [property: JsonPropertyName("max_edge_strain_ratio")] double? MaximumEdgeStrainLimit,
        [property: JsonPropertyName("max_ninety_fifth_percentile_edge_strain_ratio")] double? NinetyFifthPercentileEdgeStrainLimit,
        [property: JsonPropertyName("max_ninety_ninth_point_ninth_percentile_edge_strain_ratio")] double? NinetyNinthPointNinthPercentileEdgeStrainLimit,
        [property: JsonPropertyName("edge_contact_buffer_saturated")] bool? EdgeContactBufferSaturated,
        [property: JsonPropertyName("maximum_observed_edge_contacts")] int? MaximumObservedEdgeContacts,
        [property: JsonPropertyName("edge_contact_capacity")] int? EdgeContactCapacity,
        [property: JsonPropertyName("edge_contacts_per_spring")] int? EdgeContactsPerSpring,
        [property: JsonPropertyName("simulation_substeps")] int? SimulationSubsteps,
        [property: JsonPropertyName("body_collision_rate")] double BodyCollisionRate,
        [property: JsonPropertyName("self_collision_rate")] double SelfCollisionRate,
        [property: JsonPropertyName("output_mesh")] string OutputMesh,
        [property: JsonPropertyName("output_mesh_path")] string? OutputMeshPath,
        [property: JsonPropertyName("output_mesh_sha256")] string? OutputMeshSha256,
        [property: JsonPropertyName("output_topology_sha256")] string? OutputTopologySha256);

    private sealed record Style3DFabricReport(
        [property: JsonPropertyName("density_kg_m2")] double DensityKgM2,
        [property: JsonPropertyName("physical_thickness_cm")] double PhysicalThicknessCm,
        [property: JsonPropertyName("body_friction")] double BodyFriction,
        [property: JsonPropertyName("bend_weft")] double BendWeft);

    private sealed record Style3DPanelIndexEntry(
        [property: JsonPropertyName("source_panel_name")] string SourcePanelName,
        [property: JsonPropertyName("vertex_indices")] int[] VertexIndices);

    private sealed record Style3DPanelIndexMap(
        [property: JsonPropertyName("schema_version")] string SchemaVersion,
        [property: JsonPropertyName("vertex_count")] int VertexCount,
        IReadOnlyList<Style3DPanelIndexEntry> Panels);

    private sealed record Style3DReport(
        [property: JsonPropertyName("schema_version")] string? SchemaVersion,
        bool Accepted,
        [property: JsonPropertyName("finite_positions")] bool FinitePositions,
        [property: JsonPropertyName("equilibrium_gate_evaluated")] bool EquilibriumGateEvaluated,
        [property: JsonPropertyName("static_equilibrium_reached")] bool StaticEquilibriumReached,
        [property: JsonPropertyName("collision_gate_evaluated")] bool CollisionGateEvaluated,
        [property: JsonPropertyName("seam_closure_gate_evaluated")] bool SeamClosureGateEvaluated,
        [property: JsonPropertyName("rejection_reasons")] IReadOnlyList<string>? RejectionReasons,
        string? Solver,
        string? Device,
        [property: JsonPropertyName("source_report_path")] string? SourceReportPath,
        [property: JsonPropertyName("source_report_sha256")] string? SourceReportSha256,
        [property: JsonPropertyName("material_surface_path")] string? MaterialSurfacePath,
        [property: JsonPropertyName("material_surface_sha256")] string? MaterialSurfaceSha256,
        [property: JsonPropertyName("material_coordinates_path")] string? MaterialCoordinatesPath,
        [property: JsonPropertyName("material_coordinates_sha256")] string? MaterialCoordinatesSha256,
        [property: JsonPropertyName("body_mesh_path")] string? BodyMeshPath,
        [property: JsonPropertyName("body_mesh_sha256")] string? BodyMeshSha256,
        [property: JsonPropertyName("body_vertex_count")] int BodyVertexCount,
        [property: JsonPropertyName("body_face_count")] int BodyFaceCount,
        [property: JsonPropertyName("panel_ownership_path")] string? PanelOwnershipPath,
        [property: JsonPropertyName("panel_ownership_sha256")] string? PanelOwnershipSha256,
        [property: JsonPropertyName("rest_lengths_path")] string? RestLengthsPath,
        [property: JsonPropertyName("rest_lengths_sha256")] string? RestLengthsSha256,
        [property: JsonPropertyName("panel_index_map_path")] string? PanelIndexMapPath,
        [property: JsonPropertyName("panel_index_map_sha256")] string? PanelIndexMapSha256,
        [property: JsonPropertyName("solver_files")] IReadOnlyDictionary<string, string>? SolverFiles,
        [property: JsonPropertyName("adapter_implementation_path")] string? AdapterImplementationPath,
        [property: JsonPropertyName("adapter_implementation_sha256")] string? AdapterImplementationSha256,
        [property: JsonPropertyName("render_vertex_count")] int RenderVertexCount,
        [property: JsonPropertyName("physical_vertex_count")] int PhysicalVertexCount,
        [property: JsonPropertyName("physical_face_count")] int PhysicalFaceCount,
        [property: JsonPropertyName("mesh_resolution_cm")] double? MeshResolutionCm,
        [property: JsonPropertyName("body_collisions")] int BodyCollisions,
        [property: JsonPropertyName("self_collisions")] int SelfCollisions,
        [property: JsonPropertyName("max_body_collisions")] int MaximumBodyCollisions,
        [property: JsonPropertyName("max_self_collisions")] int MaximumSelfCollisions,
        [property: JsonPropertyName("body_collision_rate")] double BodyCollisionRate,
        [property: JsonPropertyName("self_collision_rate")] double SelfCollisionRate,
        [property: JsonPropertyName("seam_link_count")] int SeamLinkCount,
        [property: JsonPropertyName("maximum_seam_separation_cm")] double MaximumSeamSeparationCm,
        [property: JsonPropertyName("mean_seam_separation_cm")] double MeanSeamSeparationCm,
        [property: JsonPropertyName("ninety_fifth_percentile_seam_separation_cm")] double NinetyFifthPercentileSeamSeparationCm,
        [property: JsonPropertyName("max_seam_separation_cm")] double MaximumSeamSeparationLimitCm,
        [property: JsonPropertyName("evaluated_edge_count")] int EvaluatedEdgeCount,
        [property: JsonPropertyName("material_rest_length_edge_count")] int MaterialRestLengthEdgeCount,
        [property: JsonPropertyName("reference_geometry_edge_count")] int ReferenceGeometryEdgeCount,
        [property: JsonPropertyName("excluded_edge_count")] int ExcludedEdgeCount,
        [property: JsonPropertyName("maximum_edge_strain_ratio")] double MaximumEdgeStrainRatio,
        [property: JsonPropertyName("ninety_fifth_percentile_edge_strain_ratio")] double NinetyFifthPercentileEdgeStrainRatio,
        [property: JsonPropertyName("ninety_ninth_point_ninth_percentile_edge_strain_ratio")] double NinetyNinthPointNinthPercentileEdgeStrainRatio,
        [property: JsonPropertyName("ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio")] double NinetyNinthPointNinetyNinthPercentileEdgeStrainRatio,
        [property: JsonPropertyName("max_ninety_fifth_percentile_edge_strain_ratio")] double MaximumNinetyFifthPercentileEdgeStrainRatio,
        [property: JsonPropertyName("max_ninety_ninth_point_ninth_percentile_edge_strain_ratio")] double MaximumNinetyNinthPointNinthPercentileEdgeStrainRatio,
        [property: JsonPropertyName("max_ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio")] double MaximumNinetyNinthPointNinetyNinthPercentileEdgeStrainRatio,
        [property: JsonPropertyName("high_strain_edge_count")] int HighStrainEdgeCount,
        [property: JsonPropertyName("high_strain_edge_fraction")] double HighStrainEdgeFraction,
        [property: JsonPropertyName("max_high_strain_edge_fraction")] double MaximumHighStrainEdgeFraction,
        [property: JsonPropertyName("peak_edge_strain_gate_mode")] string? PeakEdgeStrainGateMode,
        [property: JsonPropertyName("simulation_substeps")] int SimulationSubsteps,
        Style3DFabricReport? Fabric,
        [property: JsonPropertyName("output_mesh_path")] string? OutputMeshPath,
        [property: JsonPropertyName("output_mesh_sha256")] string? OutputMeshSha256,
        [property: JsonPropertyName("physical_output_mesh_path")] string? PhysicalOutputMeshPath,
        [property: JsonPropertyName("physical_output_mesh_sha256")] string? PhysicalOutputMeshSha256);

    public static GarmentPrefitMeshDocument Load(
        string path,
        PatternAwareMeshDocument patternAwareMesh)
    {
        ArgumentNullException.ThrowIfNull(patternAwareMesh);
        string resolvedPath = Path.GetFullPath(path);
        List<GarmentPrefitPoint> vertices = [];
        int textureCoordinateCount = 0;
        Dictionary<int, int> textureToPosition = [];
        int triangleCount = 0;
        foreach (string rawLine in File.ReadLines(resolvedPath))
        {
            string line = rawLine.Trim();
            if (line.StartsWith("v ", StringComparison.Ordinal))
            {
                string[] values = line.Split(
                    (char[]?)null,
                    StringSplitOptions.RemoveEmptyEntries);
                if (values.Length < 4 ||
                    !double.TryParse(values[1], NumberStyles.Float, CultureInfo.InvariantCulture, out double x) ||
                    !double.TryParse(values[2], NumberStyles.Float, CultureInfo.InvariantCulture, out double y) ||
                    !double.TryParse(values[3], NumberStyles.Float, CultureInfo.InvariantCulture, out double z) ||
                    !double.IsFinite(x) ||
                    !double.IsFinite(y) ||
                    !double.IsFinite(z))
                {
                    throw new InvalidDataException($"Pre-fit OBJ contains an invalid vertex: {rawLine}");
                }
                vertices.Add(new GarmentPrefitPoint(x, y, z));
            }
            else if (line.StartsWith("vt ", StringComparison.Ordinal))
            {
                textureCoordinateCount++;
            }
            else if (line.StartsWith("f ", StringComparison.Ordinal))
            {
                string[] values = line.Split(
                    (char[]?)null,
                    StringSplitOptions.RemoveEmptyEntries);
                if (values.Length != 4)
                {
                    throw new InvalidDataException("Pre-fit OBJ must contain only triangular faces.");
                }
                foreach (string faceVertex in values.Skip(1))
                {
                    string[] indices = faceVertex.Split('/');
                    if (indices.Length < 2 ||
                        !int.TryParse(indices[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out int positionIndex) ||
                        !int.TryParse(indices[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out int textureIndex) ||
                        positionIndex <= 0 ||
                        textureIndex <= 0)
                    {
                        throw new InvalidDataException($"Pre-fit OBJ contains an invalid face vertex: {faceVertex}");
                    }
                    if (textureToPosition.TryGetValue(textureIndex, out int mappedPosition) &&
                        mappedPosition != positionIndex)
                    {
                        throw new InvalidDataException(
                            $"Pre-fit OBJ texture vertex {textureIndex} maps to multiple positions.");
                    }
                    textureToPosition[textureIndex] = positionIndex;
                }
                triangleCount++;
            }
        }

        int expectedVertexCount = patternAwareMesh.Panels.Sum(panel => panel.Vertices.Length);
        int expectedTriangleCount = patternAwareMesh.Panels.Sum(panel => panel.Triangles.Length);
        IReadOnlyList<GarmentPrefitPoint> expandedVertices = vertices;
        if (vertices.Count != expectedVertexCount && textureCoordinateCount == expectedVertexCount)
        {
            expandedVertices = Enumerable.Range(1, textureCoordinateCount)
                .Select(textureIndex =>
                {
                    if (!textureToPosition.TryGetValue(textureIndex, out int positionIndex) ||
                        positionIndex > vertices.Count)
                    {
                        throw new InvalidDataException(
                            $"Pre-fit OBJ texture vertex {textureIndex} has no valid position mapping.");
                    }
                    return vertices[positionIndex - 1];
                })
                .ToArray();
        }
        if (expandedVertices.Count != expectedVertexCount || triangleCount != expectedTriangleCount)
        {
            throw new InvalidDataException(
                $"Pre-fit OBJ topology does not match the pattern-aware mesh. " +
                $"Expected {expectedVertexCount} vertices and {expectedTriangleCount} triangles, " +
                $"but found {vertices.Count} position vertices, {textureCoordinateCount} texture vertices, " +
                $"and {triangleCount} triangles.");
        }

        List<GarmentPrefitPanel> panels = [];
        int offset = 0;
        foreach (PatternAwareMeshPanel sourcePanel in patternAwareMesh.Panels)
        {
            panels.Add(new GarmentPrefitPanel(
                sourcePanel.PanelId,
                expandedVertices.Skip(offset).Take(sourcePanel.Vertices.Length).ToArray()));
            offset += sourcePanel.Vertices.Length;
        }
        string style3DReportPath = Path.Combine(
            Path.GetDirectoryName(resolvedPath)!,
            "patterna_style3d_report.json");
        if (File.Exists(style3DReportPath))
        {
            Style3DReport? style3DReport = System.Text.Json.JsonSerializer.Deserialize<Style3DReport>(
                File.ReadAllText(style3DReportPath),
                new System.Text.Json.JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true
                });
            if (style3DReport is null || !PathsEqual(style3DReport.OutputMeshPath, resolvedPath))
            {
                throw new InvalidDataException("Style3D report does not match the supplied OBJ.");
            }
            return CreateStyle3DDocument(
                resolvedPath,
                LoadStyle3DPanels(style3DReport, patternAwareMesh, vertices),
                triangleCount,
                style3DReportPath,
                style3DReport,
                vertices.Count);
        }
        string reportPath = Path.Combine(
            Path.GetDirectoryName(resolvedPath)!,
            "patterna_warp_prefit_report.json");
        WarpPrefitReport? report = null;
        if (File.Exists(reportPath))
        {
            report = System.Text.Json.JsonSerializer.Deserialize<WarpPrefitReport>(
                File.ReadAllText(reportPath),
                new System.Text.Json.JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true
                });
            if (report is null ||
                !Path.GetFullPath(report.OutputMesh).Equals(resolvedPath, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException("Warp pre-fit report does not match the supplied OBJ.");
            }
        }
        return new GarmentPrefitMeshDocument(
            resolvedPath,
            panels,
            triangleCount,
            report is null ? null : reportPath,
            report?.Accepted ?? false,
            report?.Body,
            report?.SolverConfigPath,
            report?.SolverConfigSha256,
            report?.Fabric?.ThicknessCm,
            report?.Fabric?.Density,
            report?.Fabric?.Friction,
            report?.Fabric?.EdgeBendingStiffness,
            report?.ClothVertices,
            report?.BodyVertices,
            report?.BodyFaces,
            report?.BodyCollisions,
            report?.SelfCollisions,
            report?.BodyCollisionRate,
            report?.SelfCollisionRate,
            report?.SchemaVersion,
            report is null ? null : "NVIDIA Warp",
            report?.FinitePositions ?? false,
            report?.EquilibriumGateEvaluated ?? false,
            report?.StaticEquilibriumReached ?? false,
            report?.CollisionGateEvaluated ?? false,
            report?.SeamClosureGateEvaluated ?? false,
            report?.MaximumBodyCollisions,
            report?.MaximumSelfCollisions,
            report?.SeamLinkCount,
            report?.MaximumSeamSeparationCm,
            report?.MeanSeamSeparationCm,
            report?.NinetyFifthPercentileSeamSeparationCm,
            report?.MaximumSeamSeparationLimitCm,
            report?.EvaluatedEdgeCount,
            report?.MaterialRestLengthEdgeCount,
            report?.ReferenceGeometryEdgeCount,
            report?.ExcludedEdgeCount,
            report?.MaximumEdgeStrainRatio,
            report?.NinetyFifthPercentileEdgeStrainRatio,
            report?.NinetyNinthPointNinthPercentileEdgeStrainRatio,
            null,
            report?.MaximumEdgeStrainLimit,
            report?.NinetyFifthPercentileEdgeStrainLimit,
            report?.NinetyNinthPointNinthPercentileEdgeStrainLimit,
            null,
            null,
            null,
            null,
            report?.EdgeContactBufferSaturated,
            report?.MaximumObservedEdgeContacts,
            report?.EdgeContactCapacity,
            report?.EdgeContactsPerSpring,
            report?.SimulationSubsteps,
            report is not null && HasVerifiedPhysicalIdentity(
                report,
                resolvedPath,
                vertices.Count,
                triangleCount),
            report?.RejectionReasons ?? []);
    }

    private static IReadOnlyList<GarmentPrefitPanel> LoadStyle3DPanels(
        Style3DReport report,
        PatternAwareMeshDocument patternAwareMesh,
        IReadOnlyList<GarmentPrefitPoint> vertices)
    {
        if (string.IsNullOrWhiteSpace(report.PanelIndexMapPath) ||
            !File.Exists(report.PanelIndexMapPath))
        {
            throw new InvalidDataException("Style3D report has no verified panel index map.");
        }
        Style3DPanelIndexMap? indexMap = System.Text.Json.JsonSerializer.Deserialize<Style3DPanelIndexMap>(
            File.ReadAllText(report.PanelIndexMapPath),
            new System.Text.Json.JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        if (indexMap is null ||
            !string.Equals(
                indexMap.SchemaVersion,
                "patterna.style3d-panel-index-map/1.0",
                StringComparison.Ordinal) ||
            indexMap.VertexCount != vertices.Count)
        {
            throw new InvalidDataException("Style3D panel index map does not match the supplied OBJ.");
        }

        Dictionary<string, int[]> indicesByPanel = indexMap.Panels.ToDictionary(
            entry => entry.SourcePanelName,
            entry => entry.VertexIndices,
            StringComparer.Ordinal);
        HashSet<int> usedIndices = [];
        List<GarmentPrefitPanel> panels = [];
        foreach (PatternAwareMeshPanel panel in patternAwareMesh.Panels)
        {
            if (!indicesByPanel.TryGetValue(panel.SourcePanelName, out int[]? indices) ||
                indices.Length != panel.Vertices.Length ||
                indices.Any(index => index < 0 || index >= vertices.Count) ||
                indices.Any(index => !usedIndices.Add(index)))
            {
                throw new InvalidDataException(
                    $"Style3D panel index map does not match panel {panel.PanelId}.");
            }
            panels.Add(new GarmentPrefitPanel(
                panel.PanelId,
                indices.Select(index => vertices[index]).ToArray()));
        }
        if (usedIndices.Count != vertices.Count || indicesByPanel.Count != patternAwareMesh.Panels.Length)
        {
            throw new InvalidDataException("Style3D panel index map does not cover the complete surface once.");
        }
        return panels;
    }

    private static GarmentPrefitMeshDocument CreateStyle3DDocument(
        string resolvedPath,
        IReadOnlyList<GarmentPrefitPanel> panels,
        int triangleCount,
        string reportPath,
        Style3DReport report,
        int outputVertexCount)
        => new(
            resolvedPath,
            panels,
            triangleCount,
            reportPath,
            report.Accepted,
            report.BodyMeshPath,
            null,
            null,
            report.Fabric?.PhysicalThicknessCm,
            report.Fabric?.DensityKgM2,
            report.Fabric?.BodyFriction,
            report.Fabric?.BendWeft,
            report.PhysicalVertexCount,
            report.BodyVertexCount,
            report.BodyFaceCount,
            report.BodyCollisions,
            report.SelfCollisions,
            report.BodyCollisionRate,
            report.SelfCollisionRate,
            report.SchemaVersion,
            report.Solver,
            report.FinitePositions,
            report.EquilibriumGateEvaluated,
            report.StaticEquilibriumReached,
            report.CollisionGateEvaluated,
            report.SeamClosureGateEvaluated,
            report.MaximumBodyCollisions,
            report.MaximumSelfCollisions,
            report.SeamLinkCount,
            report.MaximumSeamSeparationCm,
            report.MeanSeamSeparationCm,
            report.NinetyFifthPercentileSeamSeparationCm,
            report.MaximumSeamSeparationLimitCm,
            report.EvaluatedEdgeCount,
            report.MaterialRestLengthEdgeCount,
            report.ReferenceGeometryEdgeCount,
            report.ExcludedEdgeCount,
            report.MaximumEdgeStrainRatio,
            report.NinetyFifthPercentileEdgeStrainRatio,
            report.NinetyNinthPointNinthPercentileEdgeStrainRatio,
            report.NinetyNinthPointNinetyNinthPercentileEdgeStrainRatio,
            double.PositiveInfinity,
            report.MaximumNinetyFifthPercentileEdgeStrainRatio,
            report.MaximumNinetyNinthPointNinthPercentileEdgeStrainRatio,
            report.MaximumNinetyNinthPointNinetyNinthPercentileEdgeStrainRatio,
            report.HighStrainEdgeCount,
            report.HighStrainEdgeFraction,
            report.MaximumHighStrainEdgeFraction,
            null,
            null,
            null,
            null,
            report.SimulationSubsteps,
            HasVerifiedStyle3DIdentity(
                report,
                resolvedPath,
                outputVertexCount,
                triangleCount),
            report.RejectionReasons ?? []);

    private static bool HasVerifiedPhysicalIdentity(
        WarpPrefitReport report,
        string resolvedOutputPath,
        int outputVertexCount,
        int outputFaceCount)
    {
        if (!string.Equals(
                report.SchemaVersion,
                "patterna.warp-prefit-report/2.6",
                StringComparison.Ordinal) ||
            report.GarmentTopologyMode is not ("explicit" or "hybrid-seams" or "welded-bootstrap") ||
            report.PhysicalVertexCount is not > 0 ||
            report.PhysicalFaceCount is not > 0 ||
            report.TextureVertexCount is not > 0 ||
            report.WeldedVertexReduction is not >= 0 ||
            report.PanelOwnershipVertexCount != report.PhysicalVertexCount ||
            report.MaterialRestGraphEdgeCount is not > 0 ||
            report.MeshResolutionCm is not > 0 ||
            report.ClothVertices != report.PhysicalVertexCount ||
            report.PhysicalFaceCount != outputFaceCount ||
            outputVertexCount != report.PhysicalVertexCount ||
            report.TextureVertexCount < report.PhysicalVertexCount ||
            report.WeldedVertexReduction != report.TextureVertexCount - report.PhysicalVertexCount ||
            !PathsEqual(report.OutputMeshPath, resolvedOutputPath) ||
            !PathsEqual(report.OutputMesh, resolvedOutputPath) ||
            !VerifiedFile(report.PatternSpecificationPath, report.PatternSpecificationSha256) ||
            !VerifiedFile(report.OutputMeshPath, report.OutputMeshSha256) ||
            !VerifiedFile(report.PhysicalMeshPath, report.PhysicalMeshSha256) ||
            !VerifiedFile(report.PanelOwnershipPath, report.PanelOwnershipSha256) ||
            !VerifiedFile(report.RestLengthsPath, report.RestLengthsSha256) ||
            !IsSha256(report.PhysicalTopologySha256) ||
            !IsSha256(report.OutputTopologySha256) ||
            !string.Equals(
                report.PhysicalTopologySha256,
                report.OutputTopologySha256,
                StringComparison.OrdinalIgnoreCase) ||
            !IsSha256(report.SurfaceCornerMappingSha256) ||
            !IsSha256(report.MaterialRestGraphSha256) ||
            !IsSha256(report.SeamConstraintGraphSha256) ||
            !IsSha256(report.MesherImplementationSha256) ||
            !IsSha256(report.SolverImplementationSha256) ||
            report.SolverImplementationFiles is not { Count: >= 4 } ||
            !report.SolverImplementationFiles.TryGetValue(
                "third_party/GarmentCode/pygarment/meshgen/boxmeshgen.py",
                out string? mesherFileHash) ||
            !string.Equals(
                mesherFileHash,
                report.MesherImplementationSha256,
                StringComparison.OrdinalIgnoreCase) ||
            report.SolverImplementationFiles.Values.Any(hash => !IsSha256(hash)))
        {
            return false;
        }
        return true;
    }

    private static bool HasVerifiedStyle3DIdentity(
        Style3DReport report,
        string resolvedOutputPath,
        int outputVertexCount,
        int outputFaceCount)
    {
        if (!string.Equals(
                report.SchemaVersion,
                "patterna.newton-style3d-report/1.0",
                StringComparison.Ordinal) ||
            !string.Equals(
                report.Solver,
                "newton.solvers.SolverStyle3D",
                StringComparison.Ordinal) ||
            !string.Equals(
                report.PeakEdgeStrainGateMode,
                "reported-only-resolution-singularity",
                StringComparison.Ordinal) ||
            report.RenderVertexCount != outputVertexCount ||
            report.PhysicalVertexCount is <= 0 ||
            report.PhysicalVertexCount > report.RenderVertexCount ||
            report.PhysicalFaceCount != outputFaceCount ||
            report.MeshResolutionCm is not > 0 ||
            report.BodyVertexCount <= 0 ||
            report.BodyFaceCount <= 0 ||
            !PathsEqual(report.OutputMeshPath, resolvedOutputPath) ||
            !VerifiedFile(report.OutputMeshPath, report.OutputMeshSha256) ||
            !VerifiedFile(report.SourceReportPath, report.SourceReportSha256) ||
            !VerifiedFile(report.MaterialSurfacePath, report.MaterialSurfaceSha256) ||
            !VerifiedFile(report.MaterialCoordinatesPath, report.MaterialCoordinatesSha256) ||
            !VerifiedFile(report.BodyMeshPath, report.BodyMeshSha256) ||
            !VerifiedFile(report.PanelOwnershipPath, report.PanelOwnershipSha256) ||
            !VerifiedFile(report.RestLengthsPath, report.RestLengthsSha256) ||
            !VerifiedFile(report.PanelIndexMapPath, report.PanelIndexMapSha256) ||
            !VerifiedFile(report.PhysicalOutputMeshPath, report.PhysicalOutputMeshSha256) ||
            !VerifiedFile(report.AdapterImplementationPath, report.AdapterImplementationSha256) ||
            report.SolverFiles is not { Count: >= 2 } ||
            report.SolverFiles.Any(file => !VerifiedFile(file.Key, file.Value)))
        {
            return false;
        }
        return true;
    }

    private static bool VerifiedFile(string? path, string? expectedHash)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path) || !IsSha256(expectedHash))
        {
            return false;
        }
        using FileStream stream = File.OpenRead(path);
        string actualHash = Convert.ToHexString(SHA256.HashData(stream));
        return actualHash.Equals(expectedHash, StringComparison.OrdinalIgnoreCase);
    }

    private static bool PathsEqual(string? first, string second)
        => !string.IsNullOrWhiteSpace(first) &&
            Path.GetFullPath(first).Equals(
                Path.GetFullPath(second),
                StringComparison.OrdinalIgnoreCase);

    private static bool IsSha256(string? value)
        => value is { Length: 64 } && value.All(character =>
            character is >= '0' and <= '9' or >= 'a' and <= 'f' or >= 'A' and <= 'F');

    public GarmentPrefitPanel RequirePanel(string panelId)
        => Panels.FirstOrDefault(panel => panel.PanelId.Equals(
            panelId,
            StringComparison.OrdinalIgnoreCase)) ??
            throw new InvalidDataException($"Pre-fit OBJ has no panel {panelId}.");
}
