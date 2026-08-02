using System.Text.Json;
using Patterna;
using Patterna.UnrealGarmentCompiler;

static void Assert(bool condition, string message)
{
    if (!condition)
    {
        throw new InvalidOperationException(message);
    }
}

static string FindRepositoryRoot()
{
    DirectoryInfo? directory = new(AppContext.BaseDirectory);
    while (directory is not null)
    {
        if (File.Exists(Path.Combine(directory.FullName, "Patternal", "Patternal.csproj")) &&
            Directory.Exists(Path.Combine(directory.FullName, "third_party", "GarmentCode")))
        {
            return directory.FullName;
        }
        directory = directory.Parent;
    }
    throw new DirectoryNotFoundException("Could not locate the Patternal repository root.");
}

static LiveBodyProfileDocument BuildTestBodyProfile()
{
    (double Height, double Width, double Depth, double CenterX, double CenterY, double Circumference, int Samples)[] specs =
    [
        (95, 32.406463623046875, 26.99819564819336, -0.042532920837402344, -0.04366302490234375, 93.50607299804688, 188),
        (97, 31.773630142211914, 26.599925994873047, -0.012362480163574219, -0.09551811218261719, 91.87313079833984, 192),
        (99, 30.870895385742188, 26.160228729248047, 0.0027146339416503906, 0.2680697441101074, 89.73714447021484, 192),
        (101, 30.244747161865234, 25.14645004272461, -0.007094383239746094, 0.857795238494873, 87.19267272949219, 176),
        (103, 29.165790557861328, 22.925880432128906, 0.010231494903564453, 1.432854175567627, 82.11920166015625, 172),
        (105, 27.833744049072266, 19.80615234375, 0.013199329376220703, 2.0835025310516357, 75.3647232055664, 172),
        (107, 26.565475463867188, 18.17998504638672, 0.014256954193115234, 2.5417702198028564, 70.90449523925781, 160),
        (109, 25.413063049316406, 18.71812629699707, 0.012871265411376953, 2.2570760250091553, 69.72053527832031, 160),
        (111, 25.96047592163086, 19.56203842163086, 0.01439046859741211, 1.7306170463562012, 71.86019897460938, 152),
        (113, 27.004955291748047, 20.177661895751953, 0.014241218566894531, 1.2583527565002441, 74.50274658203125, 152),
        (115, 27.54150390625, 20.43756675720215, 0.014217853546142578, 0.6739397048950195, 75.77898406982422, 152),
        (117, 28.26836585998535, 20.281959533691406, 0.014333724975585938, -0.07528352737426758, 76.77945709228516, 156),
        (119, 28.638347625732422, 20.237245559692383, 0.014091014862060547, -0.5731678009033203, 77.34173583984375, 168),
        (121, 29.074302673339844, 22.096338272094727, 0.013820648193359375, -0.5528783798217773, 80.75276947021484, 196),
        (123, 29.259883880615234, 23.48531723022461, 0.014102458953857422, -0.8978028297424316, 83.10041809082031, 228),
        (125, 28.219013214111328, 24.463134765625, -0.013614654541015625, -1.5255050659179688, 82.85811614990234, 186),
        (127, 27.805923461914062, 25.7216796875, -0.02331256866455078, -1.982530117034912, 84.11283874511719, 156),
        (129, 28.436134338378906, 28.19538116455078, -0.0369715690612793, -1.7334532737731934, 88.95698547363281, 160),
        (131, 28.210552215576172, 29.822547912597656, 0.010432720184326172, -1.642773151397705, 91.17576599121094, 176),
        (133, 29.628231048583984, 30.615102767944336, -0.1612563133239746, -1.7484941482543945, 94.6363525390625, 182),
        (135, 31.87389373779297, 30.625600814819336, 0.051900386810302734, -2.121577262878418, 98.18377685546875, 148),
        (137, 33.84080123901367, 21.10405158996582, 0.01294708251953125, -6.9063897132873535, 87.47057342529297, 104),
        (139, 31.737470626831055, 15.937533378601074, 0.01658916473388672, -9.236466407775879, 76.95850372314453, 76)
    ];

    LiveBodySectionDocument[] sections = specs
        .Select(spec =>
        {
            LiveBodySurfacePointDocument[] points = Enumerable.Range(0, 64)
                .Select(index =>
                {
                    double angle = -Math.PI + index * (2.0 * Math.PI / 64.0);
                    double radiusX = spec.Width * 0.5;
                    double radiusY = spec.Depth * 0.5;
                    double cosine = Math.Cos(angle);
                    double sine = Math.Sin(angle);
                    double radius = radiusX * radiusY / Math.Sqrt(
                        radiusY * radiusY * cosine * cosine +
                        radiusX * radiusX * sine * sine);
                    return new LiveBodySurfacePointDocument(
                        angle,
                        radius,
                        spec.CenterX + radius * cosine,
                        spec.CenterY + radius * sine);
                })
                .ToArray();
            return new LiveBodySectionDocument(
                spec.Height,
                spec.Width,
                spec.Depth,
                spec.CenterX,
                spec.CenterY,
                spec.Circumference,
                spec.Samples,
                points.Length,
                points);
        })
        .ToArray();

    return new LiveBodyProfileDocument(
        "patterna.live-body-profile/1.0",
        "/Game/PatternaMeasuredV2/MH_Patterna_Female_Default/Body/SKM_MH_Patterna_Female_Default_BodyMesh.SKM_MH_Patterna_Female_Default_BodyMesh",
        0,
        0.05,
        0.95,
        "torso-skin-weight-filtered-triangle-plane-intersection-above-109cm",
        sections,
        95,
        139,
        2);
}

static double PanelWrongSideRatio(ArrangedPanelMesh panel)
{
    ArrangedPanelVertex[] interior = panel.Vertices
        .Where(vertex =>
            vertex.U >= 0.15 && vertex.U <= 0.85 &&
            vertex.V >= 0.08 && vertex.V <= 0.92 &&
            vertex.Z >= 108.0 && vertex.Z <= 135.0)
        .ToArray();
    if (interior.Length == 0)
    {
        return 0;
    }

    bool expectsFront = panel.Placement.StartsWith("torsoFront", StringComparison.Ordinal) ||
        panel.Placement.StartsWith("skirtFront", StringComparison.Ordinal);
    bool expectsBack = panel.Placement.StartsWith("torsoBack", StringComparison.Ordinal) ||
        panel.Placement.StartsWith("skirtBack", StringComparison.Ordinal);
    if (!expectsFront && !expectsBack)
    {
        return 0;
    }

    int wrongSide = interior.Count(vertex => expectsFront ? vertex.Y < -0.25 : vertex.Y > 0.25);
    return wrongSide / (double)interior.Length;
}

static PatternaUnrealBridgeDocument BuildBridge(GarmentDocument garment)
{
    UnrealFabricGenerationDocument fabric = new(
        garment.Fabric.Id,
        garment.Fabric.Name,
        garment.Fabric.MassGramsPerSquareMeter,
        garment.Fabric.ThicknessMillimeters,
        garment.Fabric.WarpStretchPercent,
        garment.Fabric.WeftStretchPercent,
        garment.Fabric.BiasStretchPercent,
        garment.Fabric.BendResistance,
        garment.Fabric.ShearResistance,
        garment.Fabric.StaticFriction,
        garment.Fabric.DynamicFriction,
        garment.Fabric.Calibration);
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
        garment.Fabric.ThicknessMillimeters / 10,
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

string repositoryRoot = FindRepositoryRoot();
JsonSerializerOptions jsonOptions = new()
{
    PropertyNameCaseInsensitive = true,
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase
};
LiveBodyProfileDocument bodyProfile;
string bodyProfileJson;
if (args.Length > 0)
{
    string bodyProfilePath = Path.GetFullPath(args[0]);
    bodyProfileJson = await File.ReadAllTextAsync(bodyProfilePath);
    bodyProfile = JsonSerializer.Deserialize<LiveBodyProfileDocument>(bodyProfileJson, jsonOptions)
        ?? throw new InvalidDataException("Body profile deserialization failed.");
}
else
{
    bodyProfile = BuildTestBodyProfile();
    bodyProfileJson = JsonSerializer.Serialize(bodyProfile, jsonOptions);
}

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
string garmentCodeSamplePath = Path.GetFullPath(Path.Combine(
    repositoryRoot,
    "third_party",
    "GarmentCode",
    "assets",
    "Patterns",
    "dress_pencil_specification.json"));
GarmentDocument importedPencilDress = GarmentCodePatternImporter.Import(
    await File.ReadAllTextAsync(garmentCodeSamplePath),
    new GarmentCodeImportOptions(
        "garmentcode-pencil-dress",
        "GarmentCode fitted pencil dress",
        garment.Fabric,
        SourcePath: "third_party/GarmentCode/assets/Patterns/dress_pencil_specification.json",
        SourceRevision: "d449629979028123a5c4dc9e732a2ec19b7fce31"));
PatternTopologyCompilation importedPencilTopology = PatternTopologyCompiler.Compile(importedPencilDress);
StructuredPanelMesh[] importedPencilMeshes = importedPencilTopology.Panels
    .Select(StructuredPanelRemesher.Remesh)
    .ToArray();
Assert(importedPencilMeshes.Length == 6, "The generic simulation mesh path lost an imported panel.");
Assert(
    importedPencilMeshes.All(mesh => mesh.Triangles.Count > 0 && mesh.EdgeVertexIndices.Count >= 3),
    "The generic simulation mesh path lost triangles or semantic boundary edges.");
Assert(
    importedPencilMeshes.All(mesh => mesh.MaximumTriangleAspectRatio <= 12),
    "The adaptive simulation mesh path produced a triangle above the 12:1 aspect-ratio limit.");
Assert(
    importedPencilMeshes.All(mesh => mesh.MaximumBoundaryDeviationCm <= 0.001),
    "The adaptive simulation mesh path moved a fitted pattern boundary.");
string garmentCodeShirtPath = Path.GetFullPath(Path.Combine(
    repositoryRoot,
    "third_party",
    "GarmentCode",
    "assets",
    "Patterns",
    "shirt_mean_specification.json"));
GarmentDocument importedShirt = GarmentCodePatternImporter.Import(
    await File.ReadAllTextAsync(garmentCodeShirtPath),
    new GarmentCodeImportOptions(
        "garmentcode-shirt",
        "GarmentCode female shirt",
        garment.Fabric,
        SourcePath: "third_party/GarmentCode/assets/Patterns/shirt_mean_specification.json"));
FullGarmentArrangementReport importedShirtArrangement = FullGarmentArrangement.Arrange(
    PatternTopologyCompiler.Compile(importedShirt),
    bodyProfile);
Assert(importedShirtArrangement.Panels.Count == 8, "The imported shirt lost a pattern panel.");
Assert(importedShirtArrangement.SeamDirections.Count == 18, "The imported shirt lost a construction seam.");
Assert(
    importedShirtArrangement.Panels.SelectMany(panel => panel.Vertices).Max(vertex => vertex.Z) >= 138.0,
    "The imported shirt remained staged below the measured shoulder region.");
Assert(
    importedShirtArrangement.NinetyFifthPercentileEdgeStrainRatio <= 0.25,
    "Shoulder alignment pushed the imported shirt above the broad strain limit.");
PatternaUnrealBridgeDocument bridge = BuildBridge(garment);
string bridgeJson = JsonSerializer.Serialize(bridge, jsonOptions);
FullGarmentPreflightReport accepted = FullGarmentPreflight.Run(
    bridge,
    bodyProfile,
    bridgeJson,
    bodyProfileJson);
foreach (FullGarmentSeamReport seam in accepted.Seams)
{
    Console.WriteLine($"Seam {seam.Id}: {seam.LengthACm:F2} cm to {seam.LengthBCm:F2} cm, mismatch {seam.LengthMismatchRatio:P1}");
}
Assert(accepted.IsAccepted, string.Join(Environment.NewLine, accepted.Issues.Select(issue => issue.Message)));
Assert(accepted.Panels.Count == 8, "The full garment preflight did not retain eight panels.");
Assert(accepted.Seams.Count == 11, "The full garment preflight did not retain eleven construction seams.");
Assert(accepted.Closures.Count == 3, "The full garment preflight did not retain three explicit closures.");
Assert(
    accepted.Closures.All(closure => closure.Accepted && closure.State == GarmentClosureStates.Closed),
    "The full garment preflight did not accept every active closure.");
Assert(
    accepted.Seams.All(seam => seam.Id != "bodice-center-front"),
    "The full garment preflight incorrectly sewed the wrap opening closed.");
Assert(accepted.Panels.All(panel => panel.SewingRelationshipCount > 0), "A full garment panel remains unsewn.");
Assert(accepted.Panels.All(panel => panel.HasStructuredRemesh), "A full garment panel lacks a structured simulation mesh.");
Assert(accepted.Seams.All(seam => seam.Accepted), "A full garment seam exceeds the mismatch limit.");
Assert(accepted.BodyProfile.Accepted, "The expanded body profile was rejected.");
Assert(accepted.Arrangement.Accepted, "The body-aware full-garment arrangement was rejected.");

LiveBodySectionDocument finalNeckSection = bodyProfile.Sections
    .OrderBy(section => section.HeightCm)
    .Last();
LiveBodyProfileDocument sharpNeckProfile = bodyProfile with
{
    Sections = bodyProfile.Sections
        .Select(section => section == finalNeckSection
            ? section with { EllipseCircumferenceCm = section.EllipseCircumferenceCm * 0.55 }
            : section)
        .ToArray()
};
FullGarmentPreflightReport sharpNeckReport = FullGarmentPreflight.Run(
    bridge,
    sharpNeckProfile,
    bridgeJson,
    JsonSerializer.Serialize(sharpNeckProfile, jsonOptions));
Assert(
    !sharpNeckReport.Issues.Any(issue => issue.Code == "body-profile-discontinuity"),
    "A valid shoulder-to-neck transition was treated as a broken torso profile.");

LiveBodySectionDocument internalTorsoSection = bodyProfile.Sections
    .OrderBy(section => Math.Abs(section.HeightCm - 125.0))
    .First();
LiveBodyProfileDocument brokenTorsoProfile = bodyProfile with
{
    Sections = bodyProfile.Sections
        .Select(section => section == internalTorsoSection
            ? section with { EllipseCircumferenceCm = section.EllipseCircumferenceCm * 0.45 }
            : section)
        .ToArray()
};
FullGarmentPreflightReport brokenTorsoReport = FullGarmentPreflight.Run(
    bridge,
    brokenTorsoProfile,
    bridgeJson,
    JsonSerializer.Serialize(brokenTorsoProfile, jsonOptions));
Assert(
    brokenTorsoReport.Issues.Any(issue => issue.Code == "body-profile-discontinuity"),
    "A discontinuity inside the garment-placement torso was accepted.");

PatternTopologyCompilation compiledTopology = PatternTopologyCompiler.Compile(
    garment,
    new PatternTopologyCompilerOptions(
        MaximumCurveSegmentLengthCm: 0.75,
        MaximumSeamLengthMismatchRatio: 0.15));
StructuredPanelMesh[] structuredMeshes = compiledTopology.Panels
    .Select(StructuredPanelRemesher.Remesh)
    .ToArray();
Assert(structuredMeshes.Length == 8, "Structured remeshing did not retain all eight panels.");
Assert(
    structuredMeshes.All(mesh => mesh.MinimumTriangleAreaCm2 > 0.000001),
    "Structured remeshing produced a degenerate triangle.");
Assert(
    structuredMeshes.All(mesh => mesh.MaximumTriangleAspectRatio <= 12.0),
    "Structured remeshing produced a triangle aspect ratio above 12:1.");
Assert(
    structuredMeshes.All(mesh => mesh.MaximumBoundaryDeviationCm <= 0.001),
    "Structured remeshing moved a panel corner off its drafted boundary.");
foreach (CompiledPatternPanel panel in compiledTopology.Panels)
{
    StructuredPanelMesh mesh = structuredMeshes.Single(candidate => candidate.PanelId == panel.Id);
    Assert(
        panel.Edges.All(edge => mesh.EdgeVertexIndices.ContainsKey(edge.Id)),
        $"Structured remeshing omitted a named edge from panel {panel.Id}.");
}
string firstStructuredJson = JsonSerializer.Serialize(structuredMeshes, jsonOptions);
string secondStructuredJson = JsonSerializer.Serialize(
    compiledTopology.Panels.Select(StructuredPanelRemesher.Remesh).ToArray(),
    jsonOptions);
Assert(
    string.Equals(firstStructuredJson, secondStructuredJson, StringComparison.Ordinal),
    "Structured remeshing is not deterministic.");

FullGarmentArrangementReport arrangement = FullGarmentArrangement.Arrange(
    compiledTopology,
    bodyProfile);
Assert(arrangement.Panels.Count == 8, "Full-garment arrangement did not retain all eight panels.");
Assert(arrangement.Stitches.Count > 100, "Full-garment arrangement produced too few seam stitches.");
Assert(arrangement.Closures.Count == 3, "Full-garment arrangement did not compile all active closure constraints.");
Assert(arrangement.SeamDirections.Count == 11, "Full-garment arrangement did not validate every seam direction.");
Assert(
    arrangement.SeamDirections.All(direction =>
        direction.SelectedEndpointGapCm <= direction.OppositeEndpointGapCm + 0.01),
    "Full-garment arrangement retained a twisted seam direction.");
Assert(arrangement.MinimumTriangleAreaCm2 >= 0.001, "Full-garment arrangement produced a near-degenerate triangle.");
Assert(arrangement.MaximumSeamGapCm <= 90.0, "Full-garment staging placed a sewn edge more than 90 cm from its partner.");
Assert(arrangement.MaximumClosureGapCm <= 130.0, "Full-garment staging placed a closure more than 130 cm from its partner.");
Assert(arrangement.MaximumEdgeStrainRatio <= 2.0, "Full-garment arrangement peak edge strain exceeds 200 percent.");
Assert(
    arrangement.NinetyFifthPercentileEdgeStrainRatio <= 0.25,
    "Full-garment arrangement 95th-percentile edge strain exceeds 25 percent.");
Assert(arrangement.MinimumTorsoClearanceCm >= 0.25, "Full-garment arrangement intersects the measured torso surface.");
foreach (ArrangedPanelMesh panel in arrangement.Panels.Where(panel =>
    panel.Placement.StartsWith("torso", StringComparison.Ordinal) ||
    panel.Placement.StartsWith("skirt", StringComparison.Ordinal)))
{
    double wrongSideRatio = PanelWrongSideRatio(panel);
    Assert(
        wrongSideRatio <= 0.01,
        $"Full-garment arrangement moved {wrongSideRatio:P1} of interior vertices for {panel.PanelId} onto the wrong side of the body.");
}

FullGarmentUsdExport usdExport = FullGarmentUsdExporter.Export(arrangement, garment);
FullGarmentUsdExport repeatedUsdExport = FullGarmentUsdExporter.Export(arrangement, garment);
FullGarmentUsdExport namedUsdExport = FullGarmentUsdExporter.Export(
    arrangement,
    garment,
    "PatternaFittedPencilDress");
WeldedRenderSurface renderSurface = WeldedRenderSurfaceBuilder.Build(arrangement);
WeldedRenderSurface baseRenderSurface = WeldedRenderSurfaceBuilder.Build(
    arrangement,
    subdivisionLevel: 0);
Assert(namedUsdExport.GarmentId == "PatternaFittedPencilDress", "USD export should preserve an explicit garment identity.");
Assert(namedUsdExport.Usd.Contains("defaultPrim = \"PatternaFittedPencilDress\"", StringComparison.Ordinal), "USD export should use the explicit garment identity as its root prim.");
Assert(
    usdExport.SimulationVertexCount == structuredMeshes.Sum(mesh => mesh.Vertices.Count),
    "USD export changed the structured simulation vertex count.");
Assert(
    usdExport.SimulationTriangleCount == structuredMeshes.Sum(mesh => mesh.Triangles.Count),
    "USD export changed the structured simulation triangle count.");
Assert(usdExport.RenderMeshCount == 1, "USD export did not create one continuous render surface.");
Assert(
    renderSurface.Vertices.Count > renderSurface.SourceVertexCount,
    "The independent render surface was not subdivided above simulation density.");
Assert(
    renderSurface.Triangles.Count == arrangement.Panels.Sum(panel => panel.Triangles.Count) * 4,
    "The independent render surface did not subdivide every simulation triangle once.");
Assert(
    renderSurface.RefinementAlgorithm == "boundary-constrained Taubin fairing and Loop subdivision",
    "The independent render surface did not declare its refinement algorithm.");
Assert(
    renderSurface.MaximumBaseVertexDisplacementCm <= 0.750001,
    "The render refinement moved a base vertex beyond its displacement guard.");
Assert(
    renderSurface.MaximumBaseVertexDisplacementCm > 0.000001,
    "The render refinement did not smooth any interior base vertex.");
Assert(
    renderSurface.ProtectedBoundaryVertexCount > 0,
    "The render refinement did not identify any finished garment boundary vertices.");
HashSet<int> baseBoundaryVertices = baseRenderSurface.Triangles
    .SelectMany(triangle => new[]
    {
        triangle.A < triangle.B ? (triangle.A, triangle.B) : (triangle.B, triangle.A),
        triangle.B < triangle.C ? (triangle.B, triangle.C) : (triangle.C, triangle.B),
        triangle.C < triangle.A ? (triangle.C, triangle.A) : (triangle.A, triangle.C)
    })
    .GroupBy(edge => edge)
    .Where(group => group.Count() == 1)
    .SelectMany(group => new[] { group.Key.Item1, group.Key.Item2 })
    .ToHashSet();
Assert(
    baseBoundaryVertices.Count == renderSurface.ProtectedBoundaryVertexCount,
    "The render refinement boundary count does not match the welded base topology.");
foreach (int boundaryVertex in baseBoundaryVertices)
{
    RenderSurfaceVertex before = baseRenderSurface.Vertices[boundaryVertex];
    RenderSurfaceVertex after = renderSurface.Vertices[boundaryVertex];
    Assert(
        Math.Abs(before.X - after.X) <= 0.000001 &&
        Math.Abs(before.Y - after.Y) <= 0.000001 &&
        Math.Abs(before.Z - after.Z) <= 0.000001,
        $"Render refinement moved protected boundary vertex {boundaryVertex}.");
}
Assert(
    renderSurface.WeldedConstructionStitchCount + renderSurface.UnweldedConstructionStitchCount ==
        arrangement.Stitches.Count,
    "The render surface did not classify every construction stitch.");
Assert(usdExport.SeamCount == 11, "USD export did not retain all eleven construction seams.");
Assert(usdExport.StitchCount == arrangement.Stitches.Count, "USD export changed the verified stitch count.");
Assert(usdExport.ClosureCount == 3, "USD export did not retain all three garment closures.");
Assert(usdExport.ClosureConstraintCount == 3, "USD export changed the verified closure constraint count.");
Assert(usdExport.Usd.Contains("SewingAPI", StringComparison.Ordinal), "USD export contains no sewing schema.");
Assert(
    usdExport.Usd.Contains("patterna:constraintSemantic = \"closure\"", StringComparison.Ordinal),
    "USD export did not distinguish closures from permanent construction seams.");
Assert(usdExport.Usd.Contains("RenderPatternAPI", StringComparison.Ordinal), "USD export contains no render pattern schema.");
Assert(usdExport.Usd.Contains("def Mesh \"RenderSurface\"", StringComparison.Ordinal), "USD export contains no independent render surface.");
Assert(usdExport.Usd.Contains("primvars:st:interpolation = \"faceVarying\"", StringComparison.Ordinal), "USD export did not preserve panel UV seams on the welded surface.");
Assert(
    usdExport.RenderObj.Split('\n').Count(line => line.StartsWith("vt ", StringComparison.Ordinal)) ==
        renderSurface.Triangles.Count * 3,
    "The application OBJ did not preserve one pattern UV per face corner.");
Assert(
    usdExport.RenderObj.Contains("g patterna_seams", StringComparison.Ordinal) &&
    usdExport.RenderObj.Contains("g patterna_edges", StringComparison.Ordinal),
    "The application OBJ did not preserve construction seams and finished open edges.");
Assert(
    usdExport.ManifestJson.Contains("\"uvCoordinateSource\": \"authoritative 2D panel rest coordinates\"", StringComparison.Ordinal),
    "The render manifest did not identify the authoritative pattern UV source.");
Assert(
    string.Equals(usdExport.RenderObjSha256, repeatedUsdExport.RenderObjSha256, StringComparison.Ordinal),
    "The application OBJ export is not deterministic.");
Assert(
    usdExport.ManifestJson.Contains("\"topology\": \"welded boundary-constrained fairing and Loop render surface\"", StringComparison.Ordinal),
    "USD manifest did not declare the independent render topology.");
Assert(
    usdExport.ManifestJson.Contains("\"refinementAlgorithm\": \"boundary-constrained Taubin fairing and Loop subdivision\"", StringComparison.Ordinal),
    "USD manifest did not declare the render refinement algorithm.");
Assert(
    usdExport.ManifestJson.Contains("OpenUSD right-handed Z-up", StringComparison.Ordinal),
    "USD export did not declare its Unreal-to-OpenUSD coordinate conversion.");
Assert(
    usdExport.ManifestJson.Contains("\"reflectedAxis\": \"Y\"", StringComparison.Ordinal),
    "USD export did not record the Y reflection required for handedness conversion.");
Assert(!usdExport.Usd.Contains("NaN", StringComparison.OrdinalIgnoreCase), "USD export contains a non-finite value.");
Assert(
    string.Equals(usdExport.UsdSha256, repeatedUsdExport.UsdSha256, StringComparison.Ordinal),
    "USD export is not deterministic.");

GarmentDocument openWrapGarment = garment with
{
    Closures = garment.Closures
        .Select(closure => closure with { State = GarmentClosureStates.Open })
        .ToArray()
};
PatternaUnrealBridgeDocument openWrapBridge = BuildBridge(openWrapGarment);
string openWrapJson = JsonSerializer.Serialize(openWrapBridge, jsonOptions);
FullGarmentPreflightReport openWrapReport = FullGarmentPreflight.Run(
    openWrapBridge,
    bodyProfile,
    openWrapJson,
    bodyProfileJson);
Assert(!openWrapReport.IsAccepted, "An open wrap dress was accepted as a worn-state proof.");
Assert(
    openWrapReport.Issues.Any(issue => issue.Code == "wrap-closure-missing"),
    "The preflight did not identify the missing active wrap closure.");

GarmentDocument orphanTieGarment = garment with
{
    Seams = garment.Seams
        .Where(seam => !seam.Id.StartsWith("tie-", StringComparison.Ordinal))
        .ToArray()
};
PatternaUnrealBridgeDocument orphanTieBridge = BuildBridge(orphanTieGarment);
string orphanTieJson = JsonSerializer.Serialize(orphanTieBridge, jsonOptions);
FullGarmentPreflightReport orphanTieReport = FullGarmentPreflight.Run(
    orphanTieBridge,
    bodyProfile,
    orphanTieJson,
    bodyProfileJson);
Assert(!orphanTieReport.IsAccepted, "Unsewn waist ties were accepted.");
Assert(
    orphanTieReport.Issues.Count(issue => issue.Code == "unsewn-panel") == 2,
    "The preflight did not identify both unsewn waist ties.");

Console.WriteLine($"Panels: {accepted.Panels.Count}");
Console.WriteLine($"Seams: {accepted.Seams.Count}");
Console.WriteLine($"Body sections: {accepted.BodyProfile.SectionCount}");
Console.WriteLine($"Minimum contour intersections: {accepted.BodyProfile.MinimumIntersectionCount}");
Console.WriteLine($"Minimum angular surface points: {accepted.BodyProfile.MinimumSurfacePointCount}");
Console.WriteLine($"Maximum seam mismatch: {accepted.Seams.Max(seam => seam.LengthMismatchRatio):P1}");
Console.WriteLine($"Structured vertices: {structuredMeshes.Sum(mesh => mesh.Vertices.Count)}");
Console.WriteLine($"Structured triangles: {structuredMeshes.Sum(mesh => mesh.Triangles.Count)}");
Console.WriteLine($"Maximum structured aspect ratio: {structuredMeshes.Max(mesh => mesh.MaximumTriangleAspectRatio):F2}");
Console.WriteLine($"Arrangement stitches: {arrangement.Stitches.Count}");
foreach (ArrangedClosureConstraint closure in arrangement.Closures)
{
    Console.WriteLine(
        $"Closure {closure.ClosureId} ({closure.Kind}): {closure.InitialGapCm:F2} cm initial gap");
}
foreach (IGrouping<string, ArrangedSeamStitch> shoulder in arrangement.Stitches
    .Where(stitch => stitch.SeamId.StartsWith("shoulder-", StringComparison.Ordinal))
    .GroupBy(stitch => stitch.SeamId))
{
    ArrangedPanelMesh panelA = arrangement.Panels.Single(panel => panel.PanelId == shoulder.First().PanelA);
    ArrangedPanelMesh panelB = arrangement.Panels.Single(panel => panel.PanelId == shoulder.First().PanelB);
    ArrangedSeamStitch first = shoulder.OrderBy(stitch => stitch.NormalizedPosition).First();
    ArrangedSeamStitch last = shoulder.OrderBy(stitch => stitch.NormalizedPosition).Last();
    ArrangedPanelVertex firstA = panelA.Vertices[first.VertexA];
    ArrangedPanelVertex firstB = panelB.Vertices[first.VertexB];
    ArrangedPanelVertex lastA = panelA.Vertices[last.VertexA];
    ArrangedPanelVertex lastB = panelB.Vertices[last.VertexB];
    Console.WriteLine(
        $"{shoulder.Key} endpoints A ({firstA.X:F1},{firstA.Y:F1},{firstA.Z:F1}) to ({lastA.X:F1},{lastA.Y:F1},{lastA.Z:F1}); " +
        $"B ({firstB.X:F1},{firstB.Y:F1},{firstB.Z:F1}) to ({lastB.X:F1},{lastB.Y:F1},{lastB.Z:F1})");
}
foreach (ArrangedSeamDirectionReport direction in arrangement.SeamDirections)
{
    Console.WriteLine(
        $"Seam direction {direction.SeamId}: auto-reversed {direction.WasAutoReversed}, " +
        $"selected endpoints {direction.SelectedEndpointGapCm:F2} cm, opposite {direction.OppositeEndpointGapCm:F2} cm");
}
Console.WriteLine($"Minimum arranged triangle area: {arrangement.MinimumTriangleAreaCm2:F6} cm2");
Console.WriteLine($"Maximum initial seam gap: {arrangement.MaximumSeamGapCm:F6} cm");
Console.WriteLine($"Maximum initial closure gap: {arrangement.MaximumClosureGapCm:F6} cm");
Console.WriteLine($"Maximum arranged edge strain: {arrangement.MaximumEdgeStrainRatio:P1}");
Console.WriteLine($"95th percentile arranged edge strain: {arrangement.NinetyFifthPercentileEdgeStrainRatio:P1}");
Console.WriteLine($"Minimum measured torso clearance: {arrangement.MinimumTorsoClearanceCm:F3} cm");
Console.WriteLine($"USD SHA-256: {usdExport.UsdSha256}");
foreach (ArrangedPanelQualityReport quality in arrangement.PanelQuality)
{
    Console.WriteLine(
        $"Arrangement {quality.PanelId}: max strain {quality.MaximumEdgeStrainRatio:P1}, 95th {quality.NinetyFifthPercentileEdgeStrainRatio:P1}, min area {quality.MinimumTriangleAreaCm2:F6} cm2");
}
Console.WriteLine("Unsewn tie rejection: Passed");
Console.WriteLine("Open wrap rejection: Passed");
Console.WriteLine("Result: Passed");
