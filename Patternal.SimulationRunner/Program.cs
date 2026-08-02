using System.Text.Json;
using System.Security.Cryptography;
using Patterna;

static string? Option(string[] values, string name)
{
    int index = Array.FindIndex(values, value => string.Equals(value, name, StringComparison.OrdinalIgnoreCase));
    return index >= 0 && index + 1 < values.Length ? values[index + 1] : null;
}

static bool HasFlag(string[] values, string name)
    => values.Any(value => string.Equals(value, name, StringComparison.OrdinalIgnoreCase));

static void WriteEvent(object value)
    => Console.WriteLine(JsonSerializer.Serialize(value, RunnerJson.Options));

string? bridgeInputPath = Option(args, "--bridge");
if (string.IsNullOrWhiteSpace(bridgeInputPath) || !File.Exists(bridgeInputPath))
{
    Console.Error.WriteLine("Usage: Patternal.SimulationRunner --bridge <path> [--production-shirt-source <path>] [--job-root <path>] [--runtime-data-root <path>] [--probe-only]");
    return 2;
}

string patternaLocalData = Option(args, "--runtime-data-root") ?? Path.Combine(
    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
    "Patterna");
string jobRoot = Option(args, "--job-root") ?? Path.Combine(patternaLocalData, "HeadlessSimulation");
string applicationBase = Option(args, "--application-base") ?? AppContext.BaseDirectory;

try
{
    PatternaUnrealBridgeDocument bridge = JsonSerializer.Deserialize<PatternaUnrealBridgeDocument>(
        File.ReadAllText(bridgeInputPath),
        RunnerJson.Options)
        ?? throw new SimulationPipelineException("The bridge document is empty.");
    string? productionShirtSourcePath = Option(args, "--production-shirt-source");
    if (!string.IsNullOrWhiteSpace(productionShirtSourcePath))
    {
        if (!File.Exists(productionShirtSourcePath))
        {
            throw new SimulationPipelineException(
                $"The production shirt source does not exist: {productionShirtSourcePath}");
        }
        string sourceRevision = Convert.ToHexString(
            SHA256.HashData(File.ReadAllBytes(productionShirtSourcePath))).ToLowerInvariant();
        bridge = ProductionShirtBridgeBuilder.ReplaceGarment(
            bridge,
            File.ReadAllText(productionShirtSourcePath),
            productionShirtSourcePath,
            sourceRevision);
        WriteEvent(new
        {
            type = "production-shirt",
            source = productionShirtSourcePath,
            sourceRevision,
            panelCount = bridge.Garment.Panels.Count,
            seamCount = bridge.Garment.Seams.Count,
            ease = bridge.Garment.EaseProfile
        });
    }
    IReadOnlyList<string> validationErrors = bridge.Garment.Validate();
    if (validationErrors.Count > 0)
    {
        throw new SimulationPipelineException(
            $"The bridge garment is invalid: {string.Join("; ", validationErrors.Take(5))}");
    }

    SimulationRuntime runtime = SimulationRuntimeLocator.Resolve(applicationBase, patternaLocalData);
    string revision = SimulationPipeline.ComputeRevision(bridge);
    bool cached = SimulationPipeline.TryGetAcceptedResult(jobRoot, revision, out SimulationPipelineResult? cachedResult);
    WriteEvent(new
    {
        type = "probe",
        runtimeVersion = runtime.RuntimeVersion,
        runtimeOrigin = runtime.Origin,
        revision,
        cachedAcceptedResult = cached,
        cachedJobDirectory = cachedResult?.JobDirectory
    });
    if (HasFlag(args, "--probe-only"))
    {
        return 0;
    }

    using CancellationTokenSource cancellation = new();
    Console.CancelKeyPress += (_, eventArgs) =>
    {
        eventArgs.Cancel = true;
        cancellation.Cancel();
    };
    string bridgeOutputPath = Path.Combine(
        jobRoot,
        "UnrealBridge",
        "current.patterna-unreal.json");
    SimulationPipelineResult result = await SimulationPipeline.RunAsync(
        runtime,
        jobRoot,
        bridge,
        bridgeOutputPath,
        new JsonProgress(),
        cancellation.Token);
    WriteEvent(new
    {
        type = "result",
        result.Accepted,
        result.Revision,
        result.JobDirectory,
        result.FitReportPath,
        result.RenderMeshPath,
        result.VisualProofManifestPath,
        result.Message
    });
    return result.Accepted ? 0 : 1;
}
catch (OperationCanceledException)
{
    WriteEvent(new { type = "cancelled" });
    return 3;
}
catch (Exception exception) when (
    exception is SimulationPipelineException or
    IOException or
    UnauthorizedAccessException or
    JsonException)
{
    Console.Error.WriteLine(JsonSerializer.Serialize(
        new { type = "error", message = exception.Message },
        RunnerJson.Options));
    return 1;
}

internal sealed class JsonProgress : IProgress<SimulationPipelineProgress>
{
    public void Report(SimulationPipelineProgress value)
        => Console.WriteLine(JsonSerializer.Serialize(
            new
            {
                type = "progress",
                value.Stage,
                value.Message,
                value.Fraction
            },
            RunnerJson.Options));
}

internal static class RunnerJson
{
    public static JsonSerializerOptions Options { get; } = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = false
    };
}
