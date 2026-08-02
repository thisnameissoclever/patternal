namespace Patterna;

public sealed record UnrealBridgeMeasurementDocument(
    string Key,
    string Label,
    double Value,
    string Unit,
    string Origin);

public sealed record UnrealBridgeCustomMeasurementDocument(
    string Key,
    string Name,
    double Value,
    string Unit);

public sealed record UnrealBodyProfileDocument(
    string Units,
    string Posture,
    string BodyTemplate,
    int LinkedPhotoCount,
    IReadOnlyList<UnrealBridgeMeasurementDocument> Measurements,
    IReadOnlyList<UnrealBridgeCustomMeasurementDocument> CustomMeasurements);

public sealed record UnrealFabricGenerationDocument(
    string Id,
    string Name,
    double MassGramsPerSquareMeter,
    double ThicknessMillimeters,
    double WarpStretchPercent,
    double WeftStretchPercent,
    double BiasStretchPercent,
    double BendResistance,
    double ShearResistance,
    double StaticFriction,
    double DynamicFriction,
    string Calibration);

public sealed record UnrealGarmentGenerationDocument(
    string Profile,
    string GarmentId,
    double BodyWaistCircumferenceCm,
    double BodyHipCircumferenceCm,
    double WaistEaseCm,
    double HipEaseCm,
    double HemCircumferenceCm,
    double SkirtLengthCm,
    double WaistHeightCm,
    double DressingClearanceCm,
    double RenderThicknessCm,
    int PanelColumns,
    int VerticalRows,
    UnrealFabricGenerationDocument Fabric);

public sealed record UnrealPatternTopologyDiagnosticDocument(
    string Severity,
    string Code,
    string Message,
    string? SourceId = null);

public sealed record UnrealPatternTopologySummaryDocument(
    string SchemaVersion,
    bool IsValid,
    int PanelCount,
    int VertexCount,
    int TriangleCount,
    int SeamCount,
    int WarningCount,
    IReadOnlyList<UnrealPatternTopologyDiagnosticDocument> Diagnostics);

public sealed record PatternaUnrealBridgeDocument(
    string SchemaVersion,
    DateTimeOffset GeneratedAtUtc,
    UnrealBodyProfileDocument Body,
    GarmentDocument Garment,
    UnrealGarmentGenerationDocument UnrealGeneration,
    UnrealPatternTopologySummaryDocument PatternTopology);
