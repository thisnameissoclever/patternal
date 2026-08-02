namespace Patterna;

public sealed record PatternPointDocument(double X, double Y);

public sealed record GarmentCodeCurveSourceDocument(
    string? CurvatureJson,
    PatternPointDocument Start,
    PatternPointDocument End,
    PatternPointDocument? Control1,
    PatternPointDocument? Control2);

public sealed record PatternCurveDocument(
    string Id,
    string Kind,
    PatternPointDocument End,
    PatternPointDocument? Control1 = null,
    PatternPointDocument? Control2 = null)
{
    public string? Label { get; init; }

    public GarmentCodeCurveSourceDocument? GarmentCodeSource { get; init; }
}

public sealed record PatternLayoutDocument(
    double Left,
    double Top,
    double LabelX,
    double LabelY,
    bool ShowGrainline);

public static class PatternInternalPathKinds
{
    public const string Construction = "construction";
    public const string Stitch = "stitch";
    public const string Fold = "fold";
    public const string Cut = "cut";
    public const string Pleat = "pleat";

    public static readonly IReadOnlySet<string> Supported = new HashSet<string>(
        [Construction, Stitch, Fold, Cut, Pleat],
        StringComparer.OrdinalIgnoreCase);
}

public sealed record PatternInternalPathDocument(
    string Id,
    string Kind,
    PatternPointDocument Start,
    IReadOnlyList<PatternCurveDocument> Segments,
    bool Closed = false)
{
    public string? Label { get; init; }
}

public sealed record PatternNotchDocument(
    string Id,
    string BoundaryCurveId,
    double Parameter,
    double DepthCm,
    double WidthCm = 0,
    int Count = 1);

public sealed record PatternDartDocument(
    string Id,
    string Name,
    string FirstLegBoundaryCurveId,
    double FirstLegParameter,
    string SecondLegBoundaryCurveId,
    double SecondLegParameter,
    PatternPointDocument Apex,
    string FoldDirection = "center")
{
    public string ConstructionMode { get; init; } = PatternDartConstructionModes.Annotation;

    public bool Materialized { get; init; }
}

public static class PatternDartConstructionModes
{
    public const string Annotation = "annotation";
    public const string SewnFreeEdge = "sewn-free-edge";
    public const string SewnEdge = "sewn-edge";

    public static readonly IReadOnlySet<string> Supported = new HashSet<string>(
        [Annotation, SewnFreeEdge, SewnEdge],
        StringComparer.OrdinalIgnoreCase);
}

public sealed record PatternGrainlineDocument(
    PatternPointDocument Start,
    PatternPointDocument End,
    bool Locked = false);

public sealed record PatternPieceDocument(
    string Id,
    string Name,
    int CutQuantity,
    bool Mirrored,
    bool CutOnFold,
    double ScaleX,
    double ScaleY,
    double SeamAllowanceCm,
    PatternPointDocument Start,
    IReadOnlyList<PatternCurveDocument> Boundary,
    PatternLayoutDocument Layout)
{
    public IReadOnlyList<PatternInternalPathDocument> InternalPaths { get; init; } = [];

    public IReadOnlyList<PatternNotchDocument> Notches { get; init; } = [];

    public IReadOnlyList<PatternDartDocument> Darts { get; init; } = [];

    public PatternGrainlineDocument? Grainline { get; init; }
}

public sealed record PatternPlacement3DDocument(
    double X,
    double Y,
    double Z,
    double RotationXDegrees,
    double RotationYDegrees,
    double RotationZDegrees,
    string CoordinateSystem);

public sealed record ClothPanelDocument(
    string Id,
    string PieceId,
    string Name,
    string Placement,
    bool ReverseWinding,
    IReadOnlyList<string> PinnedEdges)
{
    public PatternPlacement3DDocument? SourcePlacement { get; init; }

    public PatternPointDocument? SourcePatternOrigin { get; init; }

    public string? SourceLabel { get; init; }
}

public sealed record GarmentSourceDocument(
    string Format,
    string SchemaVersion,
    string? SourcePath,
    string? Revision)
{
    public string? RawDocumentJson { get; init; }

    public string? StructuralSignature { get; init; }
}

public sealed record SeamSideDocument(
    string PanelId,
    IReadOnlyList<string> EdgeIds,
    bool Reverse = false);

public sealed record GarmentSeamDocument(
    string Id,
    string Name,
    SeamSideDocument SideA,
    SeamSideDocument SideB,
    double AllowanceCm,
    double Strength = 1.0);

public static class GarmentClosureKinds
{
    public const string Pin = "pin";
    public const string Tack = "tack";
    public const string Button = "button";
    public const string Zipper = "zipper";
    public const string Hook = "hook";
    public const string Buckle = "buckle";
    public const string TieKnot = "tie-knot";

    public static readonly IReadOnlySet<string> Supported = new HashSet<string>(
        [Pin, Tack, Button, Zipper, Hook, Buckle, TieKnot],
        StringComparer.OrdinalIgnoreCase);
}

public static class GarmentClosureStates
{
    public const string Open = "open";
    public const string Closed = "closed";

    public static readonly IReadOnlySet<string> Supported = new HashSet<string>(
        [Open, Closed],
        StringComparer.OrdinalIgnoreCase);
}

public sealed record GarmentClosureAnchorDocument(
    string PanelId,
    IReadOnlyList<string> EdgeIds,
    double StartPosition,
    double EndPosition,
    bool Reverse = false);

public sealed record GarmentClosureDocument(
    string Id,
    string Name,
    string Kind,
    string State,
    GarmentClosureAnchorDocument AnchorA,
    GarmentClosureAnchorDocument AnchorB,
    int ConstraintCount,
    double TargetDistanceCm = 0,
    double Strength = 1.0);

public sealed record FabricPhysicsDocument(
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

public sealed record GarmentEaseProfileDocument(
    double ChestEaseCm,
    double WaistEaseCm,
    double HipEaseCm,
    double UpperArmEaseCm)
{
    public double ArmscyeEaseCm { get; init; } = 2.5;
}

public sealed record GarmentBodyReferenceDocument(
    double ChestCm,
    double WaistCm,
    double HipCm,
    double ShoulderCm,
    double TorsoCm,
    double ArmLengthCm,
    double UpperArmCircumferenceCm,
    double ArmholeDepthCm,
    double ArmscyeCircumferenceCm);

public sealed record ShirtConstructionProfileDocument(
    double FrontWidthSharePercent,
    double NecklineWidthCm,
    double FrontNeckDepthCm,
    double BackNeckDepthCm,
    double ShoulderLengthCm,
    double ShoulderDropCm,
    double ArmscyeDepthCm,
    double SleeveCapHeightCm,
    double FrontBalanceCm)
{
    public double ArmscyeScoopCm { get; init; }

    public double UnderarmExtensionCm { get; init; }
}

public sealed record ShirtBustShapingProfileDocument(
    string Mode,
    double LeftDartIntakeCm,
    double RightDartIntakeCm,
    double BustPointSeparationCm,
    double LeftBustHeightCm,
    double RightBustHeightCm,
    double LeftBustProjectionCm,
    double RightBustProjectionCm,
    double DartTipOffsetCm,
    double DartMouthDropCm)
{
    public double ShoulderDartMouthOffsetCm { get; init; } = 5.0;

    public double ShoulderDartSharePercent { get; init; } = 35.0;
}

public static class ShirtBustShapingModes
{
    public const string None = "none";
    public const string SideDarts = "side-darts";
    public const string ShoulderDarts = "shoulder-darts";
    public const string DistributedDarts = "distributed-darts";

    public static readonly IReadOnlySet<string> Supported = new HashSet<string>(
        [None, SideDarts, ShoulderDarts, DistributedDarts],
        StringComparer.OrdinalIgnoreCase);
}

public sealed record GarmentDocument(
    string SchemaVersion,
    string Id,
    string Name,
    string Units,
    IReadOnlyList<PatternPieceDocument> Pieces,
    IReadOnlyList<ClothPanelDocument> Panels,
    IReadOnlyList<GarmentSeamDocument> Seams,
    FabricPhysicsDocument Fabric)
{
    public IReadOnlyList<GarmentClosureDocument> Closures { get; init; } = [];

    public GarmentSourceDocument? Source { get; init; }

    public GarmentEaseProfileDocument? EaseProfile { get; init; }

    public GarmentBodyReferenceDocument? BodyReference { get; init; }

    public ShirtConstructionProfileDocument? ShirtConstructionProfile { get; init; }

    public ShirtBustShapingProfileDocument? ShirtBustShapingProfile { get; init; }

    public IReadOnlyList<string> Validate()
    {
        List<string> errors = [];
        if (EaseProfile is not null)
        {
            double[] easeValues =
            [
                EaseProfile.ChestEaseCm,
                EaseProfile.WaistEaseCm,
                EaseProfile.HipEaseCm,
                EaseProfile.UpperArmEaseCm,
                EaseProfile.ArmscyeEaseCm
            ];
            if (easeValues.Any(value => !double.IsFinite(value) || value is < -20 or > 60))
            {
                errors.Add("Garment ease values must be finite and from -20 through 60 centimeters.");
            }
        }
        if (BodyReference is not null)
        {
            double[] referenceValues =
            [
                BodyReference.ChestCm,
                BodyReference.WaistCm,
                BodyReference.HipCm,
                BodyReference.ShoulderCm,
                BodyReference.TorsoCm,
                BodyReference.ArmLengthCm,
                BodyReference.UpperArmCircumferenceCm,
                BodyReference.ArmholeDepthCm,
                BodyReference.ArmscyeCircumferenceCm
            ];
            if (referenceValues.Any(value => !double.IsFinite(value) || value <= 0 || value > 300))
            {
                errors.Add("Garment source-body measurements must be finite and greater than zero through 300 centimeters.");
            }
        }
        if (ShirtConstructionProfile is not null)
        {
            ShirtConstructionProfileDocument profile = ShirtConstructionProfile;
            double[] dimensions =
            [
                profile.NecklineWidthCm,
                profile.FrontNeckDepthCm,
                profile.BackNeckDepthCm,
                profile.ShoulderLengthCm,
                profile.ShoulderDropCm,
                profile.ArmscyeDepthCm,
                profile.SleeveCapHeightCm
            ];
            if (!double.IsFinite(profile.FrontWidthSharePercent) ||
                profile.FrontWidthSharePercent is < 40 or > 65)
            {
                errors.Add("Shirt front width share must be finite and from 40 through 65 percent.");
            }
            if (dimensions.Any(value => !double.IsFinite(value) || value <= 0 || value > 50))
            {
                errors.Add("Shirt construction dimensions must be finite and greater than zero through 50 centimeters.");
            }
            if (!double.IsFinite(profile.FrontBalanceCm) || profile.FrontBalanceCm is < -8 or > 8)
            {
                errors.Add("Shirt front balance must be finite and from -8 through 8 centimeters.");
            }
            if (!double.IsFinite(profile.ArmscyeScoopCm) || profile.ArmscyeScoopCm is < -12 or > 20)
            {
                errors.Add("Shirt armscye scoop must be finite and from -12 through 20 centimeters.");
            }
            if (!double.IsFinite(profile.UnderarmExtensionCm) || profile.UnderarmExtensionCm is < 0 or > 3)
            {
                errors.Add("Shirt underarm extension must be finite and from 0 through 3 centimeters.");
            }
            if (profile.ShoulderDropCm >= profile.ShoulderLengthCm)
            {
                errors.Add("Shirt shoulder drop must be smaller than shoulder length.");
            }
        }
        if (ShirtBustShapingProfile is not null)
        {
            ShirtBustShapingProfileDocument profile = ShirtBustShapingProfile;
            if (!ShirtBustShapingModes.Supported.Contains(profile.Mode))
            {
                errors.Add($"Unsupported shirt bust-shaping mode: {profile.Mode}.");
            }
            double[] finiteValues =
            [
                profile.LeftDartIntakeCm,
                profile.RightDartIntakeCm,
                profile.BustPointSeparationCm,
                profile.LeftBustHeightCm,
                profile.RightBustHeightCm,
                profile.LeftBustProjectionCm,
                profile.RightBustProjectionCm,
                profile.DartTipOffsetCm,
                profile.DartMouthDropCm,
                profile.ShoulderDartMouthOffsetCm,
                profile.ShoulderDartSharePercent
            ];
            if (finiteValues.Any(value => !double.IsFinite(value)))
            {
                errors.Add("Shirt bust-shaping values must be finite.");
            }
            if (profile.LeftDartIntakeCm is < 0 or > 8 ||
                profile.RightDartIntakeCm is < 0 or > 8)
            {
                errors.Add("Shirt bust-dart intake must be from 0 through 8 centimeters per side.");
            }
            if (profile.BustPointSeparationCm is < 5 or > 50 ||
                profile.LeftBustHeightCm is < 5 or > 60 ||
                profile.RightBustHeightCm is < 5 or > 60 ||
                profile.LeftBustProjectionCm is < 0 or > 20 ||
                profile.RightBustProjectionCm is < 0 or > 20 ||
                profile.DartTipOffsetCm is < 0.5 or > 8 ||
                profile.DartMouthDropCm is < -10 or > 15 ||
                profile.ShoulderDartMouthOffsetCm is < 1 or > 12 ||
                profile.ShoulderDartSharePercent is < 0 or > 100)
            {
                errors.Add("Shirt bust-shaping measurements are outside supported drafting bounds.");
            }
            if (!string.Equals(profile.Mode, ShirtBustShapingModes.None, StringComparison.OrdinalIgnoreCase) &&
                profile.LeftDartIntakeCm <= 0 &&
                profile.RightDartIntakeCm <= 0)
            {
                errors.Add("Physical bust shaping requires positive intake on at least one side.");
            }
            if (string.Equals(profile.Mode, ShirtBustShapingModes.DistributedDarts, StringComparison.OrdinalIgnoreCase) &&
                profile.ShoulderDartSharePercent is <= 0 or >= 100)
            {
                errors.Add("Distributed bust shaping requires a shoulder share greater than 0 and less than 100 percent.");
            }
        }
        Dictionary<string, PatternPieceDocument> piecesById = new(StringComparer.OrdinalIgnoreCase);
        foreach (PatternPieceDocument piece in Pieces)
        {
            if (!piecesById.TryAdd(piece.Id, piece))
            {
                errors.Add($"Duplicate pattern piece id: {piece.Id}");
            }

            if (piece.Boundary.Count < 3)
            {
                errors.Add($"Pattern piece {piece.Id} has fewer than three boundary edges.");
            }

            if (piece.ScaleX <= 0 || piece.ScaleY <= 0)
            {
                errors.Add($"Pattern piece {piece.Id} has an invalid scale.");
            }

            if (piece.Boundary.Select(edge => edge.Id).Distinct(StringComparer.OrdinalIgnoreCase).Count() != piece.Boundary.Count)
            {
                errors.Add($"Pattern piece {piece.Id} contains duplicate edge ids.");
            }

            ValidateConstructionGeometry(piece, errors);
        }

        Dictionary<string, ClothPanelDocument> panelsById = new(StringComparer.OrdinalIgnoreCase);
        foreach (ClothPanelDocument panel in Panels)
        {
            if (!panelsById.TryAdd(panel.Id, panel))
            {
                errors.Add($"Duplicate cloth panel id: {panel.Id}");
            }

            if (!piecesById.TryGetValue(panel.PieceId, out PatternPieceDocument? piece))
            {
                errors.Add($"Cloth panel {panel.Id} references missing piece {panel.PieceId}.");
                continue;
            }

            HashSet<string> edgeIds = piece.Boundary.Select(edge => edge.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
            foreach (string pinnedEdge in panel.PinnedEdges.Where(edge => !edgeIds.Contains(edge)))
            {
                errors.Add($"Cloth panel {panel.Id} pins missing edge {pinnedEdge}.");
            }

            if (panel.SourcePlacement is not null &&
                (!double.IsFinite(panel.SourcePlacement.X) ||
                 !double.IsFinite(panel.SourcePlacement.Y) ||
                 !double.IsFinite(panel.SourcePlacement.Z) ||
                 !double.IsFinite(panel.SourcePlacement.RotationXDegrees) ||
                 !double.IsFinite(panel.SourcePlacement.RotationYDegrees) ||
                 !double.IsFinite(panel.SourcePlacement.RotationZDegrees)))
            {
                errors.Add($"Cloth panel {panel.Id} has a non-finite source placement.");
            }
            if (panel.SourcePatternOrigin is not null &&
                (!double.IsFinite(panel.SourcePatternOrigin.X) || !double.IsFinite(panel.SourcePatternOrigin.Y)))
            {
                errors.Add($"Cloth panel {panel.Id} has a non-finite source pattern origin.");
            }
        }

        foreach (GarmentSeamDocument seam in Seams)
        {
            ValidateSeamSide(seam, seam.SideA, "A", panelsById, piecesById, errors);
            ValidateSeamSide(seam, seam.SideB, "B", panelsById, piecesById, errors);
        }

        HashSet<string> closureIds = new(StringComparer.OrdinalIgnoreCase);
        foreach (GarmentClosureDocument closure in Closures)
        {
            if (!closureIds.Add(closure.Id))
            {
                errors.Add($"Duplicate garment closure id: {closure.Id}");
            }
            if (!GarmentClosureKinds.Supported.Contains(closure.Kind))
            {
                errors.Add($"Closure {closure.Id} uses unsupported kind {closure.Kind}.");
            }
            if (!GarmentClosureStates.Supported.Contains(closure.State))
            {
                errors.Add($"Closure {closure.Id} uses unsupported state {closure.State}.");
            }
            if (closure.ConstraintCount is < 1 or > 128)
            {
                errors.Add($"Closure {closure.Id} constraint count must be between 1 and 128.");
            }
            if (!double.IsFinite(closure.TargetDistanceCm) || closure.TargetDistanceCm < 0)
            {
                errors.Add($"Closure {closure.Id} target distance must be finite and nonnegative.");
            }
            if (!double.IsFinite(closure.Strength) || closure.Strength <= 0 || closure.Strength > 1)
            {
                errors.Add($"Closure {closure.Id} strength must be greater than zero and no more than one.");
            }
            ValidateClosureAnchor(closure, closure.AnchorA, "A", panelsById, piecesById, errors);
            ValidateClosureAnchor(closure, closure.AnchorB, "B", panelsById, piecesById, errors);
        }

        return errors;
    }

    private static void ValidateConstructionGeometry(
        PatternPieceDocument piece,
        ICollection<string> errors)
    {
        HashSet<string> boundaryIds = piece.Boundary
            .Select(edge => edge.Id)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (piece.Notches.Select(notch => notch.Id).Distinct(StringComparer.OrdinalIgnoreCase).Count() != piece.Notches.Count)
        {
            errors.Add($"Pattern piece {piece.Id} contains duplicate notch ids.");
        }
        foreach (PatternNotchDocument notch in piece.Notches)
        {
            if (!boundaryIds.Contains(notch.BoundaryCurveId))
            {
                errors.Add($"Pattern notch {piece.Id}/{notch.Id} references missing boundary curve {notch.BoundaryCurveId}.");
            }
            if (!double.IsFinite(notch.Parameter) || notch.Parameter is < 0 or > 1)
            {
                errors.Add($"Pattern notch {piece.Id}/{notch.Id} has an invalid boundary parameter.");
            }
            if (!double.IsFinite(notch.DepthCm) || notch.DepthCm <= 0 ||
                !double.IsFinite(notch.WidthCm) || notch.WidthCm < 0)
            {
                errors.Add($"Pattern notch {piece.Id}/{notch.Id} has invalid dimensions.");
            }
            if (notch.Count is < 1 or > 3)
            {
                errors.Add($"Pattern notch {piece.Id}/{notch.Id} count must be from one through three.");
            }
        }

        if (piece.Darts.Select(dart => dart.Id).Distinct(StringComparer.OrdinalIgnoreCase).Count() != piece.Darts.Count)
        {
            errors.Add($"Pattern piece {piece.Id} contains duplicate dart ids.");
        }
        foreach (PatternDartDocument dart in piece.Darts)
        {
            if (!boundaryIds.Contains(dart.FirstLegBoundaryCurveId) ||
                !boundaryIds.Contains(dart.SecondLegBoundaryCurveId))
            {
                errors.Add($"Pattern dart {piece.Id}/{dart.Id} references a missing boundary curve.");
            }
            if (!double.IsFinite(dart.FirstLegParameter) || dart.FirstLegParameter is < 0 or > 1 ||
                !double.IsFinite(dart.SecondLegParameter) || dart.SecondLegParameter is < 0 or > 1 ||
                !IsFinite(dart.Apex))
            {
                errors.Add($"Pattern dart {piece.Id}/{dart.Id} has invalid geometry.");
            }
            if (dart.FoldDirection is not "left" and not "right" and not "center")
            {
                errors.Add($"Pattern dart {piece.Id}/{dart.Id} has unsupported fold direction {dart.FoldDirection}.");
            }
            if (!PatternDartConstructionModes.Supported.Contains(dart.ConstructionMode))
            {
                errors.Add($"Pattern dart {piece.Id}/{dart.Id} has unsupported construction mode {dart.ConstructionMode}.");
            }
            if (dart.Materialized &&
                string.Equals(
                    dart.ConstructionMode,
                    PatternDartConstructionModes.Annotation,
                    StringComparison.OrdinalIgnoreCase))
            {
                errors.Add($"Pattern dart {piece.Id}/{dart.Id} is materialized without a sewn construction mode.");
            }
        }

        if (piece.InternalPaths.Select(path => path.Id).Distinct(StringComparer.OrdinalIgnoreCase).Count() != piece.InternalPaths.Count)
        {
            errors.Add($"Pattern piece {piece.Id} contains duplicate internal path ids.");
        }
        foreach (PatternInternalPathDocument path in piece.InternalPaths)
        {
            if (!PatternInternalPathKinds.Supported.Contains(path.Kind))
            {
                errors.Add($"Pattern internal path {piece.Id}/{path.Id} uses unsupported kind {path.Kind}.");
            }
            if (!IsFinite(path.Start) || path.Segments.Count == 0)
            {
                errors.Add($"Pattern internal path {piece.Id}/{path.Id} has incomplete geometry.");
                continue;
            }
            PatternPointDocument segmentStart = path.Start;
            foreach (PatternCurveDocument segment in path.Segments)
            {
                bool completeLine = string.Equals(segment.Kind, "line", StringComparison.OrdinalIgnoreCase) &&
                    segment.Control1 is null && segment.Control2 is null;
                bool completeCubic = string.Equals(segment.Kind, "cubic", StringComparison.OrdinalIgnoreCase) &&
                    segment.Control1 is not null && segment.Control2 is not null;
                if ((!completeLine && !completeCubic) ||
                    !IsFinite(segment.End) ||
                    segment.Control1 is not null && !IsFinite(segment.Control1) ||
                    segment.Control2 is not null && !IsFinite(segment.Control2))
                {
                    errors.Add($"Pattern internal path {piece.Id}/{path.Id} contains invalid segment {segment.Id}.");
                }
                else if (completeLine && PointsEqual(segmentStart, segment.End))
                {
                    errors.Add($"Pattern internal path {piece.Id}/{path.Id} contains zero-length segment {segment.Id}.");
                }
                segmentStart = segment.End;
            }
            if (path.Closed && !PointsEqual(path.Start, path.Segments[^1].End))
            {
                errors.Add($"Pattern internal path {piece.Id}/{path.Id} is marked closed but does not return to its start.");
            }
        }

        if (piece.Grainline is not null)
        {
            if (!IsFinite(piece.Grainline.Start) || !IsFinite(piece.Grainline.End) ||
                PointsEqual(piece.Grainline.Start, piece.Grainline.End))
            {
                errors.Add($"Pattern piece {piece.Id} has an invalid grainline.");
            }
        }
    }

    private static bool IsFinite(PatternPointDocument point)
        => double.IsFinite(point.X) && double.IsFinite(point.Y);

    private static bool PointsEqual(PatternPointDocument first, PatternPointDocument second)
        => Math.Abs(first.X - second.X) < 0.000001 && Math.Abs(first.Y - second.Y) < 0.000001;

    private static void ValidateClosureAnchor(
        GarmentClosureDocument closure,
        GarmentClosureAnchorDocument anchor,
        string anchorName,
        IReadOnlyDictionary<string, ClothPanelDocument> panelsById,
        IReadOnlyDictionary<string, PatternPieceDocument> piecesById,
        ICollection<string> errors)
    {
        if (!panelsById.TryGetValue(anchor.PanelId, out ClothPanelDocument? panel))
        {
            errors.Add($"Closure {closure.Id} anchor {anchorName} references missing panel {anchor.PanelId}.");
            return;
        }
        if (anchor.EdgeIds.Count == 0)
        {
            errors.Add($"Closure {closure.Id} anchor {anchorName} contains no edges.");
        }
        if (!piecesById.TryGetValue(panel.PieceId, out PatternPieceDocument? piece))
        {
            errors.Add($"Closure {closure.Id} anchor {anchorName} uses panel {panel.Id}, whose piece {panel.PieceId} is missing.");
            return;
        }
        HashSet<string> edgeIds = piece.Boundary.Select(edge => edge.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (string edgeId in anchor.EdgeIds.Where(edge => !edgeIds.Contains(edge)))
        {
            errors.Add($"Closure {closure.Id} anchor {anchorName} references missing edge {edgeId} on {panel.Id}.");
        }
        if (!double.IsFinite(anchor.StartPosition) ||
            !double.IsFinite(anchor.EndPosition) ||
            anchor.StartPosition is < 0 or > 1 ||
            anchor.EndPosition is < 0 or > 1)
        {
            errors.Add($"Closure {closure.Id} anchor {anchorName} positions must be finite values from zero through one.");
        }
    }

    private static void ValidateSeamSide(
        GarmentSeamDocument seam,
        SeamSideDocument side,
        string sideName,
        IReadOnlyDictionary<string, ClothPanelDocument> panelsById,
        IReadOnlyDictionary<string, PatternPieceDocument> piecesById,
        ICollection<string> errors)
    {
        if (!panelsById.TryGetValue(side.PanelId, out ClothPanelDocument? panel))
        {
            errors.Add($"Seam {seam.Id} side {sideName} references missing panel {side.PanelId}.");
            return;
        }

        if (!piecesById.TryGetValue(panel.PieceId, out PatternPieceDocument? piece))
        {
            errors.Add($"Seam {seam.Id} side {sideName} uses panel {panel.Id}, whose piece {panel.PieceId} is missing.");
            return;
        }
        HashSet<string> edgeIds = piece.Boundary.Select(edge => edge.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (string edgeId in side.EdgeIds.Where(edge => !edgeIds.Contains(edge)))
        {
            errors.Add($"Seam {seam.Id} side {sideName} references missing edge {edgeId} on {panel.Id}.");
        }
    }
}

public static class GarmentDocumentFactory
{
    private const double PatternPixelsPerCentimeter = 4.0;

    public static FabricPhysicsDocument CreateFabric(
        string fabricKey,
        double fabricWeight,
        double fabricStretch,
        double fabricBend,
        double fabricFriction)
    {
        string fabricName = fabricKey switch
        {
            "silk" => "Silk charmeuse",
            "linen" => "Linen twill",
            "wool" => "Wool crepe",
            _ => "Lightweight cotton jersey"
        };
        double thickness = fabricKey switch
        {
            "silk" => 0.18,
            "linen" => 0.42,
            "wool" => 0.72,
            _ => 0.50
        };

        return new FabricPhysicsDocument(
            fabricKey,
            fabricName,
            fabricWeight,
            thickness,
            Math.Max(0.1, fabricStretch * 0.55),
            Math.Max(0.1, fabricStretch),
            Math.Max(0.1, fabricStretch * 1.4),
            fabricBend,
            Math.Clamp(100 - fabricBend * 0.55, 5, 100),
            Math.Clamp(fabricFriction * 1.15, 0.05, 1.0),
            Math.Clamp(fabricFriction, 0.05, 1.0),
            fabricKey == "cotton" ? "style3d-lightweight-jersey-v1" : "prototype-unvalidated");
    }

    public static GarmentDocument CreateWrapDress(
        double height,
        double chest,
        double waist,
        double hip,
        double shoulder,
        double torso,
        string fabricKey,
        double fabricWeight,
        double fabricStretch,
        double fabricBend,
        double fabricFriction)
    {
        double chestScale = Math.Clamp(chest / 92.0, 0.78, 1.38);
        double waistScale = Math.Clamp(waist / 71.0, 0.78, 1.45);
        double hipScale = Math.Clamp(hip / 99.0, 0.78, 1.40);
        double bodiceLengthScale = Math.Clamp(torso / 42.0, 0.82, 1.22) * (45.0 / 42.0);
        double shoulderScale = Math.Clamp(shoulder / 39.0, 0.82, 1.28);
        double heightScale = Math.Clamp(height / 167.0, 0.88, 1.14);

        PatternPieceDocument bodiceFront = Piece(
            "bodice-front",
            "Wrap bodice front",
            2,
            true,
            false,
            chestScale,
            bodiceLengthScale,
            P(48, 0),
            [
                L("shoulder", 88, 8),
                C("armhole", 118, 16, 154, 44, 148, 72),
                C("side", 142, 104, 142, 140, 144, 156),
                L("tie-anchor", 144, 168),
                C("waist", 112, 174, 42, 174, 0, 168),
                L("center-front", 0, 80),
                C("neckline", 14, 52, 26, 18, 48, 0)
            ],
            new(70, 86, 38, 118, true));

        PatternPieceDocument bodiceBack = Piece(
            "bodice-back",
            "Bodice back",
            1,
            false,
            true,
            chestScale * shoulderScale,
            bodiceLengthScale,
            P(0, 8),
            [
                L("shoulder-left", 40, 0),
                C("neckline", 56, 10, 88, 10, 104, 0),
                L("shoulder-right", 144, 8),
                C("armhole-right", 168, 24, 184, 48, 176, 72),
                C("side-right", 164, 108, 160, 144, 160, 156),
                L("tie-anchor-right", 146, 168),
                L("waist", 0, 168),
                L("tie-anchor-left", -14, 156),
                C("side-left", -18, 126, -22, 92, -20, 72),
                C("armhole-left", -14, 44, -4, 20, 0, 8)
            ],
            new(326, 88, 40, 118, true));

        PatternPieceDocument skirt = Piece(
            "skirt",
            "Wrap skirt front",
            2,
            true,
            false,
            waistScale,
            heightScale,
            P(0, 0),
            [
                C("waist", 36, -4, 102, -4, 146, 0),
                C("side-outer", 154, 72, 190, 176, 216, 248),
                C("hem", 164, 260, 30, 260, -34, 248),
                L("wrap-edge", 0, 0)
            ],
            new(104, 425, 91, 92, true));

        PatternPieceDocument skirtBack = Piece(
            "skirt-back",
            "Skirt back",
            1,
            false,
            false,
            Math.Clamp((hipScale + waistScale) * 0.5, 0.78, 1.42),
            heightScale,
            P(0, 0),
            [
                C("waist", 34, -4, 104, -4, 146, 0),
                C("side-right", 158, 76, 174, 180, 184, 248),
                C("hem", 138, 260, 20, 260, -40, 248),
                L("side-left", 0, 0)
            ],
            new(402, 425, 70, 92, true));

        PatternPieceDocument tie = Piece(
            "waist-tie",
            "Waist tie",
            2,
            true,
            false,
            Math.Clamp((waistScale + hipScale) * 0.5, 0.78, 1.42),
            1,
            P(0, 0),
            [
                L("top", 80, 0),
                L("outer-end", 80, 12),
                L("bottom", 0, 12),
                L("inner-end", 0, 0)
            ],
            new(520, 512, 125, 8, false));

        PatternPieceDocument[] pieces = [bodiceFront, bodiceBack, skirt, skirtBack, tie];
        ClothPanelDocument[] panels =
        [
            new("bodice-left-wrap-panel", bodiceFront.Id, "Left wrap bodice", "torsoFrontWrapLeft", false, []),
            new("bodice-right-wrap-panel", bodiceFront.Id, "Right wrap bodice", "torsoFrontWrapRight", true, []),
            new("bodice-back-panel", bodiceBack.Id, bodiceBack.Name, "torsoBack", true, []),
            new("skirt-left-wrap-panel", skirt.Id, "Left wrap skirt", "skirtFrontWrapLeft", false, []),
            new("skirt-right-wrap-panel", skirt.Id, "Right wrap skirt", "skirtFrontWrapRight", true, []),
            new("skirt-back-panel", skirtBack.Id, skirtBack.Name, "skirtBack", true, []),
            new("tie-left-panel", tie.Id, "Waist tie left", "tieLeft", false, []),
            new("tie-right-panel", tie.Id, "Waist tie right", "tieRight", true, [])
        ];

        GarmentSeamDocument[] seams =
        [
            Seam("bodice-side-left", "Bodice left side", "bodice-left-wrap-panel", ["side", "tie-anchor"], "bodice-back-panel", ["tie-anchor-left", "side-left"], true),
            Seam("bodice-side-right", "Bodice right side", "bodice-right-wrap-panel", ["side", "tie-anchor"], "bodice-back-panel", ["side-right", "tie-anchor-right"], false),
            Seam("shoulder-left", "Left shoulder", "bodice-left-wrap-panel", ["shoulder"], "bodice-back-panel", ["shoulder-left"], true),
            Seam("shoulder-right", "Right shoulder", "bodice-right-wrap-panel", ["shoulder"], "bodice-back-panel", ["shoulder-right"], false),
            Seam("waist-left-wrap", "Left wrap waist", "bodice-left-wrap-panel", ["waist"], "skirt-left-wrap-panel", ["waist"], true),
            Seam("waist-right-wrap", "Right wrap waist", "bodice-right-wrap-panel", ["waist"], "skirt-right-wrap-panel", ["waist"], true),
            Seam("waist-back", "Back waist", "bodice-back-panel", ["waist"], "skirt-back-panel", ["waist"], true),
            Seam("skirt-side-left", "Skirt left side", "skirt-left-wrap-panel", ["side-outer"], "skirt-back-panel", ["side-left"], true),
            Seam("skirt-side-right", "Skirt right side", "skirt-right-wrap-panel", ["side-outer"], "skirt-back-panel", ["side-right"], false),
            Seam("tie-left-attachment", "Left waist tie attachment", "tie-left-panel", ["inner-end"], "bodice-left-wrap-panel", ["tie-anchor"], false),
            Seam("tie-right-attachment", "Right waist tie attachment", "tie-right-panel", ["inner-end"], "bodice-right-wrap-panel", ["tie-anchor"], true)
        ];

        GarmentClosureDocument[] closures =
        [
            Closure(
                "wrap-bodice-tack",
                "Wrap bodice overlap tack",
                GarmentClosureKinds.Tack,
                "bodice-left-wrap-panel",
                ["center-front"],
                0.34,
                "bodice-right-wrap-panel",
                ["center-front"],
                0.34),
            Closure(
                "wrap-skirt-waist-pin",
                "Wrap skirt waist pin",
                GarmentClosureKinds.Pin,
                "skirt-left-wrap-panel",
                ["wrap-edge"],
                0.98,
                "skirt-right-wrap-panel",
                ["wrap-edge"],
                0.98),
            Closure(
                "wrap-waist-buckle",
                "Waist tie buckle",
                GarmentClosureKinds.Buckle,
                "tie-left-panel",
                ["outer-end"],
                0.5,
                "tie-right-panel",
                ["outer-end"],
                0.5)
        ];

        FabricPhysicsDocument fabric = CreateFabric(
            fabricKey,
            fabricWeight,
            fabricStretch,
            fabricBend,
            fabricFriction);

        GarmentDocument document = new(
            "patterna.garment/1.1",
            "wrap-dress",
            "Body-specific wrap dress",
            "centimeters",
            pieces,
            panels,
            seams,
            fabric)
        {
            Closures = closures
        };

        IReadOnlyList<string> validationErrors = document.Validate();
        if (validationErrors.Count > 0)
        {
            throw new InvalidOperationException(string.Join(Environment.NewLine, validationErrors));
        }

        return document;
    }

    private static PatternPieceDocument Piece(
        string id,
        string name,
        int cutQuantity,
        bool mirrored,
        bool cutOnFold,
        double scaleX,
        double scaleY,
        PatternPointDocument start,
        IReadOnlyList<PatternCurveDocument> boundary,
        PatternLayoutDocument layout)
        => new(id, name, cutQuantity, mirrored, cutOnFold, scaleX, scaleY, 1.0, start, boundary, layout);

    private static PatternPointDocument P(double x, double y)
        => new(x / PatternPixelsPerCentimeter, y / PatternPixelsPerCentimeter);

    private static PatternCurveDocument L(string id, double x, double y)
        => new(id, "line", P(x, y));

    private static PatternCurveDocument C(
        string id,
        double control1X,
        double control1Y,
        double control2X,
        double control2Y,
        double endX,
        double endY)
        => new(id, "cubic", P(endX, endY), P(control1X, control1Y), P(control2X, control2Y));

    private static GarmentSeamDocument Seam(
        string id,
        string name,
        string panelA,
        IReadOnlyList<string> edgesA,
        string panelB,
        IReadOnlyList<string> edgesB,
        bool reverseB)
        => new(id, name, new(panelA, edgesA), new(panelB, edgesB, reverseB), 0.1);

    private static GarmentClosureDocument Closure(
        string id,
        string name,
        string kind,
        string panelA,
        IReadOnlyList<string> edgesA,
        double positionA,
        string panelB,
        IReadOnlyList<string> edgesB,
        double positionB)
        => new(
            id,
            name,
            kind,
            GarmentClosureStates.Closed,
            new GarmentClosureAnchorDocument(panelA, edgesA, positionA, positionA),
            new GarmentClosureAnchorDocument(panelB, edgesB, positionB, positionB),
            1);
}
