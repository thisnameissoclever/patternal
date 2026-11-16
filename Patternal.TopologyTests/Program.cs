using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Patterna;

static void Assert(bool condition, string message)
{
    if (!condition)
    {
        throw new InvalidOperationException(message);
    }
}

static string FileHash(string path)
{
    using FileStream stream = File.OpenRead(path);
    return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
}

static void ExpectRejected(string name, GarmentDocument document, string expectedText)
{
    try
    {
        PatternTopologyCompiler.Compile(document);
        throw new InvalidOperationException($"{name} was accepted unexpectedly.");
    }
    catch (PatternTopologyException exception)
    {
        Assert(
            exception.Message.Contains(expectedText, StringComparison.OrdinalIgnoreCase),
            $"{name} failed for the wrong reason: {exception.Message}");
    }
}

static FabricPhysicsDocument Fabric()
    => new(
        "test-cotton",
        "Test cotton",
        120,
        0.34,
        5,
        9,
        12.6,
        38,
        79.1,
        0.52,
        0.45,
        "test");

static PatternCurveDocument Line(string id, double x, double y)
    => new(id, "line", new PatternPointDocument(x, y));

static PatternPointDocument EvaluateCurve(
    PatternPointDocument start,
    PatternCurveDocument curve,
    double parameter)
{
    if (curve.Kind == "line")
    {
        return new PatternPointDocument(
            start.X + (curve.End.X - start.X) * parameter,
            start.Y + (curve.End.Y - start.Y) * parameter);
    }
    PatternPointDocument control1 = curve.Control1!;
    PatternPointDocument control2 = curve.Control2!;
    double inverse = 1 - parameter;
    return new PatternPointDocument(
        inverse * inverse * inverse * start.X +
            3 * inverse * inverse * parameter * control1.X +
            3 * inverse * parameter * parameter * control2.X +
            parameter * parameter * parameter * curve.End.X,
        inverse * inverse * inverse * start.Y +
            3 * inverse * inverse * parameter * control1.Y +
            3 * inverse * parameter * parameter * control2.Y +
            parameter * parameter * parameter * curve.End.Y);
}

static double PointDistance(PatternPointDocument first, PatternPointDocument second)
    => Math.Sqrt(
        (first.X - second.X) * (first.X - second.X) +
        (first.Y - second.Y) * (first.Y - second.Y));

static PatternPointDocument ScalePoint(PatternPieceDocument piece, PatternPointDocument point)
    => new(point.X * piece.ScaleX, point.Y * piece.ScaleY);

static double ScaledCurveLengthToChordRatio(PatternPieceDocument piece, string curveId)
{
    int curveIndex = piece.Boundary
        .Select((curve, index) => (curve, index))
        .Single(item => string.Equals(item.curve.Id, curveId, StringComparison.OrdinalIgnoreCase))
        .index;
    PatternCurveDocument curve = piece.Boundary[curveIndex];
    PatternPointDocument start = curveIndex == 0 ? piece.Start : piece.Boundary[curveIndex - 1].End;
    PatternPointDocument scaledStart = ScalePoint(piece, start);
    PatternPointDocument scaledEnd = ScalePoint(piece, curve.End);
    double chordLength = PointDistance(scaledStart, scaledEnd);
    double curveLength = 0;
    PatternPointDocument previous = scaledStart;
    for (int sample = 1; sample <= 192; sample++)
    {
        PatternPointDocument current = ScalePoint(piece, EvaluateCurve(start, curve, sample / 192.0));
        curveLength += PointDistance(previous, current);
        previous = current;
    }
    return curveLength / chordLength;
}

static PatternPointDocument BoundaryCurveStart(PatternPieceDocument piece, string curveId)
{
    int index = piece.Boundary
        .Select((curve, curveIndex) => (curve, curveIndex))
        .Single(item => string.Equals(item.curve.Id, curveId, StringComparison.OrdinalIgnoreCase))
        .curveIndex;
    return index == 0 ? piece.Start : piece.Boundary[index - 1].End;
}

static PatternPointDocument DartMouthMidpoint(
    PatternPieceDocument piece,
    PatternDartDocument dart)
{
    PatternCurveDocument firstCurve = piece.Boundary.Single(curve =>
        string.Equals(curve.Id, dart.FirstLegBoundaryCurveId, StringComparison.OrdinalIgnoreCase));
    PatternCurveDocument secondCurve = piece.Boundary.Single(curve =>
        string.Equals(curve.Id, dart.SecondLegBoundaryCurveId, StringComparison.OrdinalIgnoreCase));
    PatternPointDocument first = EvaluateCurve(
        BoundaryCurveStart(piece, firstCurve.Id),
        firstCurve,
        dart.FirstLegParameter);
    PatternPointDocument second = EvaluateCurve(
        BoundaryCurveStart(piece, secondCurve.Id),
        secondCurve,
        dart.SecondLegParameter);
    return new PatternPointDocument(
        (first.X + second.X) * 0.5,
        (first.Y + second.Y) * 0.5);
}

string halfCentimeterWarpConfig = WarpFabricConfigWriter.Create(Fabric(), 0.5);
Assert(
    halfCentimeterWarpConfig.Contains("resolution_scale: 0.5", StringComparison.Ordinal),
    "The Warp solver config is not using the same 0.5 cm mesh resolution as the pipeline exporter.");

UnrealBodyProfileDocument mappedProfile = new(
    "centimeters",
    "balanced",
    "individual-neutral",
    0,
    [
        new("height", "Height", 171.2, "cm", "manual"),
        new("chest", "Chest", 96.4, "cm", "manual"),
        new("underBust", "Underbust", 82.1, "cm", "manual"),
        new("waist", "Waist", 74.3, "cm", "manual"),
        new("hip", "Hip", 103.6, "cm", "manual"),
        new("shoulder", "Shoulder", 40.2, "cm", "manual"),
        new("bustHeightL", "Left bust height", 26.7, "cm", "manual"),
        new("bustHeightR", "Right bust height", 27.1, "cm", "manual"),
        new("armLengthL", "Left arm", 58.2, "cm", "manual"),
        new("armLengthR", "Right arm", 59.0, "cm", "manual"),
        new("pelvicTilt", "Pelvic tilt", -4.5, "deg", "manual")
    ],
    []);
GarmentCodeBodyMappingResult mappedBody = GarmentCodeBodyMapper.Map(mappedProfile);
Assert(mappedBody.Body.Count == 26, "Detailed body mapping did not emit all 26 GarmentCode parameters.");
Assert(Math.Abs(mappedBody.Body["height"] - 171.2) < 0.001, "Height did not reach the avatar profile.");
Assert(Math.Abs(mappedBody.Body["bust"] - 96.4) < 0.001, "Chest did not reach the avatar bust parameter.");
Assert(Math.Abs(mappedBody.Body["underbust"] - 82.1) < 0.001, "Underbust did not reach the avatar profile.");
Assert(Math.Abs(mappedBody.Body["arm_length"] - 58.6) < 0.001, "Left and right arm lengths were not averaged.");
Assert(Math.Abs(mappedBody.Body["hip_inclination"] + 4.5) < 0.001, "Signed pelvic tilt was rejected or changed.");
Assert(mappedBody.Sources["arm_length"].SequenceEqual(["armLengthL", "armLengthR"]), "Body mapping provenance was lost.");
string avatarProfileJson = mappedBody.ToAvatarJson(mappedProfile);
using (JsonDocument avatarProfile = JsonDocument.Parse(avatarProfileJson))
{
    Assert(
        avatarProfile.RootElement.GetProperty("measurements").GetProperty("armLengthL").GetDouble() == 58.2,
        "The avatar profile discarded an editable left-side measurement.");
    Assert(
        avatarProfile.RootElement.GetProperty("body").EnumerateObject().Count() == 26,
        "The avatar profile discarded GarmentCode body parameters.");
    Assert(
        avatarProfile.RootElement.GetProperty("measurementOrigins").GetProperty("armLengthL").GetString() == "manual",
        "The avatar profile discarded user measurement provenance.");
}
string silkWarpConfig = WarpFabricConfigWriter.Create(new FabricPhysicsDocument(
    "silk",
    "Silk charmeuse",
    74,
    0.18,
    8,
    14,
    21,
    12,
    93,
    0.28,
    0.24,
    "test"), 0.5);
Assert(silkWarpConfig.Contains("fabric_thickness: 0.018", StringComparison.Ordinal), "Fabric thickness was not converted from millimeters to centimeters.");
Assert(silkWarpConfig.Contains("fabric_friction: 0.24", StringComparison.Ordinal), "Fabric friction did not reach the Warp configuration.");
Assert(silkWarpConfig.Contains("max_edge_strain_ratio: 0.40", StringComparison.Ordinal), "The Warp configuration lost its catastrophic peak-strain cap.");
Assert(silkWarpConfig.Contains("max_ninety_fifth_percentile_edge_strain_ratio: 0.15", StringComparison.Ordinal), "The Warp configuration lost its broad strain gate.");
Assert(silkWarpConfig.Contains("max_ninety_ninth_point_ninth_percentile_edge_strain_ratio: 0.29", StringComparison.Ordinal), "The Warp configuration lost its localized strain gate.");
Assert(silkWarpConfig.Contains("sim_substeps: 10", StringComparison.Ordinal), "The Warp configuration lost its continuous-collision substep budget.");
Assert(silkWarpConfig.Contains("solver_iterations: 4", StringComparison.Ordinal), "The Warp configuration lost its coupled-contact iteration budget.");
Assert(silkWarpConfig.Contains("sewing_ke: 50000000.0", StringComparison.Ordinal), "The Warp configuration lost its explicit seam stiffness.");
Assert(!silkWarpConfig.Contains("fabric_thickness: 0.034", StringComparison.Ordinal), "The Warp configuration still contains the bundled cotton thickness.");
Style3DFabricParameters silkStyle3D = Style3DFabricMapper.Map(new FabricPhysicsDocument(
    "silk",
    "Silk charmeuse",
    74,
    0.18,
    8,
    14,
    21,
    12,
    93,
    0.28,
    0.24,
    "test"));
Assert(
    Math.Abs(silkStyle3D.DensityKilogramsPerSquareMeter - 0.074) < 0.000001,
    "Style3D fabric density was not converted from grams to kilograms per square meter.");
Assert(
    Math.Abs(silkStyle3D.PhysicalThicknessCentimeters - 0.018) < 0.000001,
    "Style3D physical thickness was not converted from millimeters to centimeters.");
Assert(
    Math.Abs(silkStyle3D.WeftStiffness - silkStyle3D.WarpStiffness) > 0.001,
    "Style3D collapsed the independently calibrated warp and weft response.");
Assert(
    silkStyle3D.SelfContactThicknessCentimeters >= 0.15,
    "Style3D lost the collision-stability thickness that is separate from render thickness.");
Assert(
    Math.Abs(silkStyle3D.BodyFriction - 0.24) < 0.000001,
    "Style3D body friction did not follow the selected fabric.");

static PatternPieceDocument Piece(
    string id,
    PatternPointDocument start,
    IReadOnlyList<PatternCurveDocument> boundary)
    => new(
        id,
        id,
        1,
        false,
        false,
        1,
        1,
        1,
        start,
        boundary,
        new PatternLayoutDocument(0, 0, 0, 0, true));

static GarmentDocument SinglePanelDocument(PatternPieceDocument piece)
    => new(
        "patterna.garment/1.0",
        $"test-{piece.Id}",
        piece.Name,
        "centimeters",
        [piece],
        [new ClothPanelDocument("panel", piece.Id, piece.Name, "flat", false, [])],
        [],
        Fabric());

string garmentCodeSamplePath = Path.GetFullPath(Path.Combine(
    Directory.GetCurrentDirectory(),
    "third_party",
    "GarmentCode",
    "assets",
    "Patterns",
    "dress_pencil_specification.json"));
Assert(File.Exists(garmentCodeSamplePath), $"GarmentCode sample is missing at {garmentCodeSamplePath}.");
GarmentDocument importedPencilDress = GarmentCodePatternImporter.Import(
    File.ReadAllText(garmentCodeSamplePath),
    new GarmentCodeImportOptions(
        "garmentcode-pencil-dress",
        "GarmentCode fitted pencil dress",
        Fabric(),
        SourcePath: "third_party/GarmentCode/assets/Patterns/dress_pencil_specification.json",
        SourceRevision: "d449629979028123a5c4dc9e732a2ec19b7fce31"));
Assert(importedPencilDress.Pieces.Count == 6, "The GarmentCode pencil dress did not import all six shaped panels.");
Assert(importedPencilDress.Panels.Count == 6, "The GarmentCode pencil dress did not create six cloth panels.");
Assert(importedPencilDress.Seams.Count == 23, "The GarmentCode pencil dress did not import all 23 stitches.");
Assert(
    importedPencilDress.Panels.All(panel => panel.SourcePlacement is not null),
    "The GarmentCode importer discarded source 3D placement metadata.");
Assert(
    importedPencilDress.Pieces.SelectMany(piece => piece.Boundary).Any(edge => edge.Kind == "cubic"),
    "The GarmentCode importer flattened all shaped edges to lines.");

GarmentDocument gradingFixture = importedPencilDress with
{
    Pieces =
    [
        importedPencilDress.Pieces[0] with { Id = "left_ftorso" },
        importedPencilDress.Pieces[1] with { Id = "left_sleeve_f" }
    ]
};
(GarmentDocument gradedShirt, AdaptiveShirtGrade shirtGrade) = AdaptiveShirtPatternGrader.Adapt(
    gradingFixture,
    101,
    78,
    108,
    41,
    45,
    61,
    33);
Assert(shirtGrade.TorsoWidthScale > 1, "Larger body circumferences did not widen the pattern.");
Assert(shirtGrade.TorsoLengthScale > 1, "Longer torso did not lengthen the pattern.");
Assert(shirtGrade.SleeveLengthScale > 1, "Longer arms did not lengthen sleeve pieces.");
Assert(
    gradedShirt.Pieces.Where(piece => piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase)).All(piece =>
        Math.Abs(piece.ScaleX - shirtGrade.SleeveLengthScale) < 0.000001 &&
        Math.Abs(piece.ScaleY - shirtGrade.SleeveGirthScale) < 0.000001),
    "Sleeve pairs did not receive one synchronized grade.");
Assert(
    gradedShirt.Pieces.Where(piece => !piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase)).All(piece =>
        Math.Abs(piece.ScaleX - 1) < 0.000001 &&
        Math.Abs(piece.ScaleY - 1) < 0.000001),
    "Torso shaping retained a second scale transform instead of committing graded geometry.");
PatternPieceDocument sourceTorsoPiece = gradingFixture.Pieces.Single(piece =>
    !piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase));
PatternPieceDocument gradedTorsoPiece = gradedShirt.Pieces.Single(piece =>
    !piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase));
Assert(
    sourceTorsoPiece.Boundary.Zip(gradedTorsoPiece.Boundary).Any(pair =>
        Math.Abs(pair.First.End.X - pair.Second.End.X) > 0.01 ||
        Math.Abs(pair.First.End.Y - pair.Second.End.Y) > 0.01),
    "Body and ease changes did not reshape committed torso geometry.");
Assert(
    importedPencilDress.Pieces.SelectMany(piece => piece.Boundary).Any(edge => edge.Label == "lower_interface"),
    "The GarmentCode importer discarded semantic edge labels.");
PatternTopologyCompilation importedPencilTopology = PatternTopologyCompiler.Compile(importedPencilDress);
Assert(importedPencilTopology.Panels.Count == 6, "The imported pencil dress did not compile all panels.");
Assert(importedPencilTopology.Seams.Count == 23, "The imported pencil dress did not compile its full sewing graph.");
Assert(importedPencilTopology.VertexCount > 400, "The fitted pencil dress topology is unexpectedly sparse.");

string splitShirtPath = Path.GetFullPath(Path.Combine(
    Directory.GetCurrentDirectory(),
    "third_party",
    "GarmentCode",
    "assets",
    "Patterns",
    "shirt_mean_specification.json"));
GarmentDocument splitShirt = GarmentCodePatternImporter.Import(
    File.ReadAllText(splitShirtPath),
    new GarmentCodeImportOptions(
        "garmentcode-split-shirt",
        "GarmentCode split-panel shirt",
        Fabric(),
        SourcePath: "third_party/GarmentCode/assets/Patterns/shirt_mean_specification.json")) with
{
    EaseProfile = new GarmentEaseProfileDocument(10, 16.5, 10, 5)
};
(GarmentDocument customSplitShirt, _) = AdaptiveShirtPatternGrader.Adapt(
    splitShirt,
    94,
    76,
    103,
    40,
    43,
    57.3,
    29.4,
    20.7,
    42,
    splitShirt.EaseProfile,
    constructionProfile: null);
AdaptiveShirtSourceGirths customSplitGirths =
    AdaptiveShirtPatternGrader.MeasureGeometryGirths(customSplitShirt);
Console.WriteLine(
    $"Split shirt girths before seam compilation: chest {customSplitGirths.ChestGirthCm:F2}, " +
    $"waist {customSplitGirths.WaistGirthCm:F2}, hip {customSplitGirths.HipGirthCm:F2}");
Assert(Math.Abs(customSplitGirths.ChestGirthCm - 104) < 0.2,
    $"The split-panel shirt measured {customSplitGirths.ChestGirthCm:F2} cm at the chest instead of 104 cm.");
Assert(Math.Abs(customSplitGirths.WaistGirthCm - 92.5) < 0.2,
    $"The split-panel shirt measured {customSplitGirths.WaistGirthCm:F2} cm at the waist instead of 92.5 cm.");
Assert(Math.Abs(customSplitGirths.HipGirthCm - 96.6) < 0.2,
    $"The split-panel shirt measured {customSplitGirths.HipGirthCm:F2} cm at its waist-level hem instead of 96.6 cm.");
PatternTopologyCompilation customSplitTopology = PatternTopologyCompiler.Compile(customSplitShirt);
CompiledPatternSeam[] customSplitMaterialSeams = customSplitTopology.Seams
    .Where(seam => Math.Max(seam.LengthACm, seam.LengthBCm) > 2)
    .ToArray();
CompiledPatternSeam worstSplitSeam = customSplitMaterialSeams.MaxBy(seam => seam.LengthMismatchRatio)!;
Console.WriteLine(
    $"Split shirt girths: chest {customSplitGirths.ChestGirthCm:F2}, " +
    $"waist {customSplitGirths.WaistGirthCm:F2}, hem {customSplitGirths.HipGirthCm:F2}; " +
    $"maximum material seam mismatch {worstSplitSeam.Id} " +
    $"{worstSplitSeam.LengthACm:F2}/{worstSplitSeam.LengthBCm:F2} " +
    $"{worstSplitSeam.LengthMismatchRatio:P2}");
Assert(customSplitMaterialSeams.Max(seam => seam.LengthMismatchRatio) < 0.05,
    "The split-panel shirt grade left more than five percent mismatch on a material seam.");

string generatedPatternPath = Path.GetFullPath(Path.Combine(
    Directory.GetCurrentDirectory(),
    "PatternaUnreal",
    "SourceAssets",
    "GarmentCode",
    "PatternaDefaultFemalePencilDress.pattern.json"));
Assert(File.Exists(generatedPatternPath), $"The body-specific GarmentCode pattern is missing at {generatedPatternPath}.");
GarmentDocument generatedPencilDress = GarmentCodePatternImporter.Import(
    File.ReadAllText(generatedPatternPath),
    new GarmentCodeImportOptions(
        "patterna-default-female-pencil-dress",
        "Patterna default female fitted pencil dress",
        Fabric(),
        SourcePath: "PatternaUnreal/SourceAssets/GarmentCode/PatternaDefaultFemalePencilDress.pattern.json",
        SourceRevision: "d449629979028123a5c4dc9e732a2ec19b7fce31"));
PatternTopologyCompilation generatedPencilTopology = PatternTopologyCompiler.Compile(generatedPencilDress);
Assert(generatedPencilTopology.Panels.Count == 6, "The body-specific pattern did not compile all six panels.");
Assert(generatedPencilTopology.Seams.Count == 36, "The body-specific pattern did not compile all 36 sewing relationships.");
Assert(generatedPencilTopology.VertexCount > 250, "The body-specific pattern topology is unexpectedly sparse.");

string acceptedShirtPath = Path.GetFullPath(Path.Combine(
    Directory.GetCurrentDirectory(),
    "PatternaUnreal",
    "SourceAssets",
    "GarmentCode",
    "PatternaProductionCrewNeck.specification.json"));
Assert(File.Exists(acceptedShirtPath), $"The accepted shirt source is missing at {acceptedShirtPath}.");
GarmentDocument acceptedShirt = GarmentCodePatternImporter.Import(
    File.ReadAllText(acceptedShirtPath),
    new GarmentCodeImportOptions(
        "adaptive-female-crew-neck",
        "Body-specific adaptive crew-neck shirt",
        Fabric(),
        SourcePath: "PatternaUnreal/SourceAssets/GarmentCode/PatternaProductionCrewNeck.specification.json",
        SourceRevision: "e3469c92cdc0ae6e019527ff90f32f8c096884a35f95696a5e3f4c325891b3e3"));
PatternTopologyCompilation acceptedShirtTopology = PatternTopologyCompiler.Compile(acceptedShirt);
Assert(acceptedShirt.Pieces.Count == 14, "The production shirt source did not import all 14 pattern pieces.");
PatternCanvasLayoutResult acceptedShirtLayout = PatternCanvasLayoutEngine.Arrange(
    acceptedShirt.Pieces,
    960,
    720,
    4);
PatternCanvasPlacement[] acceptedShirtPlacements = acceptedShirtLayout.Placements.Values.ToArray();
Assert(acceptedShirtPlacements.Length == 14, "The 2D auto layout dropped a production shirt piece.");
Assert(
    acceptedShirtPlacements.All(item =>
        item.Left >= 0 &&
        item.Top >= 0 &&
        item.Left + item.Width <= acceptedShirtLayout.CanvasWidth &&
        item.Top + item.Height <= acceptedShirtLayout.CanvasHeight),
    "The 2D auto layout placed a production shirt piece outside the canvas.");
Assert(
    acceptedShirtPlacements.SelectMany((first, firstIndex) =>
        acceptedShirtPlacements.Skip(firstIndex + 1).Select(second => (First: first, Second: second)))
        .All(pair =>
            pair.First.Left + pair.First.Width <= pair.Second.Left ||
            pair.Second.Left + pair.Second.Width <= pair.First.Left ||
            pair.First.Top + pair.First.Height <= pair.Second.Top ||
            pair.Second.Top + pair.Second.Height <= pair.First.Top),
    "The 2D auto layout overlaps production shirt piece cells.");
Assert(acceptedShirtLayout.CanvasHeight <= 720, "The 14-piece production shirt no longer fits the baseline 2D canvas.");
double acceptedContentAspect = acceptedShirtLayout.ContentBounds.Width / acceptedShirtLayout.ContentBounds.Height;
Assert(
    acceptedContentAspect is >= 1.15 and <= 1.55,
    $"The adaptive 2D packing aspect ratio {acceptedContentAspect:F3} wastes the baseline viewport.");
Assert(
    acceptedShirtLayout.ContentBounds.Height >= 500,
    "The adaptive 2D packing collapsed back into a shallow strip with avoidable vertical whitespace.");
PatternCanvasFrameResult allPiecesFrame = PatternCanvasLayoutEngine.FrameAll(
    acceptedShirtLayout,
    800,
    600,
    0.5f,
    3f);
Assert(allPiecesFrame.ZoomFactor is >= 0.5f and <= 3f, "Fit-all produced an invalid zoom factor.");
Assert(
    allPiecesFrame.HorizontalOffset >= 0 &&
        allPiecesFrame.HorizontalOffset <= acceptedShirtLayout.CanvasWidth * allPiecesFrame.ZoomFactor - 800,
    "Fit-all produced an invalid horizontal viewport offset.");
Assert(
    allPiecesFrame.VerticalOffset >= 0 &&
        allPiecesFrame.VerticalOffset <= acceptedShirtLayout.CanvasHeight * allPiecesFrame.ZoomFactor - 600,
    "Fit-all produced an invalid vertical viewport offset.");
PatternCanvasPlacement frontTorsoPlacement = acceptedShirtLayout.Placements["front-torso"];
PatternCanvasFrameResult frontTorsoFrame = PatternCanvasLayoutEngine.Frame(
    frontTorsoPlacement,
    acceptedShirtLayout.CanvasWidth,
    acceptedShirtLayout.CanvasHeight,
    800,
    600,
    0.5f,
    3f);
Assert(frontTorsoFrame.ZoomFactor is >= 0.5f and <= 3f, "Frame-selected produced an invalid zoom factor.");
Assert(
    frontTorsoFrame.HorizontalOffset >= 0 &&
        frontTorsoFrame.HorizontalOffset <= acceptedShirtLayout.CanvasWidth * frontTorsoFrame.ZoomFactor - 800,
    "Frame-selected produced an invalid horizontal viewport offset.");
Assert(
    frontTorsoFrame.VerticalOffset >= 0 &&
        frontTorsoFrame.VerticalOffset <= acceptedShirtLayout.CanvasHeight * frontTorsoFrame.ZoomFactor - 600,
    "Frame-selected produced an invalid vertical viewport offset.");
PatternCanvasPlacement collarPlacement = acceptedShirtLayout.Placements["left-collar-front"];
PatternCanvasFrameResult collarFrame = PatternCanvasLayoutEngine.Frame(
    collarPlacement,
    acceptedShirtLayout.CanvasWidth,
    acceptedShirtLayout.CanvasHeight,
    800,
    600,
    0.5f,
    16f);
Assert(collarFrame.ZoomFactor >= 4f, "Frame-selected no longer makes a small collar piece inspectable.");
Assert(acceptedShirt.Seams.Count == 34, "The production shirt source did not import all 34 construction seams.");
Assert(acceptedShirtTopology.Panels.Count == 14, "The production shirt source did not compile all 14 panels.");
Assert(acceptedShirtTopology.Seams.Count == 34, "The production shirt topology lost a construction seam.");
Assert(
    acceptedShirt.Seams.All(seam => seam.SideA.Reverse && !seam.SideB.Reverse),
    "The imported production shirt lost GarmentCode's first-side stitch reversal semantics.");
Assert(acceptedShirt.Pieces.Any(piece => piece.Id == "front-torso"), "The production shirt lost its uninterrupted front torso piece.");
Assert(acceptedShirt.Pieces.Any(piece => piece.Id == "back-torso"), "The production shirt lost its uninterrupted back torso piece.");
Assert(acceptedShirt.Pieces.All(piece => piece.Id is not "right-ftorso" and not "left-ftorso" and not "right-btorso" and not "left-btorso"), "The production shirt regained a mirrored torso-half piece.");
Assert(
    acceptedShirt.Panels
        .Where(panel => panel.PieceId.Contains("cuff", StringComparison.OrdinalIgnoreCase))
        .All(panel => panel.Placement is "sleeveLeft" or "sleeveRight"),
    "A production cuff was classified as a torso panel instead of part of its sleeve.");
ShirtBustShapingProfileDocument estimatedBustShaping = AdaptiveShirtBustShaper.Estimate(
    92,
    79.8,
    18.6,
    25.8,
    25.6,
    4.8,
    4.7);
Assert(
    estimatedBustShaping.LeftDartIntakeCm > estimatedBustShaping.RightDartIntakeCm &&
        estimatedBustShaping.LeftDartIntakeCm is > 1 and < 4,
    "Detailed left and right bust measurements did not produce plausible asymmetric dart intake.");
ShirtBustShapingProfileDocument manualBustShaping = estimatedBustShaping with
{
    LeftDartIntakeCm = 2.4,
    RightDartIntakeCm = 2.0,
    DartTipOffsetCm = 2.7,
    DartMouthDropCm = 0.5
};
ShirtBustShapingResult shapedBustSource = AdaptiveShirtBustShaper.Apply(
    acceptedShirt,
    manualBustShaping);
PatternPieceDocument shapedBustSourceFront = shapedBustSource.Document.Pieces.Single(piece =>
    piece.Id == "front-torso");
double shapedBustSourceMaximumY = Math.Max(
    shapedBustSourceFront.Start.Y,
    shapedBustSourceFront.Boundary.Max(curve => curve.End.Y));
PatternPointDocument leftDartMouth = DartMouthMidpoint(
    shapedBustSourceFront,
    shapedBustSourceFront.Darts.Single(dart => dart.Id == AdaptiveShirtBustShaper.LeftDartId));
PatternPointDocument rightDartMouth = DartMouthMidpoint(
    shapedBustSourceFront,
    shapedBustSourceFront.Darts.Single(dart => dart.Id == AdaptiveShirtBustShaper.RightDartId));
double requestedLeftDartMouthY = shapedBustSourceMaximumY -
    manualBustShaping.LeftBustHeightCm - manualBustShaping.DartMouthDropCm;
double requestedRightDartMouthY = shapedBustSourceMaximumY -
    manualBustShaping.RightBustHeightCm - manualBustShaping.DartMouthDropCm;
Assert(
    Math.Abs(leftDartMouth.Y - requestedLeftDartMouthY) <= 4 &&
        Math.Abs(rightDartMouth.Y - requestedRightDartMouthY) <= 4,
    $"Adaptive bust shaping moved a dart mouth away from its measured bust-level placement: " +
        $"left {leftDartMouth.Y:F2}/{requestedLeftDartMouthY:F2}, " +
        $"right {rightDartMouth.Y:F2}/{requestedRightDartMouthY:F2}.");
Assert(
    Math.Abs(leftDartMouth.Y - rightDartMouth.Y) <= 1,
    "Symmetric side seams selected different construction regions for equivalent bust measurements.");
Assert(
    shapedBustSource.GeneratedDartIds.SequenceEqual(
        [AdaptiveShirtBustShaper.LeftDartId, AdaptiveShirtBustShaper.RightDartId]),
    "Adaptive bust shaping did not generate independent left and right dart source relationships.");
Assert(
    shapedBustSource.Document.ShirtBustShapingProfile == manualBustShaping,
    "Adaptive bust shaping discarded the editable manual profile.");
GarmentDocument shapedBustGarment = PatternPhysicalDartCompiler.Compile(shapedBustSource.Document);
PatternPieceDocument shapedBustFront = shapedBustGarment.Pieces.Single(piece => piece.Id == "front-torso");
Assert(
    shapedBustGarment.Seams.Where(seam =>
        seam.Id.Contains("-patterna-", StringComparison.OrdinalIgnoreCase)).All(seam =>
            seam.SideA.Reverse != seam.SideB.Reverse),
    "Sewn-edge dart division did not preserve the source GarmentCode seam orientation.");
Assert(
    shapedBustFront.Darts.Count(dart => dart.Materialized) == 2,
    "Adaptive bust shaping did not materialize both physical side darts.");
Assert(
    shapedBustFront.Darts.Where(dart => dart.Materialized).All(dart =>
        string.Equals(
            shapedBustFront.Boundary.Single(curve => curve.Id == dart.FirstLegBoundaryCurveId).Label,
            shapedBustFront.Boundary.Single(curve => curve.Id == dart.SecondLegBoundaryCurveId).Label,
            StringComparison.Ordinal)),
    "A materialized dart closure exported different semantic labels for its sewn legs.");
PatternTopologyCompilation shapedBustTopology = PatternTopologyCompiler.Compile(shapedBustGarment);
CompiledPatternSeam[] shapedBustDartSeams = shapedBustTopology.Seams.Where(seam =>
    seam.Id.Contains("bust-dart", StringComparison.OrdinalIgnoreCase)).ToArray();
Assert(shapedBustDartSeams.Length == 6,
    "Adaptive bust shaping did not compile two closures and four divided side-seam spans.");
Assert(shapedBustDartSeams.Max(seam => seam.LengthMismatchRatio) < 0.01,
    "Adaptive bust shaping exceeded the 1 percent physical dart and seam-span gate.");
Assert(shapedBustTopology.Panels.Single(panel => panel.PieceId == "front-torso")
    .Triangles.All(triangle => triangle.AreaCm2 > 0),
    "Adaptive bust shaping produced a degenerate front-torso mesh.");
Assert(
    GarmentCodePatternExporter.ComputeStructuralSignature(shapedBustGarment) !=
        GarmentCodePatternExporter.ComputeStructuralSignature(shapedBustGarment with
        {
            ShirtBustShapingProfile = manualBustShaping with
            {
                LeftBustProjectionCm = manualBustShaping.LeftBustProjectionCm + 0.1
            }
        }),
    "Editable bust-shaping values were excluded from the structural revision.");
string shapedBustJson = GarmentCodePatternExporter.Export(
    shapedBustGarment,
    "bust-shaping-round-trip");
using (JsonDocument shapedBustExport = JsonDocument.Parse(shapedBustJson))
{
    Assert(
        shapedBustExport.RootElement.GetProperty("pattern").GetProperty("stitches")
            .EnumerateArray().All(stitch => stitch.GetArrayLength() == 2),
        "GarmentCode regeneration discarded the source seam-direction contract.");
}
GarmentDocument shapedBustRoundTrip = GarmentCodePatternImporter.Import(
    shapedBustJson,
    new GarmentCodeImportOptions(
        "bust-shaping-round-trip",
        "Bust shaping round trip",
        Fabric()));
Assert(
    shapedBustRoundTrip.ShirtBustShapingProfile == manualBustShaping,
    "GarmentCode export/import lost the editable bust-shaping profile.");
Assert(
    shapedBustRoundTrip.Pieces.Single(piece => piece.Id == "front-torso")
        .Darts.Count(dart => dart.Materialized) == 2,
    "GarmentCode export/import lost materialized automatic bust darts.");
ShirtBustShapingProfileDocument shoulderBustShaping = manualBustShaping with
{
    Mode = ShirtBustShapingModes.ShoulderDarts,
    ShoulderDartMouthOffsetCm = 5.2
};
ShirtBustShapingResult shoulderBustSource = AdaptiveShirtBustShaper.Apply(
    acceptedShirt,
    shoulderBustShaping);
Assert(
    shoulderBustSource.Document.Pieces.Single(piece => piece.Id == "front-torso")
        .Darts.All(dart => dart.Name.Contains("shoulder", StringComparison.OrdinalIgnoreCase)),
    "Dart rotation did not move the measured intake from the side seams to the shoulder seams.");
GarmentDocument shoulderBustGarment = PatternPhysicalDartCompiler.Compile(
    shoulderBustSource.Document);
PatternTopologyCompilation shoulderBustTopology = PatternTopologyCompiler.Compile(
    shoulderBustGarment);
CompiledPatternSeam[] shoulderBustDartSeams = shoulderBustTopology.Seams.Where(seam =>
    seam.Id.Contains("bust-dart", StringComparison.OrdinalIgnoreCase)).ToArray();
Assert(
    shoulderBustDartSeams.Length == 6,
    "Shoulder-dart rotation did not compile two closures and four divided shoulder-seam spans.");
Assert(
    shoulderBustDartSeams.Max(seam => seam.LengthMismatchRatio) < 0.01,
    "Shoulder-dart rotation exceeded the 1 percent physical dart and seam-span gate.");
Assert(
    shoulderBustTopology.Panels.Single(panel => panel.PieceId == "front-torso")
        .Triangles.All(triangle => triangle.AreaCm2 > 0),
    "Shoulder-dart rotation produced a degenerate front-torso mesh.");
ShirtBustShapingProfileDocument distributedBustShaping = manualBustShaping with
{
    Mode = ShirtBustShapingModes.DistributedDarts,
    ShoulderDartMouthOffsetCm = 5.2,
    ShoulderDartSharePercent = 40
};
ShirtBustShapingResult distributedBustSource = AdaptiveShirtBustShaper.Apply(
    acceptedShirt,
    distributedBustShaping);
Assert(
    distributedBustSource.GeneratedDartIds.Count == 4 &&
        distributedBustSource.GeneratedDartIds.Contains(AdaptiveShirtBustShaper.LeftDartId) &&
        distributedBustSource.GeneratedDartIds.Contains(AdaptiveShirtBustShaper.RightDartId) &&
        distributedBustSource.GeneratedDartIds.Contains(AdaptiveShirtBustShaper.LeftShoulderDartId) &&
        distributedBustSource.GeneratedDartIds.Contains(AdaptiveShirtBustShaper.RightShoulderDartId),
    "Multi-dart distribution did not preserve independent side and shoulder source relationships.");
GarmentDocument distributedBustGarment = PatternPhysicalDartCompiler.Compile(
    distributedBustSource.Document);
PatternTopologyCompilation distributedBustTopology = PatternTopologyCompiler.Compile(
    distributedBustGarment);
CompiledPatternSeam[] distributedBustDartSeams = distributedBustTopology.Seams.Where(seam =>
    seam.Id.Contains("bust-dart", StringComparison.OrdinalIgnoreCase)).ToArray();
Assert(
    distributedBustDartSeams.Length == 12,
    "Multi-dart distribution did not compile four closures and eight divided external seam spans.");
Assert(
    distributedBustDartSeams.Max(seam => seam.LengthMismatchRatio) < 0.01,
    "Multi-dart distribution exceeded the 1 percent physical dart and seam-span gate.");
Assert(
    distributedBustTopology.Panels.Single(panel => panel.PieceId == "front-torso")
        .Triangles.All(triangle => triangle.AreaCm2 > 0),
    "Multi-dart distribution produced a degenerate front-torso mesh.");
string distributedBustJson = GarmentCodePatternExporter.Export(
    distributedBustGarment,
    "distributed-bust-shaping-round-trip");
GarmentDocument distributedBustRoundTrip = GarmentCodePatternImporter.Import(
    distributedBustJson,
    new GarmentCodeImportOptions(
        "distributed-bust-shaping-round-trip",
        "Distributed bust shaping round trip",
        Fabric()));
Assert(
    distributedBustRoundTrip.ShirtBustShapingProfile == distributedBustShaping,
    "GarmentCode export/import lost the multi-dart intake distribution profile.");
ShirtConstructionProfileDocument sourceConstruction =
    ShirtConstructionPatternDrafter.Measure(acceptedShirt);
Assert(sourceConstruction.FrontWidthSharePercent is > 50 and < 56,
    "The production shirt front/back chest distribution was not measured from its pattern geometry.");
Assert(sourceConstruction.FrontNeckDepthCm > sourceConstruction.BackNeckDepthCm,
    "The construction profile did not distinguish front and back neckline depth.");
ShirtConstructionProfileDocument redesignedConstruction = sourceConstruction with
{
    FrontWidthSharePercent = sourceConstruction.FrontWidthSharePercent + 0.25,
    NecklineWidthCm = sourceConstruction.NecklineWidthCm - 0.3,
    FrontNeckDepthCm = sourceConstruction.FrontNeckDepthCm + 0.5,
    BackNeckDepthCm = sourceConstruction.BackNeckDepthCm - 0.2,
    ShoulderLengthCm = sourceConstruction.ShoulderLengthCm - 0.1,
    ShoulderDropCm = sourceConstruction.ShoulderDropCm + 0.1,
    ArmscyeDepthCm = sourceConstruction.ArmscyeDepthCm + 0.2,
    SleeveCapHeightCm = sourceConstruction.SleeveCapHeightCm + 0.2,
    FrontBalanceCm = sourceConstruction.FrontBalanceCm + 0.1,
    ArmscyeScoopCm = sourceConstruction.ArmscyeScoopCm + 0.25,
    UnderarmExtensionCm = sourceConstruction.UnderarmExtensionCm + 0.15
};
GarmentEaseProfileDocument acceptedEase = AdaptiveShirtPatternGrader.MeasureSourceEase(acceptedShirt);
(GarmentDocument redesignedShirt, _) = AdaptiveShirtPatternGrader.Adapt(
    acceptedShirt,
    92,
    71,
    99,
    39,
    42,
    57.3,
    29.4,
    acceptedEase,
    redesignedConstruction);
Assert(redesignedShirt.ShirtConstructionProfile == redesignedConstruction,
    "The adaptive grade discarded the editable shirt construction profile.");
ShirtConstructionProfileDocument measuredRedesign =
    ShirtConstructionPatternDrafter.Measure(redesignedShirt);
Assert(Math.Abs(measuredRedesign.FrontWidthSharePercent - redesignedConstruction.FrontWidthSharePercent) < 0.25,
    $"Front/back bust distribution measured {measuredRedesign.FrontWidthSharePercent:F3}% instead of {redesignedConstruction.FrontWidthSharePercent:F3}%.");
Assert(Math.Abs(measuredRedesign.NecklineWidthCm - redesignedConstruction.NecklineWidthCm) < 0.1,
    "The drafted neckline width did not reach the construction target.");
Assert(Math.Abs(measuredRedesign.FrontNeckDepthCm - redesignedConstruction.FrontNeckDepthCm) < 0.1 &&
    Math.Abs(measuredRedesign.BackNeckDepthCm - redesignedConstruction.BackNeckDepthCm) < 0.1,
    "The drafted front/back neckline depths did not reach their independent targets.");
Assert(Math.Abs(measuredRedesign.ShoulderLengthCm - redesignedConstruction.ShoulderLengthCm) < 0.1 &&
    Math.Abs(measuredRedesign.ShoulderDropCm - redesignedConstruction.ShoulderDropCm) < 0.1,
    "The drafted shoulder seam did not reach its length and drop targets.");
Assert(Math.Abs(measuredRedesign.ArmscyeDepthCm - redesignedConstruction.ArmscyeDepthCm) < 0.1,
    "The drafted armscye did not reach its depth target.");
Assert(Math.Abs(measuredRedesign.ArmscyeScoopCm - redesignedConstruction.ArmscyeScoopCm) < 0.001,
    "The drafted armscye did not preserve its independent curve-shape target.");
Assert(Math.Abs(measuredRedesign.UnderarmExtensionCm - redesignedConstruction.UnderarmExtensionCm) < 0.001,
    "The drafted armscye did not preserve its independent underarm-junction extension.");
Assert(Math.Abs(measuredRedesign.SleeveCapHeightCm - redesignedConstruction.SleeveCapHeightCm) < 0.1,
    "The drafted sleeve cap did not reach its height target.");
Assert(Math.Abs(measuredRedesign.FrontBalanceCm - redesignedConstruction.FrontBalanceCm) < 0.1,
    "The drafted front balance did not reach its target.");
Assert(
    !GarmentCodePatternExporter.ComputeStructuralSignature(redesignedShirt).Equals(
        GarmentCodePatternExporter.ComputeStructuralSignature(
            acceptedShirt with { ShirtConstructionProfile = sourceConstruction }),
        StringComparison.Ordinal),
    "Construction controls did not change the effective garment revision.");
PatternTopologyCompilation redesignedTopology = PatternTopologyCompiler.Compile(redesignedShirt);
foreach (CompiledPatternSeam seam in redesignedTopology.Seams.OrderByDescending(seam => seam.LengthMismatchRatio).Take(6))
{
    Console.WriteLine($"Redesign seam {seam.Id}: {seam.PanelA}/{seam.PanelB} {seam.LengthACm:F3}/{seam.LengthBCm:F3} cm ({seam.LengthMismatchRatio:P2})");
}
Assert(redesignedTopology.Seams.Max(seam => seam.LengthMismatchRatio) < 0.04,
    $"Construction-profile drafting exceeded the 4 percent controlled-ease limit with {redesignedTopology.Seams.Max(seam => seam.LengthMismatchRatio):P2}.");
string redesignedJson = GarmentCodePatternExporter.Export(redesignedShirt, "construction-profile-test");
GarmentDocument redesignedRoundTrip = GarmentCodePatternImporter.Import(
    redesignedJson,
    new GarmentCodeImportOptions(
        "construction-profile-roundtrip",
        "Construction profile round trip",
        Fabric()));
Assert(redesignedRoundTrip.ShirtConstructionProfile == redesignedConstruction,
    "GarmentCode export/import lost editable shirt construction dimensions.");
ShirtConstructionProfileDocument baselineArmscyeFit =
    AdaptiveShirtPatternGrader.FitArmscyeConstructionProfile(
        acceptedShirt,
        20.7,
        42,
        2.5);
GarmentDocument baselineArmscyeDraft = ShirtConstructionPatternDrafter.Apply(
    acceptedShirt,
    baselineArmscyeFit);
Assert(
    Math.Abs(baselineArmscyeFit.ArmscyeDepthCm - sourceConstruction.ArmscyeDepthCm) < 0.05,
    "Body armhole depth was incorrectly copied into pattern depth instead of driving it proportionally.");
Assert(
    Math.Abs(AdaptiveShirtPatternGrader.MeasureArmscyeCircumference(baselineArmscyeDraft) - 44.5) < 0.1,
    "Armscye circumference plus editable ease did not control the sewn curve length.");
ShirtConstructionProfileDocument deeperArmscyeFit =
    AdaptiveShirtPatternGrader.FitArmscyeConstructionProfile(
        acceptedShirt,
        24.84,
        48,
        2.5);
GarmentDocument deeperArmscyeDraft = ShirtConstructionPatternDrafter.Apply(
    acceptedShirt,
    deeperArmscyeFit);
Assert(
    deeperArmscyeFit.ArmscyeDepthCm > baselineArmscyeFit.ArmscyeDepthCm * 1.15,
    "Changing the detailed armhole-depth measurement did not materially reshape the draft.");
Assert(
    Math.Abs(AdaptiveShirtPatternGrader.MeasureArmscyeCircumference(deeperArmscyeDraft) - 50.5) < 0.1,
    "Independent armhole depth changed the requested armscye circumference and ease.");
(GarmentDocument customFitShirt, AdaptiveShirtGrade customFitGrade) = AdaptiveShirtPatternGrader.Adapt(
    acceptedShirt,
    94,
    76,
    103,
    40,
    43,
    57.3,
    29.4);
(GarmentDocument detailedCustomFitShirt, _) = AdaptiveShirtPatternGrader.Adapt(
    acceptedShirt,
    94,
    76,
    103,
    40,
    43,
    57.3,
    29.4,
    20.7,
    42,
    acceptedEase,
    constructionProfile: null);
PatternTopologyCompilation detailedCustomFitTopology =
    PatternTopologyCompiler.Compile(detailedCustomFitShirt);
CompiledPatternSeam[] detailedSleeveCapSeams = detailedCustomFitTopology.Seams.Where(seam =>
    (seam.PanelA.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
        seam.PanelB.Contains("torso", StringComparison.OrdinalIgnoreCase)) ||
    (seam.PanelB.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
        seam.PanelA.Contains("torso", StringComparison.OrdinalIgnoreCase))).ToArray();
Assert(
    detailedSleeveCapSeams.Length == 6 &&
    detailedSleeveCapSeams.All(seam => seam.LengthMismatchCm < 0.02),
    "Detailed armscye fitting did not redraft every sleeve-cap attachment to the sewn torso curve.");
Dictionary<string, ClothPanelDocument> detailedPanelsById = detailedCustomFitShirt.Panels
    .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
Dictionary<string, PatternPieceDocument> detailedPiecesById = detailedCustomFitShirt.Pieces
    .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
List<double> detailedTorsoArmscyeRatios = [];
foreach (GarmentSeamDocument seam in detailedCustomFitShirt.Seams)
{
    ClothPanelDocument panelA = detailedPanelsById[seam.SideA.PanelId];
    ClothPanelDocument panelB = detailedPanelsById[seam.SideB.PanelId];
    bool aIsSleeve = panelA.PieceId.Contains("sleeve", StringComparison.OrdinalIgnoreCase);
    bool bIsSleeve = panelB.PieceId.Contains("sleeve", StringComparison.OrdinalIgnoreCase);
    bool aIsTorso = panelA.PieceId.Contains("torso", StringComparison.OrdinalIgnoreCase);
    bool bIsTorso = panelB.PieceId.Contains("torso", StringComparison.OrdinalIgnoreCase);
    SeamSideDocument? torsoSide = aIsTorso && bIsSleeve
        ? seam.SideA
        : bIsTorso && aIsSleeve
            ? seam.SideB
            : null;
    if (torsoSide is null)
    {
        continue;
    }
    PatternPieceDocument torsoPiece = detailedPiecesById[
        detailedPanelsById[torsoSide.PanelId].PieceId];
    detailedTorsoArmscyeRatios.AddRange(torsoSide.EdgeIds.Select(edgeId =>
        ScaledCurveLengthToChordRatio(torsoPiece, edgeId)));
}
Assert(
    detailedTorsoArmscyeRatios.Count == 6 && detailedTorsoArmscyeRatios.Max() < 2.0,
    $"Detailed armscye fitting created a looping torso attachment at " +
    $"{detailedTorsoArmscyeRatios.Max():F2}:1 length-to-chord ratio.");
(GarmentDocument customFitWithConstruction, _) = AdaptiveShirtPatternGrader.Adapt(
    acceptedShirt,
    94,
    76,
    103,
    40,
    43,
    57.3,
    29.4,
    acceptedEase,
    sourceConstruction);
AdaptiveShirtSourceGirths customConstructionGirths =
    AdaptiveShirtPatternGrader.MeasureGeometryGirths(customFitWithConstruction);
Assert(Math.Abs(customConstructionGirths.ChestGirthCm - 100) < 0.2 &&
    Math.Abs(customConstructionGirths.WaistGirthCm - 82) < 0.2 &&
    Math.Abs(customConstructionGirths.HipGirthCm - 111) < 0.2,
    $"Construction controls broke body-plus-ease girths: {customConstructionGirths.ChestGirthCm:F2}/{customConstructionGirths.WaistGirthCm:F2}/{customConstructionGirths.HipGirthCm:F2} cm.");
ShirtConstructionProfileDocument measuredCustomConstruction =
    ShirtConstructionPatternDrafter.Measure(customFitWithConstruction);
Assert(ShirtConstructionPatternDrafter.AreEquivalent(
        measuredCustomConstruction,
        sourceConstruction,
        tolerance: 0.25),
    "A non-default body grade discarded the user's explicit construction dimensions.");
foreach (PatternPieceDocument sourcePiece in acceptedShirt.Pieces.Where(piece =>
             piece.Id.Contains("collar", StringComparison.OrdinalIgnoreCase) ||
             piece.Id.Contains("cuff", StringComparison.OrdinalIgnoreCase)))
{
    PatternPieceDocument gradedPiece = customFitShirt.Pieces.Single(piece => piece.Id == sourcePiece.Id);
    PatternPointDocument[] sourceAccessoryPoints = [sourcePiece.Start, .. sourcePiece.Boundary.Select(curve => curve.End)];
    PatternPointDocument[] gradedAccessoryPoints = [gradedPiece.Start, .. gradedPiece.Boundary.Select(curve => curve.End)];
    double sourceMinorDimension = Math.Min(
        sourceAccessoryPoints.Max(point => point.X) - sourceAccessoryPoints.Min(point => point.X),
        sourceAccessoryPoints.Max(point => point.Y) - sourceAccessoryPoints.Min(point => point.Y));
    double gradedMinorDimension = Math.Min(
        gradedAccessoryPoints.Max(point => point.X) - gradedAccessoryPoints.Min(point => point.X),
        gradedAccessoryPoints.Max(point => point.Y) - gradedAccessoryPoints.Min(point => point.Y));
    Assert(
        gradedPiece.ScaleX == sourcePiece.ScaleX &&
        gradedPiece.ScaleY == sourcePiece.ScaleY &&
        gradedPiece.Boundary.Count == sourcePiece.Boundary.Count &&
        Math.Abs(gradedMinorDimension - sourceMinorDimension) < 0.001,
        $"Seam-specific accessory grading distorted the crosswise shape of {sourcePiece.Id}.");
}
AdaptiveShirtSourceGirths customFitGirths = AdaptiveShirtPatternGrader.MeasureGeometryGirths(customFitShirt);
Assert(Math.Abs(customFitGirths.ChestGirthCm - 100) < 0.15, "The custom shirt missed its chest ease target.");
Assert(Math.Abs(customFitGirths.WaistGirthCm - 82) < 0.15, "The custom shirt missed its waist ease target.");
Assert(Math.Abs(customFitGirths.HipGirthCm - 111) < 0.15, "The custom shirt missed its hip ease target.");
double customSleeveOpening = AdaptiveShirtPatternGrader.MeasureSleeveOpeningCircumference(customFitShirt);
double sourceSleeveOpening = AdaptiveShirtPatternGrader.MeasureSleeveOpeningCircumference(acceptedShirt);
PatternTopologyCompilation customFitTopology = PatternTopologyCompiler.Compile(customFitShirt);
foreach (CompiledPatternSeam seam in customFitTopology.Seams.Where(seam =>
             (seam.PanelA.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
                 seam.PanelB.Contains("cuff", StringComparison.OrdinalIgnoreCase)) ||
             (seam.PanelB.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
                 seam.PanelA.Contains("cuff", StringComparison.OrdinalIgnoreCase))))
{
    Console.WriteLine($"Sleeve opening {seam.Id}: {seam.PanelA}/{seam.PanelB} {seam.LengthACm:F3}/{seam.LengthBCm:F3} cm");
}
Assert(
    Math.Abs(customSleeveOpening - 34.4) < 0.1,
    $"The custom sleeve opening measured {customSleeveOpening:F2} cm instead of the 34.40 cm upper-arm ease target. " +
    $"Source was {sourceSleeveOpening:F2} cm and applied scale was {customFitGrade.SleeveGirthScale:F4}.");
Assert(
    customFitShirt.Pieces
        .Where(piece => piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase))
        .All(piece => Math.Abs(piece.ScaleX - 1) < 0.000001 && Math.Abs(piece.ScaleY - 1) < 0.000001),
    "The production sleeve grade retained a whole-piece scale instead of committed tapered geometry.");
Assert(customFitShirt.Seams.All(seam => seam.SideA.EdgeIds.Count == 1 && seam.SideB.EdgeIds.Count == 1),
    "Body grading changed construction seam topology.");
foreach (CompiledPatternSeam seam in customFitTopology.Seams
             .OrderByDescending(seam => seam.LengthMismatchRatio)
             .Take(12))
{
    Console.WriteLine(
        $"Custom seam {seam.Id}: {seam.PanelA}/{seam.PanelB} " +
        $"{seam.LengthACm:F3}/{seam.LengthBCm:F3} cm " +
        $"({seam.LengthMismatchRatio:P2})");
}
CompiledPatternSeam[] sleeveCapSeams = customFitTopology.Seams.Where(seam =>
    (seam.PanelA.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
        seam.PanelB.Contains("torso", StringComparison.OrdinalIgnoreCase)) ||
    (seam.PanelB.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
        seam.PanelA.Contains("torso", StringComparison.OrdinalIgnoreCase))).ToArray();
Assert(sleeveCapSeams.Length == 6, "The production shirt lost a sleeve-cap construction seam.");
Assert(
    sleeveCapSeams.All(seam => seam.LengthMismatchCm < 0.02) &&
    sleeveCapSeams.Where(seam => Math.Max(seam.LengthACm, seam.LengthBCm) > 2).All(seam =>
        seam.LengthMismatchRatio < 0.005),
    $"Body grading left a sleeve-cap mismatch of {sleeveCapSeams.Max(seam => seam.LengthMismatchCm):F3} cm.");
foreach (CompiledPatternSeam customCapSeam in sleeveCapSeams)
{
    CompiledPatternSeam sourceCapSeam = acceptedShirtTopology.Seams.Single(seam => seam.Id == customCapSeam.Id);
    double customSleeveCapLength = customCapSeam.PanelA.Contains("sleeve", StringComparison.OrdinalIgnoreCase)
        ? customCapSeam.LengthACm
        : customCapSeam.LengthBCm;
    double sourceSleeveCapLength = sourceCapSeam.PanelA.Contains("sleeve", StringComparison.OrdinalIgnoreCase)
        ? sourceCapSeam.LengthACm
        : sourceCapSeam.LengthBCm;
    Assert(
        Math.Abs(customSleeveCapLength - sourceSleeveCapLength) < 0.02,
        $"Slash-spread grading changed sleeve-cap arc {customCapSeam.Id} by " +
        $"{Math.Abs(customSleeveCapLength - sourceSleeveCapLength):F3} cm.");
}
CompiledPatternSeam[] materialCustomSeams = customFitTopology.Seams
    .Where(seam => Math.Max(seam.LengthACm, seam.LengthBCm) > 2)
    .ToArray();
Assert(
    materialCustomSeams.All(seam => seam.LengthMismatchRatio < 0.005),
    $"Body grading left material seam {materialCustomSeams.MaxBy(seam => seam.LengthMismatchRatio)!.Id} " +
    $"at {materialCustomSeams.Max(seam => seam.LengthMismatchRatio):P2} mismatch.");

string mainPageXamlPath = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "Patternal", "MainPage.xaml"));
string mainPageCodePath = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "Patternal", "MainPage.xaml.cs"));
string viewportPath = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "Patternal", "Assets", "avatar3d.html"));
string candidateAvatarDirectory = Path.GetFullPath(Path.Combine(
    Directory.GetCurrentDirectory(),
    "Patternal",
    "Assets",
    "Candidate",
    "Antonia"));
string candidateAvatarManifestPath = Path.Combine(candidateAvatarDirectory, "manifest.json");
string candidateAvatarGeometryPath = Path.Combine(candidateAvatarDirectory, "antonia.glb");
string candidateAvatarLicensePath = Path.GetFullPath(Path.Combine(
    Directory.GetCurrentDirectory(),
    "third_party",
    "CharMorph-db",
    "characters",
    "antonia",
    "license.txt"));
string simulationPipelinePath = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "Patternal", "SimulationPipeline.cs"));
string simulationRuntimePath = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "Patternal", "SimulationRuntime.cs"));
string simulationRuntimeInstallerPath = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "tools", "install_patterna_simulation_runtime.ps1"));
string charmorphGlbPath = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "tools", "charmorph_glb.py"));
string charmorphAnatomyPath = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "tools", "charmorph_anatomy.py"));
string charmorphPosePath = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "tools", "charmorph_pose.py"));
string charmorphGlbVerifierPath = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "tools", "verify_charmorph_glb.py"));
string mainPageXaml = File.ReadAllText(mainPageXamlPath);
string mainPageCode = File.ReadAllText(mainPageCodePath);
string viewportSource = File.ReadAllText(viewportPath);
string simulationPipelineSource = File.ReadAllText(simulationPipelinePath);
string simulationRuntimeSource = File.ReadAllText(simulationRuntimePath);
string simulationRuntimeInstallerSource = File.ReadAllText(simulationRuntimeInstallerPath);
string charmorphGlbSource = File.ReadAllText(charmorphGlbPath);
string charmorphAnatomySource = File.ReadAllText(charmorphAnatomyPath);
string charmorphPoseSource = File.ReadAllText(charmorphPosePath);
string charmorphGlbVerifierSource = File.ReadAllText(charmorphGlbVerifierPath);
using JsonDocument candidateAvatarManifest = JsonDocument.Parse(File.ReadAllText(candidateAvatarManifestPath));
JsonElement candidateAvatarRoot = candidateAvatarManifest.RootElement;
Assert(candidateAvatarRoot.GetProperty("accepted").ValueKind == JsonValueKind.False, "The Antonia candidate crossed the production acceptance boundary.");
Assert(candidateAvatarRoot.GetProperty("candidateOnly").GetBoolean(), "The Antonia GLB is not explicitly candidate-only.");
Assert(candidateAvatarRoot.GetProperty("measurementFit").GetProperty("accepted").GetBoolean(), "The packaged Antonia candidate lost its accepted measurement-fit evidence.");
Assert(candidateAvatarRoot.GetProperty("displayYawDegrees").GetDouble() == 180, "The Antonia candidate no longer faces the semantic front camera.");
Assert(candidateAvatarRoot.GetProperty("geometryBytes").GetInt64() == new FileInfo(candidateAvatarGeometryPath).Length, "The packaged Antonia GLB byte count does not match its manifest.");
Assert(candidateAvatarRoot.GetProperty("geometrySha256").GetString() == FileHash(candidateAvatarGeometryPath), "The packaged Antonia GLB hash does not match its manifest.");
Assert(candidateAvatarRoot.GetProperty("licenseSha256").GetString() == FileHash(candidateAvatarLicensePath), "The packaged Antonia license hash does not match its manifest.");
Assert(!mainPageXaml.Contains("12 sewn panels", StringComparison.Ordinal), "The packaged 3D overlay retained stale panel metadata.");
Assert(!mainPageXaml.Contains("24 construction seams", StringComparison.Ordinal), "The packaged 3D overlay retained stale seam metadata.");
Assert(
    mainPageXaml.Contains("x:Name=\"PatternScrollViewer\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("ZoomMode=\"Enabled\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("AutomationProperties.AutomationId=\"PatternZoomOutButton\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("AutomationProperties.AutomationId=\"PatternZoomText\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("AutomationProperties.AutomationId=\"PatternZoomInButton\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("AutomationProperties.AutomationId=\"PatternFitButton\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("AutomationProperties.AutomationId=\"PatternFrameSelectedButton\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("AutomationProperties.AutomationId=\"PatternActualSizeButton\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("AutomationProperties.AutomationId=\"PatternCalibrateScaleButton\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("Text=\"10 cm grid | 50 cm major | screen uncalibrated\"", StringComparison.Ordinal) &&
        !mainPageXaml.Contains("12.5 mm grid", StringComparison.Ordinal) &&
        mainPageXaml.Contains("SelectionChanged=\"OnPatternPieceSelectionChanged\"", StringComparison.Ordinal) &&
        !mainPageXaml.Contains("86% FABRIC USE", StringComparison.Ordinal) &&
        mainPageCode.Contains("PatternCanvasLayoutEngine.Arrange", StringComparison.Ordinal) &&
        mainPageCode.Contains("PatternCanvasLayoutEngine.Frame", StringComparison.Ordinal) &&
        mainPageCode.Contains("PatternCanvasLayoutEngine.FrameAll", StringComparison.Ordinal) &&
        mainPageCode.Contains("QueueInitialPatternFit();", StringComparison.Ordinal) &&
        mainPageCode.Contains("_patternCanvasLayout is null ||", StringComparison.Ordinal) &&
        mainPageCode.Contains("FrameSelectedPatternPiece(showStatus: false)", StringComparison.Ordinal) &&
        mainPageCode.Contains("holder.PointerPressed += OnPatternPiecePointerPressed", StringComparison.Ordinal) &&
        mainPageCode.Contains("The current pan and zoom are unchanged.", StringComparison.Ordinal) &&
        mainPageCode.Contains("PatternScaleDipsPerCentimeter", StringComparison.Ordinal) &&
        mainPageCode.Contains("PatternCalibrationRulerDips / measured", StringComparison.Ordinal) &&
        mainPageCode.Contains("public override string ToString() => Name;", StringComparison.Ordinal),
    "The 2D workspace lost deterministic packing, visible pan and zoom, or truthful calibrated-scale controls.");
Assert(mainPageXaml.Contains("x:Name=\"AcceptedEquilibriumTopologyText\"", StringComparison.Ordinal), "The packaged 3D overlay is not driven by live topology metadata.");
Assert(
    mainPageXaml.Contains("x:Name=\"ShoulderSlider\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("Text=\"37 cm\"", StringComparison.Ordinal) &&
        mainPageCode.Contains("private const double DefaultShoulder = 37;", StringComparison.Ordinal),
    "The fresh-workspace shoulder value no longer matches the accepted full-bust body profile.");
Assert(mainPageCode.Contains("garment.Panels.Count", StringComparison.Ordinal) && mainPageCode.Contains("garment.Seams.Count", StringComparison.Ordinal), "The packaged 3D overlay does not source both production topology counts.");
Assert(
    mainPageCode.Contains("Assets/GarmentCode/PatternaProductionCrewNeck.specification.json", StringComparison.Ordinal) &&
        !mainPageCode.Contains("Assets/GarmentCode/PatternaUpstreamCrewNeck.specification.json", StringComparison.Ordinal),
    "The WinUI product boundary is not loading the tested production shirt source.");
Assert(
    mainPageCode.Contains("private const double DefaultHipEase = 8;", StringComparison.Ordinal) &&
        mainPageXaml.Contains("x:Name=\"HipEaseNumberBox\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("Value=\"8\"", StringComparison.Ordinal),
    "The WinUI defaults no longer match the production source's authored hip ease.");
Assert(
    mainPageCode.Contains("AdaptiveShirtPatternGrader.MeasureGeometryGirths(_garmentDocument)", StringComparison.Ordinal) &&
        mainPageCode.Contains("Measured garment: chest", StringComparison.Ordinal) &&
        mainPageCode.Contains("cm · hem", StringComparison.Ordinal),
    "The garment inspector no longer reports measurements from the current drafted geometry.");
int bustModeControlIndex = mainPageXaml.IndexOf(
    "x:Name=\"BustShapingModeComboBox\"",
    StringComparison.Ordinal);
int defaultSideDartSelectionIndex = mainPageXaml.IndexOf(
    "SelectedIndex=\"1\"",
    bustModeControlIndex,
    StringComparison.Ordinal);
Assert(
    bustModeControlIndex >= 0 &&
        defaultSideDartSelectionIndex > bustModeControlIndex &&
        defaultSideDartSelectionIndex - bustModeControlIndex < 400 &&
        mainPageXaml.Contains(
            "Measurement-driven side darts shape the default full-bust block.",
            StringComparison.Ordinal) &&
        mainPageCode.Contains("private const int BustShapingDefaultVersion = 2;", StringComparison.Ordinal) &&
        mainPageCode.Contains("isLegacyImplicitNoDartDefault", StringComparison.Ordinal),
    "The default full-bust project no longer enables or migrates measurement-driven side darts.");
Assert(mainPageXaml.Contains("Content=\"Front\"", StringComparison.Ordinal) && mainPageXaml.Contains("Tag=\"front\"", StringComparison.Ordinal), "The front camera control is not bound to the anatomical front preset.");
Assert(mainPageXaml.Contains("Content=\"Rear\"", StringComparison.Ordinal) && mainPageXaml.Contains("Tag=\"rear\"", StringComparison.Ordinal), "The rear camera control is not bound to the anatomical rear preset.");
Assert(mainPageCode.Contains("Convert.ToString(button.Tag", StringComparison.Ordinal), "Camera commands still assume that XAML Tag is stored as one runtime type.");
Assert(viewportSource.Contains("uniform float uRoughness", StringComparison.Ordinal), "The packaged renderer lost material roughness control.");
Assert(viewportSource.Contains("fabricRoughness", StringComparison.Ordinal), "The packaged renderer lost fabric-specific surface response.");
Assert(viewportSource.Contains("setCameraView(viewName)", StringComparison.Ordinal), "The renderer lost its semantic camera-view API.");
Assert(
    viewportSource.Contains("front:{yaw:180,pitch:.01,distance:5.35}", StringComparison.Ordinal) &&
        viewportSource.Contains("rear:{yaw:0,pitch:.01,distance:5.35}", StringComparison.Ordinal) &&
        viewportSource.Contains("oblique:{yaw:145,pitch:.01,distance:5.45}", StringComparison.Ordinal),
    "The packaged camera presets no longer map front, rear, and front-oblique labels to anatomical views.");
Assert(viewportSource.Contains("resetCamera(){setCameraView('fit');}", StringComparison.Ordinal), "Fit view no longer returns to the accepted full-body presentation.");
Assert(viewportSource.Contains("uniform vec3 uCameraPosition", StringComparison.Ordinal), "Material lighting is no longer derived from the live inspection camera.");
Assert(
    mainPageXaml.Contains("x:Name=\"AssemblySeamFitCard\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("x:Name=\"AssemblySeamLengthText\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("x:Name=\"AssemblySeamMismatchText\"", StringComparison.Ordinal),
    "The native seam inspector no longer exposes sewn-length compatibility diagnostics.");
Assert(
    mainPageCode.Contains("UpdateSeamFitDiagnostics", StringComparison.Ordinal) &&
        mainPageCode.Contains("compiled.LengthMismatchRatio", StringComparison.Ordinal),
    "The native seam inspector no longer derives its compatibility status from compiled pattern geometry.");
Assert(viewportSource.Contains("in vec2 aUv", StringComparison.Ordinal) && viewportSource.Contains("sampler2D uTexture", StringComparison.Ordinal), "The display avatar renderer lost UV texture support.");
Assert(
    viewportSource.IndexOf("const yScale = heightScale;", StringComparison.Ordinal) <
        viewportSource.IndexOf("supportedBustY", StringComparison.Ordinal),
    "The procedural-avatar fallback reads yScale before JavaScript initializes it.");
Assert(viewportSource.Contains("loadDisplayAvatar", StringComparison.Ordinal) && viewportSource.Contains("Production/Avatar/", StringComparison.Ordinal), "The packaged renderer no longer loads the real display-avatar stack.");
Assert(
    viewportSource.Contains("loadGlbDisplayAvatar", StringComparison.Ordinal) &&
        viewportSource.Contains("manifest.schemaVersion==='patterna.display-avatar-glb/1.0'", StringComparison.Ordinal),
    "The packaged renderer cannot load the candidate GLB display-avatar contract.");
Assert(viewportSource.Contains("fitted GLB candidate", StringComparison.Ordinal), "The candidate HUD again implies that every editable measurement is mapped into the fixed candidate.");
Assert(
    viewportSource.Contains("loadCandidateDisplayAvatar", StringComparison.Ordinal) &&
        viewportSource.Contains("crypto.subtle.digest('SHA-256'", StringComparison.Ordinal) &&
        viewportSource.Contains("manifest.accepted!==false||manifest.candidateOnly!==true", StringComparison.Ordinal) &&
        viewportSource.Contains("Number(manifest.displayYawDegrees)", StringComparison.Ordinal) &&
        viewportSource.Contains("has an unsupported transform", StringComparison.Ordinal) &&
        viewportSource.Contains("MHR baseline preview · numerical fit evidence recorded · visual, collider, cloth, and product gates open", StringComparison.Ordinal) &&
        viewportSource.Contains("3D drape unsupported for this revision", StringComparison.Ordinal) &&
        viewportSource.Contains("previewChangedKeys", StringComparison.Ordinal),
    "The packaged renderer no longer loads the hash-bound MHR GLB behind an explicit preview-only, fail-closed boundary.");
Assert(
    mainPageXaml.Contains("x:Name=\"ShowBraToggle\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("x:Name=\"BraAvailabilityText\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("Header=\"Show fitted support bra\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("without changing the supported body or collision shape", StringComparison.Ordinal) &&
        mainPageXaml.Contains("The supported bust shape and cloth collision body stay identical", StringComparison.Ordinal) &&
        mainPageCode.Contains("[\"showBra\"] = ShowBraToggle.IsOn", StringComparison.Ordinal) &&
        mainPageCode.Contains("settings.Values[\"ShowFittedBra\"] = project.ShowFittedBra", StringComparison.Ordinal) &&
        mainPageCode.Contains("settings.Values[\"ShowFittedBra\"] is not bool showFittedBra || showFittedBra", StringComparison.Ordinal) &&
        mainPageCode.Contains("ShowBraToggle.IsOn = project.ShowFittedBra", StringComparison.Ordinal) &&
        mainPageCode.Contains("window.patterna.updateAvatar({{showBra:", StringComparison.Ordinal) &&
        mainPageCode.Contains("SetBraDisplayAvailability(available)", StringComparison.Ordinal) &&
        mainPageCode.Contains("No fitted bra asset matches this edited avatar", StringComparison.Ordinal) &&
        viewportSource.Contains("{type:'bra-availability',available}", StringComparison.Ordinal) &&
        viewportSource.Contains("state.productionDisplayAssets.some(asset=>asset.key==='bra')", StringComparison.Ordinal) &&
        viewportSource.Contains("state.avatar.showBra?state.displayMeshes.find(asset=>asset.key==='bra')", StringComparison.Ordinal) &&
        viewportSource.Contains("gl.polygonOffset(-1,-1)", StringComparison.Ordinal) &&
        viewportSource.Contains("gl.depthMask(false)", StringComparison.Ordinal) &&
        viewportSource.Contains("gl.depthMask(true)", StringComparison.Ordinal),
    "The fitted bra is no longer a display-only user option over the unchanged supported body.");
Assert(
    mainPageCode.Contains("RefreshAssemblyInspectorAfterHistoryChange();", StringComparison.Ordinal) &&
        mainPageCode.Contains("DispatcherQueue.TryEnqueue(() => UpdateAssemblyInspector(false));", StringComparison.Ordinal),
    "Undo and redo no longer commit the restored assembly-toggle state after WinUI finishes the current input event.");
Assert(
    mainPageXaml.Contains("x:Name=\"StaleSimulationNotice\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("AutomationProperties.AutomationId=\"DrapeStaleSimulationState\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("AutomationProperties.LiveSetting=\"Polite\"", StringComparison.Ordinal) &&
        mainPageXaml.IndexOf("x:Name=\"StaleSimulationNotice\"", StringComparison.Ordinal) <
            mainPageXaml.IndexOf("x:Name=\"DrapeSurfaceGrid\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("x:Name=\"DrapeSurfaceGrid\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("Grid.Row=\"1\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("x:Name=\"StaleSimulationDetailText\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("MaxLines=\"1\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("Grid.Column=\"2\"", StringComparison.Ordinal) &&
        mainPageXaml.Contains("x:Name=\"SimulationStatusBorder\"", StringComparison.Ordinal) &&
        mainPageCode.Contains("StaleSimulationDetailText.Text =", StringComparison.Ordinal) &&
        mainPageCode.Contains("No matching accepted cloth:", StringComparison.Ordinal) &&
        mainPageCode.Contains("SimulationStatusBorder.Visibility = isCurrent", StringComparison.Ordinal),
    "The stale-cloth state must remain an accessible, one-line status row outside the 3D inspection viewport.");
Assert(
    mainPageCode.Contains("await LoadBundledSimulationFitEvidenceAsync();", StringComparison.Ordinal) &&
        mainPageCode.Contains("Assets/Production/patterna-production-crew-neck.fit.json", StringComparison.Ordinal),
    "The packaged Style3D fit evidence is no longer loaded for the default production garment.");
Assert(
    mainPageCode.Contains("measurableConstruction is null ? null : CurrentShirtConstructionProfile()", StringComparison.Ordinal) &&
        mainPageCode.Contains("TryMeasureShirtConstructionProfile(canonicalGarment) ?? DefaultShirtConstructionProfile()", StringComparison.Ordinal),
    "The split-torso source again assumes that the legacy one-piece construction profile is measurable.");
Assert(
    viewportSource.Contains("parseTexturedObj(garmentSource,'centimeters')", StringComparison.Ordinal) &&
    viewportSource.Contains("Production/fabric-texture.png", StringComparison.Ordinal),
    "The packaged renderer no longer loads the accepted garment through its pattern-UV fabric path.");
Assert(
    !viewportSource.Contains("sin((vWorld.x + vWorld.z * 0.24) * 245.0)", StringComparison.Ordinal),
    "The garment shader regressed to a world-space fake weave instead of pattern UVs.");
Assert(
    viewportSource.Contains("textureSize(uTexture, 0)", StringComparison.Ordinal) &&
    viewportSource.Contains("dFdx(vWorld)", StringComparison.Ordinal) &&
    viewportSource.Contains("fabricSurfaceRelief", StringComparison.Ordinal),
    "The garment material lost its pattern-space fiber relief and fabric-specific surface response.");
Assert(viewportSource.Contains("clearAcceptedRevision", StringComparison.Ordinal), "The renderer cannot hide stale accepted cloth after a source edit.");
Assert(mainPageCode.Contains("window.patterna.clearAcceptedRevision();", StringComparison.Ordinal), "Source edits do not clear stale accepted cloth in the embedded viewport.");
Assert(mainPageCode.Contains("display-avatar", StringComparison.Ordinal), "Revision-specific display avatars are not mapped into the embedded viewport.");
Assert(
    simulationPipelineSource.Contains("--glb-output", StringComparison.Ordinal) &&
        simulationPipelineSource.Contains("--glb-manifest", StringComparison.Ordinal) &&
        simulationPipelineSource.Contains("display-avatar", StringComparison.Ordinal),
    "Revision-specific simulations do not package their fitted Antonia GLB beside the collider.");
Assert(
    simulationPipelineSource.Contains("build_style3d_source.py", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("prefit_newton_style3d.py", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("style3d-stage-1-drape", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("style3d-stage-2-contact", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("style3d-stage-3-proof", StringComparison.Ordinal),
    "Revision-specific simulations no longer use the staged Newton Style3D production path.");
Assert(
    simulationPipelineSource.Contains("--initial-mesh", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("RequireStyle3DWarmStart", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("RequireAcceptedFitReport", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("ValidateAcceptedStyle3DChain", StringComparison.Ordinal),
    "Style3D staging no longer validates warm-start contact cleanup and the independent final proof.");
Assert(
    simulationPipelineSource.Contains("CanResumeAcceptedStyle3DEquilibrium", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("Reusing the hash-verified accepted Style3D equilibrium", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("TryGetVerifiedInput(root, \"output_mesh\"", StringComparison.Ordinal),
    "A downstream compiler failure would force an expensive Style3D rerun or reuse an unverified result.");
Assert(
    simulationRuntimeSource.Contains("\"bin\", \"x64\", \"Debug\", \"net10.0\"", StringComparison.Ordinal) &&
    simulationRuntimeSource.Contains("\"bin\", \"x64\", \"Release\", \"net10.0\"", StringComparison.Ordinal),
    "The developer runtime fallback no longer discovers the current platform-specific compiler build.");
Assert(
    simulationRuntimeSource.Contains("\"patterna_style3d_sewing.py\"", StringComparison.Ordinal) &&
        simulationRuntimeSource.Contains("\"charmorph_anatomy.py\"", StringComparison.Ordinal) &&
        simulationRuntimeSource.Contains("\"charmorph_pose.py\"", StringComparison.Ordinal) &&
        simulationRuntimeInstallerSource.Contains("'patterna_style3d_sewing.py'", StringComparison.Ordinal) &&
        simulationRuntimeInstallerSource.Contains("'charmorph_anatomy.py'", StringComparison.Ordinal) &&
        simulationRuntimeInstallerSource.Contains("'charmorph_pose.py'", StringComparison.Ordinal) &&
        simulationRuntimeInstallerSource.Contains("2026.08.09-style3d-antonia-v7", StringComparison.Ordinal) &&
        simulationRuntimeInstallerSource.Contains("avatarCharacterDirectory = 'third_party/CharMorph-db/characters/antonia'", StringComparison.Ordinal),
    "The project-owned Style3D sewing solver is no longer a required, versioned runtime entry point.");
Assert(
    charmorphGlbSource.Contains(
        "patterna.avatar-surface-registration/1.0",
        StringComparison.Ordinal) &&
        charmorphGlbSource.Contains(
            "bidirectional nearest-surface comparison with display-material anatomical regions",
            StringComparison.Ordinal) &&
        charmorphGlbSource.Contains(
            "collision simplification is not implemented",
            StringComparison.Ordinal) &&
        !charmorphGlbSource.Contains(
            "collision simplification and regional registration are not implemented",
            StringComparison.Ordinal),
    "The display avatar no longer enforces regional bidirectional display-to-collider registration.");
Assert(
    charmorphGlbVerifierSource.Contains("--expected-vertices", StringComparison.Ordinal) &&
        charmorphGlbVerifierSource.Contains("unexpectedPositionCount", StringComparison.Ordinal) &&
        charmorphGlbVerifierSource.Contains("missingPositionCount", StringComparison.Ordinal),
    "Fresh GLB verification no longer compares the round-tripped display position set to the exact fitted source.");
Assert(
    charmorphAnatomySource.Contains(
        "patterna.avatar-anatomy/1.0",
        StringComparison.Ordinal) &&
        simulationPipelineSource.Contains(
            "patterna.avatar-anatomy/1.0",
            StringComparison.Ordinal) &&
        simulationPipelineSource.Contains(
            "anatomyAccepted.ValueKind is not JsonValueKind.True",
            StringComparison.Ordinal),
    "Product visual proof no longer requires an accepted avatar anatomy report.");
Assert(
    charmorphPoseSource.Contains(
        "patterna.avatar-pose/1.0",
        StringComparison.Ordinal) &&
        simulationPipelineSource.Contains(
            "patterna.avatar-pose/1.0",
            StringComparison.Ordinal) &&
        simulationPipelineSource.Contains(
            "poseAccepted.ValueKind is not JsonValueKind.True",
            StringComparison.Ordinal),
    "Product visual proof no longer requires an accepted avatar inspection-pose report.");
Assert(
    simulationPipelineSource.Contains("patterna.newton-style3d-report/1.0", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("SimulationMeshResolutionCm = 0.25", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("PipelineRevisionSalt", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("material_rest_length_edge_count", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("excluded_edge_count", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("seam_closure_gate_evaluated", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("maximum_seam_separation_cm", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("material_coordinates", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("panel_ownership", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("panel_index_map", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("rest_lengths", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("physical_output_mesh", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("adapter_implementation", StringComparison.Ordinal),
    "Production acceptance no longer requires exact Style3D artifact identity, explicit seam closure, and full-surface material-space strain coverage.");
Assert(
    simulationPipelineSource.Contains("--obj-output", StringComparison.Ordinal) &&
    !simulationPipelineSource.Contains("export_usd_render_surface.py", StringComparison.Ordinal),
    "Revision-specific simulations still route the application mesh through a lossy Blender UV handoff.");
Assert(
    simulationRuntimeSource.Contains("patterna.simulation-runtime/1.0", StringComparison.Ordinal) &&
    simulationRuntimeSource.Contains("EntrypointSha256", StringComparison.Ordinal) &&
    simulationRuntimeSource.Contains("Runtime path escapes the manifest directory", StringComparison.Ordinal) &&
    mainPageCode.Contains("SimulationRuntimeLocator.Resolve", StringComparison.Ordinal) &&
    !mainPageCode.Contains("FindProjectRoot", StringComparison.Ordinal),
    "The packaged simulation command is no longer isolated from source-checkout path discovery by a hash-bound runtime manifest.");
Assert(
    simulationPipelineSource.Contains("SimulationRuntime runtime", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("JsonSerializer.Serialize(bridge, JsonOptions)", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("runtime.ToolsDirectory", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("runtime.RootDirectory", StringComparison.Ordinal),
    "A simulation job no longer owns its exact bridge snapshot and resolved runtime entry points.");
Assert(
    simulationPipelineSource.Contains("Directory.CreateDirectory(visualProofDirectory)", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("TryValidateProductVisualProof(result)", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("patterna.product-turntable/1.0", StringComparison.Ordinal),
    "A simulation job no longer owns and validates its exact six-view product proof.");
Assert(
    simulationPipelineSource.Contains("process.Kill(true)", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("WaitForExitAsync(CancellationToken.None)", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("CancellationToken.None);", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("throw new OperationCanceledException(cancellationToken);", StringComparison.Ordinal),
    "Cancelling an external simulation can again abandon its process tree or diagnostic log.");
Assert(
    simulationPipelineSource.Contains("HasPatternUvRenderMesh", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("g patterna_seams", StringComparison.Ordinal) &&
    simulationPipelineSource.Contains("g patterna_edges", StringComparison.Ordinal),
    "Accepted-result cache validation does not reject legacy geometry-only render meshes.");
string productionGarmentObjPath = Path.GetFullPath(Path.Combine(
    Directory.GetCurrentDirectory(),
    "Patternal",
    "Assets",
    "Production",
    "patterna-production-crew-neck.obj"));
int productionGarmentVertexCount = File.ReadLines(productionGarmentObjPath)
    .Count(line => line.StartsWith("v ", StringComparison.Ordinal));
int productionGarmentTextureCoordinateCount = File.ReadLines(productionGarmentObjPath)
    .Count(line => line.StartsWith("vt ", StringComparison.Ordinal));
int productionGarmentFaceCount = File.ReadLines(productionGarmentObjPath)
    .Count(line => line.StartsWith("f ", StringComparison.Ordinal));
bool productionGarmentHasSeamLines = File.ReadLines(productionGarmentObjPath)
    .Any(line => line.Equals("g patterna_seams", StringComparison.Ordinal));
bool productionGarmentHasEdgeLines = File.ReadLines(productionGarmentObjPath)
    .Any(line => line.Equals("g patterna_edges", StringComparison.Ordinal));
string productionCompilerManifestPath = Path.ChangeExtension(
    productionGarmentObjPath,
    ".compile.json");
using JsonDocument productionCompilerManifest = JsonDocument.Parse(
    File.ReadAllText(productionCompilerManifestPath));
JsonElement productionRenderEvidence = productionCompilerManifest.RootElement
    .GetProperty("render");
Assert(
    productionCompilerManifest.RootElement.GetProperty("schemaVersion").GetString() ==
        "patterna.full-garment-usd/1.1" &&
        productionRenderEvidence.GetProperty("sourceVertexCount").GetInt32() == 133_870 &&
        productionRenderEvidence.GetProperty("vertexCount").GetInt32() == 526_636 &&
        productionRenderEvidence.GetProperty("triangleCount").GetInt32() == 1_051_256 &&
        productionGarmentVertexCount == 529_632 &&
        productionGarmentTextureCoordinateCount == productionGarmentFaceCount * 3 &&
        productionGarmentFaceCount == 1_051_256 &&
        productionGarmentHasSeamLines &&
        productionGarmentHasEdgeLines,
    "The packaged baseline is not the compiler-refined accepted Style3D surface with pattern UVs and construction lines.");
string bundledStyle3DReportPath = Path.GetFullPath(Path.Combine(
    Directory.GetCurrentDirectory(),
    "Patternal",
    "Assets",
    "Production",
    "patterna-production-crew-neck.fit.json"));
using (JsonDocument bundledStyle3DReport = JsonDocument.Parse(
    File.ReadAllText(bundledStyle3DReportPath)))
{
    Assert(
        SimulationPipeline.TryParseFitEvidence(
            bundledStyle3DReport.RootElement,
            out SimulationFitEvidence? bundledStyle3DEvidence) &&
            bundledStyle3DEvidence is not null,
        "The bundled Style3D report did not produce simulation-backed fit evidence.");
    Assert(
        bundledStyle3DEvidence!.BodyCollisions == 0 &&
            bundledStyle3DEvidence.SelfCollisions == 0,
        "The bundled Style3D evidence is not collision-free.");
    Assert(
        !bundledStyle3DEvidence.PeakStrainGateEnabled &&
            bundledStyle3DEvidence.NinetyNinthPointNinetyNinthPercentileEdgeStrainRatio is double p9999 &&
            bundledStyle3DEvidence.MaximumAllowedNinetyNinthPointNinetyNinthPercentileEdgeStrainRatio is double maxP9999 &&
            p9999 < maxP9999,
        "The bundled Style3D evidence lost its resolution-aware tail-strain gate.");
    Assert(
        bundledStyle3DEvidence.SolverName.Contains("Style3D", StringComparison.Ordinal),
        "The bundled evidence lost Style3D solver provenance.");
}
string acceptedShirtSvg = PatternSvgExporter.Export(acceptedShirt, "production shirt physical export");
Assert(
    acceptedShirt.Pieces.All(piece => acceptedShirtSvg.Contains($"data-piece-id=\"{piece.Id}\"", StringComparison.Ordinal)),
    "Physical SVG export omitted one or more production shirt pieces.");
Assert(acceptedShirtSvg.Contains("width=\"1200mm\"", StringComparison.Ordinal), "Production shirt SVG did not declare a physical millimeter page.");
GarmentEaseProfileDocument acceptedSourceEase = AdaptiveShirtPatternGrader.MeasureSourceEase(acceptedShirt);
Assert(
    double.IsFinite(acceptedSourceEase.ChestEaseCm) &&
        double.IsFinite(acceptedSourceEase.WaistEaseCm) &&
        double.IsFinite(acceptedSourceEase.HipEaseCm),
    "The adaptive shirt source did not produce finite explicit ease measurements.");
Assert(Math.Abs(acceptedSourceEase.ChestEaseCm - 6) < 0.001, "The imported shirt lost its authored chest ease.");
Assert(Math.Abs(acceptedSourceEase.WaistEaseCm - 6) < 0.001, "The imported shirt lost its authored waist ease.");
Assert(Math.Abs(acceptedSourceEase.HipEaseCm - 8) < 0.001, "The imported shirt lost its authored hip ease.");
(GarmentDocument defaultFullBustShirt, _) = AdaptiveShirtPatternGrader.Adapt(
    acceptedShirt,
    112,
    82,
    108,
    37,
    44,
    57.3,
    26,
    21.8,
    45.5,
    acceptedSourceEase,
    constructionProfile: null);
AdaptiveShirtSourceGirths defaultFullBustGirths =
    AdaptiveShirtPatternGrader.MeasureGeometryGirths(defaultFullBustShirt);
double defaultFullBustChestLine =
    AdaptiveShirtPatternGrader.MeasureChestLineRelativeHeight(defaultFullBustShirt);
Console.WriteLine(
    $"Full-bust anatomical chest line: {defaultFullBustChestLine:P2}; " +
    $"girths {defaultFullBustGirths.ChestGirthCm:F2}/{defaultFullBustGirths.WaistGirthCm:F2}/{defaultFullBustGirths.HipGirthCm:F2} cm");
Assert(
    Math.Abs(defaultFullBustGirths.ChestGirthCm - 118) < 0.2 &&
        Math.Abs(defaultFullBustGirths.WaistGirthCm - 88) < 0.2 &&
        Math.Abs(defaultFullBustGirths.HipGirthCm - 116) < 0.2,
    $"The default full-bust grade missed body-plus-ease targets: " +
    $"{defaultFullBustGirths.ChestGirthCm:F2}/{defaultFullBustGirths.WaistGirthCm:F2}/{defaultFullBustGirths.HipGirthCm:F2} cm.");
Assert(
    defaultFullBustShirt.BodyReference is
    {
        ChestCm: 112,
        WaistCm: 82,
        HipCm: 108,
        ShoulderCm: 37,
        TorsoCm: 44,
        ArmLengthCm: 57.3,
        UpperArmCircumferenceCm: 26,
        ArmholeDepthCm: 21.8,
        ArmscyeCircumferenceCm: 45.5
    },
    "The graded shirt retained stale source-body metadata instead of the measurements that generated its geometry.");
AdaptiveShirtSourceGirths defaultFullBustReportedTargets =
    AdaptiveShirtPatternGrader.MeasureSourceGirths(defaultFullBustShirt);
Assert(
    Math.Abs(defaultFullBustReportedTargets.ChestGirthCm - 118) < 0.001 &&
        Math.Abs(defaultFullBustReportedTargets.WaistGirthCm - 88) < 0.001 &&
        Math.Abs(defaultFullBustReportedTargets.HipGirthCm - 116) < 0.001,
    "The graded shirt reports stale body-plus-ease targets even though its geometry was regenerated.");
Assert(
    defaultFullBustChestLine is > 0.56 and < 0.64,
    $"The full-bust grade calibrated chest ease at {defaultFullBustChestLine:P1} of panel height instead of the armscye-derived bust line.");
Assert(defaultFullBustShirt.Validate().Count == 0, "The default full-bust grade produced an invalid garment.");
Assert(
    defaultFullBustShirt.Pieces.Count == 14 && defaultFullBustShirt.Seams.Count == 34,
    "The default full-bust grade changed production shirt topology.");
string productionBridgePath = Path.GetFullPath(Path.Combine(
    Directory.GetCurrentDirectory(),
    "PatternaUnreal",
    "SourceAssets",
    "GarmentCode",
    "PatternaProductionCrewNeck.bridge.json"));
PatternaUnrealBridgeDocument productionBridgeFixture = JsonSerializer.Deserialize<PatternaUnrealBridgeDocument>(
    File.ReadAllText(productionBridgePath),
    new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
    ?? throw new InvalidOperationException("The production bridge fixture could not be read.");
UnrealBridgeMeasurementDocument M(string key, double value)
    => new(key, key, value, "cm", "manual");
productionBridgeFixture = productionBridgeFixture with
{
    Body = productionBridgeFixture.Body with
    {
        Measurements =
        [
            M("height", 167),
            M("chest", 112),
            M("underBust", 84),
            M("waist", 82),
            M("hip", 108),
            M("highHipCirc", 98),
            M("shoulder", 37),
            M("torso", 44),
            M("armLengthL", 57.3),
            M("armLengthR", 57.3),
            M("upperArmCircL", 26),
            M("upperArmCircR", 26),
            M("armholeDepthL", 21.8),
            M("armholeDepthR", 21.8),
            M("armscyeCircL", 45.5),
            M("armscyeCircR", 45.5),
            M("bustSeparation", 19),
            M("bustHeightL", 24.8),
            M("bustHeightR", 24.6),
            M("bustProjectionL", 9.6),
            M("bustProjectionR", 9.4)
        ]
    },
    Garment = productionBridgeFixture.Garment with { ShirtBustShapingProfile = null }
};
PatternaUnrealBridgeDocument defaultShapedProductionBridge =
    ProductionShirtBridgeBuilder.ReplaceGarment(
        productionBridgeFixture,
        File.ReadAllText(acceptedShirtPath),
        "PatternaUnreal/SourceAssets/GarmentCode/PatternaProductionCrewNeck.specification.json",
        "e3469c92cdc0ae6e019527ff90f32f8c096884a35f95696a5e3f4c325891b3e3");
PatternPieceDocument defaultShapedFront = defaultShapedProductionBridge.Garment.Pieces.Single(
    piece => piece.Id == "front-torso");
AdaptiveShirtSourceGirths defaultShapedProductionGirths =
    AdaptiveShirtPatternGrader.MeasureGeometryGirths(defaultShapedProductionBridge.Garment);
Assert(
    defaultShapedProductionBridge.Garment.ShirtBustShapingProfile is
    {
        Mode: ShirtBustShapingModes.SideDarts,
        LeftDartIntakeCm: > 0,
        RightDartIntakeCm: > 0
    } &&
        defaultShapedFront.Darts.Count(dart => dart.Materialized) == 2 &&
        defaultShapedProductionBridge.Garment.Seams.Count == 38 &&
        defaultShapedProductionBridge.PatternTopology.SeamCount == 38,
    "The production bridge did not convert the default full-bust measurements into two physical side darts.");
Assert(
    Math.Abs(defaultShapedProductionGirths.HipGirthCm - 105.23) < 0.2,
    $"The production shirt graded its high-hip hem to {defaultShapedProductionGirths.HipGirthCm:F2} cm instead of body plus interpolated high-hip ease.");
(GarmentDocument identityGradeShirt, _) = AdaptiveShirtPatternGrader.Adapt(
    acceptedShirt,
    92,
    71,
    99,
    39,
    42,
    57.3,
    29.4,
    acceptedSourceEase);
Assert(
    identityGradeShirt.Pieces.Sum(piece => piece.Boundary.Count) == acceptedShirt.Pieces.Sum(piece => piece.Boundary.Count),
    "An identity shirt grade changed the source topology.");
Assert(identityGradeShirt.Validate().Count == 0, "The production shirt's source compression ease was rejected.");
(GarmentDocument fittedEaseShirt, AdaptiveShirtGrade fittedEaseGrade) = AdaptiveShirtPatternGrader.Adapt(
    acceptedShirt,
    92,
    71,
    99,
    39,
    42,
    57.3,
    29.4,
    new GarmentEaseProfileDocument(6, 6, 6, 4));
AdaptiveShirtSourceGirths fittedEaseGirths = AdaptiveShirtPatternGrader.MeasureGeometryGirths(fittedEaseShirt);
Console.WriteLine($"Explicit ease girths: chest {fittedEaseGirths.ChestGirthCm:0.00} cm, waist {fittedEaseGirths.WaistGirthCm:0.00} cm, hip {fittedEaseGirths.HipGirthCm:0.00} cm");
Assert(Math.Abs(fittedEaseGirths.ChestGirthCm - 98) < 0.2, $"Explicit chest ease produced {fittedEaseGirths.ChestGirthCm:0.00} cm instead of 98 cm.");
Assert(Math.Abs(fittedEaseGirths.WaistGirthCm - 77) < 0.2, $"Explicit waist ease produced {fittedEaseGirths.WaistGirthCm:0.00} cm instead of 77 cm.");
Assert(Math.Abs(fittedEaseGirths.HipGirthCm - 105) < 0.2, $"Explicit hip ease produced {fittedEaseGirths.HipGirthCm:0.00} cm instead of 105 cm.");
Assert(fittedEaseShirt.EaseProfile == fittedEaseGrade.EaseProfile, "Explicit ease was not retained in the garment document and grade evidence.");
Assert(fittedEaseShirt.Validate().Count == 0, "Measurement-constrained grading produced an invalid garment document.");
Assert(fittedEaseShirt.Seams.Count == acceptedShirt.Seams.Count, "Measurement-constrained grading changed the garment's seam count.");
Assert(
    fittedEaseShirt.Pieces.Sum(piece => piece.Boundary.Count) == acceptedShirt.Pieces.Sum(piece => piece.Boundary.Count),
    "Measurement-constrained grading changed construction boundary topology.");
(GarmentDocument waistEaseShirt, _) = AdaptiveShirtPatternGrader.Adapt(
    acceptedShirt,
    92,
    71,
    99,
    39,
    42,
    57.3,
    29.4,
    new GarmentEaseProfileDocument(6, 10, 6, 4));
AdaptiveShirtSourceGirths waistEaseGirths = AdaptiveShirtPatternGrader.MeasureGeometryGirths(waistEaseShirt);
Assert(Math.Abs(waistEaseGirths.ChestGirthCm - 98) < 0.2, "Changing waist ease also changed the chest target.");
Assert(Math.Abs(waistEaseGirths.WaistGirthCm - 81) < 0.2, "Editable waist ease did not change actual waist geometry.");
Assert(Math.Abs(waistEaseGirths.HipGirthCm - 105) < 0.2, "Changing waist ease also changed the hip target.");
Assert(
    GarmentCodePatternExporter.ComputeStructuralSignature(fittedEaseShirt) !=
        GarmentCodePatternExporter.ComputeStructuralSignature(fittedEaseShirt with
        {
            EaseProfile = new GarmentEaseProfileDocument(7, 6, 6, 4)
        }),
    "Garment ease metadata was excluded from the structural signature.");

string acceptedFitReportPath = Path.GetFullPath(Path.Combine(
    Directory.GetCurrentDirectory(),
    "PatternaUnreal",
    "SourceAssets",
    "GarmentCode",
    "PatternaProductionCrewNeck.warp-report.json"));
Assert(File.Exists(acceptedFitReportPath), $"The accepted shirt fit report is missing at {acceptedFitReportPath}.");
using (JsonDocument acceptedFitReport = JsonDocument.Parse(File.ReadAllText(acceptedFitReportPath)))
{
    Assert(
        SimulationPipeline.TryParseFitEvidence(acceptedFitReport.RootElement, out SimulationFitEvidence? fitEvidence) &&
            fitEvidence is not null,
        "The accepted Warp report did not produce simulation-backed fit evidence.");
    SimulationFitEvidence provenFitEvidence = fitEvidence
        ?? throw new InvalidOperationException("Accepted fit evidence was unexpectedly null.");
    Assert(provenFitEvidence.BodyCollisions == 0, "The zero-contact production fit regained a body intersection.");
    Assert(provenFitEvidence.SelfCollisions == 0, "The fit evidence changed the accepted self collision count.");
    Assert(Math.Abs(provenFitEvidence.MaximumEdgeStrainRatio - 0.277985680980115) < 0.0000001, "The relaxed fit evidence changed peak material strain.");
    Assert(Math.Abs(provenFitEvidence.NinetyFifthPercentileEdgeStrainRatio - 0.0498733972419183) < 0.0000001, "The relaxed fit evidence changed broad material strain.");
    Assert(
        provenFitEvidence.NinetyNinthPointNinthPercentileEdgeStrainRatio is double localizedStrain &&
        Math.Abs(localizedStrain - 0.1597807221822039) < 0.0000001,
        "The relaxed fit evidence changed localized material strain.");
    Assert(provenFitEvidence.CompletedFrames == 203, "The relaxed fit evidence changed the equilibrium frame count.");
    Assert(provenFitEvidence.WarpDevice == "cuda:0", "The fit evidence lost solver-device provenance.");
}

string exportedAcceptedShirt = GarmentCodePatternExporter.Export(acceptedShirt, "round-trip-test");
string exportedAcceptedShirtAgain = GarmentCodePatternExporter.Export(acceptedShirt, "round-trip-test");
Assert(exportedAcceptedShirt == exportedAcceptedShirtAgain, "GarmentCode export is not deterministic.");
Assert(exportedAcceptedShirt == File.ReadAllText(acceptedShirtPath), "Unedited GarmentCode source did not retain byte-exact panel numerics.");
int sourceCircleCount = File.ReadAllText(acceptedShirtPath).Split("\"type\": \"circle\"").Length - 1;
int exportedCircleCount = exportedAcceptedShirt.Split("\"type\": \"circle\"").Length - 1;
Assert(sourceCircleCount > 0, "The accepted source no longer exercises circular GarmentCode curves.");
Assert(exportedCircleCount == sourceCircleCount, "Unedited GarmentCode circular curves were degraded during export.");
GarmentDocument roundTrippedAcceptedShirt = GarmentCodePatternImporter.Import(
    exportedAcceptedShirt,
    new GarmentCodeImportOptions(
        acceptedShirt.Id,
        acceptedShirt.Name,
        acceptedShirt.Fabric,
        SourceRevision: "round-trip-test"));
Assert(roundTrippedAcceptedShirt.Pieces.Count == acceptedShirt.Pieces.Count, "GarmentCode round trip lost a pattern piece.");
Assert(roundTrippedAcceptedShirt.Seams.Count == acceptedShirt.Seams.Count, "GarmentCode round trip lost a seam.");
for (int pieceIndex = 0; pieceIndex < acceptedShirt.Pieces.Count; pieceIndex++)
{
    PatternPieceDocument sourcePiece = acceptedShirt.Pieces[pieceIndex];
    PatternPieceDocument roundTrippedPiece = roundTrippedAcceptedShirt.Pieces[pieceIndex];
    ClothPanelDocument sourcePanel = acceptedShirt.Panels[pieceIndex];
    ClothPanelDocument roundTrippedPanel = roundTrippedAcceptedShirt.Panels[pieceIndex];
    Assert(sourcePiece.Id == roundTrippedPiece.Id, "GarmentCode round trip changed a pattern piece id.");
    Assert(sourcePiece.Boundary.Count == roundTrippedPiece.Boundary.Count, "GarmentCode round trip changed an edge count.");
    Assert(Math.Abs(sourcePiece.Start.X - roundTrippedPiece.Start.X) < 0.000001, "GarmentCode round trip moved a start point on X.");
    Assert(Math.Abs(sourcePiece.Start.Y - roundTrippedPiece.Start.Y) < 0.000001, "GarmentCode round trip moved a start point on Y.");
    Assert(sourcePanel.SourcePatternOrigin is not null, "Imported GarmentCode panel lost its source pattern origin.");
    Assert(roundTrippedPanel.SourcePatternOrigin is not null, "Round-tripped GarmentCode panel lost its source pattern origin.");
    Assert(sourcePanel.SourceLabel == roundTrippedPanel.SourceLabel, "GarmentCode round trip changed a semantic panel label.");
    Assert(Math.Abs(sourcePanel.SourcePatternOrigin!.X - roundTrippedPanel.SourcePatternOrigin!.X) < 0.000001, "GarmentCode round trip moved the source pattern origin on X.");
    Assert(Math.Abs(sourcePanel.SourcePatternOrigin.Y - roundTrippedPanel.SourcePatternOrigin.Y) < 0.000001, "GarmentCode round trip moved the source pattern origin on Y.");
    for (int edgeIndex = 0; edgeIndex < sourcePiece.Boundary.Count; edgeIndex++)
    {
        PatternCurveDocument sourceEdge = sourcePiece.Boundary[edgeIndex];
        PatternCurveDocument roundTrippedEdge = roundTrippedPiece.Boundary[edgeIndex];
        Assert(Math.Abs(sourceEdge.End.X - roundTrippedEdge.End.X) < 0.000001, "GarmentCode round trip moved an edge endpoint on X.");
        Assert(Math.Abs(sourceEdge.End.Y - roundTrippedEdge.End.Y) < 0.000001, "GarmentCode round trip moved an edge endpoint on Y.");
        if (sourceEdge.Control1 is not null && roundTrippedEdge.Control1 is not null)
        {
            Assert(Math.Abs(sourceEdge.Control1.X - roundTrippedEdge.Control1.X) < 0.000001, "GarmentCode round trip moved the first control point on X.");
            Assert(Math.Abs(sourceEdge.Control1.Y - roundTrippedEdge.Control1.Y) < 0.000001, "GarmentCode round trip moved the first control point on Y.");
        }
        if (sourceEdge.Control2 is not null && roundTrippedEdge.Control2 is not null)
        {
            Assert(Math.Abs(sourceEdge.Control2.X - roundTrippedEdge.Control2.X) < 0.000001, "GarmentCode round trip moved the second control point on X.");
            Assert(Math.Abs(sourceEdge.Control2.Y - roundTrippedEdge.Control2.Y) < 0.000001, "GarmentCode round trip moved the second control point on Y.");
        }
    }
}

GarmentDocument wrapDress = GarmentDocumentFactory.CreateWrapDress(
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
PatternTopologyCompilation firstWrapCompilation = PatternTopologyCompiler.Compile(wrapDress);
PatternTopologyCompilation secondWrapCompilation = PatternTopologyCompiler.Compile(wrapDress);
Assert(firstWrapCompilation.Panels.Count == 8, "The wrap dress did not compile all eight cloth panels.");
Assert(firstWrapCompilation.Seams.Count == 11, "The wrap dress did not compile all eleven construction seams.");
Assert(firstWrapCompilation.Closures.Count == 3, "The wrap dress did not compile all three garment closures.");
Assert(
    firstWrapCompilation.Closures.All(closure =>
        closure.State == GarmentClosureStates.Closed &&
        closure.Constraints.Count == 1),
    "The wrap dress closures are not active single-point fasteners.");
Assert(
    firstWrapCompilation.Seams.All(seam => seam.Id != "bodice-center-front"),
    "A wrap dress must keep its overlapping center-front edges free rather than sewing them together.");
Assert(firstWrapCompilation.VertexCount > 100, "The wrap dress curve sampling is unexpectedly sparse.");
Assert(firstWrapCompilation.TriangleCount > 80, "The wrap dress triangulation is unexpectedly sparse.");
Assert(
    firstWrapCompilation.Panels.All(panel =>
        panel.Triangles.Count == panel.Vertices.Count - 2 &&
        panel.Triangles.All(triangle => triangle.AreaCm2 > 0.00001)),
    "A wrap dress panel has incomplete or degenerate triangulation.");
Assert(
    firstWrapCompilation.Seams.All(seam =>
        seam.VertexPairs.Count >= 2 &&
        seam.VertexPairs[0].NormalizedPosition == 0 &&
        seam.VertexPairs[^1].NormalizedPosition == 1),
    "A wrap dress seam does not cover both endpoints.");

JsonSerializerOptions jsonOptions = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
string firstJson = JsonSerializer.Serialize(firstWrapCompilation, jsonOptions);
string secondJson = JsonSerializer.Serialize(secondWrapCompilation, jsonOptions);
string firstHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(firstJson)));
string secondHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(secondJson)));
Assert(firstHash == secondHash, "Topology compilation is not deterministic.");

CompiledPatternPanel frontPanel = firstWrapCompilation.Panels.Single(panel => panel.Id == "skirt-left-wrap-panel");
CompiledPatternPanel reverseFrontPanel = firstWrapCompilation.Panels.Single(panel => panel.Id == "skirt-right-wrap-panel");
Assert(!frontPanel.ReverseWinding && reverseFrontPanel.ReverseWinding, "Panel winding intent was not retained.");
Assert(
    frontPanel.Triangles[0].A == reverseFrontPanel.Triangles[0].A &&
    frontPanel.Triangles[0].B == reverseFrontPanel.Triangles[0].C &&
    frontPanel.Triangles[0].C == reverseFrontPanel.Triangles[0].B,
    "Reverse-winding panel triangles were not inverted.");

PatternPieceDocument concavePiece = Piece(
    "concave",
    new PatternPointDocument(0, 0),
    [
        Line("top", 6, 0),
        Line("right-upper", 6, 2),
        Line("notch-in", 2, 2),
        Line("notch-down", 2, 6),
        Line("bottom", 0, 6),
        Line("left", 0, 0)
    ]);
PatternTopologyCompilation concaveCompilation = PatternTopologyCompiler.Compile(
    SinglePanelDocument(concavePiece));
Assert(
    concaveCompilation.Panels[0].Triangles.Count == 4,
    "The concave acceptance piece did not produce n minus 2 triangles.");

PatternPieceDocument openPiece = Piece(
    "open",
    new PatternPointDocument(0, 0),
    [
        Line("top", 4, 0),
        Line("right", 4, 4),
        Line("bottom", 0, 4)
    ]);
ExpectRejected("Open boundary", SinglePanelDocument(openPiece), "is open");

PatternPieceDocument bowTiePiece = Piece(
    "bow-tie",
    new PatternPointDocument(0, 0),
    [
        Line("first", 4, 4),
        Line("second", 0, 4),
        Line("third", 4, 0),
        Line("close", 0, 0)
    ]);
ExpectRejected("Self-intersecting boundary", SinglePanelDocument(bowTiePiece), "self-intersects");

PatternPieceDocument overlappingPiece = Piece(
    "overlap",
    new PatternPointDocument(0, 0),
    [
        Line("right", 6, 0),
        Line("backtrack", 2, 0),
        Line("down", 2, 4),
        Line("left", 0, 4),
        Line("close", 0, 0)
    ]);
ExpectRejected("Overlapping boundary", SinglePanelDocument(overlappingPiece), "self-intersects");

PatternPieceDocument missingControlPiece = new(
    "missing-control",
    "missing-control",
    1,
    false,
    false,
    1,
    1,
    1,
    new PatternPointDocument(0, 0),
    [
        new PatternCurveDocument("curve", "cubic", new PatternPointDocument(4, 0)),
        Line("right", 4, 4),
        Line("bottom", 0, 4),
        Line("left", 0, 0)
    ],
    new PatternLayoutDocument(0, 0, 0, 0, true));
ExpectRejected("Missing cubic controls", SinglePanelDocument(missingControlPiece), "missing a control point");

PatternPieceDocument rectangle = Piece(
    "rectangle",
    new PatternPointDocument(0, 0),
    [
        Line("top", 8, 0),
        Line("right", 8, 4),
        Line("bottom", 0, 4),
        Line("left", 0, 0)
    ]);
GarmentDocument noncontiguousSeamDocument = new(
    "patterna.garment/1.0",
    "noncontiguous-seam",
    "Noncontiguous seam",
    "centimeters",
    [rectangle],
    [
        new ClothPanelDocument("panel-a", rectangle.Id, "A", "flat", false, []),
        new ClothPanelDocument("panel-b", rectangle.Id, "B", "flat", false, [])
    ],
    [
        new GarmentSeamDocument(
            "bad-seam",
            "Bad seam",
            new SeamSideDocument("panel-a", ["top", "bottom"]),
            new SeamSideDocument("panel-b", ["top"]),
            0.1)
    ],
    Fabric());
ExpectRejected("Noncontiguous seam", noncontiguousSeamDocument, "noncontiguous edge sequence");

GarmentDocument invalidClosureDocument = SinglePanelDocument(rectangle) with
{
    Closures =
    [
        new GarmentClosureDocument(
            "bad-closure",
            "Bad closure",
            GarmentClosureKinds.Pin,
            GarmentClosureStates.Closed,
            new GarmentClosureAnchorDocument("panel", ["missing"], 0.5, 0.5),
            new GarmentClosureAnchorDocument("panel", ["top"], 0.5, 0.5),
            1)
    ]
};
ExpectRejected("Missing closure edge", invalidClosureDocument, "references missing edge");

PatternPieceDocument cubicSplitPiece = Piece(
    "cubic-split",
    new PatternPointDocument(0, 0),
    [
        new PatternCurveDocument(
            "neckline",
            "cubic",
            new PatternPointDocument(8, 0),
            new PatternPointDocument(0, 5),
            new PatternPointDocument(8, 5)),
        Line("right", 8, 8),
        Line("bottom", 0, 8),
        Line("left", 0, 0)
    ]);
const double cubicSplitParameter = 0.37;
PatternBoundarySplitResult cubicSplit = PatternStructuralEditor.SplitBoundarySegment(
    SinglePanelDocument(cubicSplitPiece),
    cubicSplitPiece.Id,
    "neckline",
    cubicSplitParameter);
PatternPieceDocument splitCubicPiece = cubicSplit.Document.Pieces[0];
Assert(splitCubicPiece.Boundary.Count == 5, "Cubic splitting did not insert one exact boundary segment.");
PatternCurveDocument firstCubic = splitCubicPiece.Boundary[0];
PatternCurveDocument secondCubic = splitCubicPiece.Boundary[1];
for (int sample = 0; sample <= 20; sample++)
{
    double originalParameter = sample / 20.0;
    PatternPointDocument originalPoint = EvaluateCurve(cubicSplitPiece.Start, cubicSplitPiece.Boundary[0], originalParameter);
    PatternPointDocument splitPoint = originalParameter <= cubicSplitParameter
        ? EvaluateCurve(cubicSplitPiece.Start, firstCubic, originalParameter / cubicSplitParameter)
        : EvaluateCurve(firstCubic.End, secondCubic, (originalParameter - cubicSplitParameter) / (1 - cubicSplitParameter));
    Assert(PointDistance(originalPoint, splitPoint) < 0.0000001, "De Casteljau splitting changed the cubic curve shape.");
}

PatternPieceDocument seamPieceA = Piece(
    "seam-piece-a",
    new PatternPointDocument(0, 0),
    [Line("seam-edge-a", 10, 0), Line("right-a", 10, 5), Line("bottom-a", 0, 5), Line("left-a", 0, 0)]);
PatternPieceDocument seamPieceB = Piece(
    "seam-piece-b",
    new PatternPointDocument(0, 0),
    [Line("seam-edge-b", 10, 0), Line("right-b", 10, 5), Line("bottom-b", 0, 5), Line("left-b", 0, 0)]);
PatternPlacement3DDocument flatPlacement = new(0, 0, 0, 0, 0, 0, "GarmentCode");
GarmentDocument synchronizedSeamDocument = new(
    "patterna.garment/1.0",
    "synchronized-seam-split",
    "Synchronized seam split",
    "centimeters",
    [seamPieceA, seamPieceB],
    [
        new ClothPanelDocument("panel-a", seamPieceA.Id, "A", "flat", false, ["seam-edge-a"])
        {
            SourcePlacement = flatPlacement,
            SourcePatternOrigin = new PatternPointDocument(0, 0)
        },
        new ClothPanelDocument("panel-b", seamPieceB.Id, "B", "flat", false, [])
        {
            SourcePlacement = flatPlacement,
            SourcePatternOrigin = new PatternPointDocument(0, 0)
        }
    ],
    [
        new GarmentSeamDocument(
            "split-seam",
            "Split seam",
            new SeamSideDocument("panel-a", ["seam-edge-a"]),
            new SeamSideDocument("panel-b", ["seam-edge-b"]),
            0.1)
    ],
    Fabric())
{
    Closures =
    [
        new GarmentClosureDocument(
            "split-closure",
            "Split closure",
            GarmentClosureKinds.Pin,
            GarmentClosureStates.Closed,
            new GarmentClosureAnchorDocument("panel-a", ["seam-edge-a"], 0.2, 0.8),
            new GarmentClosureAnchorDocument("panel-b", ["seam-edge-b"], 0.2, 0.8),
            3)
    ],
    Source = new GarmentSourceDocument("GarmentCode JSON", "1.0", null, "test")
};
PatternBoundarySplitResult synchronizedSplit = PatternStructuralEditor.SplitBoundarySegment(
    synchronizedSeamDocument,
    seamPieceA.Id,
    "seam-edge-a",
    0.3);
Assert(synchronizedSplit.Mappings.Count == 2, "A sewn edge split did not synchronize the opposite seam side.");
Assert(synchronizedSplit.Document.Seams[0].SideA.EdgeIds.Count == 2, "The selected seam side did not retain both split edges.");
Assert(synchronizedSplit.Document.Seams[0].SideB.EdgeIds.Count == 2, "The opposite seam side did not receive a matched split.");
Assert(synchronizedSplit.Document.Panels[0].PinnedEdges.Count == 2, "Pinned edge references were lost during splitting.");
Assert(synchronizedSplit.Document.Closures[0].AnchorA.EdgeIds.Count == 2, "Closure anchors were not updated during splitting.");
Assert(synchronizedSplit.Document.Validate().Count == 0, "A synchronized boundary split produced an invalid garment document.");
PatternTopologyCompilation splitCompilation = PatternTopologyCompiler.Compile(synchronizedSplit.Document);
Assert(splitCompilation.Seams[0].EdgeIdsA.Count == 2, "The topology compiler discarded a split seam chain.");
GarmentDocument exportableSynchronizedSplit = synchronizedSplit.Document with { Closures = [] };
string synchronizedExport = GarmentCodePatternExporter.Export(exportableSynchronizedSplit, "split-test");
using (JsonDocument splitExportJson = JsonDocument.Parse(synchronizedExport))
{
    Assert(
        splitExportJson.RootElement.GetProperty("pattern").GetProperty("stitches").GetArrayLength() == 2,
        "GarmentCode export did not preserve synchronized compound seam edges.");
    JsonElement splitStitches = splitExportJson.RootElement.GetProperty("pattern").GetProperty("stitches");
    Assert(
        splitStitches[0][0].GetProperty("edge").GetInt32() == 0 &&
        splitStitches[0][1].GetProperty("edge").GetInt32() == 1 &&
        splitStitches[1][0].GetProperty("edge").GetInt32() == 1 &&
        splitStitches[1][1].GetProperty("edge").GetInt32() == 0,
        "GarmentCode compound seam segments are not paired in continuous manifold order.");
}

PatternBoundarySplitResult replayedSplit = PatternStructuralEditor.Apply(
    synchronizedSeamDocument,
    [new PatternBoundarySplitCommand(seamPieceA.Id, "seam-edge-a", 0.3)]);
Assert(
    GarmentCodePatternExporter.ComputeStructuralSignature(replayedSplit.Document) ==
        GarmentCodePatternExporter.ComputeStructuralSignature(synchronizedSplit.Document),
    "Replayable structural split commands were not deterministic.");

JsonSerializerOptions structuralJsonOptions = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
PatternPieceDocument draftedPiece = PatternDraftFactory.CreatePiece(
    "drafted-piece",
    "Drafted piece",
    PatternDraftShape.Rectangle,
    12,
    18,
    1,
    1,
    false,
    false,
    40,
    60);
ClothPanelDocument draftedPanel = PatternDraftFactory.CreatePanel(
    "drafted-panel",
    draftedPiece,
    2);
Assert(draftedPiece.Boundary.Count == 4 && draftedPiece.Boundary.All(curve => curve.Kind == "line"), "Rectangle drafting did not create four editable line segments.");
Assert(draftedPiece.Grainline is not null && draftedPiece.Layout.LabelX == 24 && draftedPiece.Layout.LabelY == 36, "Rectangle drafting lost its grainline or scaled label placement.");
Assert(draftedPiece.ScaleX == 1 && draftedPiece.ScaleY == 1 && draftedPiece.SeamAllowanceCm == 1, "Rectangle drafting mapped seam allowance into a geometry scale.");
PatternPieceDocument draftedEllipse = PatternDraftFactory.CreatePiece(
    "drafted-ellipse",
    "Drafted ellipse",
    PatternDraftShape.Ellipse,
    20,
    14,
    0.8,
    2,
    true,
    false,
    80,
    90);
Assert(draftedEllipse.Boundary.Count == 4 && draftedEllipse.Boundary.All(curve => curve.Kind == "cubic"), "Ellipse drafting did not create four editable cubic segments.");
Assert(draftedEllipse.Boundary.All(curve => curve.Control1 is not null && curve.Control2 is not null), "Ellipse drafting omitted Bezier controls.");
Assert(PointDistance(draftedEllipse.Start, draftedEllipse.Boundary[^1].End) < 0.0000001, "Ellipse drafting did not close its boundary.");
Assert(draftedEllipse.ScaleX == 1 && draftedEllipse.ScaleY == 1 && draftedEllipse.SeamAllowanceCm == 0.8, "Ellipse drafting did not preserve its exact seam allowance and unit geometry scale.");
PatternPieceDocument draftedPolygon = PatternDraftFactory.CreatePolygonPiece(
    "drafted-polygon",
    "Drafted polygon",
    [
        new PatternPointDocument(0, 0),
        new PatternPointDocument(18, 0),
        new PatternPointDocument(15, 24),
        new PatternPointDocument(3, 24)
    ],
    1.1,
    1,
    false,
    false,
    120,
    100);
Assert(draftedPolygon.Boundary.Count == 4 && draftedPolygon.Boundary.All(curve => curve.Kind == "line"), "Polygon drafting did not create one stable line per vertex.");
Assert(draftedPolygon.Boundary.Select(curve => curve.Id).SequenceEqual(["edge-1", "edge-2", "edge-3", "edge-4"]), "Polygon drafting did not create stable ordered edge identities.");
Assert(PointDistance(draftedPolygon.Start, draftedPolygon.Boundary[^1].End) < 0.0000001, "Polygon drafting did not close its boundary.");
bool rejectedSelfIntersectingPolygon = false;
try
{
    _ = PatternDraftFactory.CreatePolygonPiece(
        "self-intersecting-polygon",
        "Self-intersecting polygon",
        [
            new PatternPointDocument(0, 0),
            new PatternPointDocument(10, 10),
            new PatternPointDocument(0, 10),
            new PatternPointDocument(10, 0)
        ],
        1,
        1,
        false,
        false,
        0,
        0);
}
catch (ArgumentException)
{
    rejectedSelfIntersectingPolygon = true;
}
Assert(rejectedSelfIntersectingPolygon, "Polygon drafting accepted a self-intersecting bow-tie boundary.");
bool rejectedOverlappingPolygonEdge = false;
try
{
    _ = PatternDraftFactory.CreatePolygonPiece(
        "overlapping-edge-polygon",
        "Overlapping edge polygon",
        [
            new PatternPointDocument(0, 0),
            new PatternPointDocument(10, 0),
            new PatternPointDocument(5, 0),
            new PatternPointDocument(10, 10),
            new PatternPointDocument(0, 10)
        ],
        1,
        1,
        false,
        false,
        0,
        0);
}
catch (ArgumentException)
{
    rejectedOverlappingPolygonEdge = true;
}
Assert(rejectedOverlappingPolygonEdge, "Polygon drafting accepted an overlapping reversed boundary edge.");
PatternPieceDocument canvasPolygon = PatternDraftFactory.CreateCanvasPolygonPiece(
    "canvas-polygon",
    "Canvas polygon",
    [
        new PatternPointDocument(25, 30),
        new PatternPointDocument(35, 30),
        new PatternPointDocument(33, 42),
        new PatternPointDocument(27, 42)
    ],
    4,
    1,
    1,
    false,
    false);
Assert(canvasPolygon.Layout.Left == 100 && canvasPolygon.Layout.Top == 120, "Canvas polygon drafting did not preserve the clicked physical origin in canvas placement.");
Assert(canvasPolygon.Start.X == 0 && canvasPolygon.Start.Y == 0, "Canvas polygon drafting did not normalize local piece coordinates.");
Assert(canvasPolygon.Layout.LabelX == 20 && canvasPolygon.Layout.LabelY == 24, "Canvas polygon drafting did not center its label in display pixels.");
ClothPanelDocument draftedEllipsePanel = PatternDraftFactory.CreatePanel("drafted-ellipse-panel", draftedEllipse, 3);
GarmentDocument withDraftedEllipse = PatternStructuralEditor.ApplyEdits(
    synchronizedSeamDocument,
    [new PatternPieceCreateCommand(draftedEllipse, draftedEllipsePanel)]);
Assert(withDraftedEllipse.Validate().Count == 0, "A factory-created ellipse produced an invalid garment document.");
PatternPieceCreateCommand createPieceCommand = new(draftedPiece, draftedPanel);
GarmentDocument withDraftedPiece = PatternStructuralEditor.ApplyEdits(
    synchronizedSeamDocument,
    [createPieceCommand]);
Assert(withDraftedPiece.Pieces.Count == 3 && withDraftedPiece.Panels.Count == 3, "A drafted piece did not create both pattern and cloth-panel records.");
Assert(withDraftedPiece.Validate().Count == 0, "A replay-created pattern piece produced an invalid garment document.");
PatternDartDocument physicalDart = new(
    "physical-waist-dart",
    "Physical waist dart",
    "top",
    0.35,
    "top",
    0.65,
    new PatternPointDocument(6, 5),
    "center")
{
    ConstructionMode = PatternDartConstructionModes.SewnFreeEdge
};
GarmentDocument physicalDartBase = SinglePanelDocument(draftedPiece) with
{
    Panels = [draftedPanel],
    Source = new GarmentSourceDocument(
        "GarmentCode JSON",
        "garmentcode.pattern/2",
        null,
        "physical-dart-test")
};
GarmentDocument physicalDartSource = PatternStructuralEditor.ApplyEdits(
    physicalDartBase,
    [new PatternDartCreateCommand(draftedPiece.Id, physicalDart)]);
Assert(
    !physicalDartSource.Pieces.Single(piece => piece.Id == draftedPiece.Id).Darts.Single().Materialized,
    "Editable physical-dart source was materialized before compilation.");
string physicalDartCommandJson = JsonSerializer.Serialize<PatternStructuralEditCommand[]>(
    [new PatternDartCreateCommand(draftedPiece.Id, physicalDart)],
    structuralJsonOptions);
PatternStructuralEditCommand[] restoredPhysicalDartCommands =
    JsonSerializer.Deserialize<PatternStructuralEditCommand[]>(
        physicalDartCommandJson,
        structuralJsonOptions)
    ?? throw new InvalidOperationException("Physical-dart command JSON did not deserialize.");
GarmentDocument replayedPhysicalDartSource = PatternStructuralEditor.ApplyEdits(
    physicalDartBase,
    restoredPhysicalDartCommands);
Assert(
    replayedPhysicalDartSource.Pieces.Single(piece => piece.Id == draftedPiece.Id)
        .Darts.Single().ConstructionMode == PatternDartConstructionModes.SewnFreeEdge,
    "Snapshot command replay discarded the physical-dart construction mode.");
ClothPanelDocument secondPhysicalDartPanel = draftedPanel with
{
    Id = "drafted-panel-second",
    Name = "Drafted piece second cut"
};
GarmentDocument multiPanelPhysicalDartSource = PatternStructuralEditor.ApplyEdits(
    physicalDartBase with { Panels = [draftedPanel, secondPhysicalDartPanel] },
    [new PatternDartCreateCommand(draftedPiece.Id, physicalDart)]);
GarmentDocument multiPanelPhysicalDartDocument = PatternPhysicalDartCompiler.Compile(
    multiPanelPhysicalDartSource);
Assert(
    multiPanelPhysicalDartDocument.Seams.Count(seam =>
        seam.Name == $"{physicalDart.Name} closure") == 2,
    "A shared pattern piece did not materialize its physical dart on every cloth-panel instance.");
GarmentDocument physicalDartDocument = PatternPhysicalDartCompiler.Compile(physicalDartSource);
PatternPieceDocument physicalDartPiece = physicalDartDocument.Pieces.Single(piece => piece.Id == draftedPiece.Id);
PatternDartDocument materializedDart = physicalDartPiece.Darts.Single(dart => dart.Id == physicalDart.Id);
Assert(materializedDart.Materialized, "Physical-dart compilation did not mark its editable source relationship as materialized.");
Assert(
    physicalDartPiece.Boundary.Count == draftedPiece.Boundary.Count + 3,
    "Physical-dart compilation did not replace the mouth with two cut boundary legs.");
GarmentSeamDocument physicalDartSeam = physicalDartDocument.Seams.Single(seam =>
    seam.Id.StartsWith($"{physicalDart.Id}-seam", StringComparison.OrdinalIgnoreCase));
Assert(
    physicalDartSeam.SideA.PanelId == physicalDartBase.Panels.Single().Id &&
        physicalDartSeam.SideB.PanelId == physicalDartBase.Panels.Single().Id,
    "Physical-dart compilation did not create a same-panel closure seam.");
Assert(
    physicalDartSeam.SideA.EdgeIds.Single() == materializedDart.FirstLegBoundaryCurveId &&
        physicalDartSeam.SideB.EdgeIds.Single() == materializedDart.SecondLegBoundaryCurveId,
    "Physical-dart closure seam does not reference the two generated dart legs.");
PatternTopologyCompilation physicalDartTopology = PatternTopologyCompiler.Compile(physicalDartDocument);
CompiledPatternSeam compiledPhysicalDartSeam = physicalDartTopology.Seams.Single(seam =>
    seam.Id == physicalDartSeam.Id);
Assert(
    compiledPhysicalDartSeam.PanelA == compiledPhysicalDartSeam.PanelB &&
        compiledPhysicalDartSeam.LengthMismatchRatio < 0.01,
    "Physical-dart topology did not compile into equal-length same-panel stitch constraints.");
Assert(
    physicalDartTopology.Panels.Single(panel => panel.PieceId == draftedPiece.Id).Triangles.All(triangle =>
        triangle.AreaCm2 > 0),
    "Physical-dart compilation produced a degenerate cloth mesh.");
GarmentDocument physicalDartAgain = PatternPhysicalDartCompiler.Compile(physicalDartDocument);
Assert(
    GarmentCodePatternExporter.ComputeStructuralSignature(physicalDartAgain) ==
        GarmentCodePatternExporter.ComputeStructuralSignature(physicalDartDocument),
    "Physical-dart compilation was not idempotent.");
string physicalDartJson = GarmentCodePatternExporter.Export(physicalDartDocument, "physical-dart-round-trip");
GarmentDocument physicalDartRoundTrip = GarmentCodePatternImporter.Import(
    physicalDartJson,
    new GarmentCodeImportOptions(
        "physical-dart-round-trip",
        "Physical dart round trip",
        Fabric()));
PatternDartDocument roundTripPhysicalDart = physicalDartRoundTrip.Pieces
    .Single(piece => piece.Id == draftedPiece.Id)
    .Darts.Single(dart => dart.Id == physicalDart.Id);
Assert(
    roundTripPhysicalDart.Materialized &&
        roundTripPhysicalDart.ConstructionMode == PatternDartConstructionModes.SewnFreeEdge,
    "GarmentCode round trip discarded physical-dart construction metadata.");
Assert(
    GarmentCodePatternExporter.ComputeStructuralSignature(
        PatternPhysicalDartCompiler.Compile(physicalDartRoundTrip)) ==
        GarmentCodePatternExporter.ComputeStructuralSignature(physicalDartRoundTrip),
    "Imported physical-dart topology was compiled a second time.");
PatternPieceDocument sewnDartFrontPiece = PatternDraftFactory.CreatePiece(
    "sewn-dart-front",
    "Sewn dart front",
    PatternDraftShape.Rectangle,
    10,
    12,
    1,
    1,
    false,
    false,
    0,
    0);
PatternPieceDocument sewnDartBackPiece = PatternDraftFactory.CreatePiece(
    "sewn-dart-back",
    "Sewn dart back",
    PatternDraftShape.Rectangle,
    10,
    9.6,
    1,
    1,
    false,
    false,
    50,
    0);
ClothPanelDocument sewnDartFrontPanel = PatternDraftFactory.CreatePanel(
    "sewn-dart-front-panel",
    sewnDartFrontPiece,
    0);
ClothPanelDocument sewnDartBackPanel = PatternDraftFactory.CreatePanel(
    "sewn-dart-back-panel",
    sewnDartBackPiece,
    1);
GarmentSeamDocument sewnDartSourceSeam = new(
    "sewn-dart-side-seam",
    "Side seam",
    new SeamSideDocument(sewnDartFrontPanel.Id, ["right"]),
    new SeamSideDocument(sewnDartBackPanel.Id, ["left"]),
    1);
GarmentDocument sewnDartBase = new(
    "patterna.garment/1.0",
    "sewn-edge-dart-test",
    "Sewn edge dart test",
    "centimeters",
    [sewnDartFrontPiece, sewnDartBackPiece],
    [sewnDartFrontPanel, sewnDartBackPanel],
    [sewnDartSourceSeam],
    Fabric())
{
    Source = new GarmentSourceDocument(
        "GarmentCode JSON",
        "garmentcode.pattern/2",
        null,
        "sewn-edge-dart-test")
};
PatternDartDocument sewnEdgeDart = new(
    "side-bust-dart",
    "Side bust dart",
    "right",
    0.4,
    "right",
    0.6,
    new PatternPointDocument(8, 6),
    "center")
{
    ConstructionMode = PatternDartConstructionModes.SewnEdge
};
GarmentDocument sewnDartSource = PatternStructuralEditor.ApplyEdits(
    sewnDartBase,
    [new PatternDartCreateCommand(sewnDartFrontPiece.Id, sewnEdgeDart)]);
GarmentDocument sewnDartDocument = PatternPhysicalDartCompiler.Compile(sewnDartSource);
Assert(
    sewnDartDocument.Seams.All(seam => seam.Id != sewnDartSourceSeam.Id),
    "Sewn-edge dart compilation retained the unsplit source seam.");
Assert(
    sewnDartDocument.Seams.Count == 3,
    "Sewn-edge dart compilation did not create one dart closure and two external seam spans.");
Assert(
    sewnDartDocument.Pieces.Single(piece => piece.Id == sewnDartFrontPiece.Id)
        .Darts.Single().Materialized,
    "Sewn-edge dart compilation did not materialize its source relationship.");
PatternTopologyCompilation sewnDartTopology = PatternTopologyCompiler.Compile(sewnDartDocument);
Assert(
    sewnDartTopology.Seams.All(seam => seam.LengthMismatchRatio < 0.01),
    "Sewn-edge dart compilation produced a mismatched dart leg or external seam span.");
Assert(
    sewnDartTopology.Panels.All(panel =>
        panel.Triangles.All(triangle => triangle.AreaCm2 > 0)),
    "Sewn-edge dart compilation produced a degenerate cloth mesh.");
string sewnDartJson = GarmentCodePatternExporter.Export(
    sewnDartDocument,
    "sewn-edge-dart-round-trip");
GarmentDocument sewnDartRoundTrip = GarmentCodePatternImporter.Import(
    sewnDartJson,
    new GarmentCodeImportOptions(
        "sewn-edge-dart-round-trip",
        "Sewn edge dart round trip",
        Fabric()));
Assert(
    sewnDartRoundTrip.Pieces.Single(piece => piece.Id == sewnDartFrontPiece.Id)
        .Darts.Single().ConstructionMode == PatternDartConstructionModes.SewnEdge,
    "GarmentCode round trip discarded the sewn-edge dart mode.");
Assert(
    GarmentCodePatternExporter.ComputeStructuralSignature(
        PatternPhysicalDartCompiler.Compile(sewnDartRoundTrip)) ==
        GarmentCodePatternExporter.ComputeStructuralSignature(sewnDartRoundTrip),
    "Imported sewn-edge dart topology was materialized a second time.");
bool rejectedSewnDartWithoutIntake = false;
try
{
    PatternPieceDocument equalLengthBack = PatternDraftFactory.CreatePiece(
        "sewn-dart-back",
        "Sewn dart back",
        PatternDraftShape.Rectangle,
        10,
        12,
        1,
        1,
        false,
        false,
        50,
        0);
    GarmentDocument noIntakeSource = sewnDartSource with
    {
        Pieces = [sewnDartFrontPiece with { Darts = [sewnEdgeDart] }, equalLengthBack]
    };
    _ = PatternPhysicalDartCompiler.Compile(noIntakeSource);
}
catch (InvalidOperationException exception)
{
    rejectedSewnDartWithoutIntake = exception.Message.Contains(
        "needs drafted intake",
        StringComparison.OrdinalIgnoreCase);
}
Assert(
    rejectedSewnDartWithoutIntake,
    "Sewn-edge dart compilation accepted a pattern with no physical dart intake.");
PatternSeamCreateCommand createSeamCommand = new(new GarmentSeamDocument(
    "drafted-side-seam",
    "Drafted side seam",
    new SeamSideDocument(draftedPanel.Id, ["right"]),
    new SeamSideDocument("panel-a", ["right-a"]),
    1));
PatternInternalPathCreateCommand createInternalPathCommand = new(
    draftedPiece.Id,
    new PatternInternalPathDocument(
        "drafted-fold-line",
        PatternInternalPathKinds.Fold,
        new PatternPointDocument(2, 9),
        [new PatternCurveDocument("drafted-fold-segment", "line", new PatternPointDocument(10, 9))])
    {
        Label = "Center fold"
    });
PatternDartCreateCommand createDartCommand = new(
    draftedPiece.Id,
    new PatternDartDocument(
        "drafted-dart",
        "Drafted dart",
        "top",
        0.35,
        "top",
        0.65,
        new PatternPointDocument(6, 5),
        "center"));
PatternPiecePropertiesCommand updatePiecePropertiesCommand = new(
    draftedPiece.Id,
    "Drafted shell panel",
    2,
    true,
    false,
    1.25,
    new PatternGrainlineDocument(
        new PatternPointDocument(6, 2),
        new PatternPointDocument(6, 16),
        true));
GarmentDocument withDraftedSeam = PatternStructuralEditor.ApplyEdits(
    synchronizedSeamDocument,
    [createPieceCommand, updatePiecePropertiesCommand, createInternalPathCommand, createDartCommand, createSeamCommand]);
Assert(withDraftedSeam.Seams.Count == 2, "Free sewing did not add a first-class seam relationship.");
PatternPieceDocument authoredDraftedPiece = withDraftedSeam.Pieces.Single(piece => piece.Id == draftedPiece.Id);
Assert(authoredDraftedPiece.InternalPaths.Count == 1, "Internal line authoring did not add first-class piece geometry.");
Assert(authoredDraftedPiece.Darts.Count == 1, "Dart authoring did not add a first-class dart relationship.");
Assert(authoredDraftedPiece.Name == "Drafted shell panel" && authoredDraftedPiece.SeamAllowanceCm == 1.25, "Piece settings did not preserve name or seam allowance.");
Assert(authoredDraftedPiece.CutQuantity == 2 && authoredDraftedPiece.Mirrored && authoredDraftedPiece.Grainline?.Locked == true, "Piece settings did not preserve cutting or grainline properties.");
Assert(withDraftedSeam.Validate().Count == 0, "A free-sewn drafted piece produced an invalid garment document.");
bool rejectedPhysicalDartOnSewnEdge = false;
try
{
    GarmentDocument sewnEdgePhysicalDart = PatternStructuralEditor.ApplyEdits(
        withDraftedSeam,
        [new PatternDartCreateCommand(
            draftedPiece.Id,
            physicalDart with
            {
                Id = "sewn-edge-physical-dart",
                FirstLegBoundaryCurveId = "right",
                FirstLegParameter = 0.35,
                SecondLegBoundaryCurveId = "right",
                SecondLegParameter = 0.65,
                Apex = new PatternPointDocument(8, 9)
            })]);
    _ = PatternPhysicalDartCompiler.Compile(sewnEdgePhysicalDart);
}
catch (InvalidOperationException exception)
{
    rejectedPhysicalDartOnSewnEdge = exception.Message.Contains(
        "unsewn free edges only",
        StringComparison.OrdinalIgnoreCase);
}
Assert(
    rejectedPhysicalDartOnSewnEdge,
    "Physical-dart compilation accepted a mouth on an externally sewn boundary edge.");
PatternStructuralEditCommand[] draftedCommands =
    [createPieceCommand, updatePiecePropertiesCommand, createInternalPathCommand, createDartCommand, createSeamCommand];
string draftedCommandsJson = JsonSerializer.Serialize(draftedCommands, structuralJsonOptions);
PatternStructuralEditCommand[] restoredDraftedCommands =
    JsonSerializer.Deserialize<PatternStructuralEditCommand[]>(draftedCommandsJson, structuralJsonOptions)
    ?? throw new InvalidOperationException("Drafting command JSON did not deserialize.");
GarmentDocument replayedDraftedDocument = PatternStructuralEditor.ApplyEdits(
    synchronizedSeamDocument,
    restoredDraftedCommands);
Assert(
    GarmentCodePatternExporter.ComputeStructuralSignature(replayedDraftedDocument) ==
    GarmentCodePatternExporter.ComputeStructuralSignature(withDraftedSeam),
    "Piece, internal-line, dart, and free-sewing commands were not deterministic after serialization.");
PatternPieceDocument replayedAuthoredPiece = replayedDraftedDocument.Pieces.Single(piece => piece.Id == draftedPiece.Id);
Assert(replayedAuthoredPiece.InternalPaths.Single().Label == "Center fold", "Internal line metadata was discarded during command replay.");
Assert(replayedAuthoredPiece.Darts.Single().Name == "Drafted dart", "Dart metadata was discarded during command replay.");
string draftedSvg = PatternSvgExporter.Export(
    SinglePanelDocument(authoredDraftedPiece),
    "physical <pattern>",
    new PatternSvgExportOptions(PageWidthMm: 400));
Assert(draftedSvg.Contains("width=\"400mm\"", StringComparison.Ordinal), "SVG export did not preserve its declared physical page width.");
Assert(draftedSvg.Contains("height=\"220mm\"", StringComparison.Ordinal), "SVG export did not size its page from centimeter geometry.");
Assert(draftedSvg.Contains("M 20 20 L 140 20 L 140 200 L 20 200 L 20 20 Z", StringComparison.Ordinal), "SVG export did not convert a 12 by 18 centimeter piece to exact millimeters.");
Assert(draftedSvg.Contains("data-seam-allowance-cm=\"1.25\"", StringComparison.Ordinal) && draftedSvg.Contains("stroke-width=\"25\"", StringComparison.Ordinal), "SVG export did not preserve the exact physical seam-allowance zone.");
Assert(draftedSvg.Contains("data-path-id=\"drafted-fold-line\"", StringComparison.Ordinal), "SVG export discarded an authored internal path.");
Assert(draftedSvg.Contains("data-dart-id=\"drafted-dart\"", StringComparison.Ordinal), "SVG export discarded an authored dart.");
Assert(draftedSvg.Contains("class=\"grainline\"", StringComparison.Ordinal), "SVG export discarded exact grainline geometry.");
Assert(draftedSvg.Contains("physical &lt;pattern&gt;", StringComparison.Ordinal), "SVG export did not encode metadata safely.");

PatternInternalPathUpdateCommand updateInternalPathCommand = new(
    draftedPiece.Id,
    "drafted-fold-line",
    new PatternInternalPathDocument(
        "drafted-fold-line",
        PatternInternalPathKinds.Construction,
        new PatternPointDocument(1, 8),
        [new PatternCurveDocument("drafted-fold-segment", "line", new PatternPointDocument(11, 8))])
    {
        Label = "Updated construction line"
    });
PatternDartUpdateCommand updateDartCommand = new(
    draftedPiece.Id,
    "drafted-dart",
    authoredDraftedPiece.Darts.Single() with
    {
        Name = "Updated dart",
        Apex = new PatternPointDocument(6, 6)
    });
GarmentDocument updatedConstructionDocument = PatternStructuralEditor.ApplyEdits(
    withDraftedSeam,
    [updateInternalPathCommand, updateDartCommand]);
PatternPieceDocument updatedConstructionPiece = updatedConstructionDocument.Pieces.Single(piece => piece.Id == draftedPiece.Id);
Assert(updatedConstructionPiece.InternalPaths.Single().Kind == PatternInternalPathKinds.Construction, "Internal line update did not replace its purpose.");
Assert(updatedConstructionPiece.InternalPaths.Single().Label == "Updated construction line", "Internal line update did not replace its label.");
Assert(updatedConstructionPiece.Darts.Single().Name == "Updated dart" && updatedConstructionPiece.Darts.Single().Apex.Y == 6, "Dart update did not replace its exact geometry.");
PatternStructuralEditCommand[] constructionLifecycleCommands =
[
    updateInternalPathCommand,
    updateDartCommand,
    new PatternInternalPathDeleteCommand(draftedPiece.Id, "drafted-fold-line"),
    new PatternDartDeleteCommand(draftedPiece.Id, "drafted-dart")
];
string constructionLifecycleJson = JsonSerializer.Serialize(constructionLifecycleCommands, structuralJsonOptions);
PatternStructuralEditCommand[] restoredConstructionLifecycleCommands =
    JsonSerializer.Deserialize<PatternStructuralEditCommand[]>(constructionLifecycleJson, structuralJsonOptions)
    ?? throw new InvalidOperationException("Construction lifecycle command JSON did not deserialize.");
GarmentDocument clearedConstructionDocument = PatternStructuralEditor.ApplyEdits(
    withDraftedSeam,
    restoredConstructionLifecycleCommands);
PatternPieceDocument clearedConstructionPiece = clearedConstructionDocument.Pieces.Single(piece => piece.Id == draftedPiece.Id);
Assert(clearedConstructionPiece.InternalPaths.Count == 0, "Internal line deletion was not deterministic after serialization.");
Assert(clearedConstructionPiece.Darts.Count == 0, "Dart deletion was not deterministic after serialization.");

PatternBoundaryCurveKindCommand makeTopCurveCommand = new(draftedPiece.Id, "top", "cubic");
GarmentDocument curvedBoundaryDocument = PatternStructuralEditor.ApplyEdits(withDraftedSeam, [makeTopCurveCommand]);
PatternCurveDocument curvedTop = curvedBoundaryDocument.Pieces.Single(piece => piece.Id == draftedPiece.Id).Boundary.Single(curve => curve.Id == "top");
Assert(curvedTop.Kind == "cubic" && curvedTop.Control1 is not null && curvedTop.Control2 is not null, "Line-to-curve conversion did not create editable Bezier controls.");
Assert(PointDistance(curvedTop.End, draftedPiece.Boundary.Single(curve => curve.Id == "top").End) < 0.0000001, "Line-to-curve conversion moved the segment endpoint.");
Assert(curvedBoundaryDocument.Seams.Any(seam => seam.SideA.EdgeIds.Contains("right") || seam.SideB.EdgeIds.Contains("right")), "Boundary conversion detached an unrelated sewing reference.");
PatternStructuralEditCommand[] boundaryKindCommands =
[
    makeTopCurveCommand,
    new PatternBoundaryCurveKindCommand(draftedPiece.Id, "top", "line")
];
string boundaryKindJson = JsonSerializer.Serialize(boundaryKindCommands, structuralJsonOptions);
PatternStructuralEditCommand[] restoredBoundaryKindCommands =
    JsonSerializer.Deserialize<PatternStructuralEditCommand[]>(boundaryKindJson, structuralJsonOptions)
    ?? throw new InvalidOperationException("Boundary kind command JSON did not deserialize.");
GarmentDocument restoredLineDocument = PatternStructuralEditor.ApplyEdits(withDraftedSeam, restoredBoundaryKindCommands);
PatternCurveDocument restoredTopLine = restoredLineDocument.Pieces.Single(piece => piece.Id == draftedPiece.Id).Boundary.Single(curve => curve.Id == "top");
Assert(restoredTopLine.Kind == "line" && restoredTopLine.Control1 is null && restoredTopLine.Control2 is null, "Curve-to-line conversion was not deterministic after serialization.");

PatternPieceDocument zeroLengthInternalPathPiece = draftedPiece with
{
    InternalPaths =
    [
        new PatternInternalPathDocument(
            "zero-length-line",
            PatternInternalPathKinds.Construction,
            new PatternPointDocument(4, 4),
            [new PatternCurveDocument("zero-length-segment", "line", new PatternPointDocument(4, 4))])
    ]
};
Assert(
    SinglePanelDocument(zeroLengthInternalPathPiece).Validate().Any(error => error.Contains("zero-length", StringComparison.OrdinalIgnoreCase)),
    "Document validation accepted a zero-length internal line.");

GarmentDocument notchedCubicDocument = PatternStructuralEditor.AddNotch(
    SinglePanelDocument(cubicSplitPiece),
    new PatternNotchCommand(cubicSplitPiece.Id, "neckline", 0.74, 0.45, 0.18, 2));
PatternNotchDocument originalNotch = notchedCubicDocument.Pieces[0].Notches.Single();
PatternPointDocument originalNotchPoint = EvaluateCurve(
    cubicSplitPiece.Start,
    cubicSplitPiece.Boundary[0],
    originalNotch.Parameter);
PatternBoundarySplitResult notchedSplit = PatternStructuralEditor.SplitBoundarySegment(
    notchedCubicDocument,
    cubicSplitPiece.Id,
    "neckline",
    cubicSplitParameter);
PatternPieceDocument notchedSplitPiece = notchedSplit.Document.Pieces[0];
PatternNotchDocument remappedNotch = notchedSplitPiece.Notches.Single();
Assert(remappedNotch.BoundaryCurveId == notchedSplit.SecondCurveId, "A notch after the split point remained attached to the removed curve.");
int remappedCurveIndex = notchedSplitPiece.Boundary
    .Select((curve, index) => new { curve.Id, Index = index })
    .Single(item => item.Id == remappedNotch.BoundaryCurveId)
    .Index;
PatternPointDocument remappedCurveStart = remappedCurveIndex == 0
    ? notchedSplitPiece.Start
    : notchedSplitPiece.Boundary[remappedCurveIndex - 1].End;
PatternPointDocument remappedNotchPoint = EvaluateCurve(
    remappedCurveStart,
    notchedSplitPiece.Boundary[remappedCurveIndex],
    remappedNotch.Parameter);
Assert(PointDistance(originalNotchPoint, remappedNotchPoint) < 0.0000001, "A boundary split moved its anchored construction notch.");

PatternPieceDocument constructionPiece = cubicSplitPiece with
{
    InternalPaths =
    [
        new PatternInternalPathDocument(
            "fold-guide",
            PatternInternalPathKinds.Fold,
            new PatternPointDocument(2, 2),
            [Line("fold-guide-line", 6, 2)])
    ],
    Darts =
    [
        new PatternDartDocument(
            "waist-dart",
            "Waist dart",
            "neckline",
            0.2,
            "neckline",
            0.8,
            new PatternPointDocument(4, 4))
    ],
    Grainline = new PatternGrainlineDocument(
        new PatternPointDocument(4, 1),
        new PatternPointDocument(4, 7),
        true)
};
GarmentDocument constructionDocument = SinglePanelDocument(constructionPiece);
Assert(constructionDocument.Validate().Count == 0, "Valid internal paths, darts, and grainlines were rejected.");
PatternBoundarySplitResult constructionSplit = PatternStructuralEditor.SplitBoundarySegment(
    constructionDocument,
    constructionPiece.Id,
    "neckline",
    0.5);
PatternDartDocument remappedDart = constructionSplit.Document.Pieces[0].Darts.Single();
Assert(
    remappedDart.FirstLegBoundaryCurveId == constructionSplit.FirstCurveId &&
        remappedDart.SecondLegBoundaryCurveId == constructionSplit.SecondCurveId,
    "A boundary split did not preserve both anchored dart legs.");

PatternStructuralEditCommand[] constructionCommands =
[
    new PatternNotchCommand(cubicSplitPiece.Id, "neckline", 0.25),
    new PatternBoundarySplitCommand(cubicSplitPiece.Id, "neckline", 0.5)
];
string structuralCommandsJson = JsonSerializer.Serialize(constructionCommands, structuralJsonOptions);
PatternStructuralEditCommand[] restoredConstructionCommands =
    JsonSerializer.Deserialize<PatternStructuralEditCommand[]>(structuralCommandsJson, structuralJsonOptions)
    ?? throw new InvalidOperationException("Structural command JSON did not deserialize.");
GarmentDocument restoredConstructionDocument = PatternStructuralEditor.ApplyEdits(
    SinglePanelDocument(cubicSplitPiece),
    restoredConstructionCommands);
Assert(restoredConstructionDocument.Pieces[0].Notches.Count == 1, "Snapshot serialization discarded a construction notch command.");
Assert(restoredConstructionDocument.Pieces[0].Boundary.Count == 5, "Snapshot serialization discarded a boundary split command.");

PatternPieceDocument exportConstructionPiece = exportableSynchronizedSplit.Pieces[0] with
{
    InternalPaths = constructionPiece.InternalPaths,
    Notches =
    [
        new PatternNotchDocument(
            "production-notch",
            exportableSynchronizedSplit.Pieces[0].Boundary[0].Id,
            0.4,
            0.45,
            0.18,
            2)
    ],
    Grainline = new PatternGrainlineDocument(
        new PatternPointDocument(5, 0.8),
        new PatternPointDocument(5, 4.2),
        true)
};
GarmentDocument exportConstructionDocument = exportableSynchronizedSplit with
{
    Pieces =
    [
        exportConstructionPiece,
        exportableSynchronizedSplit.Pieces[1]
    ]
};
string constructionExportJson = GarmentCodePatternExporter.Export(exportConstructionDocument, "construction-round-trip");
GarmentDocument constructionRoundTrip = GarmentCodePatternImporter.Import(
    constructionExportJson,
    new GarmentCodeImportOptions(
        "construction-round-trip",
        "Construction round trip",
        Fabric()));
PatternPieceDocument importedConstructionPiece = constructionRoundTrip.Pieces.Single(piece => piece.Id == exportConstructionPiece.Id);
Assert(importedConstructionPiece.InternalPaths.Count == 1, "GarmentCode round trip discarded a first-class internal path.");
Assert(importedConstructionPiece.Notches.Count == 1, "GarmentCode round trip discarded a construction notch.");
Assert(importedConstructionPiece.Grainline?.Locked == true, "GarmentCode round trip discarded the locked grainline.");

GarmentDocument missingNotchEdgeDocument = SinglePanelDocument(cubicSplitPiece with
{
    Notches = [new PatternNotchDocument("bad-notch", "missing", 0.5, 0.4)]
});
Assert(
    missingNotchEdgeDocument.Validate().Any(error => error.Contains("missing boundary curve", StringComparison.OrdinalIgnoreCase)),
    "A construction notch anchored to a missing edge passed validation.");

string runtimeFixtureBase = Path.Combine(
    Path.GetTempPath(),
    $"patterna-runtime-{Guid.NewGuid():N}");
string runtimeFixtureRoot = Path.Combine(
    runtimeFixtureBase,
    SimulationRuntimeLocator.InstalledRuntimeDirectoryName,
    SimulationRuntimeLocator.CurrentRuntimeDirectoryName);
try
{
    string garmentCodePythonRelative = ".venv-garmentcode/Scripts/python.exe";
    string style3DPythonRelative = ".venv-newton/Scripts/python.exe";
    string blenderRelative = "blender/blender.exe";
    string compilerRelative = "compiler/Patternal.UnrealGarmentCompiler.exe";
    string toolsRelative = "tools";
    string avatarLicenseRelative = "third_party/CharMorph-db/characters/antonia/license.txt";
    string avatarCharacterDirectoryRelative = "third_party/CharMorph-db/characters/antonia";
    string[] scriptNames =
    [
        "fit_charmorph_profile.py",
        "generate_charmorph_avatar.py",
        "prepare_charmorph_garmentcode_body.py",
        "charmorph_collision.py",
        "charmorph_character.py",
        "charmorph_anatomy.py",
        "charmorph_pose.py",
        "charmorph_glb.py",
        "verify_charmorph_glb.py",
        "charmorph_morphs.py",
        "charmorph_profile_controls.py",
        "mesh_torso_arcs.py",
        "generate_body_profile_from_mesh.py",
        "export_garmentcode_pattern_mesh.py",
        "build_style3d_source.py",
        "prefit_newton_style3d.py",
        "patterna_style3d_sewing.py",
        "render_product_acceptance.py",
        "record_product_visual_review.py",
        "product_registration.py"
    ];
    string[] entrypointRelativePaths =
    [
        garmentCodePythonRelative,
        style3DPythonRelative,
        blenderRelative,
        compilerRelative,
        avatarLicenseRelative,
        .. scriptNames.Select(script => $"{toolsRelative}/{script}")
    ];
    foreach (string relativePath in entrypointRelativePaths)
    {
        string path = Path.Combine(runtimeFixtureRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, $"fixture:{relativePath}", new UTF8Encoding(false));
    }
    Dictionary<string, string> runtimeHashes = entrypointRelativePaths.ToDictionary(
        relativePath => relativePath,
        relativePath => FileHash(Path.Combine(
            runtimeFixtureRoot,
            relativePath.Replace('/', Path.DirectorySeparatorChar))),
        StringComparer.OrdinalIgnoreCase);
    string manifestPath = Path.Combine(
        runtimeFixtureRoot,
        SimulationRuntimeLocator.ManifestFileName);
    string ValidManifest(string compilerPath = "compiler/Patternal.UnrealGarmentCompiler.exe")
        => JsonSerializer.Serialize(
            new
            {
                schemaVersion = SimulationRuntimeLocator.ManifestSchema,
                runtimeVersion = "test-runtime",
                garmentCodePython = garmentCodePythonRelative,
                style3DPython = style3DPythonRelative,
                blender = blenderRelative,
                compiler = compilerPath,
                toolsDirectory = toolsRelative,
                avatarBackend = "CharMorph Antonia",
                avatarOutputLicense = "CC-BY-3.0",
                avatarLicenseFile = avatarLicenseRelative,
                avatarCharacterDirectory = avatarCharacterDirectoryRelative,
                entrypointSha256 = runtimeHashes
            },
            new JsonSerializerOptions { WriteIndented = true });
    File.WriteAllText(manifestPath, ValidManifest(), new UTF8Encoding(false));

    SimulationRuntime installedRuntime = SimulationRuntimeLocator.Resolve(
        Path.Combine(runtimeFixtureBase, "not-a-checkout"),
        runtimeFixtureBase);
    Assert(
        installedRuntime.Origin == "installed-manifest" &&
            installedRuntime.RuntimeVersion == "test-runtime" &&
            installedRuntime.AvatarBackend == "CharMorph Antonia" &&
            installedRuntime.AvatarOutputLicense == "CC-BY-3.0" &&
            string.Equals(
                installedRuntime.AvatarLicensePath,
                Path.Combine(runtimeFixtureRoot, avatarLicenseRelative.Replace('/', Path.DirectorySeparatorChar)),
                StringComparison.OrdinalIgnoreCase) &&
            string.Equals(
                installedRuntime.AvatarCharacterDirectory,
                Path.Combine(runtimeFixtureRoot, avatarCharacterDirectoryRelative.Replace('/', Path.DirectorySeparatorChar)),
                StringComparison.OrdinalIgnoreCase) &&
            string.Equals(
                installedRuntime.RootDirectory,
                runtimeFixtureRoot,
                StringComparison.OrdinalIgnoreCase),
        "The runtime locator did not prefer a valid installed manifest without a source checkout.");

    string avatarLicensePath = Path.Combine(
        runtimeFixtureRoot,
        avatarLicenseRelative.Replace('/', Path.DirectorySeparatorChar));
    File.AppendAllText(avatarLicensePath, ":tampered");
    Assert(
        !SimulationRuntimeLocator.TryLoadManifest(manifestPath, out _, out string licenseTamperRejection) &&
            licenseTamperRejection.Contains("SHA-256", StringComparison.Ordinal),
        "The runtime manifest accepted a modified avatar license declaration.");
    File.WriteAllText(avatarLicensePath, $"fixture:{avatarLicenseRelative}", new UTF8Encoding(false));

    string tamperedScript = Path.Combine(runtimeFixtureRoot, "tools", scriptNames[0]);
    File.AppendAllText(tamperedScript, ":tampered");
    Assert(
        !SimulationRuntimeLocator.TryLoadManifest(manifestPath, out _, out string tamperRejection) &&
            tamperRejection.Contains("SHA-256", StringComparison.Ordinal),
        "The runtime manifest accepted a modified simulation entry point.");

    File.WriteAllText(manifestPath, ValidManifest("../outside.exe"), new UTF8Encoding(false));
    Assert(
        !SimulationRuntimeLocator.TryLoadManifest(manifestPath, out _, out string escapeRejection) &&
            escapeRejection.Contains("escapes", StringComparison.OrdinalIgnoreCase),
        "The runtime manifest accepted a path outside its owned directory.");
}
finally
{
    string tempRoot = Path.GetFullPath(Path.GetTempPath());
    string fixtureRoot = Path.GetFullPath(runtimeFixtureBase);
    if (Directory.Exists(fixtureRoot) &&
        fixtureRoot.StartsWith(tempRoot, StringComparison.OrdinalIgnoreCase))
    {
        Directory.Delete(fixtureRoot, true);
    }
}

string visualProofFixtureRoot = Path.Combine(
    Path.GetTempPath(),
    $"patterna-visual-proof-{Guid.NewGuid():N}");
try
{
    string visualProofJob = Path.Combine(visualProofFixtureRoot, "job");
    string displayAvatarDirectory = Path.Combine(visualProofJob, "display-avatar");
    string proofDirectory = Path.Combine(visualProofJob, "proofs", "fixture");
    Directory.CreateDirectory(displayAvatarDirectory);
    Directory.CreateDirectory(proofDirectory);

    string[] avatarAssetNames =
    [
        "body",
        "bra",
        "eyes",
        "teeth",
        "eyebrows",
        "eyelashes",
        "hair"
    ];
    Dictionary<string, object> avatarAssets = new(StringComparer.Ordinal);
    Dictionary<string, string> avatarHashes = new(StringComparer.Ordinal);
    foreach (string assetName in avatarAssetNames)
    {
        string geometryName = $"{assetName}.obj";
        string textureName = $"{assetName}.png";
        string geometryPath = Path.Combine(displayAvatarDirectory, geometryName);
        string texturePath = Path.Combine(displayAvatarDirectory, textureName);
        File.WriteAllText(geometryPath, $"fixture geometry {assetName}", new UTF8Encoding(false));
        File.WriteAllText(texturePath, $"fixture texture {assetName}", new UTF8Encoding(false));
        avatarAssets[assetName] = assetName == "bra"
            ? new
            {
                geometry = geometryName,
                texture = textureName,
                display_optional = true,
                maximum_surface_offset_m = 0.0001
            }
            : new { geometry = geometryName, texture = textureName };
        avatarHashes[$"{assetName}_geometry"] = FileHash(geometryPath);
        avatarHashes[$"{assetName}_texture"] = FileHash(texturePath);
    }

    string displayManifestPath = Path.Combine(displayAvatarDirectory, "manifest.json");
    File.WriteAllText(
        displayManifestPath,
        JsonSerializer.Serialize(new
        {
            schema_version = "patterna.display-avatar/1.0",
            assets = avatarAssets
        }),
        new UTF8Encoding(false));
    avatarHashes["manifest"] = FileHash(displayManifestPath);

    string garmentPath = Path.Combine(visualProofJob, "garment.render.obj");
    string fabricPath = Path.Combine(visualProofJob, "fabric.png");
    File.WriteAllText(garmentPath, "fixture garment", new UTF8Encoding(false));
    File.WriteAllText(fabricPath, "fixture fabric", new UTF8Encoding(false));

    string[] viewNames =
    [
        "front",
        "front-oblique",
        "left",
        "back",
        "back-oblique",
        "right"
    ];
    Dictionary<string, object> proofRenders = new(StringComparer.Ordinal);
    Dictionary<string, string> reviewedRenderHashes = new(StringComparer.Ordinal);
    foreach (string viewName in viewNames)
    {
        string renderName = $"{viewName}.png";
        string renderPath = Path.Combine(proofDirectory, renderName);
        File.WriteAllText(renderPath, $"fixture render {viewName}", new UTF8Encoding(false));
        string renderHash = FileHash(renderPath);
        proofRenders[viewName] = new
        {
            path = renderName,
            sha256 = renderHash
        };
        reviewedRenderHashes[viewName] = renderHash;
    }

    string proofManifestPath = Path.Combine(proofDirectory, "manifest.json");
    File.WriteAllText(
        proofManifestPath,
        JsonSerializer.Serialize(new
        {
            schema_version = "patterna.product-turntable/1.0",
            avatar_manifest = displayManifestPath,
            garment = garmentPath,
            fabric = fabricPath,
            avatar_object_count = avatarAssetNames.Length,
            show_bra = true,
            avatar_hashes = avatarHashes,
            garment_sha256 = FileHash(garmentPath),
            fabric_sha256 = FileHash(fabricPath),
            registration = new
            {
                schema_version = "patterna.product-registration/2.0",
                accepted = true
            },
            visual_quality = new
            {
                accepted = true,
                review_required = false,
                reviewed_render_sha256 = reviewedRenderHashes,
                issues = Array.Empty<string>()
            },
            resolution = new[] { 720, 900 },
            renders = proofRenders
        }),
        new UTF8Encoding(false));

    SimulationPipelineResult visualProofResult = new(
        Accepted: true,
        Revision: "fixture",
        JobDirectory: visualProofJob,
        PatternPath: garmentPath,
        MeshPath: garmentPath,
        RestPrefitPath: garmentPath,
        PrefitPath: garmentPath,
        FitReportPath: garmentPath,
        SolverName: "fixture",
        PreflightPath: garmentPath,
        BodyPath: garmentPath,
        BodySegmentationPath: garmentPath,
        BodyProfilePath: garmentPath,
        BodyPoseReportPath: garmentPath,
        DressedPoseReportPath: garmentPath,
        RenderMeshPath: garmentPath,
        UsdPath: garmentPath,
        ManifestPath: garmentPath,
        FabricName: "fixture",
        FabricThicknessMillimeters: 0.34,
        Message: "fixture",
        VisualProofManifestPath: proofManifestPath);
    Assert(
        SimulationPipeline.TryValidateProductVisualProof(visualProofResult),
        "A complete hash-bound six-view product proof was rejected.");

    JsonNode rejectedProof = JsonNode.Parse(File.ReadAllText(proofManifestPath))
        ?? throw new InvalidOperationException("The product-proof fixture did not parse.");
    rejectedProof["visual_quality"]!["accepted"] = false;
    File.WriteAllText(proofManifestPath, rejectedProof.ToJsonString(), new UTF8Encoding(false));
    Assert(
        !SimulationPipeline.TryValidateProductVisualProof(visualProofResult),
        "A visually rejected product proof was accepted.");
    rejectedProof["visual_quality"]!["accepted"] = true;
    File.WriteAllText(proofManifestPath, rejectedProof.ToJsonString(), new UTF8Encoding(false));

    string antoniaGeometryPath = Path.Combine(displayAvatarDirectory, "avatar.glb");
    string antoniaLicensePath = Path.Combine(displayAvatarDirectory, "license.txt");
    File.WriteAllText(antoniaGeometryPath, "fixture Antonia GLB", new UTF8Encoding(false));
    File.WriteAllText(antoniaLicensePath, "fixture Antonia license", new UTF8Encoding(false));
    void WriteAntoniaDisplayManifest(bool anatomyAccepted, bool poseAccepted)
    {
        File.WriteAllText(
            displayManifestPath,
            JsonSerializer.Serialize(new
            {
                schemaVersion = "patterna.display-avatar-glb/1.0",
                geometry = "avatar.glb",
                geometrySha256 = FileHash(antoniaGeometryPath),
                licenseFile = "license.txt",
                licenseSha256 = FileHash(antoniaLicensePath),
                measurementFit = new { accepted = true },
                anatomy = new
                {
                    schemaVersion = "patterna.avatar-anatomy/1.0",
                    accepted = anatomyAccepted
                },
                pose = new
                {
                    schemaVersion = "patterna.avatar-pose/1.0",
                    accepted = poseAccepted
                }
            }),
            new UTF8Encoding(false));
    }

    WriteAntoniaDisplayManifest(true, true);
    JsonNode antoniaProof = JsonNode.Parse(File.ReadAllText(proofManifestPath))
        ?? throw new InvalidOperationException("The Antonia product-proof fixture did not parse.");
    antoniaProof["show_bra"] = false;
    antoniaProof["avatar_object_count"] = 1;
    antoniaProof["avatar_hashes"] = new JsonObject
    {
        ["manifest"] = FileHash(displayManifestPath),
        ["body_geometry"] = FileHash(antoniaGeometryPath),
        ["avatar_license"] = FileHash(antoniaLicensePath)
    };
    File.WriteAllText(proofManifestPath, antoniaProof.ToJsonString(), new UTF8Encoding(false));
    Assert(
        SimulationPipeline.TryValidateProductVisualProof(visualProofResult),
        "An Antonia proof with accepted anatomy and pose evidence was rejected.");

    WriteAntoniaDisplayManifest(false, true);
    antoniaProof["avatar_hashes"]!["manifest"] = FileHash(displayManifestPath);
    File.WriteAllText(proofManifestPath, antoniaProof.ToJsonString(), new UTF8Encoding(false));
    Assert(
        !SimulationPipeline.TryValidateProductVisualProof(visualProofResult),
        "An Antonia product proof accepted a rejected anatomy report.");

    WriteAntoniaDisplayManifest(true, false);
    antoniaProof["avatar_hashes"]!["manifest"] = FileHash(displayManifestPath);
    File.WriteAllText(proofManifestPath, antoniaProof.ToJsonString(), new UTF8Encoding(false));
    Assert(
        !SimulationPipeline.TryValidateProductVisualProof(visualProofResult),
        "An Antonia product proof accepted a rejected inspection-pose report.");

    WriteAntoniaDisplayManifest(true, true);
    antoniaProof["avatar_hashes"]!["manifest"] = FileHash(displayManifestPath);
    File.WriteAllText(proofManifestPath, antoniaProof.ToJsonString(), new UTF8Encoding(false));

    File.AppendAllText(Path.Combine(proofDirectory, "back.png"), ":tampered");
    Assert(
        !SimulationPipeline.TryValidateProductVisualProof(visualProofResult),
        "The product proof accepted a modified rear view.");
}
finally
{
    string tempRoot = Path.GetFullPath(Path.GetTempPath());
    string fixtureRoot = Path.GetFullPath(visualProofFixtureRoot);
    if (Directory.Exists(fixtureRoot) &&
        fixtureRoot.StartsWith(tempRoot, StringComparison.OrdinalIgnoreCase))
    {
        Directory.Delete(fixtureRoot, true);
    }
}

string? installedRuntimeDataRoot = Environment.GetEnvironmentVariable(
    "PATTERNA_TEST_INSTALLED_RUNTIME_DATA_ROOT");
if (!string.IsNullOrWhiteSpace(installedRuntimeDataRoot))
{
    SimulationRuntime installedMachineRuntime = SimulationRuntimeLocator.Resolve(
        Path.Combine(installedRuntimeDataRoot, "not-a-source-checkout"),
        installedRuntimeDataRoot);
    Assert(
        installedMachineRuntime.Origin == "installed-manifest" &&
            Directory.Exists(installedMachineRuntime.RootDirectory) &&
            File.Exists(installedMachineRuntime.CompilerPath),
        "The installed machine runtime did not pass the same manifest resolver used by the packaged app.");
    Console.WriteLine(
        $"Installed simulation runtime: {installedMachineRuntime.RuntimeVersion} " +
        $"({installedMachineRuntime.Origin})");
}

string? acceptedJobRoot = Environment.GetEnvironmentVariable(
    "PATTERNA_TEST_ACCEPTED_JOB_ROOT");
string? acceptedJobRevision = Environment.GetEnvironmentVariable(
    "PATTERNA_TEST_ACCEPTED_JOB_REVISION");
if (!string.IsNullOrWhiteSpace(acceptedJobRoot) &&
    !string.IsNullOrWhiteSpace(acceptedJobRevision))
{
    Assert(
        SimulationPipeline.TryGetAcceptedResult(
            acceptedJobRoot,
            acceptedJobRevision,
            out SimulationPipelineResult? acceptedMachineResult) &&
            acceptedMachineResult is not null &&
            !string.IsNullOrWhiteSpace(acceptedMachineResult.VisualProofManifestPath) &&
            File.Exists(acceptedMachineResult.VisualProofManifestPath),
        "The installed-runtime job did not reopen with its exact hash-bound visual proof.");
    Console.WriteLine($"Accepted installed-runtime job: {acceptedJobRevision}");
}

Console.WriteLine($"Wrap panels: {firstWrapCompilation.Panels.Count}");
Console.WriteLine($"Adaptive shirt source ease: chest {acceptedSourceEase.ChestEaseCm:0.00} cm, waist {acceptedSourceEase.WaistEaseCm:0.00} cm, hip {acceptedSourceEase.HipEaseCm:0.00} cm");
Console.WriteLine("Adaptive shirt girth profile: " + string.Join(", ", Enumerable.Range(1, 12).Select(index =>
    $"{index * 0.05:0.00}={AdaptiveShirtPatternGrader.MeasureTorsoGirthAtRelativeHeight(acceptedShirt, index * 0.05):0.0}")));
Console.WriteLine($"Wrap seams: {firstWrapCompilation.Seams.Count}");
Console.WriteLine($"Wrap closures: {firstWrapCompilation.Closures.Count}");
Console.WriteLine($"Wrap vertices: {firstWrapCompilation.VertexCount}");
Console.WriteLine($"Wrap triangles: {firstWrapCompilation.TriangleCount}");
Console.WriteLine($"Warnings: {firstWrapCompilation.Diagnostics.Count(item => item.Severity == PatternTopologyDiagnosticSeverity.Warning)}");
foreach (PatternTopologyDiagnostic diagnostic in firstWrapCompilation.Diagnostics.Where(item =>
    item.Severity == PatternTopologyDiagnosticSeverity.Warning))
{
    Console.WriteLine($"Warning {diagnostic.Code}: {diagnostic.Message}");
}
Console.WriteLine($"Deterministic SHA-256: {firstHash.ToLowerInvariant()}");
Console.WriteLine("Result: Passed");
