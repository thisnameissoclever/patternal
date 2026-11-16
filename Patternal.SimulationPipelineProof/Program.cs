using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Patterna;

static string RequireValue(string[] arguments, ref int index, string option)
{
    if (index + 1 >= arguments.Length)
    {
        throw new ArgumentException($"{option} requires a value.");
    }
    return arguments[++index];
}

static double RequireDouble(string[] arguments, ref int index, string option)
{
    string raw = RequireValue(arguments, ref index, option);
    if (!double.TryParse(
            raw,
            System.Globalization.NumberStyles.Float,
            System.Globalization.CultureInfo.InvariantCulture,
            out double value) ||
        !double.IsFinite(value))
    {
        throw new ArgumentException($"{option} requires a finite number.");
    }
    return value;
}

static string Sha256(string path)
{
    using FileStream source = File.OpenRead(path);
    return Convert.ToHexStringLower(SHA256.HashData(source));
}

static bool IsSha256(string value)
    => value.Length == 64 && value.All(character =>
        character is >= '0' and <= '9' or >= 'a' and <= 'f' or >= 'A' and <= 'F');

static bool IsVerifiedArtifact(JsonElement root, string propertyPrefix)
{
    if (!root.TryGetProperty($"{propertyPrefix}_path", out JsonElement pathElement) ||
        pathElement.ValueKind is not JsonValueKind.String ||
        string.IsNullOrWhiteSpace(pathElement.GetString()) ||
        !root.TryGetProperty($"{propertyPrefix}_sha256", out JsonElement hashElement) ||
        hashElement.ValueKind is not JsonValueKind.String ||
        !IsSha256(hashElement.GetString() ?? string.Empty))
    {
        return false;
    }

    string path = pathElement.GetString()!;
    return File.Exists(path) &&
        Sha256(path).Equals(hashElement.GetString(), StringComparison.OrdinalIgnoreCase);
}

static double ReadMeasurement(UnrealBodyProfileDocument body, string key)
    => body.Measurements.First(measurement =>
        measurement.Key.Equals(key, StringComparison.OrdinalIgnoreCase)).Value;

static string MeasurementOrigin(UnrealBodyProfileDocument body, string key)
    => body.Measurements.First(measurement =>
        measurement.Key.Equals(key, StringComparison.OrdinalIgnoreCase)).Origin;

string? projectRoot = null;
string? baseBridgePath = null;
string? basePatternPath = null;
string? profileBridgePath = null;
string? outputRoot = null;
string bustMode = ShirtBustShapingModes.None;
double? leftDartIntakeCm = null;
double? rightDartIntakeCm = null;
double? dartTipOffsetCm = null;
double? dartMouthDropCm = null;
double? shoulderDartMouthOffsetCm = null;
double? shoulderDartSharePercent = null;
double? chestEaseCm = null;
double? waistEaseCm = null;
double? hipEaseCm = null;
double? upperArmEaseCm = null;
double? armscyeEaseCm = null;
double? underarmExtensionCm = null;
bool patternOnly = false;
bool reuseBaseGarment = false;
Dictionary<string, double> overrides = new(StringComparer.OrdinalIgnoreCase);
for (int index = 0; index < args.Length; ++index)
{
    switch (args[index])
    {
        case "--project-root":
            projectRoot = RequireValue(args, ref index, "--project-root");
            break;
        case "--base-bridge":
            baseBridgePath = RequireValue(args, ref index, "--base-bridge");
            break;
        case "--base-pattern":
            basePatternPath = RequireValue(args, ref index, "--base-pattern");
            break;
        case "--profile-bridge":
            profileBridgePath = RequireValue(args, ref index, "--profile-bridge");
            break;
        case "--output-root":
            outputRoot = RequireValue(args, ref index, "--output-root");
            break;
        case "--bust-mode":
            bustMode = RequireValue(args, ref index, "--bust-mode");
            break;
        case "--left-dart-intake":
            leftDartIntakeCm = RequireDouble(args, ref index, "--left-dart-intake");
            break;
        case "--right-dart-intake":
            rightDartIntakeCm = RequireDouble(args, ref index, "--right-dart-intake");
            break;
        case "--dart-tip-offset":
            dartTipOffsetCm = RequireDouble(args, ref index, "--dart-tip-offset");
            break;
        case "--dart-mouth-drop":
            dartMouthDropCm = RequireDouble(args, ref index, "--dart-mouth-drop");
            break;
        case "--shoulder-dart-mouth-offset":
            shoulderDartMouthOffsetCm = RequireDouble(
                args,
                ref index,
                "--shoulder-dart-mouth-offset");
            break;
        case "--shoulder-dart-share":
            shoulderDartSharePercent = RequireDouble(args, ref index, "--shoulder-dart-share");
            break;
        case "--chest-ease":
            chestEaseCm = RequireDouble(args, ref index, "--chest-ease");
            break;
        case "--waist-ease":
            waistEaseCm = RequireDouble(args, ref index, "--waist-ease");
            break;
        case "--hip-ease":
            hipEaseCm = RequireDouble(args, ref index, "--hip-ease");
            break;
        case "--upper-arm-ease":
            upperArmEaseCm = RequireDouble(args, ref index, "--upper-arm-ease");
            break;
        case "--armscye-ease":
            armscyeEaseCm = RequireDouble(args, ref index, "--armscye-ease");
            break;
        case "--underarm-extension":
            underarmExtensionCm = RequireDouble(args, ref index, "--underarm-extension");
            break;
        case "--pattern-only":
            patternOnly = true;
            break;
        case "--reuse-base-garment":
            reuseBaseGarment = true;
            break;
        case "--measurement":
            string assignment = RequireValue(args, ref index, "--measurement");
            string[] parts = assignment.Split('=', 2, StringSplitOptions.TrimEntries);
            if (parts.Length != 2 ||
                string.IsNullOrWhiteSpace(parts[0]) ||
                !double.TryParse(parts[1], System.Globalization.CultureInfo.InvariantCulture, out double value) ||
                !double.IsFinite(value) ||
                value <= 0)
            {
                throw new ArgumentException($"Invalid measurement assignment: {assignment}");
            }
            overrides[parts[0]] = value;
            break;
        case "--help":
        case "-h":
            Console.WriteLine(
                "Usage: Patternal.SimulationPipelineProof --project-root <path> --base-bridge <json> " +
                "[--base-pattern <GarmentCode json>] " +
                "--profile-bridge <json> --output-root <path> --measurement <key=value> [...] " +
                "[--bust-mode <none|side-darts|shoulder-darts|distributed-darts>] " +
                "[--left-dart-intake <cm>] [--right-dart-intake <cm>] " +
                "[--dart-tip-offset <cm>] [--dart-mouth-drop <cm>] " +
                "[--shoulder-dart-mouth-offset <cm>] [--shoulder-dart-share <percent>] " +
                "[--chest-ease <cm>] [--waist-ease <cm>] [--hip-ease <cm>] [--upper-arm-ease <cm>] " +
                "[--armscye-ease <cm>] " +
                "[--underarm-extension <cm>] " +
                "[--pattern-only] [--reuse-base-garment]");
            return 0;
        default:
            throw new ArgumentException($"Unknown argument: {args[index]}");
    }
}

if (string.IsNullOrWhiteSpace(projectRoot) ||
    string.IsNullOrWhiteSpace(baseBridgePath) ||
    string.IsNullOrWhiteSpace(profileBridgePath) ||
    string.IsNullOrWhiteSpace(outputRoot) ||
    overrides.Count == 0)
{
    throw new ArgumentException(
        "Project root, base bridge, profile bridge, output root, and at least one measurement override are required.");
}

projectRoot = Path.GetFullPath(projectRoot);
baseBridgePath = Path.GetFullPath(baseBridgePath);
basePatternPath = string.IsNullOrWhiteSpace(basePatternPath)
    ? null
    : Path.GetFullPath(basePatternPath);
profileBridgePath = Path.GetFullPath(profileBridgePath);
outputRoot = Path.GetFullPath(outputRoot);
Directory.CreateDirectory(outputRoot);

JsonSerializerOptions jsonOptions = new()
{
    PropertyNameCaseInsensitive = true,
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    WriteIndented = true
};
PatternaUnrealBridgeDocument baseBridge = JsonSerializer.Deserialize<PatternaUnrealBridgeDocument>(
    File.ReadAllText(baseBridgePath),
    jsonOptions) ?? throw new InvalidDataException("The base bridge is empty.");
PatternaUnrealBridgeDocument profileBridge = JsonSerializer.Deserialize<PatternaUnrealBridgeDocument>(
    File.ReadAllText(profileBridgePath),
    jsonOptions) ?? throw new InvalidDataException("The profile bridge is empty.");
if (basePatternPath is not null)
{
    if (!File.Exists(basePatternPath))
    {
        throw new FileNotFoundException("The GarmentCode base pattern is missing.", basePatternPath);
    }
    GarmentDocument importedBaseGarment = GarmentCodePatternImporter.Import(
        File.ReadAllText(basePatternPath),
        new GarmentCodeImportOptions(
            "simulation-proof-base",
            "Simulation proof base garment",
            baseBridge.Garment.Fabric,
            SourcePath: basePatternPath,
            SourceRevision: Sha256(basePatternPath)));
    baseBridge = baseBridge with
    {
        Garment = importedBaseGarment with
        {
            EaseProfile = baseBridge.Garment.EaseProfile
        }
    };
}
if (profileBridge.Body.Measurements.Count < 145)
{
    throw new InvalidDataException(
        $"The detailed body profile has only {profileBridge.Body.Measurements.Count} measurements.");
}

HashSet<string> foundOverrides = new(StringComparer.OrdinalIgnoreCase);
UnrealBridgeMeasurementDocument[] measurements = profileBridge.Body.Measurements
    .Select(measurement => overrides.TryGetValue(measurement.Key, out double value)
        ? measurement with { Value = value, Origin = "manual-override" }
        : measurement)
    .Select(measurement =>
    {
        if (overrides.ContainsKey(measurement.Key))
        {
            foundOverrides.Add(measurement.Key);
        }
        return measurement;
    })
    .ToArray();
string[] missingOverrides = overrides.Keys.Where(key => !foundOverrides.Contains(key)).ToArray();
if (missingOverrides.Length > 0)
{
    throw new InvalidDataException(
        $"The detailed body profile does not contain: {string.Join(", ", missingOverrides)}.");
}

UnrealBodyProfileDocument body = profileBridge.Body with { Measurements = measurements };
double chest = ReadMeasurement(body, "chest");
double waist = ReadMeasurement(body, "waist");
double hip = ReadMeasurement(body, "hip");
double shoulder = ReadMeasurement(body, "shoulder");
double torso = ReadMeasurement(body, "torso");
double armLength = 0.5 * (ReadMeasurement(body, "armLengthL") + ReadMeasurement(body, "armLengthR"));
double upperArm = 0.5 * (ReadMeasurement(body, "upperArmCircL") + ReadMeasurement(body, "upperArmCircR"));
double armholeDepth = 0.5 * (ReadMeasurement(body, "armholeDepthL") + ReadMeasurement(body, "armholeDepthR"));
double armscyeCircumference = 0.5 * (ReadMeasurement(body, "armscyeCircL") + ReadMeasurement(body, "armscyeCircR"));
GarmentEaseProfileDocument ease = baseBridge.Garment.EaseProfile
    ?? AdaptiveShirtPatternGrader.MeasureSourceEase(baseBridge.Garment);
ease = ease with
{
    ChestEaseCm = chestEaseCm ?? ease.ChestEaseCm,
    WaistEaseCm = waistEaseCm ?? ease.WaistEaseCm,
    HipEaseCm = hipEaseCm ?? ease.HipEaseCm,
    UpperArmEaseCm = upperArmEaseCm ?? ease.UpperArmEaseCm,
    ArmscyeEaseCm = armscyeEaseCm ?? ease.ArmscyeEaseCm
};
if (new[]
    {
        ease.ChestEaseCm,
        ease.WaistEaseCm,
        ease.HipEaseCm,
        ease.UpperArmEaseCm,
        ease.ArmscyeEaseCm
    }
    .Any(value => !double.IsFinite(value) || value < 0))
{
    throw new ArgumentOutOfRangeException(
        nameof(args),
        "Garment ease values must be finite and nonnegative.");
}
GarmentDocument garment;
AdaptiveShirtGrade grade;
if (reuseBaseGarment)
{
    garment = underarmExtensionCm is null
        ? baseBridge.Garment
        : AdaptiveShirtPatternGrader.ApplyConstructionProfile(
            baseBridge.Garment,
            ShirtConstructionPatternDrafter.Measure(baseBridge.Garment) with
            {
                UnderarmExtensionCm = underarmExtensionCm.Value
            });
    AdaptiveShirtSourceGirths sourceGirths = AdaptiveShirtPatternGrader.MeasureSourceGirths(garment);
    grade = new AdaptiveShirtGrade(
        1,
        1,
        1,
        1,
        sourceGirths.ChestGirthCm,
        sourceGirths.WaistGirthCm,
        sourceGirths.HipGirthCm,
        ease);
}
else
{
    ShirtConstructionProfileDocument? constructionProfile = underarmExtensionCm is null
        ? null
        : AdaptiveShirtPatternGrader.FitArmscyeConstructionProfile(
            baseBridge.Garment,
            armholeDepth,
            armscyeCircumference,
            ease.ArmscyeEaseCm) with
        {
            UnderarmExtensionCm = underarmExtensionCm.Value
        };
    (garment, grade) = AdaptiveShirtPatternGrader.Adapt(
        baseBridge.Garment,
        chest,
        waist,
        hip,
        shoulder,
        torso,
        armLength,
        upperArm,
        armholeDepth,
        armscyeCircumference,
        ease,
        constructionProfile);
}
if (!string.Equals(bustMode, ShirtBustShapingModes.None, StringComparison.OrdinalIgnoreCase))
{
    ShirtBustShapingProfileDocument estimatedBustShaping = AdaptiveShirtBustShaper.Estimate(
        chest,
        ReadMeasurement(body, "underBust"),
        ReadMeasurement(body, "bustSeparation"),
        ReadMeasurement(body, "bustHeightL"),
        ReadMeasurement(body, "bustHeightR"),
        ReadMeasurement(body, "bustProjectionL"),
        ReadMeasurement(body, "bustProjectionR"));
    ShirtBustShapingProfileDocument bustShaping = estimatedBustShaping with
    {
        Mode = bustMode,
        LeftDartIntakeCm = leftDartIntakeCm ?? estimatedBustShaping.LeftDartIntakeCm,
        RightDartIntakeCm = rightDartIntakeCm ?? estimatedBustShaping.RightDartIntakeCm,
        DartTipOffsetCm = dartTipOffsetCm ?? estimatedBustShaping.DartTipOffsetCm,
        DartMouthDropCm = dartMouthDropCm ?? estimatedBustShaping.DartMouthDropCm,
        ShoulderDartMouthOffsetCm = shoulderDartMouthOffsetCm ??
            estimatedBustShaping.ShoulderDartMouthOffsetCm,
        ShoulderDartSharePercent = shoulderDartSharePercent ?? 35
    };
    garment = PatternPhysicalDartCompiler.Compile(
        AdaptiveShirtBustShaper.Apply(garment, bustShaping).Document);
}
IReadOnlyList<string> garmentErrors = garment.Validate();
if (garmentErrors.Count > 0)
{
    throw new InvalidDataException(
        "The graded garment is invalid: " + string.Join("; ", garmentErrors));
}
AdaptiveShirtSourceGirths resolvedGirths =
    AdaptiveShirtPatternGrader.MeasureSourceGirths(garment);
Console.WriteLine(
    $"Resolved garment girths: chest {resolvedGirths.ChestGirthCm:0.###} cm, " +
    $"waist {resolvedGirths.WaistGirthCm:0.###} cm, hip {resolvedGirths.HipGirthCm:0.###} cm.");

UnrealGarmentGenerationDocument generation = baseBridge.UnrealGeneration with
{
    GarmentId = garment.Id,
    BodyWaistCircumferenceCm = waist,
    BodyHipCircumferenceCm = hip,
    Fabric = baseBridge.UnrealGeneration.Fabric with
    {
        Id = garment.Fabric.Id,
        Name = garment.Fabric.Name,
        MassGramsPerSquareMeter = garment.Fabric.MassGramsPerSquareMeter,
        ThicknessMillimeters = garment.Fabric.ThicknessMillimeters,
        WarpStretchPercent = garment.Fabric.WarpStretchPercent,
        WeftStretchPercent = garment.Fabric.WeftStretchPercent,
        BiasStretchPercent = garment.Fabric.BiasStretchPercent,
        BendResistance = garment.Fabric.BendResistance,
        ShearResistance = garment.Fabric.ShearResistance,
        StaticFriction = garment.Fabric.StaticFriction,
        DynamicFriction = garment.Fabric.DynamicFriction,
        Calibration = garment.Fabric.Calibration
    }
};
PatternaUnrealBridgeDocument bridge = baseBridge with
{
    GeneratedAtUtc = DateTimeOffset.UtcNow,
    Body = body,
    Garment = garment,
    UnrealGeneration = generation
};
string bridgePath = Path.Combine(outputRoot, "custom-measurement.bridge.json");
await File.WriteAllTextAsync(
    bridgePath,
    JsonSerializer.Serialize(bridge, jsonOptions),
    new UTF8Encoding(false));
if (patternOnly)
{
    // Returning here skips the pipeline, and with it the topology compiler
    // that is the only thing which checks a panel boundary for crossing
    // itself. A graded panel whose boundary folds over still measures and
    // still serialises; it fails much later, inside the mesher, as a
    // degenerate-triangle error that names no cause. Run the compiler's own
    // check here so the pattern is refused where it was made.
    try
    {
        PatternTopologyCompiler.Compile(garment);
    }
    catch (PatternTopologyException exception)
    {
        Console.Error.WriteLine("The graded pattern is not usable:");
        Console.Error.WriteLine($"  {exception.Message}");
        return 2;
    }

    string patternOnlyPath = Path.Combine(outputRoot, "pattern-only.specification.json");
    await File.WriteAllTextAsync(
        patternOnlyPath,
        GarmentCodePatternExporter.Export(garment, "pattern-only-proof"),
        new UTF8Encoding(false));
    Console.WriteLine($"Wrote {patternOnlyPath}");
    return 0;
}

Progress<SimulationPipelineProgress> progress = new(update =>
    Console.WriteLine($"[{update.Fraction,5:P0}] {update.Stage}: {update.Message}"));
SimulationRuntime runtime = SimulationRuntimeLocator.Resolve(projectRoot, outputRoot);
SimulationPipelineResult result = await SimulationPipeline.RunAsync(
    runtime,
    outputRoot,
    bridge,
    bridgePath,
    progress,
    CancellationToken.None);
if (!SimulationPipeline.TryGetAcceptedResult(outputRoot, result.Revision, out _))
{
    throw new InvalidDataException("The completed custom revision does not pass the product cache validator.");
}

string displayAvatarManifestPath = Path.Combine(result.JobDirectory, "display-avatar", "manifest.json");
string displayAvatarBodyPath = Path.Combine(result.JobDirectory, "display-avatar", "body.obj");
string prefitReportPath = result.FitReportPath;
string defaultBodyPath = Path.Combine(
    projectRoot,
    "third_party",
    "GarmentCode",
    "assets",
    "bodies",
    "patterna_mpfb_female.obj");
string defaultPatternPath = Path.Combine(
    projectRoot,
    "PatternaUnreal",
    "SourceAssets",
    "GarmentCode",
    "PatternaProductionCrewNeck.specification.json");
string defaultRenderPath = Path.Combine(
    projectRoot,
    "Patterna",
    "Assets",
    "Production",
    "patterna-production-crew-neck.obj");
foreach (string required in new[]
{
    displayAvatarManifestPath,
    displayAvatarBodyPath,
    prefitReportPath,
    defaultBodyPath,
    defaultPatternPath,
    defaultRenderPath
})
{
    if (!File.Exists(required))
    {
        throw new FileNotFoundException("Required proof artifact is missing.", required);
    }
}

Dictionary<string, string> artifactHashes = new(StringComparer.Ordinal)
{
    ["bridge"] = Sha256(bridgePath),
    ["body"] = Sha256(result.BodyPath),
    ["bodySegmentation"] = Sha256(result.BodySegmentationPath),
    ["bodyProfile"] = Sha256(result.BodyProfilePath),
    ["displayAvatarManifest"] = Sha256(displayAvatarManifestPath),
    ["displayAvatarBody"] = Sha256(displayAvatarBodyPath),
    ["pattern"] = Sha256(result.PatternPath),
    ["mesh"] = Sha256(result.MeshPath),
    ["prefit"] = Sha256(result.PrefitPath),
    ["prefitReport"] = Sha256(prefitReportPath),
    ["preflight"] = Sha256(result.PreflightPath),
    ["render"] = Sha256(result.RenderMeshPath),
    ["usd"] = Sha256(result.UsdPath),
    ["manifest"] = Sha256(result.ManifestPath)
};
Dictionary<string, string> baselineHashes = new(StringComparer.Ordinal)
{
    ["baseBridge"] = Sha256(baseBridgePath),
    ["profileBridge"] = Sha256(profileBridgePath),
    ["body"] = Sha256(defaultBodyPath),
    ["pattern"] = Sha256(defaultPatternPath),
    ["render"] = Sha256(defaultRenderPath)
};
if (artifactHashes["body"] == baselineHashes["body"] ||
    artifactHashes["pattern"] == baselineHashes["pattern"] ||
    artifactHashes["render"] == baselineHashes["render"])
{
    throw new InvalidDataException(
        "The custom measurement proof reused a baseline body, pattern, or render asset.");
}

using JsonDocument prefitReport = JsonDocument.Parse(File.ReadAllText(prefitReportPath));
JsonElement prefit = prefitReport.RootElement;
string prefitSchema = prefit.GetProperty("schema_version").GetString() ?? string.Empty;
bool solverAccepted = prefit.GetProperty("accepted").GetBoolean();
bool staticEquilibriumReached = prefit.GetProperty("static_equilibrium_reached").GetBoolean();
bool hasAcceptedFitEvidence = SimulationPipeline.TryParseFitEvidence(
    prefit,
    out SimulationFitEvidence? fitEvidence) &&
    fitEvidence is not null;
int bodyCollisions = fitEvidence?.BodyCollisions ?? int.MaxValue;
int selfCollisions = fitEvidence?.SelfCollisions ?? int.MaxValue;
int simulationSubsteps = fitEvidence?.SimulationSubsteps ?? 0;
bool seamClosureGateEvaluated = prefit.GetProperty("seam_closure_gate_evaluated").GetBoolean();
int seamLinkCount = fitEvidence?.SeamLinkCount ?? 0;
double maximumSeamSeparationCm = fitEvidence?.MaximumSeamSeparationCm ?? double.NaN;
double meanSeamSeparationCm = fitEvidence?.MeanSeamSeparationCm ?? double.NaN;
double p95SeamSeparationCm = fitEvidence?.NinetyFifthPercentileSeamSeparationCm ?? double.NaN;
double maximumAllowedSeamSeparationCm = fitEvidence?.MaximumAllowedSeamSeparationCm ?? double.NaN;
int evaluatedEdgeCount = prefit.GetProperty("evaluated_edge_count").GetInt32();
int materialRestLengthEdgeCount = prefit
    .GetProperty("material_rest_length_edge_count")
    .GetInt32();
int referenceGeometryEdgeCount = prefit
    .GetProperty("reference_geometry_edge_count")
    .GetInt32();
int excludedEdgeCount = prefit.GetProperty("excluded_edge_count").GetInt32();
int physicalVertexCount = prefit.GetProperty("physical_vertex_count").GetInt32();
int physicalFaceCount = prefit.GetProperty("physical_face_count").GetInt32();
double meshResolutionCm = prefit.GetProperty("mesh_resolution_cm").GetDouble();
string seamTopologyMode = prefit.GetProperty("seam_topology_mode").GetString() ?? string.Empty;
string[] boundArtifactPrefixes =
[
    "source_report",
    "material_surface",
    "material_coordinates",
    "body_mesh",
    "panel_ownership",
    "rest_lengths",
    "panel_index_map",
    "adapter_implementation",
    "pattern_specification",
    "output_mesh",
    "physical_output_mesh"
];
bool hasExactArtifactIdentity = boundArtifactPrefixes.All(prefix =>
    IsVerifiedArtifact(prefit, prefix));
if (prefitSchema != "patterna.newton-style3d-report/1.0" ||
    !solverAccepted ||
    !hasAcceptedFitEvidence ||
    !staticEquilibriumReached ||
    bodyCollisions != 0 ||
    selfCollisions != 0 ||
    simulationSubsteps < 10 ||
    !seamClosureGateEvaluated ||
    seamLinkCount <= 0 ||
    maximumSeamSeparationCm < 0 ||
    meanSeamSeparationCm < 0 ||
    p95SeamSeparationCm < 0 ||
    maximumAllowedSeamSeparationCm <= 0 ||
    maximumSeamSeparationCm > maximumAllowedSeamSeparationCm ||
    evaluatedEdgeCount <= 0 ||
    materialRestLengthEdgeCount <= 0 ||
    referenceGeometryEdgeCount < 0 ||
    excludedEdgeCount != 0 ||
    evaluatedEdgeCount != materialRestLengthEdgeCount + referenceGeometryEdgeCount ||
    physicalVertexCount <= 0 ||
    physicalFaceCount <= 0 ||
    Math.Abs(meshResolutionCm - 0.25) > 0.000001 ||
    !seamTopologyMode.Equals("welded-components", StringComparison.Ordinal) ||
    !hasExactArtifactIdentity)
{
    throw new InvalidDataException(
        "The exact proof did not satisfy the topology-bound, explicit-seam, full-surface Style3D equilibrium contract.");
}
object proof = new
{
    schemaVersion = "patterna.custom-measurement-proof/1.1",
    accepted = result.Accepted,
    result.Revision,
    result.JobDirectory,
    input = new
    {
        measurementCount = body.Measurements.Count,
        overrides,
        overrideOrigins = overrides.Keys.ToDictionary(
            key => key,
            key => MeasurementOrigin(body, key),
            StringComparer.OrdinalIgnoreCase),
        garmentPanelCount = garment.Panels.Count,
        garmentSeamCount = garment.Seams.Count,
        grade
    },
    solver = new
    {
        schemaVersion = prefitSchema,
        device = fitEvidence!.WarpDevice,
        completedFrames = fitEvidence.CompletedFrames,
        staticEquilibriumReached,
        bodyCollisions,
        selfCollisions,
        simulationSubsteps,
        meshResolutionCm,
        seamTopologyMode,
        hasExactArtifactIdentity,
        seamClosureGateEvaluated,
        seamLinkCount,
        maximumSeamSeparationCm,
        meanSeamSeparationCm,
        p95SeamSeparationCm,
        maximumAllowedSeamSeparationCm,
        evaluatedEdgeCount,
        materialRestLengthEdgeCount,
        referenceGeometryEdgeCount,
        excludedEdgeCount,
        fitEvidence.MaximumEdgeStrainRatio,
        fitEvidence.NinetyFifthPercentileEdgeStrainRatio,
        fitEvidence.NinetyNinthPointNinthPercentileEdgeStrainRatio,
        fitEvidence.NinetyNinthPointNinetyNinthPercentileEdgeStrainRatio,
        fitEvidence.HighStrainEdgeFraction
    },
    baselineHashes,
    artifactHashes,
    distinct = new
    {
        body = artifactHashes["body"] != baselineHashes["body"],
        pattern = artifactHashes["pattern"] != baselineHashes["pattern"],
        render = artifactHashes["render"] != baselineHashes["render"]
    },
    cacheValidationAccepted = true
};
string proofPath = Path.Combine(outputRoot, "manifest.json");
await File.WriteAllTextAsync(
    proofPath,
    JsonSerializer.Serialize(proof, jsonOptions) + Environment.NewLine,
    new UTF8Encoding(false));
Console.WriteLine($"Accepted custom measurement proof {result.Revision}.");
Console.WriteLine($"Wrote {proofPath}");
return 0;
