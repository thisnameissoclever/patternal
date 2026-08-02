using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text;
using System.Security.Cryptography;
using Patterna;
using Patterna.UnrealGarmentCompiler;

static string RequireValue(string[] arguments, ref int index, string option)
{
    if (index + 1 >= arguments.Length)
    {
        throw new ArgumentException($"{option} requires a value.");
    }

    index++;
    return arguments[index];
}

string? bridgePath = null;
string? bodyProfilePath = null;
string? outputPath = null;
string? usdOutputPath = null;
string? objOutputPath = null;
string? manifestOutputPath = null;
string? bridgeOutputPath = null;
string? garmentCodeBodyOutputPath = null;
string? garmentCodePatternPath = null;
string? garmentCodePatternReferencePath = null;
string? garmentCodeMeshPath = null;
string? garmentCodePrefitPath = null;
string? initialArrangementOutputPath = null;
string garmentId = "PatternaWrapDress";
bool reportOnly = false;
bool useFactoryDefault = false;

for (int index = 0; index < args.Length; index++)
{
    switch (args[index])
    {
        case "--bridge":
            bridgePath = RequireValue(args, ref index, "--bridge");
            break;
        case "--body-profile":
            bodyProfilePath = RequireValue(args, ref index, "--body-profile");
            break;
        case "--output":
            outputPath = RequireValue(args, ref index, "--output");
            break;
        case "--usd-output":
            usdOutputPath = RequireValue(args, ref index, "--usd-output");
            break;
        case "--obj-output":
            objOutputPath = RequireValue(args, ref index, "--obj-output");
            break;
        case "--manifest-output":
            manifestOutputPath = RequireValue(args, ref index, "--manifest-output");
            break;
        case "--bridge-output":
            bridgeOutputPath = RequireValue(args, ref index, "--bridge-output");
            break;
        case "--garmentcode-body-output":
            garmentCodeBodyOutputPath = RequireValue(args, ref index, "--garmentcode-body-output");
            break;
        case "--garmentcode-pattern":
            garmentCodePatternPath = RequireValue(args, ref index, "--garmentcode-pattern");
            break;
        case "--garmentcode-pattern-reference":
            garmentCodePatternReferencePath = RequireValue(args, ref index, "--garmentcode-pattern-reference");
            break;
        case "--garmentcode-mesh":
            garmentCodeMeshPath = RequireValue(args, ref index, "--garmentcode-mesh");
            break;
        case "--garmentcode-prefit":
            garmentCodePrefitPath = RequireValue(args, ref index, "--garmentcode-prefit");
            break;
        case "--initial-arrangement-output":
            initialArrangementOutputPath = RequireValue(args, ref index, "--initial-arrangement-output");
            break;
        case "--garment-id":
            garmentId = RequireValue(args, ref index, "--garment-id");
            break;
        case "--factory-default":
            useFactoryDefault = true;
            break;
        case "--report-only":
            reportOnly = true;
            break;
        case "--help":
        case "-h":
            Console.WriteLine("Usage: Patternal.UnrealGarmentCompiler (--bridge <json> | --factory-default | --garmentcode-pattern <json>) --body-profile <json> [--garmentcode-pattern-reference <json>] [--garmentcode-mesh <json>] [--garmentcode-prefit <obj>] [--initial-arrangement-output <json>] [--output <json>] [--usd-output <usda>] [--obj-output <obj>] [--manifest-output <json>] [--bridge-output <json>] [--garmentcode-body-output <json>] [--garment-id <identifier>] [--report-only]");
            return 0;
        default:
            throw new ArgumentException($"Unknown argument: {args[index]}");
    }
}

int garmentSourceCount =
    (string.IsNullOrWhiteSpace(bridgePath) ? 0 : 1) +
    (useFactoryDefault ? 1 : 0) +
    (string.IsNullOrWhiteSpace(garmentCodePatternPath) ? 0 : 1);
if (string.IsNullOrWhiteSpace(bodyProfilePath) || garmentSourceCount != 1)
{
    throw new ArgumentException(
        "--body-profile and exactly one garment source are required.");
}
if (!string.IsNullOrWhiteSpace(garmentCodePatternReferencePath) && string.IsNullOrWhiteSpace(bridgePath))
{
    throw new ArgumentException("--garmentcode-pattern-reference is only valid with --bridge.");
}
if ((!string.IsNullOrWhiteSpace(garmentCodeMeshPath) || !string.IsNullOrWhiteSpace(garmentCodePrefitPath)) &&
    string.IsNullOrWhiteSpace(garmentCodePatternPath) &&
    string.IsNullOrWhiteSpace(garmentCodePatternReferencePath))
{
    throw new ArgumentException("GarmentCode mesh and pre-fit inputs require --garmentcode-pattern or --garmentcode-pattern-reference.");
}

JsonSerializerOptions jsonOptions = new()
{
    PropertyNameCaseInsensitive = true,
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals,
    WriteIndented = true
};

PatternaUnrealBridgeDocument bridge;
string bridgeJson;
PatternAwareMeshDocument? patternAwareMesh = null;
GarmentPrefitMeshDocument? prefitMesh = null;
if (!string.IsNullOrWhiteSpace(garmentCodePatternPath))
{
    string resolvedPatternPath = Path.GetFullPath(garmentCodePatternPath);
    string patternJson = await File.ReadAllTextAsync(resolvedPatternPath);
    string patternRevision = Convert.ToHexStringLower(
        SHA256.HashData(Encoding.UTF8.GetBytes(patternJson)));
    GarmentDocument defaultGarment = BuildFactoryDefaultBridge().Garment;
    GarmentDocument importedGarment = GarmentCodePatternImporter.Import(
        patternJson,
        new GarmentCodeImportOptions(
            Path.GetFileNameWithoutExtension(resolvedPatternPath),
            "GarmentCode fitted garment",
            defaultGarment.Fabric,
            SourcePath: resolvedPatternPath,
            SourceRevision: patternRevision));
    PatternaUnrealBridgeDocument factoryBridge = BuildFactoryDefaultBridge();
    bridge = factoryBridge with
    {
        Garment = importedGarment,
        UnrealGeneration = factoryBridge.UnrealGeneration with
        {
            Profile = "garmentcode-v1",
            GarmentId = importedGarment.Id
        }
    };
    bridgeJson = JsonSerializer.Serialize(bridge, jsonOptions);

    string automaticMeshName = Path.GetFileNameWithoutExtension(resolvedPatternPath);
    if (automaticMeshName.EndsWith(".specification", StringComparison.OrdinalIgnoreCase))
    {
        automaticMeshName = automaticMeshName[..^".specification".Length];
    }
    string automaticMeshPath = Path.Combine(
        Path.GetDirectoryName(resolvedPatternPath)!,
        $"{automaticMeshName}.patterna-mesh.json");
    string? selectedMeshPath = !string.IsNullOrWhiteSpace(garmentCodeMeshPath)
        ? Path.GetFullPath(garmentCodeMeshPath)
        : File.Exists(automaticMeshPath) ? automaticMeshPath : null;
    if (selectedMeshPath is not null)
    {
        patternAwareMesh = PatternAwareMeshDocument.Load(selectedMeshPath, resolvedPatternPath);
        Console.Error.WriteLine(
            $"Using stitch-aware GarmentCode mesh {selectedMeshPath} at {patternAwareMesh.MeshResolutionCm:F2} cm resolution.");
    }
    if (!string.IsNullOrWhiteSpace(garmentCodePrefitPath))
    {
        if (patternAwareMesh is null)
        {
            throw new ArgumentException("--garmentcode-prefit requires --garmentcode-mesh or its automatic sidecar.");
        }
        prefitMesh = GarmentPrefitMeshDocument.Load(
            Path.GetFullPath(garmentCodePrefitPath),
            patternAwareMesh);
        Console.Error.WriteLine(
            $"Using {prefitMesh.SolverName ?? "garment solver"} pre-fit {prefitMesh.SourcePath} with {prefitMesh.Panels.Sum(panel => panel.Vertices.Count)} vertices.");
    }
}
else if (useFactoryDefault)
{
    bridge = BuildFactoryDefaultBridge();
    bridgeJson = JsonSerializer.Serialize(bridge, jsonOptions);
}
else
{
    bridgeJson = await File.ReadAllTextAsync(Path.GetFullPath(bridgePath!));
    bridge = JsonSerializer.Deserialize<PatternaUnrealBridgeDocument>(bridgeJson, jsonOptions)
        ?? throw new InvalidDataException("The bridge document is empty.");

    if (!string.IsNullOrWhiteSpace(garmentCodePatternReferencePath))
    {
        string resolvedPatternPath = Path.GetFullPath(garmentCodePatternReferencePath);
        string automaticMeshName = Path.GetFileNameWithoutExtension(resolvedPatternPath);
        if (automaticMeshName.EndsWith(".specification", StringComparison.OrdinalIgnoreCase))
        {
            automaticMeshName = automaticMeshName[..^".specification".Length];
        }
        string automaticMeshPath = Path.Combine(
            Path.GetDirectoryName(resolvedPatternPath)!,
            $"{automaticMeshName}.patterna-mesh.json");
        string? selectedMeshPath = !string.IsNullOrWhiteSpace(garmentCodeMeshPath)
            ? Path.GetFullPath(garmentCodeMeshPath)
            : File.Exists(automaticMeshPath) ? automaticMeshPath : null;
        if (selectedMeshPath is not null)
        {
            patternAwareMesh = PatternAwareMeshDocument.Load(selectedMeshPath, resolvedPatternPath);
            Console.Error.WriteLine(
                $"Using stitch-aware GarmentCode mesh {selectedMeshPath} at {patternAwareMesh.MeshResolutionCm:F2} cm resolution.");
        }
        if (!string.IsNullOrWhiteSpace(garmentCodePrefitPath))
        {
            if (patternAwareMesh is null)
            {
                throw new ArgumentException("--garmentcode-prefit requires --garmentcode-mesh or its automatic sidecar.");
            }
            prefitMesh = GarmentPrefitMeshDocument.Load(
                Path.GetFullPath(garmentCodePrefitPath),
                patternAwareMesh);
            Console.Error.WriteLine(
                $"Using {prefitMesh.SolverName ?? "garment solver"} pre-fit {prefitMesh.SourcePath} with {prefitMesh.Panels.Sum(panel => panel.Vertices.Count)} vertices.");
        }
    }
}
string bodyProfileJson = await File.ReadAllTextAsync(Path.GetFullPath(bodyProfilePath));
LiveBodyProfileDocument bodyProfile = JsonSerializer.Deserialize<LiveBodyProfileDocument>(bodyProfileJson, jsonOptions)
    ?? throw new InvalidDataException("The live body profile is empty.");

if (prefitMesh is not null)
{
    Console.Error.WriteLine(
        $"Pre-fit evidence: schema {prefitMesh.SolverReportSchemaVersion ?? "missing"}, " +
        $"solver {prefitMesh.SolverName ?? "missing"}, accepted {prefitMesh.SolverAccepted}, " +
        $"finite {prefitMesh.SolverFinitePositions}, equilibrium {prefitMesh.SolverStaticEquilibriumReached}, " +
        $"collision gate {prefitMesh.SolverCollisionGateEvaluated}, seam gate {prefitMesh.SolverSeamClosureGateEvaluated}, " +
        $"physical identity {prefitMesh.SolverPhysicalIdentityVerified}, " +
        $"body collisions {prefitMesh.BodyCollisionCount?.ToString() ?? "missing"}, " +
        $"self collisions {prefitMesh.SelfCollisionCount?.ToString() ?? "missing"}, " +
        $"substeps {prefitMesh.SolverSimulationSubsteps?.ToString() ?? "missing"}.");
}

FullGarmentPreflightReport report = FullGarmentPreflight.Run(
    bridge,
    bodyProfile,
    bridgeJson,
    bodyProfileJson,
    patternAwareMesh,
    prefitMesh);
string reportJson = JsonSerializer.Serialize(report, jsonOptions);

PatternTopologyCompilation? exportTopology = null;
FullGarmentArrangementReport? exportArrangement = null;
if (!string.IsNullOrWhiteSpace(initialArrangementOutputPath))
{
    exportTopology = PatternTopologyCompiler.Compile(
        bridge.Garment,
        new PatternTopologyCompilerOptions(
            MaximumCurveSegmentLengthCm: 0.75,
            MaximumSeamLengthMismatchRatio: 0.15));
    FullGarmentArrangementReport initialArrangement = FullGarmentArrangement.Arrange(
        exportTopology,
        bodyProfile,
        patternAwareMesh,
        prefitMesh);
    await WriteTextAsync(
        initialArrangementOutputPath,
        JsonSerializer.Serialize(initialArrangement, jsonOptions));
    Console.Error.WriteLine(
        $"Wrote body-aware initial arrangement with {initialArrangement.Panels.Count} panels and {initialArrangement.Stitches.Count} stitches.");
}

if (!string.IsNullOrWhiteSpace(outputPath))
{
    await WriteTextAsync(outputPath, reportJson);
}

if (!string.IsNullOrWhiteSpace(bridgeOutputPath))
{
    await WriteTextAsync(bridgeOutputPath, bridgeJson);
}

if (!string.IsNullOrWhiteSpace(garmentCodeBodyOutputPath))
{
    GarmentCodeBodyMappingResult bodyMapping = GarmentCodeBodyMapper.Map(bridge.Body);
    await WriteTextAsync(garmentCodeBodyOutputPath, bodyMapping.ToJson());
    Console.Error.WriteLine(
        $"Wrote {bodyMapping.Body.Count} GarmentCode body parameters. " +
        $"Fallback source measurements: {bodyMapping.FallbackParameters.Count}.");
}

bool exportRequested =
    !string.IsNullOrWhiteSpace(usdOutputPath) ||
    !string.IsNullOrWhiteSpace(objOutputPath) ||
    !string.IsNullOrWhiteSpace(manifestOutputPath);
if (exportRequested)
{
    if (string.IsNullOrWhiteSpace(usdOutputPath) || string.IsNullOrWhiteSpace(manifestOutputPath))
    {
        throw new ArgumentException("--usd-output and --manifest-output must be supplied together.");
    }
    if (!string.IsNullOrWhiteSpace(objOutputPath) &&
        (string.IsNullOrWhiteSpace(usdOutputPath) || string.IsNullOrWhiteSpace(manifestOutputPath)))
    {
        throw new ArgumentException("--obj-output requires --usd-output and --manifest-output.");
    }
    if (!report.IsAccepted)
    {
        Console.Error.WriteLine("The garment failed preflight. No Unreal cloth files were written.");
    }
    else
    {
        PatternTopologyCompilation topology = exportTopology ?? PatternTopologyCompiler.Compile(
            bridge.Garment,
            new PatternTopologyCompilerOptions(
                MaximumCurveSegmentLengthCm: 0.75,
                MaximumSeamLengthMismatchRatio: 0.15));
        FullGarmentArrangementReport arrangement = exportArrangement ?? FullGarmentArrangement.Arrange(
            topology,
            bodyProfile,
            patternAwareMesh,
            prefitMesh);
        FullGarmentUsdExport export = FullGarmentUsdExporter.Export(
            arrangement,
            bridge.Garment,
            garmentId);
        await WriteTextAsync(usdOutputPath, export.Usd);
        if (!string.IsNullOrWhiteSpace(objOutputPath))
        {
            await WriteTextAsync(objOutputPath, export.RenderObj);
        }
        await WriteTextAsync(manifestOutputPath, export.ManifestJson);
        Console.Error.WriteLine(
            $"Wrote verified Unreal cloth {export.UsdSha256} with {export.SimulationVertexCount} vertices, {export.SimulationTriangleCount} triangles, {export.SeamCount} construction seams, {export.StitchCount} stitches, {export.ClosureCount} closures, and {export.ClosureConstraintCount} closure constraints.");
    }
}

Console.WriteLine(reportJson);
return report.IsAccepted || reportOnly ? 0 : 2;

static async Task WriteTextAsync(string path, string text)
{
    string resolvedPath = Path.GetFullPath(path);
    string? parent = Path.GetDirectoryName(resolvedPath);
    if (!string.IsNullOrWhiteSpace(parent))
    {
        Directory.CreateDirectory(parent);
    }
    await File.WriteAllTextAsync(resolvedPath, text, new UTF8Encoding(false));
}

static PatternaUnrealBridgeDocument BuildFactoryDefaultBridge()
{
    GarmentDocument garment = GarmentDocumentFactory.CreateWrapDress(
        167,
        92,
        71,
        99,
        39,
        42,
        "cotton",
        120,
        9,
        38,
        0.45);
    FabricPhysicsDocument sourceFabric = garment.Fabric;
    UnrealFabricGenerationDocument fabric = new(
        sourceFabric.Id,
        sourceFabric.Name,
        sourceFabric.MassGramsPerSquareMeter,
        sourceFabric.ThicknessMillimeters,
        sourceFabric.WarpStretchPercent,
        sourceFabric.WeftStretchPercent,
        sourceFabric.BiasStretchPercent,
        sourceFabric.BendResistance,
        sourceFabric.ShearResistance,
        sourceFabric.StaticFriction,
        sourceFabric.DynamicFriction,
        sourceFabric.Calibration);
    UnrealGarmentGenerationDocument generation = new(
        "full-wrap-dress-v1",
        "PatternaWrapDress",
        71,
        99,
        2,
        5,
        190,
        62,
        103,
        0,
        sourceFabric.ThicknessMillimeters / 10,
        72,
        48,
        fabric);
    UnrealBodyProfileDocument body = new(
        "centimeters",
        "balanced",
        "neutral",
        0,
        [],
        []);
    UnrealPatternTopologySummaryDocument topology = new(
        "patterna.topology/1.1",
        true,
        garment.Panels.Count,
        0,
        0,
        garment.Seams.Count,
        0,
        []);
    return new PatternaUnrealBridgeDocument(
        "patterna.unreal-bridge/1.0",
        DateTimeOffset.UnixEpoch,
        body,
        garment,
        generation,
        topology);
}
