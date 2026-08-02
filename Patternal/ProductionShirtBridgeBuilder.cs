using System.Text.Json;

namespace Patterna;

public static class ProductionShirtBridgeBuilder
{
    public static PatternaUnrealBridgeDocument ReplaceGarment(
        PatternaUnrealBridgeDocument bridge,
        string sourceJson,
        string sourcePath,
        string sourceRevision)
    {
        ArgumentNullException.ThrowIfNull(bridge);
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceJson);
        ArgumentException.ThrowIfNullOrWhiteSpace(sourcePath);
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceRevision);

        Dictionary<string, double> measurements = bridge.Body.Measurements
            .ToDictionary(item => item.Key, item => item.Value, StringComparer.OrdinalIgnoreCase);
        double Required(string key)
            => measurements.TryGetValue(key, out double value) && double.IsFinite(value) && value > 0
                ? value
                : throw new SimulationPipelineException(
                    $"The production shirt bridge requires a positive {key} measurement.");
        double Average(string leftKey, string rightKey)
            => 0.5 * (Required(leftKey) + Required(rightKey));
        double PositiveOrDefault(string key, double fallback)
            => measurements.TryGetValue(key, out double value) && double.IsFinite(value) && value > 0
                ? value
                : fallback;

        GarmentDocument source = GarmentCodePatternImporter.Import(
            sourceJson,
            new GarmentCodeImportOptions(
                "adaptive-female-crew-neck",
                "Full-bust adaptive crew-neck shirt",
                bridge.Garment.Fabric,
                SourcePath: sourcePath,
                SourceRevision: sourceRevision));
        bool isBodySpecificPrincessBlock = IsBodySpecificPrincessBlock(sourceJson);
        GarmentDocument garment;
        if (isBodySpecificPrincessBlock)
        {
            // This block was drafted directly from the current detailed body
            // measurements. Running the generic shirt grader over it would
            // reinterpret its waist hem as a full-hip hem and destroy the
            // cup-aware princess geometry.
            garment = source;
        }
        else
        {
            GarmentEaseProfileDocument ease = AdaptiveShirtPatternGrader.MeasureSourceEase(source);
            double armholeDepth = Average("armholeDepthL", "armholeDepthR");
            double armscyeCircumference = Average("armscyeCircL", "armscyeCircR");
            ShirtConstructionProfileDocument construction =
                AdaptiveShirtPatternGrader.FitArmscyeConstructionProfile(
                    source,
                    armholeDepth,
                    armscyeCircumference,
                    ease.ArmscyeEaseCm);
            garment = AdaptiveShirtPatternGrader.Adapt(
                source,
                Required("chest"),
                Required("waist"),
                Required("hip"),
                Required("shoulder"),
                Required("torso"),
                Average("armLengthL", "armLengthR"),
                Average("upperArmCircL", "upperArmCircR"),
                armholeDepth,
                armscyeCircumference,
                ease,
                construction,
                highHipCircumferenceCm: PositiveOrDefault(
                    "highHipCirc",
                    Required("waist") + (Required("hip") - Required("waist")) * 0.57)).Document;
        }

        ShirtBustShapingProfileDocument? shaping = bridge.Garment.ShirtBustShapingProfile ??
            AdaptiveShirtBustShaper.Estimate(
                Required("chest"),
                PositiveOrDefault("underBust", Required("chest") * 0.75),
                PositiveOrDefault("bustSeparation", Required("chest") * 0.17),
                PositiveOrDefault("bustHeightL", Required("torso") * 0.56),
                PositiveOrDefault("bustHeightR", Required("torso") * 0.56),
                PositiveOrDefault("bustProjectionL", Required("chest") * 0.086),
                PositiveOrDefault("bustProjectionR", Required("chest") * 0.084));
        if (!isBodySpecificPrincessBlock &&
            shaping is not null &&
            !string.Equals(shaping.Mode, ShirtBustShapingModes.None, StringComparison.OrdinalIgnoreCase))
        {
            garment = PatternPhysicalDartCompiler.Compile(
                AdaptiveShirtBustShaper.Apply(garment, shaping).Document);
        }

        PatternTopologyCompilation topology = PatternTopologyCompiler.Compile(garment);
        UnrealPatternTopologyDiagnosticDocument[] diagnostics = topology.Diagnostics
            .Select(item => new UnrealPatternTopologyDiagnosticDocument(
                item.Severity.ToString().ToLowerInvariant(),
                item.Code,
                item.Message,
                item.SourceId))
            .ToArray();
        UnrealPatternTopologySummaryDocument topologySummary = new(
            topology.SchemaVersion,
            true,
            topology.Panels.Count,
            topology.VertexCount,
            topology.TriangleCount,
            topology.Seams.Count,
            diagnostics.Count(item => item.Severity == "warning"),
            diagnostics);

        double maximumPieceWidth = garment.Pieces.Max(piece => PieceDimensions(piece).Width);
        double maximumPieceHeight = garment.Pieces.Max(piece => PieceDimensions(piece).Height);
        UnrealGarmentGenerationDocument generation = bridge.UnrealGeneration with
        {
            Profile = "source-pattern-v1",
            GarmentId = garment.Id,
            BodyWaistCircumferenceCm = Required("waist"),
            BodyHipCircumferenceCm = Required("hip"),
            HemCircumferenceCm = maximumPieceWidth,
            SkirtLengthCm = maximumPieceHeight,
            RenderThicknessCm = garment.Fabric.ThicknessMillimeters / 10.0
        };

        return bridge with
        {
            GeneratedAtUtc = DateTimeOffset.UtcNow,
            Garment = garment,
            UnrealGeneration = generation,
            PatternTopology = topologySummary
        };
    }

    private static bool IsBodySpecificPrincessBlock(string sourceJson)
    {
        using JsonDocument document = JsonDocument.Parse(sourceJson);
        return document.RootElement.TryGetProperty("patterna", out JsonElement patterna) &&
            patterna.ValueKind is JsonValueKind.Object &&
            patterna.TryGetProperty("style", out JsonElement style) &&
            style.ValueKind is JsonValueKind.String &&
            string.Equals(
                style.GetString(),
                "cup-aware-princess-top",
                StringComparison.OrdinalIgnoreCase);
    }

    private static (double Width, double Height) PieceDimensions(PatternPieceDocument piece)
    {
        PatternPointDocument[] points = [piece.Start, .. piece.Boundary.Select(curve => curve.End)];
        return (
            (points.Max(point => point.X) - points.Min(point => point.X)) * piece.ScaleX,
            (points.Max(point => point.Y) - points.Min(point => point.Y)) * piece.ScaleY);
    }
}
