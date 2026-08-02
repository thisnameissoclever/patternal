namespace Patterna;

public sealed record ShirtBustShapingResult(
    GarmentDocument Document,
    IReadOnlyList<string> GeneratedDartIds,
    double GeneratedLeftIntakeCm,
    double GeneratedRightIntakeCm);

public static class AdaptiveShirtBustShaper
{
    public const string LeftDartId = "patterna-left-bust-dart";
    public const string RightDartId = "patterna-right-bust-dart";
    public const string LeftShoulderDartId = "patterna-left-shoulder-bust-dart";
    public const string RightShoulderDartId = "patterna-right-shoulder-bust-dart";
    private const int CurveSamples = 128;
    private const double GeometryEpsilon = 0.000001;
    private const double MaximumExternalLegMismatchRatio = 0.001;
    private const double MaximumDartMouthArcDriftCm = 5.0;
    private const double MaximumApexBalanceCorrectionCm = 2.0;

    public static ShirtBustShapingProfileDocument Estimate(
        double chestCm,
        double underBustCm,
        double bustPointSeparationCm,
        double leftBustHeightCm,
        double rightBustHeightCm,
        double leftBustProjectionCm,
        double rightBustProjectionCm)
    {
        double[] values =
        [
            chestCm,
            underBustCm,
            bustPointSeparationCm,
            leftBustHeightCm,
            rightBustHeightCm,
            leftBustProjectionCm,
            rightBustProjectionCm
        ];
        if (values.Any(value => !double.IsFinite(value)) ||
            chestCm <= 0 ||
            underBustCm <= 0 ||
            bustPointSeparationCm <= 0 ||
            leftBustHeightCm <= 0 ||
            rightBustHeightCm <= 0 ||
            leftBustProjectionCm < 0 ||
            rightBustProjectionCm < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(chestCm), "Bust-shaping measurements must be finite and physically valid.");
        }

        double circumferenceDifference = Math.Max(0, chestCm - underBustCm);
        double leftIntake = EstimateSideIntake(circumferenceDifference, leftBustProjectionCm);
        double rightIntake = EstimateSideIntake(circumferenceDifference, rightBustProjectionCm);
        return new ShirtBustShapingProfileDocument(
            ShirtBustShapingModes.SideDarts,
            leftIntake,
            rightIntake,
            bustPointSeparationCm,
            leftBustHeightCm,
            rightBustHeightCm,
            leftBustProjectionCm,
            rightBustProjectionCm,
            2.5,
            0.5);
    }

    public static ShirtBustShapingResult Apply(
        GarmentDocument document,
        ShirtBustShapingProfileDocument profile)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(profile);
        IReadOnlyList<string> profileErrors = (document with { ShirtBustShapingProfile = profile })
            .Validate()
            .Where(error => error.Contains("bust", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (profileErrors.Count > 0)
        {
            throw new InvalidOperationException(string.Join(Environment.NewLine, profileErrors));
        }

        GarmentDocument cleaned = RemoveGeneratedDarts(document);
        if (string.Equals(profile.Mode, ShirtBustShapingModes.None, StringComparison.OrdinalIgnoreCase))
        {
            return new ShirtBustShapingResult(
                cleaned with { ShirtBustShapingProfile = null },
                [],
                0,
                0);
        }
        cleaned = cleaned with { ShirtBustShapingProfile = profile };

        PatternPieceDocument frontPiece = cleaned.Pieces.SingleOrDefault(IsFrontTorsoPiece)
            ?? throw new InvalidOperationException("Side-dart bust shaping requires one identifiable front torso pattern piece.");
        ClothPanelDocument frontPanel = cleaned.Panels.SingleOrDefault(panel =>
            string.Equals(panel.PieceId, frontPiece.Id, StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidOperationException("Side-dart bust shaping requires one cloth panel for the front torso piece.");
        double minimumX = Math.Min(frontPiece.Start.X, frontPiece.Boundary.Min(curve => curve.End.X));
        double maximumX = Math.Max(frontPiece.Start.X, frontPiece.Boundary.Max(curve => curve.End.X));
        double maximumY = Math.Max(frontPiece.Start.Y, frontPiece.Boundary.Max(curve => curve.End.Y));
        double centerX = (minimumX + maximumX) * 0.5;
        double sideThreshold = (maximumX - minimumX) * 0.5 * 0.65;
        Dictionary<string, PatternCurveDocument> replacements = new(StringComparer.OrdinalIgnoreCase);
        List<PatternDartDocument> generatedDarts = [];
        bool shoulderOnly = string.Equals(
            profile.Mode,
            ShirtBustShapingModes.ShoulderDarts,
            StringComparison.OrdinalIgnoreCase);
        bool distributed = string.Equals(
            profile.Mode,
            ShirtBustShapingModes.DistributedDarts,
            StringComparison.OrdinalIgnoreCase);
        bool usesSideDarts = !shoulderOnly;
        bool usesShoulderDarts = shoulderOnly || distributed;
        MatchedSeamCandidate[] sideCandidates = usesSideDarts
            ? FindSideSeamCandidates(cleaned, frontPiece, frontPanel, centerX, sideThreshold).ToArray()
            : [];
        MatchedSeamCandidate[] shoulderCandidates = usesShoulderDarts
            ? FindShoulderSeamCandidates(cleaned, frontPiece, frontPanel, centerX, maximumY).ToArray()
            : [];
        if (usesSideDarts && sideCandidates.Length < 2)
        {
            throw new InvalidOperationException(
                "Side-dart bust shaping could not find both owned front-to-back side seam families.");
        }
        if (usesShoulderDarts && shoulderCandidates.Length < 2)
        {
            throw new InvalidOperationException(
                "Shoulder-dart bust shaping could not find both owned front-to-back shoulder seams.");
        }

        void AddDraft(DraftedDart drafted)
        {
            replacements[drafted.Curve.Id] = drafted.Curve;
            generatedDarts.Add(drafted.Dart);
        }

        void DraftForSide(
            int sideSign,
            double totalIntakeCm,
            double bustHeightCm,
            string sideDartId,
            string shoulderDartId,
            string sideName)
        {
            if (totalIntakeCm <= GeometryEpsilon)
            {
                return;
            }
            double shoulderShare = shoulderOnly
                ? 1
                : distributed
                    ? profile.ShoulderDartSharePercent / 100
                    : 0;
            double shoulderIntake = totalIntakeCm * shoulderShare;
            double sideIntake = totalIntakeCm - shoulderIntake;
            if (sideIntake > GeometryEpsilon)
            {
                AddDraft(DraftSide(
                    frontPiece,
                    sideCandidates,
                    sideSign,
                    sideIntake,
                    bustHeightCm,
                    profile.BustPointSeparationCm,
                    profile.DartTipOffsetCm,
                    profile.DartMouthDropCm,
                    maximumY,
                    centerX,
                    sideDartId,
                    $"{sideName} side bust dart"));
            }
            if (shoulderIntake > GeometryEpsilon)
            {
                AddDraft(DraftShoulder(
                    frontPiece,
                    shoulderCandidates,
                    sideSign,
                    shoulderIntake,
                    bustHeightCm,
                    profile.BustPointSeparationCm,
                    profile.DartTipOffsetCm,
                    profile.ShoulderDartMouthOffsetCm,
                    maximumY,
                    centerX,
                    shoulderDartId,
                    $"{sideName} shoulder bust dart"));
            }
        }

        DraftForSide(
            -1,
            profile.LeftDartIntakeCm,
            profile.LeftBustHeightCm,
            LeftDartId,
            LeftShoulderDartId,
            "Left");
        DraftForSide(
            1,
            profile.RightDartIntakeCm,
            profile.RightBustHeightCm,
            RightDartId,
            RightShoulderDartId,
            "Right");

        PatternPieceDocument shapedFront = frontPiece with
        {
            Boundary = frontPiece.Boundary.Select(curve =>
                replacements.TryGetValue(curve.Id, out PatternCurveDocument? replacement)
                    ? replacement
                    : curve).ToArray(),
            Darts = [.. frontPiece.Darts, .. generatedDarts]
        };
        GarmentDocument shaped = cleaned with
        {
            Pieces = cleaned.Pieces.Select(piece =>
                string.Equals(piece.Id, frontPiece.Id, StringComparison.OrdinalIgnoreCase)
                    ? shapedFront
                    : piece).ToArray()
        };
        IReadOnlyList<string> errors = shaped.Validate();
        if (errors.Count > 0)
        {
            throw new InvalidOperationException(string.Join(Environment.NewLine, errors));
        }
        return new ShirtBustShapingResult(
            shaped,
            generatedDarts.Select(dart => dart.Id).ToArray(),
            profile.LeftDartIntakeCm,
            profile.RightDartIntakeCm);
    }

    private static double EstimateSideIntake(double circumferenceDifference, double projectionCm)
        => Math.Clamp(circumferenceDifference * 0.08 + projectionCm * 0.25, 0, 5);

    private static GarmentDocument RemoveGeneratedDarts(GarmentDocument document)
        => document with
        {
            Pieces = document.Pieces.Select(piece => piece with
            {
                Darts = piece.Darts.Where(dart =>
                    !string.Equals(dart.Id, LeftDartId, StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(dart.Id, RightDartId, StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(dart.Id, LeftShoulderDartId, StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(dart.Id, RightShoulderDartId, StringComparison.OrdinalIgnoreCase)).ToArray()
            }).ToArray()
        };

    private static bool IsFrontTorsoPiece(PatternPieceDocument piece)
        => piece.Id.Contains("front-torso", StringComparison.OrdinalIgnoreCase) ||
            piece.Name.Contains("front torso", StringComparison.OrdinalIgnoreCase);

    private static IEnumerable<MatchedSeamCandidate> FindSideSeamCandidates(
        GarmentDocument document,
        PatternPieceDocument frontPiece,
        ClothPanelDocument frontPanel,
        double centerX,
        double sideThreshold)
        => FindFrontBackSeamCandidates(document, frontPiece, frontPanel, centerX)
            .Where(candidate =>
                Math.Abs(candidate.MidpointX - centerX) >= sideThreshold &&
                Math.Abs(candidate.DeltaY) >= Math.Abs(candidate.DeltaX) * 0.6);

    private static IEnumerable<MatchedSeamCandidate> FindShoulderSeamCandidates(
        GarmentDocument document,
        PatternPieceDocument frontPiece,
        ClothPanelDocument frontPanel,
        double centerX,
        double maximumY)
        => FindFrontBackSeamCandidates(document, frontPiece, frontPanel, centerX)
            .Where(candidate =>
                candidate.MidpointY >= maximumY - 8 &&
                Math.Abs(candidate.DeltaX) >= Math.Abs(candidate.DeltaY) * 2);

    private static IEnumerable<MatchedSeamCandidate> FindFrontBackSeamCandidates(
        GarmentDocument document,
        PatternPieceDocument frontPiece,
        ClothPanelDocument frontPanel,
        double centerX)
    {
        Dictionary<string, ClothPanelDocument> panels = document.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, PatternPieceDocument> pieces = document.Pieces
            .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
        foreach (GarmentSeamDocument seam in document.Seams)
        {
            SeamSideDocument? frontSide = null;
            SeamSideDocument? oppositeSide = null;
            if (string.Equals(seam.SideA.PanelId, frontPanel.Id, StringComparison.OrdinalIgnoreCase))
            {
                frontSide = seam.SideA;
                oppositeSide = seam.SideB;
            }
            else if (string.Equals(seam.SideB.PanelId, frontPanel.Id, StringComparison.OrdinalIgnoreCase))
            {
                frontSide = seam.SideB;
                oppositeSide = seam.SideA;
            }
            if (frontSide is null ||
                oppositeSide is null ||
                frontSide.EdgeIds.Count != 1 ||
                oppositeSide.EdgeIds.Count != 1 ||
                !panels.TryGetValue(oppositeSide.PanelId, out ClothPanelDocument? oppositePanel) ||
                !pieces.TryGetValue(oppositePanel.PieceId, out PatternPieceDocument? oppositePiece) ||
                !oppositePiece.Id.Contains("back-torso", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }
            string frontCurveId = frontSide.EdgeIds[0];
            PatternCurveDocument? frontCurve = frontPiece.Boundary.FirstOrDefault(curve =>
                string.Equals(curve.Id, frontCurveId, StringComparison.OrdinalIgnoreCase));
            PatternCurveDocument? oppositeCurve = oppositePiece.Boundary.FirstOrDefault(curve =>
                string.Equals(curve.Id, oppositeSide.EdgeIds[0], StringComparison.OrdinalIgnoreCase));
            if (frontCurve is null || oppositeCurve is null)
            {
                continue;
            }
            PatternPointDocument frontStart = CurveStart(frontPiece, frontCurveId);
            PatternPointDocument midpoint = Evaluate(frontStart, frontCurve, 0.5);
            yield return new MatchedSeamCandidate(
                seam,
                frontCurveId,
                oppositePiece,
                oppositeSide.EdgeIds[0],
                Math.Sign(midpoint.X - centerX),
                midpoint.X,
                midpoint.Y,
                frontCurve.End.X - frontStart.X,
                frontCurve.End.Y - frontStart.Y,
                Math.Min(frontStart.Y, frontCurve.End.Y),
                Math.Max(frontStart.Y, frontCurve.End.Y));
        }
    }

    private static DraftedDart DraftSide(
        PatternPieceDocument frontPiece,
        IReadOnlyList<MatchedSeamCandidate> candidates,
        int sideSign,
        double intakeCm,
        double bustHeightCm,
        double bustPointSeparationCm,
        double dartTipOffsetCm,
        double dartMouthDropCm,
        double maximumY,
        double centerX,
        string dartId,
        string dartName)
    {
        double bustY = maximumY - bustHeightCm;
        double mouthY = bustY - dartMouthDropCm;
        MatchedSeamCandidate candidate = candidates
            .Where(item => item.SideSign == sideSign)
            .OrderBy(item => DistanceToRange(mouthY, item.MinimumY, item.MaximumY))
            .ThenBy(item => Math.Abs(item.MidpointY - mouthY))
            .FirstOrDefault()
            ?? throw new InvalidOperationException($"Could not find the {(sideSign < 0 ? "left" : "right")} front side seam for bust shaping.");
        PatternCurveDocument sourceCurve = frontPiece.Boundary.Single(curve =>
            string.Equals(curve.Id, candidate.FrontCurveId, StringComparison.OrdinalIgnoreCase));
        PatternPointDocument sourceStart = CurveStart(frontPiece, sourceCurve.Id);
        PatternCurveDocument oppositeCurve = candidate.OppositePiece.Boundary.Single(curve =>
            string.Equals(curve.Id, candidate.OppositeCurveId, StringComparison.OrdinalIgnoreCase));
        PatternPointDocument oppositeStart = CurveStart(candidate.OppositePiece, oppositeCurve.Id);
        double oppositeLength = CurveLength(oppositeStart, oppositeCurve, 1);
        double targetLength = oppositeLength + intakeCm;
        PatternCurveDocument shapedCurve = CreateLengthenedCurve(
            sourceCurve,
            sourceStart,
            targetLength,
            sideSign,
            0);
        double centerParameter = ParameterClosestToY(sourceStart, shapedCurve, mouthY);
        double centerLength = CurveLength(sourceStart, shapedCurve, centerParameter);
        return CreateDraftedDart(
            shapedCurve,
            sourceStart,
            oppositeLength,
            intakeCm,
            centerLength,
            mouthY,
            sideSign,
            bustHeightCm,
            bustPointSeparationCm,
            dartTipOffsetCm,
            maximumY,
            centerX,
            dartId,
            dartName);
    }

    private static DraftedDart DraftShoulder(
        PatternPieceDocument frontPiece,
        IReadOnlyList<MatchedSeamCandidate> candidates,
        int sideSign,
        double intakeCm,
        double bustHeightCm,
        double bustPointSeparationCm,
        double dartTipOffsetCm,
        double mouthOffsetFromNeckCm,
        double maximumY,
        double centerX,
        string dartId,
        string dartName)
    {
        MatchedSeamCandidate candidate = candidates
            .Where(item => item.SideSign == sideSign)
            .OrderByDescending(item => item.MidpointY)
            .FirstOrDefault()
            ?? throw new InvalidOperationException($"Could not find the {(sideSign < 0 ? "left" : "right")} front shoulder seam for bust shaping.");
        PatternCurveDocument sourceCurve = frontPiece.Boundary.Single(curve =>
            string.Equals(curve.Id, candidate.FrontCurveId, StringComparison.OrdinalIgnoreCase));
        PatternPointDocument sourceStart = CurveStart(frontPiece, sourceCurve.Id);
        PatternCurveDocument oppositeCurve = candidate.OppositePiece.Boundary.Single(curve =>
            string.Equals(curve.Id, candidate.OppositeCurveId, StringComparison.OrdinalIgnoreCase));
        PatternPointDocument oppositeStart = CurveStart(candidate.OppositePiece, oppositeCurve.Id);
        double oppositeLength = CurveLength(oppositeStart, oppositeCurve, 1);
        PatternCurveDocument shapedCurve = CreateLengthenedCurve(
            sourceCurve,
            sourceStart,
            oppositeLength + intakeCm,
            0,
            1);
        double totalLength = CurveLength(sourceStart, shapedCurve, 1);
        bool neckAtStart = Math.Abs(sourceStart.X - centerX) < Math.Abs(shapedCurve.End.X - centerX);
        double centerLength = neckAtStart
            ? mouthOffsetFromNeckCm
            : totalLength - mouthOffsetFromNeckCm;
        return CreateDraftedDart(
            shapedCurve,
            sourceStart,
            oppositeLength,
            intakeCm,
            centerLength,
            null,
            sideSign,
            bustHeightCm,
            bustPointSeparationCm,
            dartTipOffsetCm,
            maximumY,
            centerX,
            dartId,
            dartName);
    }

    private static DraftedDart CreateDraftedDart(
        PatternCurveDocument shapedCurve,
        PatternPointDocument sourceStart,
        double oppositeLength,
        double intakeCm,
        double requestedCenterLength,
        double? requestedMouthY,
        int sideSign,
        double bustHeightCm,
        double bustPointSeparationCm,
        double dartTipOffsetCm,
        double maximumY,
        double centerX,
        string dartId,
        string dartName)
    {
        CurveArcLengthTable arcLengths = new(sourceStart, shapedCurve, 1024);
        double totalLength = arcLengths.TotalLength;
        double minimumMargin = Math.Min(oppositeLength * 0.2, 3);
        double minimumCenterLength = intakeCm * 0.5 + minimumMargin;
        double maximumCenterLength = totalLength - intakeCm * 0.5 - minimumMargin;
        double preferredCenterLength = Math.Clamp(
            requestedCenterLength,
            minimumCenterLength,
            maximumCenterLength);
        double minimumSearchCenter = Math.Max(
            minimumCenterLength,
            preferredCenterLength - MaximumDartMouthArcDriftCm);
        double maximumSearchCenter = Math.Min(
            maximumCenterLength,
            preferredCenterLength + MaximumDartMouthArcDriftCm);
        double bustY = maximumY - bustHeightCm;
        PatternPointDocument bustPoint = new(
            centerX + sideSign * bustPointSeparationCm * 0.5,
            bustY);
        MouthSolution MouthAt(double centerLength, double firstIntakeLength)
        {
            double secondIntakeLength = intakeCm - firstIntakeLength;
            double firstParameter = arcLengths.ParameterAtLength(
                centerLength - firstIntakeLength);
            double secondParameter = arcLengths.ParameterAtLength(
                centerLength + secondIntakeLength);
            PatternPointDocument firstMouth = Evaluate(sourceStart, shapedCurve, firstParameter);
            PatternPointDocument secondMouth = Evaluate(sourceStart, shapedCurve, secondParameter);
            PatternPointDocument midpoint = new(
                (firstMouth.X + secondMouth.X) * 0.5,
                (firstMouth.Y + secondMouth.Y) * 0.5);
            PatternPointDocument desiredApex = MoveToward(bustPoint, midpoint, dartTipOffsetCm);
            PatternPointDocument apex = ProjectToPerpendicularBisector(
                desiredApex,
                firstMouth,
                secondMouth);
            return new MouthSolution(
                centerLength,
                firstParameter,
                secondParameter,
                firstMouth,
                secondMouth,
                midpoint,
                desiredApex,
                apex,
                Distance(apex, desiredApex));
        }

        MouthSolution? best = null;
        double bestScore = double.PositiveInfinity;
        const int centerSamples = 64;
        const int balanceSamples = 256;
        for (int centerSample = 0; centerSample <= centerSamples; centerSample++)
        {
            double centerLength = minimumSearchCenter +
                (maximumSearchCenter - minimumSearchCenter) * centerSample / centerSamples;
            for (int balanceSample = 1; balanceSample < balanceSamples; balanceSample++)
            {
                double firstIntakeLength = intakeCm * balanceSample / balanceSamples;
                MouthSolution current = MouthAt(centerLength, firstIntakeLength);
                double mouthPlacementError = requestedMouthY.HasValue
                    ? Math.Abs(current.MouthMidpoint.Y - requestedMouthY.Value)
                    : 0;
                double score = current.ProjectionDisplacementCm +
                    Math.Abs(current.CenterLengthCm - preferredCenterLength) * 0.25 +
                    mouthPlacementError +
                    Math.Abs(firstIntakeLength - intakeCm * 0.5) * 0.001;
                if (score < bestScore)
                {
                    best = current;
                    bestScore = score;
                }
            }
        }
        MouthSolution solution = best
            ?? throw new InvalidOperationException($"Bust dart {dartId} could not place a valid mouth.");
        if (Math.Abs(solution.CenterLengthCm - preferredCenterLength) >
            MaximumDartMouthArcDriftCm + GeometryEpsilon)
        {
            throw new InvalidOperationException(
                $"Bust dart {dartId} moved its mouth too far from the measured placement.");
        }
        if (requestedMouthY.HasValue &&
            Math.Abs(solution.MouthMidpoint.Y - requestedMouthY.Value) > 4)
        {
            throw new InvalidOperationException(
                $"Bust dart {dartId} placed its mouth {Math.Abs(solution.MouthMidpoint.Y - requestedMouthY.Value):F2} cm away from the measured height.");
        }
        double maximumLegLength = Math.Max(
            Distance(solution.Apex, Evaluate(sourceStart, shapedCurve, solution.FirstParameter)),
            Distance(solution.Apex, Evaluate(sourceStart, shapedCurve, solution.SecondParameter)));
        double legLengthDifference =
            Distance(solution.Apex, Evaluate(sourceStart, shapedCurve, solution.FirstParameter)) -
            Distance(solution.Apex, Evaluate(sourceStart, shapedCurve, solution.SecondParameter));
        if (Math.Abs(legLengthDifference) /
            Math.Max(maximumLegLength, GeometryEpsilon) > MaximumExternalLegMismatchRatio)
        {
            throw new InvalidOperationException(
                $"Bust dart {dartId} cannot balance equal legs near its requested mouth position.");
        }
        if (solution.ProjectionDisplacementCm > MaximumApexBalanceCorrectionCm)
        {
            throw new InvalidOperationException(
                $"Bust dart {dartId} would move its apex {solution.ProjectionDisplacementCm:F2} cm away from the measured tip. " +
                $"Mouth ({solution.FirstMouth.X:F2}, {solution.FirstMouth.Y:F2}) to " +
                $"({solution.SecondMouth.X:F2}, {solution.SecondMouth.Y:F2}); " +
                $"desired apex ({solution.DesiredApex.X:F2}, {solution.DesiredApex.Y:F2}).");
        }
        return new DraftedDart(
            shapedCurve,
            new PatternDartDocument(
                dartId,
                dartName,
                shapedCurve.Id,
                solution.FirstParameter,
                shapedCurve.Id,
                solution.SecondParameter,
                solution.Apex,
                "center")
            {
                ConstructionMode = PatternDartConstructionModes.SewnEdge
            });
    }

    private static PatternCurveDocument CreateLengthenedCurve(
        PatternCurveDocument source,
        PatternPointDocument start,
        double targetLength,
        double preferredNormalX,
        double preferredNormalY)
    {
        double deltaX = source.End.X - start.X;
        double deltaY = source.End.Y - start.Y;
        double chordLength = Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
        if (targetLength < chordLength - 0.001)
        {
            throw new InvalidOperationException(
                $"Bust intake cannot fit on {source.Id}: requested seam length {targetLength:F3} cm is shorter than its {chordLength:F3} cm chord.");
        }
        double normalX = -deltaY / Math.Max(chordLength, GeometryEpsilon);
        double normalY = deltaX / Math.Max(chordLength, GeometryEpsilon);
        if (normalX * preferredNormalX + normalY * preferredNormalY < 0)
        {
            normalX = -normalX;
            normalY = -normalY;
        }
        PatternCurveDocument CurveAt(double bulge)
        {
            PatternPointDocument baseControl1 = source.Control1 ?? new PatternPointDocument(
                start.X + deltaX / 3,
                start.Y + deltaY / 3);
            PatternPointDocument baseControl2 = source.Control2 ?? new PatternPointDocument(
                start.X + 2 * deltaX / 3,
                start.Y + 2 * deltaY / 3);
            return new PatternCurveDocument(
                source.Id,
                "cubic",
                source.End,
                new PatternPointDocument(
                    baseControl1.X + normalX * bulge,
                    baseControl1.Y + normalY * bulge),
                new PatternPointDocument(
                    baseControl2.X + normalX * bulge,
                    baseControl2.Y + normalY * bulge))
            {
                Label = source.Label
            };
        }

        double lower = 0;
        double upper = 1;
        while (CurveLength(start, CurveAt(upper), 1) < targetLength && upper < 100)
        {
            upper *= 2;
        }
        if (CurveLength(start, CurveAt(upper), 1) < targetLength)
        {
            throw new InvalidOperationException($"Bust intake on {source.Id} exceeds the supported curve-spread range.");
        }
        for (int iteration = 0; iteration < 64; iteration++)
        {
            double middle = (lower + upper) * 0.5;
            if (CurveLength(start, CurveAt(middle), 1) < targetLength)
            {
                lower = middle;
            }
            else
            {
                upper = middle;
            }
        }
        return CurveAt((lower + upper) * 0.5);
    }

    private static double ParameterClosestToY(
        PatternPointDocument start,
        PatternCurveDocument curve,
        double targetY)
    {
        double parameter = 0;
        double bestDistance = double.PositiveInfinity;
        for (int sample = 0; sample <= 512; sample++)
        {
            double candidate = sample / 512.0;
            double distance = Math.Abs(Evaluate(start, curve, candidate).Y - targetY);
            if (distance < bestDistance)
            {
                bestDistance = distance;
                parameter = candidate;
            }
        }
        return parameter;
    }

    private static double CurveLength(
        PatternPointDocument start,
        PatternCurveDocument curve,
        double endParameter)
    {
        int samples = string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase)
            ? 1
            : CurveSamples;
        double clampedEnd = Math.Clamp(endParameter, 0, 1);
        PatternPointDocument previous = start;
        double length = 0;
        for (int sample = 1; sample <= samples; sample++)
        {
            PatternPointDocument current = Evaluate(
                start,
                curve,
                clampedEnd * sample / samples);
            length += Distance(previous, current);
            previous = current;
        }
        return length;
    }

    private static PatternPointDocument CurveStart(PatternPieceDocument piece, string curveId)
    {
        int index = piece.Boundary
            .Select((curve, curveIndex) => (curve, curveIndex))
            .Single(item => string.Equals(
                item.curve.Id,
                curveId,
                StringComparison.OrdinalIgnoreCase)).curveIndex;
        return index == 0 ? piece.Start : piece.Boundary[index - 1].End;
    }

    private static PatternPointDocument Evaluate(
        PatternPointDocument start,
        PatternCurveDocument curve,
        double parameter)
    {
        if (string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase))
        {
            return new PatternPointDocument(
                start.X + (curve.End.X - start.X) * parameter,
                start.Y + (curve.End.Y - start.Y) * parameter);
        }
        PatternPointDocument control1 = curve.Control1
            ?? throw new InvalidOperationException($"Cubic curve {curve.Id} is missing its first control point.");
        PatternPointDocument control2 = curve.Control2
            ?? throw new InvalidOperationException($"Cubic curve {curve.Id} is missing its second control point.");
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

    private static PatternPointDocument MoveToward(
        PatternPointDocument start,
        PatternPointDocument target,
        double distance)
    {
        double deltaX = target.X - start.X;
        double deltaY = target.Y - start.Y;
        double length = Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
        if (length <= GeometryEpsilon)
        {
            return start;
        }
        double scale = Math.Min(distance, length * 0.85) / length;
        return new PatternPointDocument(
            start.X + deltaX * scale,
            start.Y + deltaY * scale);
    }

    private static PatternPointDocument ProjectToPerpendicularBisector(
        PatternPointDocument desired,
        PatternPointDocument first,
        PatternPointDocument second)
    {
        PatternPointDocument midpoint = new(
            (first.X + second.X) * 0.5,
            (first.Y + second.Y) * 0.5);
        double mouthX = second.X - first.X;
        double mouthY = second.Y - first.Y;
        double mouthLength = Math.Sqrt(mouthX * mouthX + mouthY * mouthY);
        if (mouthLength <= GeometryEpsilon)
        {
            throw new InvalidOperationException("Bust dart mouth collapsed to a single point.");
        }
        double normalX = -mouthY / mouthLength;
        double normalY = mouthX / mouthLength;
        double projection =
            (desired.X - midpoint.X) * normalX +
            (desired.Y - midpoint.Y) * normalY;
        return new PatternPointDocument(
            midpoint.X + normalX * projection,
            midpoint.Y + normalY * projection);
    }

    private static double Distance(PatternPointDocument first, PatternPointDocument second)
    {
        double deltaX = second.X - first.X;
        double deltaY = second.Y - first.Y;
        return Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
    }

    private static double DistanceToRange(double value, double minimum, double maximum)
        => value < minimum
            ? minimum - value
            : value > maximum
                ? value - maximum
                : 0;

    private sealed record MatchedSeamCandidate(
        GarmentSeamDocument Seam,
        string FrontCurveId,
        PatternPieceDocument OppositePiece,
        string OppositeCurveId,
        int SideSign,
        double MidpointX,
        double MidpointY,
        double DeltaX,
        double DeltaY,
        double MinimumY,
        double MaximumY);

    private sealed record DraftedDart(
        PatternCurveDocument Curve,
        PatternDartDocument Dart);

    private sealed record MouthSolution(
        double CenterLengthCm,
        double FirstParameter,
        double SecondParameter,
        PatternPointDocument FirstMouth,
        PatternPointDocument SecondMouth,
        PatternPointDocument MouthMidpoint,
        PatternPointDocument DesiredApex,
        PatternPointDocument Apex,
        double ProjectionDisplacementCm);

    private sealed class CurveArcLengthTable
    {
        private readonly double[] cumulativeLengths;

        public CurveArcLengthTable(
            PatternPointDocument start,
            PatternCurveDocument curve,
            int samples)
        {
            cumulativeLengths = new double[samples + 1];
            PatternPointDocument previous = start;
            for (int sample = 1; sample <= samples; sample++)
            {
                PatternPointDocument current = Evaluate(
                    start,
                    curve,
                    sample / (double)samples);
                cumulativeLengths[sample] = cumulativeLengths[sample - 1] +
                    Distance(previous, current);
                previous = current;
            }
        }

        public double TotalLength => cumulativeLengths[^1];

        public double ParameterAtLength(double targetLength)
        {
            double clamped = Math.Clamp(targetLength, 0, TotalLength);
            int upperIndex = Array.BinarySearch(cumulativeLengths, clamped);
            if (upperIndex >= 0)
            {
                return upperIndex / (double)(cumulativeLengths.Length - 1);
            }
            upperIndex = ~upperIndex;
            if (upperIndex <= 0)
            {
                return 0;
            }
            if (upperIndex >= cumulativeLengths.Length)
            {
                return 1;
            }
            int lowerIndex = upperIndex - 1;
            double segmentLength = cumulativeLengths[upperIndex] - cumulativeLengths[lowerIndex];
            double fraction = segmentLength <= GeometryEpsilon
                ? 0
                : (clamped - cumulativeLengths[lowerIndex]) / segmentLength;
            return (lowerIndex + fraction) / (cumulativeLengths.Length - 1);
        }
    }
}
