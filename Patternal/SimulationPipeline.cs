using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Patterna;

public sealed record SimulationPipelineProgress(string Stage, string Message, double Fraction);

public sealed record SimulationPipelineResult(
    bool Accepted,
    string Revision,
    string JobDirectory,
    string PatternPath,
    string MeshPath,
    string RestPrefitPath,
    string PrefitPath,
    string FitReportPath,
    string SolverName,
    string PreflightPath,
    string BodyPath,
    string BodySegmentationPath,
    string BodyProfilePath,
    string BodyPoseReportPath,
    string DressedPoseReportPath,
    string RenderMeshPath,
    string UsdPath,
    string ManifestPath,
    string FabricName,
    double FabricThicknessMillimeters,
    string Message,
    string? VisualProofManifestPath = null);

public sealed record SimulationFitEvidence(
    int BodyCollisions,
    int SelfCollisions,
    int? SeamLinkCount,
    double? MaximumSeamSeparationCm,
    double? MeanSeamSeparationCm,
    double? NinetyFifthPercentileSeamSeparationCm,
    double? MaximumAllowedSeamSeparationCm,
    double MaximumEdgeStrainRatio,
    double NinetyFifthPercentileEdgeStrainRatio,
    double? NinetyNinthPointNinthPercentileEdgeStrainRatio,
    double MaximumAllowedEdgeStrainRatio,
    double MaximumAllowedNinetyFifthPercentileEdgeStrainRatio,
    double? MaximumAllowedNinetyNinthPointNinthPercentileEdgeStrainRatio,
    int CompletedFrames,
    string WarpDevice,
    bool? EdgeContactBufferSaturated,
    int? MaximumObservedEdgeContacts,
    int? EdgeContactCapacity,
    int? EdgeContactsPerSpring,
    int? SimulationSubsteps,
    string SolverName,
    bool PeakStrainGateEnabled,
    double? NinetyNinthPointNinetyNinthPercentileEdgeStrainRatio,
    double? MaximumAllowedNinetyNinthPointNinetyNinthPercentileEdgeStrainRatio,
    int? HighStrainEdgeCount,
    double? HighStrainEdgeFraction,
    double? MaximumAllowedHighStrainEdgeFraction);

public sealed class SimulationPipelineException : InvalidOperationException
{
    public SimulationPipelineException(string message)
        : base(message)
    {
    }
}

public static class SimulationPipeline
{
    private const string ProductArmLoweringDegrees = "12";
    private const string ProductBodyAnimationFrames = "180";
    private const string CurrentWarpPrefitSchema = "patterna.warp-prefit-report/2.6";
    private const string CurrentStyle3DReportSchema = "patterna.newton-style3d-report/1.0";
    private const double SimulationMeshResolutionCm = 0.25;
    private const string PipelineRevisionSalt = "patterna-simulation-pipeline/4.1:newton-style3d:mesh=0.25cm:body-aware-warm-start:three-stage";

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true
    };

    public static string ComputeRevision(PatternaUnrealBridgeDocument bridge)
    {
        PatternaUnrealBridgeDocument stable = bridge with { GeneratedAtUtc = DateTimeOffset.UnixEpoch };
        string json = JsonSerializer.Serialize(stable, JsonOptions);
        byte[] revisionPayload = Encoding.UTF8.GetBytes($"{PipelineRevisionSalt}\n{json}");
        return Convert.ToHexString(SHA256.HashData(revisionPayload)).ToLowerInvariant();
    }

    public static bool HasAcceptedResult(string localAppDataPath, string revision)
        => TryGetAcceptedResult(localAppDataPath, revision, out _);

    public static bool TryGetAcceptedResult(
        string localAppDataPath,
        string revision,
        out SimulationPipelineResult? acceptedResult)
    {
        acceptedResult = null;
        if (string.IsNullOrWhiteSpace(localAppDataPath) ||
            string.IsNullOrWhiteSpace(revision))
        {
            return false;
        }

        try
        {
            string jobDirectory = Path.Combine(localAppDataPath, "SimulationJobs", revision);
            string reportPath = Path.Combine(jobDirectory, "simulation-job.json");
            if (!File.Exists(reportPath))
            {
                return false;
            }

            SimulationPipelineResult? result = JsonSerializer.Deserialize<SimulationPipelineResult>(
                File.ReadAllText(reportPath),
                JsonOptions);
            if (result is not { Accepted: true } ||
                !string.Equals(result.Revision, revision, StringComparison.Ordinal) ||
                !File.Exists(result.PatternPath) ||
                !File.Exists(result.MeshPath) ||
                !File.Exists(result.RestPrefitPath) ||
                !File.Exists(result.PrefitPath) ||
                !File.Exists(result.FitReportPath) ||
                string.IsNullOrWhiteSpace(result.SolverName) ||
                !File.Exists(result.PreflightPath) ||
                !File.Exists(result.BodyPath) ||
                !File.Exists(result.BodySegmentationPath) ||
                !File.Exists(result.BodyProfilePath) ||
                !File.Exists(result.BodyPoseReportPath) ||
                !File.Exists(result.DressedPoseReportPath) ||
                !File.Exists(result.RenderMeshPath) ||
                !HasPatternUvRenderMesh(result.RenderMeshPath) ||
                !File.Exists(result.UsdPath) ||
                !File.Exists(result.ManifestPath) ||
                string.IsNullOrWhiteSpace(result.VisualProofManifestPath) ||
                !File.Exists(result.VisualProofManifestPath) ||
                string.IsNullOrWhiteSpace(result.FabricName) ||
                !double.IsFinite(result.FabricThicknessMillimeters) ||
                result.FabricThicknessMillimeters <= 0)
            {
                return false;
            }

            using JsonDocument preflight = JsonDocument.Parse(File.ReadAllText(result.PreflightPath));
            if (!preflight.RootElement.TryGetProperty("isAccepted", out JsonElement preflightAccepted) ||
                preflightAccepted.ValueKind is not JsonValueKind.True)
            {
                return false;
            }

            using JsonDocument prefit = JsonDocument.Parse(File.ReadAllText(result.FitReportPath));
            if (!TryParseFitEvidence(prefit.RootElement, out _) ||
                !ValidateAcceptedSimulationChain(result, prefit.RootElement) ||
                !TryValidateProductVisualProof(result))
            {
                return false;
            }

            acceptedResult = result;
            return true;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            return false;
        }
    }

    private static bool ValidateAcceptedSimulationChain(
        SimulationPipelineResult result,
        JsonElement finalPrefit)
    {
        if (finalPrefit.TryGetProperty("schema_version", out JsonElement schema) &&
            string.Equals(schema.GetString(), CurrentStyle3DReportSchema, StringComparison.Ordinal))
        {
            return ValidateAcceptedStyle3DChain(result, finalPrefit);
        }
        return ValidateAcceptedPoseChain(result, finalPrefit);
    }

    private static bool ValidateAcceptedStyle3DChain(
        SimulationPipelineResult result,
        JsonElement finalPrefit)
        => TryGetVerifiedInput(finalPrefit, "output_mesh", out string outputMeshPath) &&
            TryGetVerifiedInput(finalPrefit, "body_mesh", out string bodyMeshPath) &&
            TryGetVerifiedInput(finalPrefit, "source_report", out _) &&
            TryGetVerifiedInput(finalPrefit, "material_surface", out _) &&
            TryGetVerifiedInput(finalPrefit, "material_coordinates", out _) &&
            TryGetVerifiedInput(finalPrefit, "panel_ownership", out _) &&
            TryGetVerifiedInput(finalPrefit, "rest_lengths", out _) &&
            TryGetVerifiedInput(finalPrefit, "panel_index_map", out _) &&
            TryGetVerifiedInput(finalPrefit, "physical_output_mesh", out _) &&
            TryGetVerifiedInput(finalPrefit, "adapter_implementation", out _) &&
            PathsEqual(result.PrefitPath, outputMeshPath) &&
            PathsEqual(result.BodyPath, bodyMeshPath) &&
            string.Equals(
                result.SolverName,
                "newton.solvers.SolverStyle3D",
                StringComparison.Ordinal);

    private static bool HasPatternUvRenderMesh(string path)
    {
        bool hasTextureCoordinate = false;
        bool hasConstructionSeams = false;
        bool hasFinishedEdges = false;
        foreach (string line in File.ReadLines(path))
        {
            if (!hasTextureCoordinate && line.StartsWith("vt ", StringComparison.Ordinal))
            {
                hasTextureCoordinate = true;
            }
            else if (!hasConstructionSeams &&
                line.Equals("g patterna_seams", StringComparison.Ordinal))
            {
                hasConstructionSeams = true;
            }
            else if (!hasFinishedEdges &&
                line.Equals("g patterna_edges", StringComparison.Ordinal))
            {
                hasFinishedEdges = true;
            }

            if (hasTextureCoordinate && hasConstructionSeams && hasFinishedEdges)
            {
                return true;
            }
        }
        return false;
    }

    public static bool TryValidateProductVisualProof(SimulationPipelineResult result)
    {
        try
        {
            string proofManifestPath = result.VisualProofManifestPath!;
            string proofDirectory = Path.GetDirectoryName(proofManifestPath)!;
            string displayManifestPath = Path.Combine(
                result.JobDirectory,
                "display-avatar",
                "manifest.json");
            if (!File.Exists(displayManifestPath))
            {
                return false;
            }

            using JsonDocument proofDocument = JsonDocument.Parse(File.ReadAllText(proofManifestPath));
            using JsonDocument displayDocument = JsonDocument.Parse(File.ReadAllText(displayManifestPath));
            JsonElement proof = proofDocument.RootElement;
            JsonElement display = displayDocument.RootElement;
            if (!TryGetString(proof, "schema_version", out string schema) ||
                !string.Equals(schema, "patterna.product-turntable/1.0", StringComparison.Ordinal) ||
                !proof.TryGetProperty("show_bra", out JsonElement showBra) ||
                showBra.ValueKind is not (JsonValueKind.True or JsonValueKind.False) ||
                !proof.TryGetProperty("avatar_object_count", out JsonElement avatarObjectCount) ||
                !avatarObjectCount.TryGetInt32(out int avatarObjects) ||
                !TryGetString(proof, "avatar_manifest", out string proofAvatarManifest) ||
                !PathsEqual(proofAvatarManifest, displayManifestPath) ||
                !TryGetString(proof, "garment", out string proofGarment) ||
                !PathsEqual(proofGarment, result.RenderMeshPath) ||
                !TryGetString(proof, "garment_sha256", out string garmentHash) ||
                !HashesEqual(garmentHash, FileSha256(result.RenderMeshPath)) ||
                !TryGetString(proof, "fabric", out string fabricPath) ||
                !File.Exists(fabricPath) ||
                !TryGetString(proof, "fabric_sha256", out string fabricHash) ||
                !HashesEqual(fabricHash, FileSha256(fabricPath)) ||
                !proof.TryGetProperty("registration", out JsonElement registration) ||
                !TryGetString(registration, "schema_version", out string registrationSchema) ||
                !string.Equals(registrationSchema, "patterna.product-registration/2.0", StringComparison.Ordinal) ||
                !registration.TryGetProperty("accepted", out JsonElement registrationAccepted) ||
                registrationAccepted.ValueKind is not JsonValueKind.True ||
                !proof.TryGetProperty("resolution", out JsonElement resolution) ||
                resolution.ValueKind is not JsonValueKind.Array ||
                resolution.GetArrayLength() != 2 ||
                !resolution[0].TryGetInt32(out int resolutionX) ||
                !resolution[1].TryGetInt32(out int resolutionY) ||
                resolutionX < 720 ||
                resolutionY < 900 ||
                !proof.TryGetProperty("avatar_hashes", out JsonElement avatarHashes) ||
                !TryGetString(avatarHashes, "manifest", out string avatarManifestHash) ||
                !HashesEqual(avatarManifestHash, FileSha256(displayManifestPath)) ||
                !display.TryGetProperty("assets", out JsonElement displayAssets) ||
                displayAssets.ValueKind is not JsonValueKind.Object)
            {
                return false;
            }

            string displayDirectory = Path.GetDirectoryName(displayManifestPath)!;
            bool isCharMorph = TryGetString(display, "source", out string avatarSource) &&
                string.Equals(avatarSource, "CharMorph mb_female", StringComparison.Ordinal);
            string[] requiredAvatarAssets = isCharMorph
                ? ["body", "bra"]
                : ["body", "bra", "eyes", "teeth", "eyebrows", "eyelashes", "hair"];
            bool expectedBraVisibility = !isCharMorph;
            int expectedAvatarObjects = requiredAvatarAssets.Length - (expectedBraVisibility ? 0 : 1);
            if (showBra.GetBoolean() != expectedBraVisibility ||
                avatarObjects != expectedAvatarObjects)
            {
                return false;
            }
            if (displayAssets.EnumerateObject().Count() < requiredAvatarAssets.Length ||
                requiredAvatarAssets.Any(assetName => !displayAssets.TryGetProperty(assetName, out _)))
            {
                return false;
            }
            foreach (JsonProperty asset in displayAssets.EnumerateObject())
            {
                if (!TryGetString(asset.Value, "geometry", out string geometryRelativePath) ||
                    !TryGetString(asset.Value, "texture", out string textureRelativePath))
                {
                    return false;
                }
                string geometryPath = ResolveContainedEvidencePath(displayDirectory, geometryRelativePath);
                string texturePath = ResolveContainedEvidencePath(displayDirectory, textureRelativePath);
                if (!File.Exists(geometryPath) ||
                    !File.Exists(texturePath) ||
                    !TryGetString(avatarHashes, $"{asset.Name}_geometry", out string geometryHash) ||
                    !TryGetString(avatarHashes, $"{asset.Name}_texture", out string textureHash) ||
                    !HashesEqual(geometryHash, FileSha256(geometryPath)) ||
                    !HashesEqual(textureHash, FileSha256(texturePath)))
                {
                    return false;
                }
                if (string.Equals(asset.Name, "bra", StringComparison.Ordinal) &&
                    (!asset.Value.TryGetProperty("display_optional", out JsonElement displayOptional) ||
                        displayOptional.ValueKind is not JsonValueKind.True ||
                        !asset.Value.TryGetProperty("maximum_surface_offset_m", out JsonElement offset) ||
                        !offset.TryGetDouble(out double offsetMeters) ||
                        !double.IsFinite(offsetMeters) ||
                        offsetMeters < 0 ||
                        offsetMeters > (isCharMorph ? 0.003 : 0.0001) ||
                        (isCharMorph &&
                            (!asset.Value.TryGetProperty("default_visible", out JsonElement defaultVisible) ||
                                defaultVisible.ValueKind is not JsonValueKind.False))))
                {
                    return false;
                }
            }

            string[] requiredViews =
            [
                "front",
                "front-oblique",
                "left",
                "back",
                "back-oblique",
                "right"
            ];
            if (!proof.TryGetProperty("renders", out JsonElement renders) ||
                renders.ValueKind is not JsonValueKind.Object ||
                renders.EnumerateObject().Count() != requiredViews.Length)
            {
                return false;
            }
            foreach (string view in requiredViews)
            {
                if (!renders.TryGetProperty(view, out JsonElement render) ||
                    !TryGetString(render, "path", out string relativePath) ||
                    !TryGetString(render, "sha256", out string expectedHash))
                {
                    return false;
                }
                string renderPath = ResolveContainedEvidencePath(proofDirectory, relativePath);
                if (!File.Exists(renderPath) ||
                    !HashesEqual(expectedHash, FileSha256(renderPath)))
                {
                    return false;
                }
            }
            return true;
        }
        catch (Exception exception) when (
            exception is IOException or
            UnauthorizedAccessException or
            JsonException or
            ArgumentException or
            NotSupportedException)
        {
            return false;
        }
    }

    private static string ResolveContainedEvidencePath(string root, string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath) || Path.IsPathRooted(relativePath))
        {
            throw new ArgumentException("Evidence paths must be relative to their manifest directory.");
        }
        string fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        string fullPath = Path.GetFullPath(Path.Combine(fullRoot, relativePath));
        if (!fullPath.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("Evidence path escapes its manifest directory.");
        }
        return fullPath;
    }

    private static bool ValidateAcceptedPoseChain(
        SimulationPipelineResult result,
        JsonElement finalPrefit)
    {
        string restPrefitReportPath = Path.Combine(
            Path.GetDirectoryName(result.RestPrefitPath)!,
            "patterna_warp_prefit_report.json");
        if (!File.Exists(restPrefitReportPath))
        {
            return false;
        }

        using JsonDocument restPrefit = JsonDocument.Parse(
            File.ReadAllText(restPrefitReportPath));
        using JsonDocument bodyPose = JsonDocument.Parse(
            File.ReadAllText(result.BodyPoseReportPath));
        // DressedPoseReportPath is retained in the serialized result for cache
        // compatibility. New revisions point it at the exact body-preparation
        // report because cloth pose transition evidence now lives in Warp.
        using JsonDocument bodyPreparation = JsonDocument.Parse(
            File.ReadAllText(result.DressedPoseReportPath));
        JsonElement bodyPoseRoot = bodyPose.RootElement;
        JsonElement bodyPreparationRoot = bodyPreparation.RootElement;
        JsonElement restPrefitRoot = restPrefit.RootElement;
        if (!ValidateAcceptedPrefit(restPrefitRoot, out _) ||
            !IsAcceptedReport(bodyPoseRoot, "patterna.mpfb-body-pose/1.0") ||
            !bodyPreparationRoot.TryGetProperty("schemaVersion", out JsonElement bodySchema) ||
            !string.Equals(
                bodySchema.GetString(),
                "patterna.mpfb-garmentcode-body/1.0",
                StringComparison.Ordinal) ||
            !bodyPreparationRoot.TryGetProperty("accepted", out JsonElement bodyAccepted) ||
            bodyAccepted.ValueKind is not JsonValueKind.True)
        {
            return false;
        }

        if (!TryGetString(bodyPreparationRoot, "sourcePoseReportSha256", out string bodyPoseHash) ||
            !TryGetString(bodyPreparationRoot, "outputBodySha256", out string posedBodyHash) ||
            !TryGetString(finalPrefit, "staged_initial_mesh_path", out string finalStagedPath) ||
            !TryGetString(finalPrefit, "staged_initial_mesh_sha256", out string finalStagedHash) ||
            !TryGetString(finalPrefit, "body_animation_start_path", out string animationStartPath) ||
            !TryGetString(finalPrefit, "body_animation_start_sha256", out string animationStartHash) ||
            !TryGetString(finalPrefit, "body_mesh_sha256", out string finalBodyHash) ||
            !finalPrefit.TryGetProperty("body_animation_frames", out JsonElement animationFrames) ||
            !animationFrames.TryGetInt32(out int frameCount) ||
            frameCount <= 0 ||
            !finalPrefit.TryGetProperty("body_animation_completed", out JsonElement animationCompleted) ||
            animationCompleted.ValueKind is not JsonValueKind.True ||
            !TryGetVerifiedInput(finalPrefit, "rest_lengths", out _) ||
            !TryGetVerifiedInput(finalPrefit, "strain_reference_mesh", out _) ||
            !HaveMatchingPhysicalIdentity(restPrefitRoot, finalPrefit))
        {
            return false;
        }

        return PathsEqual(result.RestPrefitPath, finalStagedPath) &&
            File.Exists(animationStartPath) &&
            HashesEqual(FileSha256(result.RestPrefitPath), finalStagedHash) &&
            HashesEqual(FileSha256(animationStartPath), animationStartHash) &&
            HashesEqual(FileSha256(result.BodyPoseReportPath), bodyPoseHash) &&
            HashesEqual(FileSha256(result.BodyPath), posedBodyHash) &&
            HashesEqual(posedBodyHash, finalBodyHash);
    }

    private static bool IsAcceptedReport(JsonElement root, string schemaVersion)
        => root.TryGetProperty("schema_version", out JsonElement schema) &&
            string.Equals(schema.GetString(), schemaVersion, StringComparison.Ordinal) &&
            root.TryGetProperty("accepted", out JsonElement accepted) &&
            accepted.ValueKind is JsonValueKind.True;

    private static bool TryGetVerifiedInput(
        JsonElement root,
        string propertyPrefix,
        out string path)
    {
        path = string.Empty;
        return TryGetString(root, $"{propertyPrefix}_path", out path) &&
            TryGetString(root, $"{propertyPrefix}_sha256", out string expectedHash) &&
            File.Exists(path) &&
            HashesEqual(FileSha256(path), expectedHash);
    }

    private static bool TryGetString(
        JsonElement root,
        string propertyName,
        out string value)
    {
        value = string.Empty;
        if (!root.TryGetProperty(propertyName, out JsonElement element) ||
            element.ValueKind is not JsonValueKind.String ||
            string.IsNullOrWhiteSpace(element.GetString()))
        {
            return false;
        }
        value = element.GetString()!;
        return true;
    }

    private static bool PathsEqual(string first, string second)
        => string.Equals(
            Path.GetFullPath(first),
            Path.GetFullPath(second),
            StringComparison.OrdinalIgnoreCase);

    private static bool HashesEqual(string first, string second)
        => string.Equals(first, second, StringComparison.OrdinalIgnoreCase);

    private static string FileSha256(string path)
    {
        using FileStream stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    public static bool TryReadFitEvidence(
        SimulationPipelineResult result,
        out SimulationFitEvidence? evidence)
    {
        evidence = null;
        ArgumentNullException.ThrowIfNull(result);
        try
        {
            string reportPath = result.FitReportPath;
            if (!File.Exists(reportPath))
            {
                return false;
            }
            using JsonDocument report = JsonDocument.Parse(File.ReadAllText(reportPath));
            return TryParseFitEvidence(report.RootElement, out evidence);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            return false;
        }
    }

    public static bool TryParseFitEvidence(
        JsonElement root,
        out SimulationFitEvidence? evidence)
    {
        evidence = null;
        if (root.TryGetProperty("schema_version", out JsonElement reportSchema) &&
            string.Equals(
                reportSchema.GetString(),
                CurrentStyle3DReportSchema,
                StringComparison.Ordinal))
        {
            return TryParseStyle3DFitEvidence(root, out evidence);
        }
        double p999Strain = double.NaN;
        double maxP999Strain = double.NaN;
        bool hasLocalizedStrain =
            TryGetNonNegativeFiniteDouble(
                root,
                "ninety_ninth_point_ninth_percentile_edge_strain_ratio",
                out p999Strain) &&
            TryGetNonNegativeFiniteDouble(
                root,
                "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio",
                out maxP999Strain);
        bool isCurrentSchema = root.TryGetProperty("schema_version", out JsonElement schema) &&
            string.Equals(schema.GetString(), CurrentWarpPrefitSchema, StringComparison.Ordinal);
        int seamLinkCount = -1;
        double maximumSeamSeparationCm = double.NaN;
        double meanSeamSeparationCm = double.NaN;
        double p95SeamSeparationCm = double.NaN;
        double maximumAllowedSeamSeparationCm = double.NaN;
        bool hasSeamClosure =
            root.TryGetProperty("seam_closure_gate_evaluated", out JsonElement seamEvaluated) &&
            seamEvaluated.ValueKind is JsonValueKind.True &&
            TryGetPositiveInt(root, "seam_link_count", out seamLinkCount) &&
            TryGetNonNegativeFiniteDouble(
                root,
                "maximum_seam_separation_cm",
                out maximumSeamSeparationCm) &&
            TryGetNonNegativeFiniteDouble(
                root,
                "mean_seam_separation_cm",
                out meanSeamSeparationCm) &&
            TryGetNonNegativeFiniteDouble(
                root,
                "ninety_fifth_percentile_seam_separation_cm",
                out p95SeamSeparationCm) &&
            TryGetPositiveFiniteDouble(
                root,
                "max_seam_separation_cm",
                out maximumAllowedSeamSeparationCm) &&
            maximumSeamSeparationCm <= maximumAllowedSeamSeparationCm;
        int observedContacts = -1;
        int contactCapacity = -1;
        int contactsPerSpring = -1;
        int simulationSubsteps = -1;
        bool hasContactCapacity =
            root.TryGetProperty("edge_contact_buffer_saturated", out JsonElement saturatedElement) &&
            saturatedElement.ValueKind is JsonValueKind.False &&
            TryGetNonNegativeInt(root, "maximum_observed_edge_contacts", out observedContacts) &&
            TryGetPositiveInt(root, "edge_contact_capacity", out contactCapacity) &&
            TryGetPositiveInt(root, "edge_contacts_per_spring", out contactsPerSpring) &&
            observedContacts < contactCapacity;
        bool hasContinuousCollisionBudget =
            TryGetPositiveInt(root, "simulation_substeps", out simulationSubsteps) &&
            simulationSubsteps >= 10;
        if (!ValidateAcceptedPrefit(root, out _, allowLegacySchema: true) ||
                (isCurrentSchema && !hasLocalizedStrain) ||
                (isCurrentSchema && !hasContactCapacity) ||
                (isCurrentSchema && !hasContinuousCollisionBudget) ||
                (isCurrentSchema && !hasSeamClosure) ||
                (isCurrentSchema && !HasMaterialSpaceStrainCoverage(root)) ||
                !TryGetNonNegativeInt(root, "body_collisions", out int bodyCollisions) ||
                !TryGetNonNegativeInt(root, "self_collisions", out int selfCollisions) ||
                !TryGetNonNegativeInt(root, "completed_frames", out int completedFrames) ||
                !TryGetNonNegativeFiniteDouble(root, "maximum_edge_strain_ratio", out double peakStrain) ||
                !TryGetNonNegativeFiniteDouble(root, "ninety_fifth_percentile_edge_strain_ratio", out double p95Strain) ||
                !TryGetNonNegativeFiniteDouble(root, "max_edge_strain_ratio", out double maxPeakStrain) ||
                !TryGetNonNegativeFiniteDouble(
                    root,
                    "max_ninety_fifth_percentile_edge_strain_ratio",
                    out double maxP95Strain) ||
                !root.TryGetProperty("warp_device", out JsonElement deviceElement) ||
                deviceElement.ValueKind != JsonValueKind.String ||
                string.IsNullOrWhiteSpace(deviceElement.GetString()))
        {
            return false;
        }
        evidence = new SimulationFitEvidence(
            bodyCollisions,
            selfCollisions,
            isCurrentSchema ? seamLinkCount : null,
            isCurrentSchema ? maximumSeamSeparationCm : null,
            isCurrentSchema ? meanSeamSeparationCm : null,
            isCurrentSchema ? p95SeamSeparationCm : null,
            isCurrentSchema ? maximumAllowedSeamSeparationCm : null,
            peakStrain,
            p95Strain,
            hasLocalizedStrain ? p999Strain : null,
            maxPeakStrain,
            maxP95Strain,
            hasLocalizedStrain ? maxP999Strain : null,
            completedFrames,
            deviceElement.GetString()!,
            isCurrentSchema ? false : null,
            isCurrentSchema ? observedContacts : null,
            isCurrentSchema ? contactCapacity : null,
            isCurrentSchema ? contactsPerSpring : null,
            isCurrentSchema ? simulationSubsteps : null,
            "NVIDIA Warp",
            true,
            null,
            null,
            null,
            null,
            null);
        return true;
    }

    private static bool TryParseStyle3DFitEvidence(
        JsonElement root,
        out SimulationFitEvidence? evidence)
    {
        evidence = null;
        if (!root.TryGetProperty("accepted", out JsonElement accepted) ||
            accepted.ValueKind is not JsonValueKind.True ||
            !root.TryGetProperty("finite_positions", out JsonElement finite) ||
            finite.ValueKind is not JsonValueKind.True ||
            !root.TryGetProperty("static_equilibrium_reached", out JsonElement equilibrium) ||
            equilibrium.ValueKind is not JsonValueKind.True ||
            !root.TryGetProperty("collision_gate_evaluated", out JsonElement collisionGate) ||
            collisionGate.ValueKind is not JsonValueKind.True ||
            !TryGetNonNegativeInt(root, "body_collisions", out int bodyCollisions) ||
            bodyCollisions != 0 ||
            !TryGetNonNegativeInt(root, "self_collisions", out int selfCollisions) ||
            selfCollisions != 0 ||
            !TryGetPositiveInt(root, "seam_link_count", out int seamLinkCount) ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "maximum_seam_separation_cm",
                out double maximumSeamSeparationCm) ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "mean_seam_separation_cm",
                out double meanSeamSeparationCm) ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "ninety_fifth_percentile_seam_separation_cm",
                out double p95SeamSeparationCm) ||
            !TryGetPositiveFiniteDouble(
                root,
                "max_seam_separation_cm",
                out double maximumAllowedSeamSeparationCm) ||
            maximumSeamSeparationCm > maximumAllowedSeamSeparationCm ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "maximum_edge_strain_ratio",
                out double peakStrain) ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "ninety_fifth_percentile_edge_strain_ratio",
                out double p95Strain) ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "ninety_ninth_point_ninth_percentile_edge_strain_ratio",
                out double p999Strain) ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio",
                out double p9999Strain) ||
            !TryGetPositiveFiniteDouble(
                root,
                "high_strain_edge_threshold_ratio",
                out double highStrainThreshold) ||
            !TryGetNonNegativeInt(root, "high_strain_edge_count", out int highStrainEdgeCount) ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "high_strain_edge_fraction",
                out double highStrainEdgeFraction) ||
            !TryGetPositiveFiniteDouble(
                root,
                "max_ninety_fifth_percentile_edge_strain_ratio",
                out double maxP95Strain) ||
            p95Strain > maxP95Strain ||
            !TryGetPositiveFiniteDouble(
                root,
                "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio",
                out double maxP999Strain) ||
            p999Strain > maxP999Strain ||
            !TryGetPositiveFiniteDouble(
                root,
                "max_ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio",
                out double maxP9999Strain) ||
            p9999Strain > maxP9999Strain ||
            !TryGetPositiveFiniteDouble(
                root,
                "max_high_strain_edge_fraction",
                out double maxHighStrainEdgeFraction) ||
            highStrainEdgeFraction > maxHighStrainEdgeFraction ||
            !TryGetPositiveInt(root, "completed_frames", out int completedFrames) ||
            !TryGetPositiveInt(root, "simulation_substeps", out int simulationSubsteps) ||
            !TryGetString(root, "solver", out string solverName) ||
            !TryGetString(root, "device", out string solverDevice))
        {
            return false;
        }

        evidence = new SimulationFitEvidence(
            bodyCollisions,
            selfCollisions,
            seamLinkCount,
            maximumSeamSeparationCm,
            meanSeamSeparationCm,
            p95SeamSeparationCm,
            maximumAllowedSeamSeparationCm,
            peakStrain,
            p95Strain,
            p999Strain,
            highStrainThreshold,
            maxP95Strain,
            maxP999Strain,
            completedFrames,
            solverDevice,
            null,
            null,
            null,
            null,
            simulationSubsteps,
            solverName,
            false,
            p9999Strain,
            maxP9999Strain,
            highStrainEdgeCount,
            highStrainEdgeFraction,
            maxHighStrainEdgeFraction);
        return true;
    }

    public static async Task<SimulationPipelineResult> RunAsync(
        SimulationRuntime runtime,
        string localAppDataPath,
        PatternaUnrealBridgeDocument bridge,
        string bridgePath,
        IProgress<SimulationPipelineProgress>? progress,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(runtime);
        string revision = ComputeRevision(bridge);
        string shortRevision = revision[..12];
        string jobDirectory = Path.Combine(localAppDataPath, "SimulationJobs", revision);
        Directory.CreateDirectory(jobDirectory);

        string patternStem = $"PatternaLiveShirt_{shortRevision}";
        string patternPath = Path.Combine(jobDirectory, $"{patternStem}.specification.json");
        string meshPath = Path.Combine(jobDirectory, $"{patternStem}.patterna-mesh.json");
        string initialArrangementPath = Path.Combine(
            jobDirectory,
            $"{patternStem}.initial-arrangement.json");
        string initialArrangementPreflightPath = Path.Combine(
            jobDirectory,
            $"{patternStem}.initial-arrangement.preflight.json");
        string avatarProfilePath = Path.Combine(jobDirectory, "avatar-garmentcode-profile.json");
        string avatarBodyPath = Path.Combine(jobDirectory, "avatar-charmorph.obj");
        string avatarControlsPath = Path.Combine(jobDirectory, "avatar-charmorph.controls.json");
        string avatarVerticesPath = Path.Combine(jobDirectory, "avatar-charmorph.vertices.npy");
        string avatarFitReportPath = Path.Combine(jobDirectory, "avatar-charmorph.fit-report.json");
        string avatarReportPath = Path.Combine(jobDirectory, "avatar-report.json");
        string displayAvatarDirectory = Path.Combine(jobDirectory, "display-avatar");
        string displayAvatarManifestPath = Path.Combine(displayAvatarDirectory, "manifest.json");
        string bodyPath = Path.Combine(jobDirectory, "simulation-body.obj");
        string bodyMeasurementsPath = Path.Combine(jobDirectory, "simulation-body.yaml");
        string bodySegmentationPath = Path.Combine(jobDirectory, "simulation-body.segmentation.json");
        string bodyPreparationReportPath = Path.Combine(jobDirectory, "simulation-body.report.json");
        string bodyProfilePath = Path.Combine(jobDirectory, "compiler-body-profile.json");
        string sourceDirectory = Path.Combine(jobDirectory, "style3d-source");
        string sourceStem = $"patterna-style3d-source-{SimulationMeshResolutionCm:F3}cm";
        string sourceReportPath = Path.Combine(sourceDirectory, $"{sourceStem}.report.json");
        string materialCoordinatesPath = Path.Combine(
            sourceDirectory,
            $"{sourceStem}.material-coordinates.npz");
        string stageOneDirectory = Path.Combine(jobDirectory, "style3d-stage-1-drape");
        string stageTwoDirectory = Path.Combine(jobDirectory, "style3d-stage-2-contact");
        string finalDirectory = Path.Combine(jobDirectory, "style3d-stage-3-proof");
        string stageOnePath = Path.Combine(stageOneDirectory, "patterna_style3d_sim.obj");
        string stageOneReportPath = Path.Combine(stageOneDirectory, "patterna_style3d_report.json");
        string stageTwoPath = Path.Combine(stageTwoDirectory, "patterna_style3d_sim.obj");
        string stageTwoReportPath = Path.Combine(stageTwoDirectory, "patterna_style3d_report.json");
        string prefitPath = Path.Combine(finalDirectory, "patterna_style3d_sim.obj");
        string prefitReportPath = Path.Combine(finalDirectory, "patterna_style3d_report.json");
        string preflightPath = Path.Combine(jobDirectory, "unreal-preflight.json");
        string usdPath = Path.Combine(jobDirectory, $"{patternStem}.usda");
        string manifestPath = Path.Combine(jobDirectory, $"{patternStem}.manifest.json");
        string renderMeshPath = Path.Combine(jobDirectory, $"{patternStem}.render.obj");
        string reportPath = Path.Combine(jobDirectory, "simulation-job.json");
        string visualProofDirectory = Path.Combine(
            jobDirectory,
            "proofs",
            Guid.NewGuid().ToString("N")[..12]);
        string visualProofManifestPath = Path.Combine(visualProofDirectory, "manifest.json");

        string? bridgeDirectory = Path.GetDirectoryName(bridgePath);
        if (!string.IsNullOrWhiteSpace(bridgeDirectory))
        {
            Directory.CreateDirectory(bridgeDirectory);
        }
        await File.WriteAllTextAsync(
            bridgePath,
            JsonSerializer.Serialize(bridge, JsonOptions),
            new UTF8Encoding(false),
            cancellationToken);

        string garmentCodePythonPath = RequireFile(
            runtime.GarmentCodePythonPath,
            "GarmentCode Python environment");
        string style3DPythonPath = RequireFile(
            runtime.Style3DPythonPath,
            "Newton Style3D Python environment");
        string blenderPath = RequireFile(runtime.BlenderPath, "managed Blender runtime");
        string avatarFitScript = RequireFile(
            Path.Combine(runtime.ToolsDirectory, "fit_charmorph_profile.py"),
            "CharMorph measurement fitter");
        string avatarScript = RequireFile(
            Path.Combine(runtime.ToolsDirectory, "generate_charmorph_avatar.py"),
            "CharMorph avatar generator");
        string bodyPreparationScript = RequireFile(
            Path.Combine(runtime.ToolsDirectory, "prepare_charmorph_garmentcode_body.py"),
            "CharMorph GarmentCode body converter");
        string charMorphCharacterDirectory = RequireDirectory(
            Path.Combine(
                runtime.RootDirectory,
                "third_party",
                "CharMorph-db",
                "characters",
                "mb_female"),
            "CharMorph female character data");
        string charMorphBlendPath = RequireFile(
            Path.Combine(charMorphCharacterDirectory, "char.blend"),
            "CharMorph female source mesh");
        string bodyProfileScript = RequireFile(
            Path.Combine(runtime.ToolsDirectory, "generate_body_profile_from_mesh.py"),
            "compiler body-profile generator");
        string meshScript = RequireFile(
            Path.Combine(runtime.ToolsDirectory, "export_garmentcode_pattern_mesh.py"),
            "GarmentCode mesh exporter");
        string sourceScript = RequireFile(
            Path.Combine(runtime.ToolsDirectory, "build_style3d_source.py"),
            "Style3D material-surface builder");
        string style3DScript = RequireFile(
            Path.Combine(runtime.ToolsDirectory, "prefit_newton_style3d.py"),
            "Newton Style3D solver adapter");
        string productRenderScript = RequireFile(
            Path.Combine(runtime.ToolsDirectory, "render_product_acceptance.py"),
            "product turntable renderer");
        RequireFile(
            Path.Combine(runtime.ToolsDirectory, "product_registration.py"),
            "product registration gate");
        string fabricTexturePath = RequireFile(
            Path.Combine(
                runtime.RootDirectory,
                "third_party",
                "GarmentCode",
                "assets",
                "img",
                "fabric_texture.png"),
            "GarmentCode fabric texture");
        string compilerPath = RequireFile(runtime.CompilerPath, "Unreal garment compiler");

        Style3DResumeArtifacts resumeArtifacts = new(
            patternPath,
            meshPath,
            avatarFitReportPath,
            displayAvatarManifestPath,
            bodyPath,
            bodySegmentationPath,
            bodyPreparationReportPath,
            bodyProfilePath,
            sourceReportPath,
            materialCoordinatesPath,
            stageOnePath,
            stageOneReportPath,
            stageTwoPath,
            stageTwoReportPath,
            prefitPath,
            prefitReportPath);
        bool resumeAcceptedEquilibrium = CanResumeAcceptedStyle3DEquilibrium(resumeArtifacts);

        if (!resumeAcceptedEquilibrium)
        {
            progress?.Report(new(
                "body-profile",
                "Mapping every editable measurement into one revisioned body profile",
                0.03));
            GarmentCodeBodyMappingResult bodyMapping = GarmentCodeBodyMapper.Map(bridge.Body);
            await File.WriteAllTextAsync(
                avatarProfilePath,
                bodyMapping.ToAvatarJson(bridge.Body),
                new UTF8Encoding(false),
                cancellationToken);

            progress?.Report(new(
                "avatar",
                "Fitting the CharMorph female anatomy to the current measurements",
                0.08));
            await RunProcessAsync(
                garmentCodePythonPath,
                [
                    avatarFitScript,
                "--character-dir", charMorphCharacterDirectory,
                "--profile", avatarProfilePath,
                "--output", avatarControlsPath,
                "--report", avatarFitReportPath,
                "--vertices", avatarVerticesPath
                ],
                runtime.RootDirectory,
                Path.Combine(jobDirectory, "01-avatar-fit.log"),
                cancellationToken);
            RequireFile(avatarControlsPath, "measurement-fitted CharMorph controls");
            RequireFile(avatarVerticesPath, "measurement-fitted CharMorph vertices");
            RequireAcceptedJson(avatarFitReportPath, "CharMorph measurement fit");
            await RunProcessAsync(
                blenderPath,
                [
                    charMorphBlendPath,
                    "--background",
                "--python", avatarScript,
                "--",
                "--character-dir", charMorphCharacterDirectory,
                "--profile", avatarProfilePath,
                "--controls", avatarControlsPath,
                "--vertices", avatarVerticesPath,
                "--fit-report", avatarFitReportPath,
                "--output-dir", jobDirectory,
                "--output", avatarBodyPath,
                "--render-output-dir", displayAvatarDirectory
                ],
                runtime.RootDirectory,
                Path.Combine(jobDirectory, "02-avatar-export.log"),
                cancellationToken);
            RequireFile(avatarBodyPath, "measurement-fitted CharMorph avatar");
            RequireAcceptedJson(avatarReportPath, "CharMorph avatar export");
            RequireFile(displayAvatarManifestPath, "measurement-fitted display avatar manifest");

            progress?.Report(new(
                "collision-body",
                "Building the exact measured collision body and anatomical segmentation",
                0.16));
            await RunProcessAsync(
                garmentCodePythonPath,
                [
                    bodyPreparationScript,
                "--avatar-body", avatarBodyPath,
                "--avatar-report", avatarReportPath,
                "--fit-report", avatarFitReportPath,
                "--profile", avatarProfilePath,
                "--output-body", bodyPath
                ],
                runtime.RootDirectory,
                Path.Combine(jobDirectory, "03-body.log"),
                cancellationToken);
            RequireFile(bodyPath, "revision-specific simulation body");
            RequireFile(bodyMeasurementsPath, "revision-specific body measurements");
            RequireFile(bodySegmentationPath, "revision-specific anatomical segmentation");
            RequireAcceptedJson(bodyPreparationReportPath, "simulation body preparation");

            await RunProcessAsync(
                garmentCodePythonPath,
                [
                bodyProfileScript,
                "--body", bodyPath,
                "--segmentation", bodySegmentationPath,
                "--output", bodyProfilePath
                ],
                runtime.RootDirectory,
                Path.Combine(jobDirectory, "04-body-profile.log"),
                cancellationToken);
            RequireFile(bodyProfilePath, "revision-specific compiler body profile");

            progress?.Report(new(
                "export",
                "Exporting the edited 2D pattern as authoritative GarmentCode geometry",
                0.24));
            string patternJson = GarmentCodePatternExporter.Export(bridge.Garment, revision);
            await File.WriteAllTextAsync(
                patternPath,
                patternJson,
                new UTF8Encoding(false),
                cancellationToken);
            await RunProcessAsync(
                garmentCodePythonPath,
                [
                    meshScript,
                patternPath,
                meshPath,
                "--resolution-cm",
                SimulationMeshResolutionCm.ToString("0.########", CultureInfo.InvariantCulture)
                ],
                runtime.RootDirectory,
                Path.Combine(jobDirectory, "05-mesh.log"),
                cancellationToken);
            RequireFile(meshPath, "generated seam-matched pattern mesh");

            progress?.Report(new(
                "arrangement",
                "Wrapping and sewing the flat panels into a measured body-aware warm start",
                0.28));
            await RunProcessAsync(
                compilerPath,
                [
                    "--bridge", bridgePath,
                    "--body-profile", bodyProfilePath,
                    "--garmentcode-pattern-reference", patternPath,
                    "--garmentcode-mesh", meshPath,
                    "--initial-arrangement-output", initialArrangementPath,
                    "--output", initialArrangementPreflightPath,
                    "--report-only"
                ],
                runtime.RootDirectory,
                Path.Combine(jobDirectory, "06-initial-arrangement.log"),
                cancellationToken);
            RequireFile(initialArrangementPath, "body-aware initial garment arrangement");
            RequireUsableBodyAwareArrangement(
                initialArrangementPreflightPath,
                bridge.Garment.Panels.Count);

            progress?.Report(new(
                "style3d-source",
                "Building the 0.25 cm material-space surface and exact seam graph",
                0.30));
            await RunProcessAsync(
                garmentCodePythonPath,
                [
                    sourceScript,
                "--pattern", patternPath,
                "--body", bodyPath,
                "--initial-arrangement", initialArrangementPath,
                "--output-dir", sourceDirectory,
                "--resolution-cm",
                SimulationMeshResolutionCm.ToString("0.########", CultureInfo.InvariantCulture)
                ],
                runtime.RootDirectory,
                Path.Combine(jobDirectory, "07-style3d-source.log"),
                cancellationToken);
            RequireFile(sourceReportPath, "Style3D source report");
            RequireFile(materialCoordinatesPath, "Style3D material coordinates");

            Style3DFabricParameters fabric = Style3DFabricMapper.Map(bridge.Garment.Fabric);
            progress?.Report(new(
                "style3d-drape",
                "Sewing and settling the authored panels on the measured body",
                0.36));
            await RunProcessAsync(
                style3DPythonPath,
                CreateStyle3DArguments(
                    style3DScript,
                    sourceReportPath,
                    materialCoordinatesPath,
                    stageOneDirectory,
                    null,
                    fabric,
                    Style3DStage.InitialDrape),
                runtime.RootDirectory,
                Path.Combine(jobDirectory, "08-style3d-drape.log"),
                cancellationToken,
                [2]);
            RequireFile(stageOnePath, "Style3D initial drape");
            RequireStyle3DWarmStart(stageOneReportPath, Style3DStage.InitialDrape);

            progress?.Report(new(
                "style3d-contact",
                "Resolving cloth-to-body and cloth-to-cloth contact at production resolution",
                0.56));
            await RunProcessAsync(
                style3DPythonPath,
                CreateStyle3DArguments(
                    style3DScript,
                    sourceReportPath,
                    materialCoordinatesPath,
                    stageTwoDirectory,
                    stageOnePath,
                    fabric,
                    Style3DStage.ContactRefinement),
                runtime.RootDirectory,
                Path.Combine(jobDirectory, "09-style3d-contact.log"),
                cancellationToken,
                [2]);
            RequireFile(stageTwoPath, "collision-clean Style3D warm start");
            RequireStyle3DWarmStart(stageTwoReportPath, Style3DStage.ContactRefinement);

            progress?.Report(new(
                "style3d-proof",
                "Proving static equilibrium, exact seams, zero intersections, and strain-tail limits",
                0.78));
            await RunProcessAsync(
                style3DPythonPath,
                CreateStyle3DArguments(
                    style3DScript,
                    sourceReportPath,
                    materialCoordinatesPath,
                    finalDirectory,
                    stageTwoPath,
                    fabric,
                    Style3DStage.FinalProof),
                runtime.RootDirectory,
                Path.Combine(jobDirectory, "10-style3d-proof.log"),
                cancellationToken);
            RequireFile(prefitPath, "accepted Style3D equilibrium mesh");
            RequireAcceptedFitReport(prefitReportPath);
        }
        else
        {
            progress?.Report(new(
                "resume",
                "Reusing the hash-verified accepted Style3D equilibrium for compiler handoff",
                0.90));
        }

        progress?.Report(new(
            "compile",
            "Compiling the exact pattern, body, fabric, and accepted Style3D equilibrium",
            0.92));
        await RunProcessAsync(
            compilerPath,
            [
                "--bridge", bridgePath,
                "--body-profile", bodyProfilePath,
                "--garmentcode-pattern-reference", patternPath,
                "--garmentcode-mesh", meshPath,
                "--garmentcode-prefit", prefitPath,
                "--output", preflightPath,
                "--usd-output", usdPath,
                "--obj-output", renderMeshPath,
                "--manifest-output", manifestPath,
                "--garment-id", "PatternaFemaleShirt"
            ],
            runtime.RootDirectory,
            Path.Combine(jobDirectory, "11-compiler.log"),
            cancellationToken);
        RequireAcceptedPreflight(preflightPath);
        RequireFile(usdPath, "compiled Unreal cloth source");
        RequireFile(manifestPath, "compiled Unreal cloth manifest");
        RequireFile(renderMeshPath, "pattern-UV application render surface");

        progress?.Report(new(
            "visual-proof",
            "Rendering and hashing six registered views of this exact body and cloth revision",
            0.97));
        Directory.CreateDirectory(visualProofDirectory);
        await RunProcessAsync(
            blenderPath,
            [
                "--background",
                "--python", productRenderScript,
                "--",
                "--avatar-manifest", displayAvatarManifestPath,
                "--garment", renderMeshPath,
                "--fabric", fabricTexturePath,
                "--output-directory", visualProofDirectory,
                "--hide-bra"
            ],
            runtime.RootDirectory,
            Path.Combine(jobDirectory, "12-product-acceptance.log"),
            cancellationToken);
        RequireFile(visualProofManifestPath, "revision-specific six-view visual proof");

        SimulationPipelineResult result = new(
            true,
            revision,
            jobDirectory,
            patternPath,
            meshPath,
            stageOnePath,
            prefitPath,
            prefitReportPath,
            "newton.solvers.SolverStyle3D",
            preflightPath,
            bodyPath,
            bodySegmentationPath,
            bodyProfilePath,
            avatarFitReportPath,
            bodyPreparationReportPath,
            renderMeshPath,
            usdPath,
            manifestPath,
            bridge.Garment.Fabric.Name,
            bridge.Garment.Fabric.ThicknessMillimeters,
            "The current measurements and edited pattern were solved through the three-stage Newton Style3D production gate.",
            visualProofManifestPath);
        if (!TryValidateProductVisualProof(result))
        {
            throw new SimulationPipelineException(
                "The current cloth revision failed its exact six-view body, garment, and render-hash gate.");
        }
        await File.WriteAllTextAsync(
            reportPath,
            JsonSerializer.Serialize(result, JsonOptions),
            new UTF8Encoding(false),
            cancellationToken);
        progress?.Report(new("complete", result.Message, 1.0));
        return result;
    }

    private static async Task<SimulationPipelineResult> RunLegacyWarpAsync(
        string projectRoot,
        string localAppDataPath,
        PatternaUnrealBridgeDocument bridge,
        string bridgePath,
        IProgress<SimulationPipelineProgress>? progress,
        CancellationToken cancellationToken)
    {
        string revision = ComputeRevision(bridge);
        string shortRevision = revision[..12];
        string jobDirectory = Path.Combine(localAppDataPath, "SimulationJobs", revision);
        Directory.CreateDirectory(jobDirectory);

        string patternStem = $"PatternaLiveShirt_{shortRevision}";
        string patternPath = Path.Combine(jobDirectory, $"{patternStem}.specification.json");
        string meshPath = Path.Combine(jobDirectory, $"{patternStem}.patterna-mesh.json");
        string initialArrangementPath = Path.Combine(jobDirectory, $"{patternStem}.initial-arrangement.json");
        string initialArrangementPreflightPath = Path.Combine(
            jobDirectory,
            $"{patternStem}.initial-arrangement.preflight.json");
        string avatarProfilePath = Path.Combine(jobDirectory, "avatar-garmentcode-profile.json");
        string avatarBodyPath = Path.Combine(jobDirectory, "avatar-mpfb.obj");
        string avatarFitReportPath = Path.Combine(jobDirectory, "avatar-mpfb.fit-report.json");
        string posedAvatarBodyPath = Path.Combine(jobDirectory, "avatar-mpfb.relaxed.obj");
        string bodyPoseReportPath = Path.Combine(jobDirectory, "avatar-mpfb.relaxed.pose-report.json");
        string displayAvatarDirectory = Path.Combine(jobDirectory, "display-avatar");
        string displayAvatarManifestPath = Path.Combine(displayAvatarDirectory, "manifest.json");
        string displayAvatarRestBodyPath = Path.Combine(displayAvatarDirectory, "body.rest.obj");
        string displayAvatarBodyPath = Path.Combine(displayAvatarDirectory, "body.obj");
        string restBodyPath = Path.Combine(jobDirectory, "simulation-body.rest.obj");
        string restBodyMeasurementsPath = Path.Combine(jobDirectory, "simulation-body.rest.yaml");
        string restBodySegmentationPath = Path.Combine(jobDirectory, "simulation-body.rest.segmentation.json");
        string restBodyPreparationReportPath = Path.Combine(jobDirectory, "simulation-body.rest.report.json");
        string bodyPath = Path.Combine(jobDirectory, "simulation-body.obj");
        string bodyMeasurementsPath = Path.Combine(jobDirectory, "simulation-body.yaml");
        string bodySegmentationPath = Path.Combine(jobDirectory, "simulation-body.segmentation.json");
        string bodyPreparationReportPath = Path.Combine(jobDirectory, "simulation-body.report.json");
        string bodyProfilePath = Path.Combine(jobDirectory, "compiler-body-profile.json");
        string preflightPath = Path.Combine(jobDirectory, "unreal-preflight.json");
        string reportPath = Path.Combine(jobDirectory, "simulation-job.json");
        string prefitConfig = Path.Combine(jobDirectory, "warp-fabric-config.yaml");
        string warpDirectory = Path.Combine(jobDirectory, "warp");
        string restWarpDirectory = Path.Combine(jobDirectory, "warp-rest");
        string restPrefitDirectory = Path.Combine(restWarpDirectory, patternStem);
        string restPrefitPath = Path.Combine(restPrefitDirectory, $"{patternStem}_sim.obj");
        string restPrefitReportPath = Path.Combine(restPrefitDirectory, "patterna_warp_prefit_report.json");
        string restBoxMeshPath = Path.Combine(restPrefitDirectory, $"{patternStem}_boxmesh.obj");
        string restLengthsPath = Path.Combine(restPrefitDirectory, $"{patternStem}_orig_lens.pickle");
        string restGarmentSegmentationPath = Path.Combine(
            restPrefitDirectory,
            $"{patternStem}_sim_segmentation.txt");
        string prefitDirectory = Path.Combine(warpDirectory, patternStem);
        string prefitPath = Path.Combine(prefitDirectory, $"{patternStem}_sim.obj");
        string prefitReportPath = Path.Combine(prefitDirectory, "patterna_warp_prefit_report.json");
        string usdPath = Path.Combine(jobDirectory, $"{patternStem}.usda");
        string manifestPath = Path.Combine(jobDirectory, $"{patternStem}.manifest.json");
        string renderMeshPath = Path.Combine(jobDirectory, $"{patternStem}.render.obj");

        string garmentCodePythonPath = RequireFile(
            Path.Combine(projectRoot, ".venv-garmentcode", "Scripts", "python.exe"),
            "GarmentCode Python environment");
        // Garment construction and Warp must run in one complete environment.
        // This environment contains the customized CUDA-enabled Warp build plus
        // GarmentCode's SciPy, SVG, geometry, and rendering dependencies.
        string warpPythonPath = garmentCodePythonPath;
        string blenderPath = FindBlender(projectRoot, localAppDataPath);
        string avatarScript = RequireFile(
            Path.Combine(projectRoot, "tools", "generate_mpfb_avatar.py"),
            "MPFB measurement fitter");
        string bodyPreparationScript = RequireFile(
            Path.Combine(projectRoot, "tools", "prepare_mpfb_garmentcode_body.py"),
            "MPFB GarmentCode body converter");
        string bodyPoseScript = RequireFile(
            Path.Combine(projectRoot, "tools", "pose_mpfb_body.py"),
            "topology-preserving MPFB pose transfer");
        string rigWeightsPath = RequireFile(
            Path.Combine(
                projectRoot,
                "third_party",
                "MPFB2",
                "src",
                "mpfb",
                "data",
                "rigs",
                "standard",
                "weights.default.json"),
            "MPFB default rig weights");
        string bodyProfileScript = RequireFile(
            Path.Combine(projectRoot, "tools", "generate_body_profile_from_mesh.py"),
            "compiler body-profile generator");
        string meshScript = RequireFile(
            Path.Combine(projectRoot, "tools", "export_garmentcode_pattern_mesh.py"),
            "GarmentCode mesh exporter");
        string prefitScript = RequireFile(
            Path.Combine(projectRoot, "tools", "prefit_garmentcode_warp.py"),
            "Warp pre-fit runner");
        string compilerPath = FindCompiler(projectRoot);

        await WarpFabricConfigWriter.WriteAsync(
            prefitConfig,
            bridge.Garment.Fabric,
            SimulationMeshResolutionCm,
            cancellationToken);

        progress?.Report(new("body-profile", "Mapping every editable measurement into one revisioned body profile", 0.03));
        GarmentCodeBodyMappingResult bodyMapping = GarmentCodeBodyMapper.Map(bridge.Body);
        await File.WriteAllTextAsync(
            avatarProfilePath,
            bodyMapping.ToAvatarJson(bridge.Body),
            new UTF8Encoding(false),
            cancellationToken);

        progress?.Report(new("avatar", "Fitting a female MPFB body to the current detailed measurements", 0.08));
        await RunProcessAsync(
            blenderPath,
            [
                "--background",
                "--python", avatarScript,
                "--",
                "--profile", avatarProfilePath,
                "--output", avatarBodyPath,
                "--render-output-dir", displayAvatarDirectory
            ],
            projectRoot,
            Path.Combine(jobDirectory, "01-avatar.log"),
            cancellationToken);
        RequireFile(avatarBodyPath, "measurement-fitted MPFB avatar");
        RequireAcceptedJson(avatarFitReportPath, "MPFB measurement fit");
        RequireFile(displayAvatarManifestPath, "measurement-fitted display avatar manifest");

        progress?.Report(new("collision-body", "Building the exact rest-pose body and anatomical segmentation", 0.16));
        await RunProcessAsync(
            garmentCodePythonPath,
            [
                bodyPreparationScript,
                "--avatar-body", avatarBodyPath,
                "--fit-report", avatarFitReportPath,
                "--profile", avatarProfilePath,
                "--output-body", restBodyPath
            ],
            projectRoot,
            Path.Combine(jobDirectory, "02-body.log"),
            cancellationToken);
        RequireFile(restBodyPath, "revision-specific rest-pose simulation body");
        RequireFile(restBodyMeasurementsPath, "revision-specific rest-pose body measurements");
        RequireFile(restBodySegmentationPath, "revision-specific rest-pose anatomical segmentation");
        RequireAcceptedJson(restBodyPreparationReportPath, "rest-pose simulation body preparation");

        await RunProcessAsync(
            garmentCodePythonPath,
            [
                bodyProfileScript,
                "--body", restBodyPath,
                "--segmentation", restBodySegmentationPath,
                "--output", bodyProfilePath
            ],
            projectRoot,
            Path.Combine(jobDirectory, "03-body-profile.log"),
            cancellationToken);
        RequireFile(bodyProfilePath, "revision-specific compiler body profile");

        progress?.Report(new("export", "Exporting the edited 2D pattern as authoritative GarmentCode geometry", 0.25));
        string patternJson = GarmentCodePatternExporter.Export(bridge.Garment, revision);
        await File.WriteAllTextAsync(patternPath, patternJson, new UTF8Encoding(false), cancellationToken);

        progress?.Report(new("mesh", "Building a seam-matched simulation mesh from the edited pattern", 0.32));
        await RunProcessAsync(
            garmentCodePythonPath,
            [
                meshScript,
                patternPath,
                meshPath,
                "--resolution-cm",
                SimulationMeshResolutionCm.ToString("0.########", CultureInfo.InvariantCulture)
            ],
            projectRoot,
            Path.Combine(jobDirectory, "04-mesh.log"),
            cancellationToken);
        RequireFile(meshPath, "generated seam-matched mesh");

        progress?.Report(new("arrangement", "Wrapping and sewing the flat panels into a measured body-aware starting shell", 0.37));
        await RunProcessAsync(
            compilerPath,
            [
                "--bridge", bridgePath,
                "--body-profile", bodyProfilePath,
                "--garmentcode-pattern-reference", patternPath,
                "--garmentcode-mesh", meshPath,
                "--initial-arrangement-output", initialArrangementPath,
                "--output", initialArrangementPreflightPath,
                "--report-only"
            ],
            projectRoot,
            Path.Combine(jobDirectory, "05-initial-arrangement.log"),
            cancellationToken);
        RequireFile(initialArrangementPath, "body-aware initial garment arrangement");
        RequireFile(initialArrangementPreflightPath, "body-aware arrangement preflight");
        bool hasAuthoritativeSourcePlacement = HasAuthoritativeSourcePlacement(
            bridge.Garment);
        bool useBodyAwareInitialArrangement = !hasAuthoritativeSourcePlacement &&
            HasAcceptedInitialArrangement(initialArrangementPreflightPath);

        progress?.Report(new(
            "dress",
            hasAuthoritativeSourcePlacement
                ? "Draping from the authored panel placement on the measured rest-pose body"
                : useBodyAwareInitialArrangement
                ? "Draping the sewn garment on the measured rest-pose body"
                : "Draping the proven pattern placement on the measured rest-pose body",
            0.42));
        List<string> restPrefitArguments =
        [
            prefitScript,
            "--pattern", patternPath,
            "--config", prefitConfig,
            "--body", "patterna_mpfb_female",
            "--body-obj", restBodyPath,
            "--body-measurements", restBodyMeasurementsPath,
            "--body-segmentation", restBodySegmentationPath,
            "--output-directory", restWarpDirectory,
            "--device", "auto",
            "--rebuild-mesh",
            "--count-collisions",
            "--stop-when-static"
        ];
        if (useBodyAwareInitialArrangement)
        {
            int outputIndex = restPrefitArguments.IndexOf("--output-directory");
            restPrefitArguments.Insert(outputIndex, initialArrangementPath);
            restPrefitArguments.Insert(outputIndex, "--initial-arrangement");
        }
        await RunProcessAsync(
            warpPythonPath,
            restPrefitArguments,
            projectRoot,
            Path.Combine(jobDirectory, "06-rest-pose-drape.log"),
            cancellationToken);
        RequireFile(restPrefitPath, "rest-pose Warp equilibrium mesh");
        RequireAcceptedPrefit(restPrefitReportPath);
        RequireFile(restBoxMeshPath, "rest-pose strain reference mesh");
        RequireFile(restLengthsPath, "rest-pose pattern edge lengths");
        RequireFile(restGarmentSegmentationPath, "rest-pose garment segmentation");

        progress?.Report(new(
            "pose",
            "Preparing the fitted body for a collision-driven garment pose",
            0.62));
        await RunProcessAsync(
            garmentCodePythonPath,
            [
                bodyPoseScript,
                "--input", avatarBodyPath,
                "--output", posedAvatarBodyPath,
                "--rig-weights", rigWeightsPath,
                "--source-fit-report", avatarFitReportPath,
                "--arm-lowering-degrees", ProductArmLoweringDegrees
            ],
            projectRoot,
            Path.Combine(jobDirectory, "07-body-pose.log"),
            cancellationToken);
        RequireFile(posedAvatarBodyPath, "relaxed measurement-fitted MPFB avatar");
        RequireAcceptedJson(bodyPoseReportPath, "relaxed body pose");

        File.Copy(displayAvatarBodyPath, displayAvatarRestBodyPath, overwrite: true);
        await RunProcessAsync(
            garmentCodePythonPath,
            [
                bodyPoseScript,
                "--input", displayAvatarRestBodyPath,
                "--output", displayAvatarBodyPath,
                "--rig-weights", rigWeightsPath,
                "--arm-lowering-degrees", ProductArmLoweringDegrees
            ],
            projectRoot,
            Path.Combine(jobDirectory, "08-display-avatar-pose.log"),
            cancellationToken);
        RequireFile(displayAvatarBodyPath, "relaxed textured display avatar");
        RequireAcceptedJson(
            Path.Combine(displayAvatarDirectory, "body.pose-report.json"),
            "relaxed display-avatar pose");

        await RunProcessAsync(
            garmentCodePythonPath,
            [
                bodyPreparationScript,
                "--avatar-body", posedAvatarBodyPath,
                "--fit-report", avatarFitReportPath,
                "--pose-report", bodyPoseReportPath,
                "--profile", avatarProfilePath,
                "--output-body", bodyPath
            ],
            projectRoot,
            Path.Combine(jobDirectory, "09-relaxed-collision-body.log"),
            cancellationToken);
        RequireFile(bodyPath, "relaxed revision-specific simulation body");
        RequireFile(bodyMeasurementsPath, "relaxed revision-specific body measurements");
        RequireFile(bodySegmentationPath, "relaxed anatomical segmentation");
        RequireAcceptedJson(bodyPreparationReportPath, "relaxed simulation body preparation");

        progress?.Report(new(
            "resettle",
            "Animating the measured body inside the dressed cloth, then resettling it",
            0.72));
        await RunProcessAsync(
            warpPythonPath,
            [
                prefitScript,
                "--pattern", patternPath,
                "--config", prefitConfig,
                "--body", "patterna_mpfb_female",
                "--body-obj", bodyPath,
                "--body-measurements", bodyMeasurementsPath,
                "--body-segmentation", bodySegmentationPath,
                "--initial-mesh", restPrefitPath,
                "--rest-lengths", restLengthsPath,
                "--strain-reference-mesh", restBoxMeshPath,
                "--body-start-obj", restBodyPath,
                "--body-animation-frames", ProductBodyAnimationFrames,
                "--output-directory", warpDirectory,
                "--device", "auto",
                "--rebuild-mesh",
                "--count-collisions",
                "--stop-when-static"
            ],
            projectRoot,
            Path.Combine(jobDirectory, "11-relaxed-resettle.log"),
            cancellationToken);
        RequireFile(prefitPath, "Warp equilibrium mesh");
        RequireAcceptedPrefit(prefitReportPath);

        progress?.Report(new("compile", "Compiling the same body, pattern, seams, fabric, and relaxed Warp equilibrium", 0.84));
        await RunProcessAsync(
            compilerPath,
            [
                "--bridge", bridgePath,
                "--body-profile", bodyProfilePath,
                "--garmentcode-pattern-reference", patternPath,
                "--garmentcode-mesh", meshPath,
                "--garmentcode-prefit", prefitPath,
                "--output", preflightPath,
                "--usd-output", usdPath,
                "--obj-output", renderMeshPath,
                "--manifest-output", manifestPath,
                "--garment-id", "PatternaFemaleShirt"
            ],
            projectRoot,
            Path.Combine(jobDirectory, "12-compiler.log"),
            cancellationToken);
        RequireAcceptedPreflight(preflightPath);
        RequireFile(usdPath, "compiled Unreal cloth source");
        RequireFile(manifestPath, "compiled Unreal cloth manifest");
        RequireFile(renderMeshPath, "pattern-UV application render surface");
        progress?.Report(new(
            "render-surface",
            "Loaded the compiler-native thin-cloth surface with panel UVs and construction lines",
            0.96));

        SimulationPipelineResult result = new(
            true,
            revision,
            jobDirectory,
            patternPath,
            meshPath,
            restPrefitPath,
            prefitPath,
            prefitReportPath,
            "NVIDIA Warp",
            preflightPath,
            bodyPath,
            bodySegmentationPath,
            bodyProfilePath,
            bodyPoseReportPath,
            bodyPreparationReportPath,
            renderMeshPath,
            usdPath,
            manifestPath,
            bridge.Garment.Fabric.Name,
            bridge.Garment.Fabric.ThicknessMillimeters,
            "The exact avatar was animated inside the accepted dressed cloth and resettled from the current Patternal document.");
        await File.WriteAllTextAsync(
            reportPath,
            JsonSerializer.Serialize(result, JsonOptions),
            new UTF8Encoding(false),
            cancellationToken);
        progress?.Report(new("complete", result.Message, 1.0));
        return result;
    }

    private enum Style3DStage
    {
        InitialDrape,
        ContactRefinement,
        FinalProof
    }

    private sealed record Style3DResumeArtifacts(
        string PatternPath,
        string MeshPath,
        string AvatarFitReportPath,
        string DisplayAvatarManifestPath,
        string BodyPath,
        string BodySegmentationPath,
        string BodyPreparationReportPath,
        string BodyProfilePath,
        string SourceReportPath,
        string MaterialCoordinatesPath,
        string StageOnePath,
        string StageOneReportPath,
        string StageTwoPath,
        string StageTwoReportPath,
        string FinalPath,
        string FinalReportPath);

    private static List<string> CreateStyle3DArguments(
        string scriptPath,
        string sourceReportPath,
        string materialCoordinatesPath,
        string outputDirectory,
        string? initialMeshPath,
        Style3DFabricParameters fabric,
        Style3DStage stage)
    {
        static string Number(double value)
            => value.ToString("0.########", CultureInfo.InvariantCulture);

        bool initialDrape = stage is Style3DStage.InitialDrape;
        bool finalProof = stage is Style3DStage.FinalProof;
        List<string> arguments =
        [
            scriptPath,
            "--source-report", sourceReportPath,
            "--material-coordinates", materialCoordinatesPath,
            "--output-dir", outputDirectory,
            "--device", "cuda:0",
            "--frames", initialDrape ? "650" : finalProof ? "500" : "800",
            "--minimum-frames", stage is Style3DStage.ContactRefinement ? "800" : "120",
            "--substeps", "20",
            "--nonlinear-iterations", "4",
            "--linear-iterations", initialDrape ? "10" : "12",
            "--static-consecutive-frames", initialDrape ? "15" : "20",
            "--static-threshold-cm", "0.01",
            "--non-static-percent", initialDrape ? "5" : "0.1",
            "--static-mean-threshold-cm", initialDrape ? "0.003" : "0.001",
            "--static-p999-threshold-cm", initialDrape ? "0.08" : "0.03",
            "--density-kg-m2", Number(fabric.DensityKilogramsPerSquareMeter),
            "--weft-stiffness", Number(fabric.WeftStiffness),
            "--warp-stiffness", Number(fabric.WarpStiffness),
            "--shear-stiffness", Number(fabric.ShearStiffness),
            "--bend-weft", Number(fabric.BendWeft),
            "--bend-warp", Number(fabric.BendWarp),
            "--bend-bias", Number(fabric.BendBias),
            "--cloth-thickness-cm", Number(fabric.PhysicalThicknessCentimeters),
            "--self-contact-thickness-cm",
            Number(initialDrape ? 0.07 : fabric.SelfContactThicknessCentimeters),
            "--body-contact-radius-cm", "0.20",
            "--body-contact-margin-cm", "0.35",
            "--body-contact-stiffness", initialDrape ? "100" : "1000",
            "--body-friction",
            Number(initialDrape ? fabric.BodyFriction : Math.Clamp(fabric.BodyFriction * 0.78, 0.05, 1.0)),
            "--initial-body-clearance-cm", initialDrape ? "0.35" : "0.10",
            "--hard-body-clearance-cm", initialDrape ? "0" : "0.10",
            "--max-seam-separation-cm", "0.25",
            "--max-edge-strain", "0.40",
            "--max-p95-edge-strain", initialDrape ? "0.20" : "0.15",
            "--max-p999-edge-strain", initialDrape ? "0.35" : "0.29",
            "--max-p9999-edge-strain", initialDrape ? "5.0" : "0.55",
            "--max-high-strain-edge-fraction", initialDrape ? "0.05" : "0.0005"
        ];
        if (!string.IsNullOrWhiteSpace(initialMeshPath))
        {
            arguments.Add("--initial-mesh");
            arguments.Add(initialMeshPath);
        }
        return arguments;
    }

    private static void RequireStyle3DWarmStart(string reportPath, Style3DStage stage)
    {
        using JsonDocument report = JsonDocument.Parse(
            File.ReadAllText(RequireFile(reportPath, "Style3D stage report")));
        JsonElement root = report.RootElement;
        bool initialDrape = stage is Style3DStage.InitialDrape;
        if (!root.TryGetProperty("schema_version", out JsonElement schema) ||
            !string.Equals(schema.GetString(), CurrentStyle3DReportSchema, StringComparison.Ordinal) ||
            !root.TryGetProperty("finite_positions", out JsonElement finite) ||
            finite.ValueKind is not JsonValueKind.True ||
            (initialDrape &&
                (!root.TryGetProperty("static_equilibrium_reached", out JsonElement equilibrium) ||
                    equilibrium.ValueKind is not JsonValueKind.True)) ||
            !TryGetNonNegativeInt(root, "body_collisions", out int bodyCollisions) ||
            bodyCollisions != 0 ||
            !TryGetNonNegativeInt(root, "self_collisions", out int selfCollisions) ||
            selfCollisions > (initialDrape ? 32 : 0) ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "maximum_seam_separation_cm",
                out double seamSeparation) ||
            seamSeparation > 0.25 ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "ninety_fifth_percentile_edge_strain_ratio",
                out double p95Strain) ||
            p95Strain > (initialDrape ? 0.20 : 0.15) ||
            !TryGetNonNegativeFiniteDouble(
                root,
                "ninety_ninth_point_ninth_percentile_edge_strain_ratio",
                out double p999Strain) ||
            p999Strain > (initialDrape ? 0.35 : 0.29) ||
            (!initialDrape &&
                (!TryGetNonNegativeFiniteDouble(
                        root,
                        "ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio",
                        out double p9999Strain) ||
                    p9999Strain > 0.55 ||
                    !TryGetNonNegativeFiniteDouble(
                        root,
                        "high_strain_edge_fraction",
                        out double highStrainFraction) ||
                    highStrainFraction > 0.0005)) ||
            !TryGetVerifiedInput(root, "output_mesh", out _))
        {
            throw new SimulationPipelineException(
                $"Style3D rejected the {stage} warm start: {ReadPrefitRejectionReason(root)}.");
        }
    }

    private static void RequireAcceptedFitReport(string reportPath)
    {
        using JsonDocument report = JsonDocument.Parse(
            File.ReadAllText(RequireFile(reportPath, "Style3D final proof report")));
        if (!TryParseFitEvidence(report.RootElement, out _))
        {
            throw new SimulationPipelineException(
                $"Style3D rejected the current cloth revision: {ReadPrefitRejectionReason(report.RootElement)}.");
        }
    }

    private static bool CanResumeAcceptedStyle3DEquilibrium(
        Style3DResumeArtifacts artifacts)
    {
        try
        {
            string[] requiredFiles =
            [
                artifacts.PatternPath,
                artifacts.MeshPath,
                artifacts.DisplayAvatarManifestPath,
                artifacts.BodyPath,
                artifacts.BodySegmentationPath,
                artifacts.BodyProfilePath,
                artifacts.MaterialCoordinatesPath,
                artifacts.StageOnePath,
                artifacts.StageTwoPath,
                artifacts.FinalPath
            ];
            if (requiredFiles.Any(path => !File.Exists(path)))
            {
                return false;
            }

            RequireAcceptedJson(artifacts.AvatarFitReportPath, "MPFB measurement fit");
            RequireAcceptedJson(artifacts.BodyPreparationReportPath, "simulation body preparation");
            RequireStyle3DWarmStart(artifacts.StageOneReportPath, Style3DStage.InitialDrape);
            RequireStyle3DWarmStart(artifacts.StageTwoReportPath, Style3DStage.ContactRefinement);
            RequireAcceptedFitReport(artifacts.FinalReportPath);

            using JsonDocument finalReport = JsonDocument.Parse(
                File.ReadAllText(artifacts.FinalReportPath));
            JsonElement root = finalReport.RootElement;
            return TryGetVerifiedInput(root, "pattern_specification", out string patternPath) &&
                PathsEqual(patternPath, artifacts.PatternPath) &&
                TryGetVerifiedInput(root, "source_report", out string sourceReportPath) &&
                PathsEqual(sourceReportPath, artifacts.SourceReportPath) &&
                TryGetVerifiedInput(root, "material_coordinates", out string materialCoordinatesPath) &&
                PathsEqual(materialCoordinatesPath, artifacts.MaterialCoordinatesPath) &&
                TryGetVerifiedInput(root, "body_mesh", out string bodyPath) &&
                PathsEqual(bodyPath, artifacts.BodyPath) &&
                TryGetVerifiedInput(root, "output_mesh", out string outputPath) &&
                PathsEqual(outputPath, artifacts.FinalPath);
        }
        catch (Exception exception) when (
            exception is IOException or
            UnauthorizedAccessException or
            JsonException or
            SimulationPipelineException)
        {
            return false;
        }
    }

    private static bool HasAcceptedInitialArrangement(string preflightPath)
    {
        using JsonDocument report = JsonDocument.Parse(
            File.ReadAllText(RequireFile(preflightPath, "body-aware arrangement preflight")));
        return report.RootElement.TryGetProperty("arrangement", out JsonElement arrangement) &&
            arrangement.ValueKind is JsonValueKind.Object &&
            arrangement.TryGetProperty("accepted", out JsonElement accepted) &&
            accepted.ValueKind is JsonValueKind.True;
    }

    private static void RequireUsableBodyAwareArrangement(
        string preflightPath,
        int expectedPanelCount)
    {
        using JsonDocument report = JsonDocument.Parse(
            File.ReadAllText(RequireFile(preflightPath, "body-aware arrangement preflight")));
        if (!report.RootElement.TryGetProperty("arrangement", out JsonElement arrangement) ||
            arrangement.ValueKind is not JsonValueKind.Object ||
            !arrangement.TryGetProperty("panelCount", out JsonElement panelCountProperty) ||
            !panelCountProperty.TryGetInt32(out int panelCount) ||
            panelCount != expectedPanelCount ||
            !arrangement.TryGetProperty("stitchCount", out JsonElement stitchCountProperty) ||
            !stitchCountProperty.TryGetInt32(out int stitchCount) ||
            stitchCount <= 0 ||
            !TryGetNonNegativeFiniteDouble(
                arrangement,
                "maximumSeamGapCm",
                out double maximumSeamGapCm) ||
            maximumSeamGapCm > 0.001 ||
            !TryGetPositiveFiniteDouble(
                arrangement,
                "minimumTorsoClearanceCm",
                out _))
        {
            throw new SimulationPipelineException(
                "The compiler did not produce a complete, sewn, body-aware warm-start shell.");
        }
    }

    private static bool HasAuthoritativeSourcePlacement(GarmentDocument garment)
        => string.Equals(
                garment.Source?.Format,
                "GarmentCode JSON",
                StringComparison.OrdinalIgnoreCase) &&
            garment.Panels.Count > 0 &&
            garment.Panels.All(panel => panel.SourcePlacement is not null);

    private static async Task RunProcessAsync(
        string executable,
        IReadOnlyList<string> arguments,
        string workingDirectory,
        string logPath,
        CancellationToken cancellationToken,
        IReadOnlyCollection<int>? additionalAcceptedExitCodes = null)
    {
        ProcessStartInfo startInfo = new(executable)
        {
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        foreach (string argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        using Process process = new() { StartInfo = startInfo };
        if (!process.Start())
        {
            throw new SimulationPipelineException($"Could not start {Path.GetFileName(executable)}.");
        }

        Task<string> standardOutput = process.StandardOutput.ReadToEndAsync();
        Task<string> standardError = process.StandardError.ReadToEndAsync();
        bool cancelled = false;
        try
        {
            await process.WaitForExitAsync(cancellationToken);
        }
        catch (OperationCanceledException)
        {
            cancelled = true;
            if (!process.HasExited)
            {
                process.Kill(true);
                await process.WaitForExitAsync(CancellationToken.None);
            }
        }

        string output = await standardOutput;
        string error = await standardError;
        await File.WriteAllTextAsync(
            logPath,
            output + (string.IsNullOrWhiteSpace(error) ? string.Empty : Environment.NewLine + error),
            new UTF8Encoding(false),
            CancellationToken.None);
        if (cancelled)
        {
            throw new OperationCanceledException(cancellationToken);
        }
        if (process.ExitCode != 0 &&
            additionalAcceptedExitCodes?.Contains(process.ExitCode) is not true)
        {
            string detail = LastMeaningfulLine(error) ?? LastMeaningfulLine(output) ?? "No diagnostic output was produced.";
            throw new SimulationPipelineException($"{Path.GetFileName(executable)} exited with code {process.ExitCode}: {detail}");
        }
    }

    private static void RequireAcceptedPrefit(string reportPath)
    {
        using JsonDocument report = JsonDocument.Parse(File.ReadAllText(RequireFile(reportPath, "Warp pre-fit report")));
        if (!ValidateAcceptedPrefit(report.RootElement, out string reason))
        {
            throw new SimulationPipelineException($"Warp rejected the current cloth revision: {reason}.");
        }
    }

    private static void RequireAcceptedJson(string reportPath, string description)
    {
        using JsonDocument report = JsonDocument.Parse(File.ReadAllText(RequireFile(reportPath, $"{description} report")));
        if (!report.RootElement.TryGetProperty("accepted", out JsonElement accepted) ||
            accepted.ValueKind is not JsonValueKind.True)
        {
            throw new SimulationPipelineException($"Patternal rejected the {description} artifact.");
        }
    }

    private static bool ValidateAcceptedPrefit(
        JsonElement root,
        out string rejectionReason,
        bool allowLegacySchema = false)
    {
        rejectionReason = ReadPrefitRejectionReason(root);

        bool hasSchema = root.TryGetProperty("schema_version", out JsonElement schema);
        bool hasCurrentSchema = hasSchema &&
            string.Equals(schema.GetString(), CurrentWarpPrefitSchema, StringComparison.Ordinal);
        bool hasLegacySchema = allowLegacySchema && hasSchema &&
            (string.Equals(schema.GetString(), "patterna.warp-prefit-report/2.5", StringComparison.Ordinal) ||
                string.Equals(schema.GetString(), "patterna.warp-prefit-report/2.4", StringComparison.Ordinal) ||
                string.Equals(schema.GetString(), "patterna.warp-prefit-report/2.3", StringComparison.Ordinal) ||
                string.Equals(schema.GetString(), "patterna.warp-prefit-report/2.2", StringComparison.Ordinal) ||
                string.Equals(schema.GetString(), "patterna.warp-prefit-report/2.1", StringComparison.Ordinal));
        bool hasSupportedSchema = hasCurrentSchema || hasLegacySchema;
        bool solverAccepted = root.TryGetProperty("accepted", out JsonElement accepted) &&
            accepted.ValueKind is JsonValueKind.True;
        bool finitePositions = root.TryGetProperty("finite_positions", out JsonElement finite) &&
            finite.ValueKind is JsonValueKind.True;
        bool equilibriumGateEvaluated = root.TryGetProperty(
                "equilibrium_gate_evaluated",
                out JsonElement equilibriumEvaluated) &&
            equilibriumEvaluated.ValueKind is JsonValueKind.True;
        bool staticEquilibriumReached = root.TryGetProperty(
                "static_equilibrium_reached",
                out JsonElement equilibriumReached) &&
            equilibriumReached.ValueKind is JsonValueKind.True;
        bool collisionGateEvaluated = root.TryGetProperty("collision_gate_evaluated", out JsonElement evaluated) &&
            evaluated.ValueKind is JsonValueKind.True;

        bool hasCollisionProof = TryGetNonNegativeInt(root, "body_collisions", out int bodyCollisionCount) &&
            TryGetNonNegativeInt(root, "self_collisions", out int selfCollisionCount) &&
            TryGetNonNegativeInt(root, "max_body_collisions", out int maximumBodyCollisionCount) &&
            TryGetNonNegativeInt(root, "max_self_collisions", out int maximumSelfCollisionCount) &&
            bodyCollisionCount <= maximumBodyCollisionCount &&
            selfCollisionCount <= maximumSelfCollisionCount;

        bool hasSeamClosureProof = hasLegacySchema ||
            (root.TryGetProperty(
                    "seam_closure_gate_evaluated",
                    out JsonElement seamClosureEvaluated) &&
                seamClosureEvaluated.ValueKind is JsonValueKind.True &&
                TryGetPositiveInt(root, "seam_link_count", out _) &&
                TryGetNonNegativeFiniteDouble(
                    root,
                    "maximum_seam_separation_cm",
                    out double maximumSeamSeparationCm) &&
                TryGetNonNegativeFiniteDouble(
                    root,
                    "mean_seam_separation_cm",
                    out _) &&
                TryGetNonNegativeFiniteDouble(
                    root,
                    "ninety_fifth_percentile_seam_separation_cm",
                    out _) &&
                TryGetPositiveFiniteDouble(
                    root,
                    "max_seam_separation_cm",
                    out double maximumSeamSeparationLimitCm) &&
                maximumSeamSeparationCm <= maximumSeamSeparationLimitCm);

        bool hasLocalizedStrainProof = hasLegacySchema ||
            (TryGetNonNegativeFiniteDouble(
                    root,
                    "ninety_ninth_point_ninth_percentile_edge_strain_ratio",
                    out double ninetyNinthPointNinthPercentileEdgeStrainRatio) &&
                TryGetNonNegativeFiniteDouble(
                    root,
                    "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio",
                    out double ninetyNinthPointNinthPercentileEdgeStrainLimit) &&
                ninetyNinthPointNinthPercentileEdgeStrainRatio <=
                    ninetyNinthPointNinthPercentileEdgeStrainLimit);
        bool hasContactCapacityProof = hasLegacySchema ||
            (root.TryGetProperty("edge_contact_buffer_saturated", out JsonElement saturated) &&
                saturated.ValueKind is JsonValueKind.False &&
                TryGetNonNegativeInt(
                    root,
                    "maximum_observed_edge_contacts",
                    out int maximumObservedEdgeContacts) &&
                TryGetPositiveInt(root, "edge_contact_capacity", out int edgeContactCapacity) &&
                TryGetPositiveInt(root, "edge_contacts_per_spring", out _) &&
                maximumObservedEdgeContacts < edgeContactCapacity);
        bool hasContinuousCollisionProof = hasLegacySchema ||
            (TryGetPositiveInt(root, "simulation_substeps", out int simulationSubsteps) &&
                simulationSubsteps >= 10);
        bool hasMaterialSpaceStrainProof = hasLegacySchema ||
            HasMaterialSpaceStrainCoverage(root);
        bool hasPhysicalIdentityProof = hasLegacySchema ||
            HasPhysicalArtifactIdentity(root);
        bool hasStrainProof = TryGetNonNegativeInt(root, "evaluated_edge_count", out int evaluatedEdgeCount) &&
            evaluatedEdgeCount > 0 &&
            TryGetNonNegativeFiniteDouble(root, "maximum_edge_strain_ratio", out double maximumEdgeStrainRatio) &&
            TryGetNonNegativeFiniteDouble(
                root,
                "ninety_fifth_percentile_edge_strain_ratio",
                out double ninetyFifthPercentileEdgeStrainRatio) &&
            TryGetNonNegativeFiniteDouble(root, "max_edge_strain_ratio", out double maximumEdgeStrainLimit) &&
            TryGetNonNegativeFiniteDouble(
                root,
                "max_ninety_fifth_percentile_edge_strain_ratio",
                out double ninetyFifthPercentileEdgeStrainLimit) &&
            maximumEdgeStrainRatio <= maximumEdgeStrainLimit &&
            ninetyFifthPercentileEdgeStrainRatio <= ninetyFifthPercentileEdgeStrainLimit &&
            hasLocalizedStrainProof &&
            hasMaterialSpaceStrainProof;

        bool hasFabricProof = root.TryGetProperty("solver_config_sha256", out JsonElement configHash) &&
            configHash.GetString() is string hash &&
            hash.Length == 64 &&
            root.TryGetProperty("fabric", out JsonElement fabric) &&
            TryGetPositiveFiniteDouble(fabric, "thickness_cm", out double thicknessCm) &&
            thicknessCm <= 0.10 &&
            TryGetPositiveFiniteDouble(fabric, "density", out _) &&
            TryGetNonNegativeFiniteDouble(fabric, "friction", out _) &&
            TryGetNonNegativeFiniteDouble(fabric, "edge_bending_stiffness", out _);

        if (!hasSupportedSchema)
        {
            rejectionReason = "the solver report schema is missing or unsupported";
        }
        else if (!finitePositions)
        {
            rejectionReason = "the solver produced non-finite cloth positions";
        }
        else if (!equilibriumGateEvaluated || !staticEquilibriumReached)
        {
            rejectionReason = "the solver report does not prove a static cloth equilibrium";
        }
        else if (!collisionGateEvaluated || !hasCollisionProof)
        {
            rejectionReason = "the solver report does not prove an accepted collision gate";
        }
        else if (!hasSeamClosureProof)
        {
            rejectionReason = "the solver report does not prove closed explicit sewing constraints";
        }
        else if (!hasStrainProof)
        {
            rejectionReason = "the solver report does not prove a full-surface material-space edge-strain gate";
        }
        else if (!hasContactCapacityProof)
        {
            rejectionReason = "the solver report does not prove unsaturated edge-contact capacity";
        }
        else if (!hasContinuousCollisionProof)
        {
            rejectionReason = "the solver report does not prove a continuous-collision substep budget";
        }
        else if (!hasFabricProof)
        {
            rejectionReason = "the solver report does not prove a thin, versioned physical fabric configuration";
        }
        else if (!hasPhysicalIdentityProof)
        {
            rejectionReason = "the solver report does not bind the physical topology and implementation identity";
        }

        return hasSupportedSchema &&
            solverAccepted &&
            finitePositions &&
            equilibriumGateEvaluated &&
            staticEquilibriumReached &&
            collisionGateEvaluated &&
            hasCollisionProof &&
            hasSeamClosureProof &&
            hasStrainProof &&
            hasContactCapacityProof &&
            hasContinuousCollisionProof &&
            hasFabricProof &&
            hasPhysicalIdentityProof;
    }

    private static bool HasPhysicalArtifactIdentity(JsonElement root)
    {
        if (!TryGetString(root, "garment_topology_mode", out string topologyMode) ||
            topologyMode is not ("explicit" or "hybrid-seams" or "welded-bootstrap") ||
            !TryGetVerifiedInput(root, "pattern_specification", out _) ||
            !TryGetPositiveFiniteDouble(root, "mesh_resolution_cm", out _) ||
            !TryGetVerifiedInput(root, "physical_mesh", out _) ||
            !TryGetVerifiedInput(root, "panel_ownership", out _) ||
            !TryGetVerifiedInput(root, "rest_lengths", out _) ||
            !TryGetVerifiedInput(root, "output_mesh", out string outputMeshPath) ||
            !TryGetString(root, "output_mesh", out string legacyOutputMeshPath) ||
            !PathsEqual(outputMeshPath, legacyOutputMeshPath) ||
            !TryGetSha256(root, "physical_topology_sha256", out string physicalTopologyHash) ||
            !TryGetSha256(root, "output_topology_sha256", out string outputTopologyHash) ||
            !HashesEqual(physicalTopologyHash, outputTopologyHash) ||
            !TryGetSha256(root, "surface_corner_mapping_sha256", out _) ||
            !TryGetSha256(root, "material_rest_graph_sha256", out _) ||
            !TryGetSha256(root, "panel_ownership_sha256", out _) ||
            !TryGetSha256(root, "seam_constraint_graph_sha256", out _) ||
            !TryGetSha256(root, "mesher_implementation_sha256", out string mesherHash) ||
            !TryGetSha256(root, "solver_implementation_sha256", out _) ||
            !TryGetPositiveInt(root, "physical_vertex_count", out int physicalVertexCount) ||
            !TryGetPositiveInt(root, "physical_face_count", out _) ||
            !TryGetPositiveInt(root, "texture_vertex_count", out int textureVertexCount) ||
            !TryGetNonNegativeInt(root, "welded_vertex_reduction", out int weldedReduction) ||
            !TryGetPositiveInt(root, "panel_ownership_vertex_count", out int ownershipVertexCount) ||
            !TryGetPositiveInt(root, "material_rest_graph_edge_count", out _) ||
            !TryGetPositiveInt(root, "cloth_vertices", out int clothVertexCount) ||
            textureVertexCount < physicalVertexCount ||
            weldedReduction != textureVertexCount - physicalVertexCount ||
            ownershipVertexCount != physicalVertexCount ||
            clothVertexCount != physicalVertexCount ||
            !root.TryGetProperty("solver_implementation_files", out JsonElement implementationFiles) ||
            implementationFiles.ValueKind is not JsonValueKind.Object ||
            !implementationFiles.TryGetProperty(
                "third_party/GarmentCode/pygarment/meshgen/boxmeshgen.py",
                out JsonElement mesherFileHash) ||
            mesherFileHash.ValueKind is not JsonValueKind.String ||
            !HashesEqual(mesherHash, mesherFileHash.GetString() ?? string.Empty))
        {
            return false;
        }

        int implementationFileCount = 0;
        foreach (JsonProperty implementationFile in implementationFiles.EnumerateObject())
        {
            implementationFileCount++;
            if (implementationFile.Value.ValueKind is not JsonValueKind.String ||
                !IsSha256(implementationFile.Value.GetString()))
            {
                return false;
            }
        }
        return implementationFileCount >= 4;
    }

    private static bool HaveMatchingPhysicalIdentity(JsonElement first, JsonElement second)
    {
        string[] hashProperties =
        [
            "physical_topology_sha256",
            "surface_corner_mapping_sha256",
            "material_rest_graph_sha256",
            "panel_ownership_sha256",
            "seam_constraint_graph_sha256",
            "mesher_implementation_sha256",
            "solver_implementation_sha256"
        ];
        if (!TryGetString(first, "garment_topology_mode", out string firstMode) ||
            !TryGetString(second, "garment_topology_mode", out string secondMode) ||
            !string.Equals(firstMode, secondMode, StringComparison.Ordinal))
        {
            return false;
        }
        foreach (string property in hashProperties)
        {
            if (!TryGetSha256(first, property, out string firstHash) ||
                !TryGetSha256(second, property, out string secondHash) ||
                !HashesEqual(firstHash, secondHash))
            {
                return false;
            }
        }
        return true;
    }

    private static bool TryGetSha256(JsonElement root, string propertyName, out string hash)
    {
        hash = string.Empty;
        return TryGetString(root, propertyName, out hash) && IsSha256(hash);
    }

    private static bool IsSha256(string? value)
        => value is { Length: 64 } && value.All(character =>
            character is >= '0' and <= '9' or >= 'a' and <= 'f' or >= 'A' and <= 'F');

    private static bool HasMaterialSpaceStrainCoverage(JsonElement root)
    {
        return TryGetPositiveInt(root, "evaluated_edge_count", out int evaluatedEdgeCount) &&
            TryGetPositiveInt(
                root,
                "material_rest_length_edge_count",
                out int materialRestLengthEdgeCount) &&
            TryGetNonNegativeInt(
                root,
                "reference_geometry_edge_count",
                out int referenceGeometryEdgeCount) &&
            TryGetNonNegativeInt(root, "excluded_edge_count", out int excludedEdgeCount) &&
            excludedEdgeCount == 0 &&
            evaluatedEdgeCount == materialRestLengthEdgeCount + referenceGeometryEdgeCount &&
            root.TryGetProperty("strain_reference_mode", out JsonElement mode) &&
            mode.ValueKind is JsonValueKind.String &&
            string.Equals(
                mode.GetString(),
                "material-space-rest-lengths-with-geometry-fallback",
                StringComparison.Ordinal);
    }

    private static bool TryGetNonNegativeInt(JsonElement root, string propertyName, out int value)
    {
        value = -1;
        return root.TryGetProperty(propertyName, out JsonElement property) &&
            property.TryGetInt32(out value) &&
            value >= 0;
    }

    private static bool TryGetPositiveInt(JsonElement root, string propertyName, out int value)
        => TryGetNonNegativeInt(root, propertyName, out value) && value > 0;

    private static bool TryGetNonNegativeFiniteDouble(JsonElement root, string propertyName, out double value)
    {
        value = double.NaN;
        return root.TryGetProperty(propertyName, out JsonElement property) &&
            property.TryGetDouble(out value) &&
            double.IsFinite(value) &&
            value >= 0;
    }

    private static bool TryGetPositiveFiniteDouble(JsonElement root, string propertyName, out double value)
        => TryGetNonNegativeFiniteDouble(root, propertyName, out value) && value > 0;

    private static string ReadPrefitRejectionReason(JsonElement root)
    {
        if (root.TryGetProperty("rejection_reasons", out JsonElement reasons) &&
            reasons.ValueKind is JsonValueKind.Array)
        {
            string[] messages = reasons
                .EnumerateArray()
                .Select(value => value.GetString())
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value!)
                .ToArray();
            if (messages.Length > 0)
            {
                return string.Join("; ", messages);
            }
        }

        return "the solver did not produce a finite, collision-gated, strain-gated cloth equilibrium";
    }

    private static void RequireAcceptedPreflight(string reportPath)
    {
        using JsonDocument report = JsonDocument.Parse(File.ReadAllText(RequireFile(reportPath, "Unreal garment preflight report")));
        if (!report.RootElement.TryGetProperty("isAccepted", out JsonElement accepted) || !accepted.GetBoolean())
        {
            string issue = "Unknown preflight issue.";
            if (report.RootElement.TryGetProperty("issues", out JsonElement issues) && issues.GetArrayLength() > 0)
            {
                JsonElement firstIssue = issues[0];
                issue = firstIssue.ValueKind == JsonValueKind.Object &&
                    firstIssue.TryGetProperty("message", out JsonElement message)
                        ? message.GetString() ?? issue
                        : firstIssue.ToString();
            }
            throw new SimulationPipelineException($"The current cloth revision failed the Unreal quality gate: {issue}");
        }
    }

    private static string FindCompiler(string projectRoot)
    {
        string[] candidates =
        [
            Path.Combine(projectRoot, "Patternal.UnrealGarmentCompiler", "bin", "x64", "Debug", "net10.0", "Patternal.UnrealGarmentCompiler.exe"),
            Path.Combine(projectRoot, "Patternal.UnrealGarmentCompiler", "bin", "x64", "Release", "net10.0", "Patternal.UnrealGarmentCompiler.exe"),
            Path.Combine(projectRoot, "Patternal.UnrealGarmentCompiler", "bin", "Debug", "net10.0", "Patternal.UnrealGarmentCompiler.exe"),
            Path.Combine(projectRoot, "Patternal.UnrealGarmentCompiler", "bin", "Release", "net10.0", "Patternal.UnrealGarmentCompiler.exe")
        ];
        return candidates
            .Where(File.Exists)
            .OrderByDescending(CompilerBuildTimestampUtc)
            .FirstOrDefault()
            ?? throw new SimulationPipelineException("The Unreal garment compiler has not been built.");
    }

    private static DateTime CompilerBuildTimestampUtc(string executablePath)
    {
        string assemblyPath = Path.ChangeExtension(executablePath, ".dll");
        return File.Exists(assemblyPath)
            ? File.GetLastWriteTimeUtc(assemblyPath)
            : File.GetLastWriteTimeUtc(executablePath);
    }

    private static string FindBlender(string projectRoot, string localAppDataPath)
    {
        string sharedLocalAppData = Environment.GetFolderPath(
            Environment.SpecialFolder.LocalApplicationData);
        string[] managedRoots =
        [
            Path.Combine(sharedLocalAppData, "Patternal", "Tools"),
            Path.Combine(sharedLocalAppData, "Patterna", "Tools"),
            Path.Combine(localAppDataPath, "Tools")
        ];
        string? managedRuntime = managedRoots
            .Where(Directory.Exists)
            .SelectMany(root => Directory.EnumerateFiles(
                root,
                "blender.exe",
                SearchOption.AllDirectories))
            .OrderByDescending(File.GetLastWriteTimeUtc)
            .FirstOrDefault();
        if (managedRuntime is not null)
        {
            return managedRuntime;
        }

        return RequireFile(
            Path.Combine(
                projectRoot,
                ".runtime",
                "blender",
                "blender-4.5.9-windows-x64",
                "blender.exe"),
            "managed or project-local Blender runtime");
    }

    private static string RequireFile(string path, string description)
        => File.Exists(path)
            ? path
            : throw new SimulationPipelineException($"Patternal could not find the {description} at {path}.");

    private static string RequireDirectory(string path, string description)
        => Directory.Exists(path)
            ? path
            : throw new SimulationPipelineException($"Patternal could not find the {description} at {path}.");

    private static string? LastMeaningfulLine(string text)
        => text.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .LastOrDefault();
}
