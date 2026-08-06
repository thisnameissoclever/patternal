namespace Patterna;

public sealed record AdaptiveShirtGrade(
    double TorsoWidthScale,
    double TorsoLengthScale,
    double SleeveLengthScale,
    double SleeveGirthScale,
    double SourceChestGirthCm,
    double SourceWaistGirthCm,
    double SourceHipGirthCm,
    GarmentEaseProfileDocument EaseProfile);

public sealed record AdaptiveShirtSourceGirths(
    double ChestGirthCm,
    double WaistGirthCm,
    double HipGirthCm);

public static class AdaptiveShirtPatternGrader
{
    private const double LegacyChestRelativeHeight = 0.45;
    private const double BustDropBelowUnderarmFraction = 0.06;

    private static readonly GarmentBodyReferenceDocument LegacyBodyReference = new(
        92.0,
        71.0,
        99.0,
        39.0,
        42.0,
        57.3,
        29.4,
        20.7,
        42.0);
    private const double MaximumAttachmentLengthToChordRatio = 2.0;

    public static (GarmentDocument Document, AdaptiveShirtGrade Grade) Adapt(
        GarmentDocument source,
        double chestCm,
        double waistCm,
        double hipCm,
        double shoulderCm,
        double torsoCm,
        double armLengthCm,
        double upperArmCircumferenceCm)
        => Adapt(
            source,
            chestCm,
            waistCm,
            hipCm,
            shoulderCm,
            torsoCm,
            armLengthCm,
            upperArmCircumferenceCm,
            MeasureSourceEase(source),
            source.ShirtConstructionProfile);

    public static (GarmentDocument Document, AdaptiveShirtGrade Grade) Adapt(
        GarmentDocument source,
        double chestCm,
        double waistCm,
        double hipCm,
        double shoulderCm,
        double torsoCm,
        double armLengthCm,
        double upperArmCircumferenceCm,
        GarmentEaseProfileDocument easeProfile)
        => Adapt(
            source,
            chestCm,
            waistCm,
            hipCm,
            shoulderCm,
            torsoCm,
            armLengthCm,
            upperArmCircumferenceCm,
            easeProfile,
            source.ShirtConstructionProfile);

    public static (GarmentDocument Document, AdaptiveShirtGrade Grade) Adapt(
        GarmentDocument source,
        double chestCm,
        double waistCm,
        double hipCm,
        double shoulderCm,
        double torsoCm,
        double armLengthCm,
        double upperArmCircumferenceCm,
        double armholeDepthCm,
        double armscyeCircumferenceCm,
        GarmentEaseProfileDocument easeProfile,
        ShirtConstructionProfileDocument? constructionProfile,
        double? highHipCircumferenceCm = null)
    {
        GarmentBodyReferenceDocument bodyReference = new(
            chestCm,
            waistCm,
            hipCm,
            shoulderCm,
            torsoCm,
            armLengthCm,
            upperArmCircumferenceCm,
            armholeDepthCm,
            armscyeCircumferenceCm);
        (GarmentDocument graded, AdaptiveShirtGrade grade) = Adapt(
            source,
            chestCm,
            waistCm,
            hipCm,
            shoulderCm,
            torsoCm,
            armLengthCm,
            upperArmCircumferenceCm,
            easeProfile,
            constructionProfile: null,
            highHipCircumferenceCm);
        ShirtConstructionProfileDocument? effectiveConstruction = constructionProfile;
        if (effectiveConstruction is null && TryMeasureConstructionProfile(graded) is not null)
        {
            effectiveConstruction = FitArmscyeConstructionProfile(
                graded,
                armholeDepthCm,
                armscyeCircumferenceCm,
                easeProfile.ArmscyeEaseCm);
        }
        if (effectiveConstruction is null)
        {
            return (graded with
            {
                BodyReference = bodyReference,
                ShirtConstructionProfile = null
            }, grade);
        }
        (GarmentDocument constructed, _) = Adapt(
            source,
            chestCm,
            waistCm,
            hipCm,
            shoulderCm,
            torsoCm,
            armLengthCm,
            upperArmCircumferenceCm,
            easeProfile,
            effectiveConstruction,
            highHipCircumferenceCm);
        return (constructed with { BodyReference = bodyReference }, grade);
    }

    public static (GarmentDocument Document, AdaptiveShirtGrade Grade) Adapt(
        GarmentDocument source,
        double chestCm,
        double waistCm,
        double hipCm,
        double shoulderCm,
        double torsoCm,
        double armLengthCm,
        double upperArmCircumferenceCm,
        GarmentEaseProfileDocument easeProfile,
        ShirtConstructionProfileDocument? constructionProfile,
        double? highHipCircumferenceCm = null)
    {
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(easeProfile);
        double[] measurements =
        [
            chestCm,
            waistCm,
            hipCm,
            shoulderCm,
            torsoCm,
            armLengthCm,
            upperArmCircumferenceCm
        ];
        if (measurements.Any(value => !double.IsFinite(value) || value <= 0))
        {
            throw new ArgumentOutOfRangeException(nameof(chestCm), "Adaptive shirt measurements must be finite and positive.");
        }
        if (highHipCircumferenceCm is double highHip &&
            (!double.IsFinite(highHip) || highHip <= 0))
        {
            throw new ArgumentOutOfRangeException(
                nameof(highHipCircumferenceCm),
                "The optional high-hip circumference must be finite and positive.");
        }

        AdaptiveShirtSourceGirths sourceGeometry = MeasureGeometryGirths(source);
        GarmentBodyReferenceDocument sourceBody = SourceBodyReference(source);
        GarmentBodyReferenceDocument bodyReference = sourceBody with
        {
            ChestCm = chestCm,
            WaistCm = waistCm,
            HipCm = hipCm,
            ShoulderCm = shoulderCm,
            TorsoCm = torsoCm,
            ArmLengthCm = armLengthCm,
            UpperArmCircumferenceCm = upperArmCircumferenceCm
        };
        double sourceChestGirth = sourceGeometry.ChestGirthCm;
        double sourceWaistGirth = sourceGeometry.WaistGirthCm;
        double sourceHipGirth = sourceGeometry.HipGirthCm;
        double highHipProgress = Math.Abs(hipCm - waistCm) < 0.0001
            ? 0.5
            : Math.Clamp(
                ((highHipCircumferenceCm ?? hipCm) - waistCm) / (hipCm - waistCm),
                0,
                1);
        double highHipEase = easeProfile.WaistEaseCm +
            (easeProfile.HipEaseCm - easeProfile.WaistEaseCm) * highHipProgress;
        double explicitHemGirth = (highHipCircumferenceCm ?? hipCm) + highHipEase;
        double chestScale = ClampScale((chestCm + easeProfile.ChestEaseCm) / sourceChestGirth);
        double waistScale = ClampScale((waistCm + easeProfile.WaistEaseCm) / sourceWaistGirth);
        double hipScale = ClampScale(explicitHemGirth / sourceHipGirth);
        double shoulderScale = ClampScale(shoulderCm / sourceBody.ShoulderCm);
        double torsoWidthScale = 0.5 * chestScale + 0.2 * waistScale + 0.3 * hipScale;
        double torsoLengthScale = ClampScale(torsoCm / sourceBody.TorsoCm);
        double sleeveLengthScale = ClampScale(armLengthCm / sourceBody.ArmLengthCm);
        double sourceSleeveOpeningCircumference = MeasureSleeveOpeningCircumference(source);
        double sleeveGirthScale = ClampScale(
            (upperArmCircumferenceCm + easeProfile.UpperArmEaseCm) /
            sourceSleeveOpeningCircumference);
        AdaptiveShirtGrade grade = new(
            torsoWidthScale,
            torsoLengthScale,
            sleeveLengthScale,
            sleeveGirthScale,
            sourceChestGirth,
            sourceWaistGirth,
            sourceHipGirth,
            easeProfile);
        ShirtConstructionProfileDocument? sourceConstructionProfile =
            constructionProfile is null ? null : TryMeasureConstructionProfile(source);
        bool constructionUnchanged = constructionProfile is null ||
            sourceConstructionProfile is not null &&
            ShirtConstructionPatternDrafter.AreEquivalent(
                constructionProfile,
                sourceConstructionProfile);
        if (new[]
            {
                chestScale,
                waistScale,
                hipScale,
                shoulderScale,
                torsoLengthScale,
                sleeveLengthScale,
                sleeveGirthScale
            }.All(scale => Math.Abs(scale - 1) < 0.0000001) && constructionUnchanged)
        {
            return (source with
            {
                BodyReference = bodyReference,
                EaseProfile = easeProfile,
                ShirtConstructionProfile = constructionProfile
            }, grade);
        }

        bool supportsMeasurementConstrainedGrade =
            source.Validate().Count == 0 &&
            source.Pieces.Count(piece => piece.Id.Contains("torso", StringComparison.OrdinalIgnoreCase)) >= 2;
        GarmentDocument gradingSource = source;
        IReadOnlyDictionary<string, SleeveGradeGeometry> sleeveGradeGeometry =
            supportsMeasurementConstrainedGrade
                ? MeasureSleeveGradeGeometry(gradingSource)
                : new Dictionary<string, SleeveGradeGeometry>(StringComparer.OrdinalIgnoreCase);
        IReadOnlyDictionary<string, IReadOnlySet<string>> splitTorsoSideCurves =
            MeasureSplitTorsoSideCurves(gradingSource);
        double chestRelativeHeight = MeasureChestLineRelativeHeight(gradingSource);

        PatternPieceDocument[] pieces = gradingSource.Pieces
            .Select(piece =>
            {
                bool isSleeve = piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase);
                if (isSleeve)
                {
                    return sleeveGradeGeometry.TryGetValue(piece.Id, out SleeveGradeGeometry? geometry)
                        ? ReshapeSleevePiece(
                            piece,
                            sleeveLengthScale,
                            sleeveGirthScale,
                            geometry)
                        : piece with
                        {
                            ScaleX = piece.ScaleX * sleeveLengthScale,
                            ScaleY = piece.ScaleY * sleeveGirthScale
                        };
                }
                if (!IsTorsoPiece(piece))
                {
                    return piece;
                }
                return ReshapeTorsoPiece(
                    piece,
                    hipScale,
                    waistScale,
                    chestScale,
                    shoulderScale,
                    torsoLengthScale,
                    chestRelativeHeight,
                    splitTorsoSideCurves.GetValueOrDefault(piece.Id));
            })
            .ToArray();
        bool usesSplitTorsoBlock = gradingSource.Pieces.Count(IsTorsoPiece) >= 4;
        double targetChestGirth = chestCm + easeProfile.ChestEaseCm;
        double targetWaistGirth = waistCm + easeProfile.WaistEaseCm;
        double targetHipGirth = highHipCircumferenceCm is not null
            ? explicitHemGirth
            : usesSplitTorsoBlock
            ? MeasureSplitShirtHemTarget(
                gradingSource,
                waistCm,
                hipCm,
                torsoCm,
                torsoLengthScale,
                easeProfile)
            : hipCm + easeProfile.HipEaseCm;
        int couplingPasses = supportsMeasurementConstrainedGrade ? 12 : 1;
        for (int couplingPass = 0; couplingPass < couplingPasses; couplingPass++)
        {
            for (int calibrationPass = 0;
                calibrationPass < (supportsMeasurementConstrainedGrade ? 8 : 0);
                calibrationPass++)
            {
                AdaptiveShirtSourceGirths measured = MeasureGeometryGirths(gradingSource with { Pieces = pieces });
                double[] error =
                [
                    targetHipGirth - measured.HipGirthCm,
                    targetWaistGirth - measured.WaistGirthCm,
                    targetChestGirth - measured.ChestGirthCm
                ];
                if (error.Max(Math.Abs) < 0.05)
                {
                    break;
                }
                const double probe = 0.01;
                double[,] jacobian = new double[3, 3];
                for (int control = 0; control < 3; control++)
                {
                    double[] factors = [1, 1, 1];
                    factors[control] += probe;
                    PatternPieceDocument[] perturbedPieces = ApplyTorsoCorrections(
                        pieces,
                        factors[0],
                        factors[1],
                        factors[2],
                        chestRelativeHeight);
                    AdaptiveShirtSourceGirths perturbed = MeasureGeometryGirths(gradingSource with { Pieces = perturbedPieces });
                    jacobian[0, control] = (perturbed.HipGirthCm - measured.HipGirthCm) / probe;
                    jacobian[1, control] = (perturbed.WaistGirthCm - measured.WaistGirthCm) / probe;
                    jacobian[2, control] = (perturbed.ChestGirthCm - measured.ChestGirthCm) / probe;
                }
                double[] step = SolveRegularizedLeastSquares(jacobian, error);
                double bestErrorSquared = error.Sum(value => value * value);
                PatternPieceDocument[] bestPieces = pieces;
                for (int lineSearch = 0; lineSearch < 8; lineSearch++)
                {
                    double fraction = Math.Pow(0.5, lineSearch);
                    PatternPieceDocument[] candidate = ApplyTorsoCorrections(
                        pieces,
                        1 + Math.Clamp(step[0] * fraction, -0.35, 0.35),
                        1 + Math.Clamp(step[1] * fraction, -0.35, 0.35),
                        1 + Math.Clamp(step[2] * fraction, -0.35, 0.35),
                        chestRelativeHeight);
                    AdaptiveShirtSourceGirths candidateGirths =
                        MeasureGeometryGirths(gradingSource with { Pieces = candidate });
                    double candidateErrorSquared =
                        Math.Pow(targetHipGirth - candidateGirths.HipGirthCm, 2) +
                        Math.Pow(targetWaistGirth - candidateGirths.WaistGirthCm, 2) +
                        Math.Pow(targetChestGirth - candidateGirths.ChestGirthCm, 2);
                    if (candidateErrorSquared < bestErrorSquared)
                    {
                        bestErrorSquared = candidateErrorSquared;
                        bestPieces = candidate;
                    }
                }
                if (ReferenceEquals(bestPieces, pieces))
                {
                    break;
                }
                pieces = bestPieces;
            }
            pieces = RegularizeFrontNeckline(pieces);
            pieces = MatchConstructionSeamLengths(gradingSource, pieces);
        }
        if (constructionProfile is not null)
        {
            GarmentDocument constructed = ApplyConstructionProfile(
                gradingSource with { Pieces = pieces },
                constructionProfile);
            pieces = constructed.Pieces.ToArray();
        }
        if (supportsMeasurementConstrainedGrade)
        {
            for (int finalCalibrationPass = 0; finalCalibrationPass < 6; finalCalibrationPass++)
            {
                AdaptiveShirtSourceGirths measured = MeasureGeometryGirths(
                    gradingSource with { Pieces = pieces });
                double maximumError = new[]
                {
                    targetHipGirth - measured.HipGirthCm,
                    targetWaistGirth - measured.WaistGirthCm,
                    targetChestGirth - measured.ChestGirthCm
                }.Max(Math.Abs);
                if (maximumError < 0.05)
                {
                    break;
                }
                pieces = ApplyTorsoCorrections(
                    pieces,
                    Math.Clamp(targetHipGirth / measured.HipGirthCm, 0.95, 1.05),
                    Math.Clamp(targetWaistGirth / measured.WaistGirthCm, 0.95, 1.05),
                    Math.Clamp(targetChestGirth / measured.ChestGirthCm, 0.95, 1.05),
                    chestRelativeHeight);
            }
        }
        GarmentDocument graded = gradingSource with
        {
            BodyReference = bodyReference,
            Pieces = pieces,
            EaseProfile = easeProfile,
            ShirtConstructionProfile = constructionProfile
        };
        return (graded, grade);
    }

    public static GarmentDocument ApplyConstructionProfile(
        GarmentDocument document,
        ShirtConstructionProfileDocument constructionProfile)
    {
        GarmentDocument drafted = ShirtConstructionPatternDrafter.Apply(document, constructionProfile);
        PatternPieceDocument[] pieces = drafted.Pieces.ToArray();
        for (int pass = 0; pass < 3; pass++)
        {
            pieces = MatchConstructionSeamLengths(
                drafted,
                pieces,
                preserveTorsoConstruction: true);
        }
        return drafted with { Pieces = pieces };
    }

    public static ShirtConstructionProfileDocument FitArmscyeConstructionProfile(
        GarmentDocument source,
        double armholeDepthCm,
        double armscyeCircumferenceCm,
        double armscyeEaseCm)
    {
        ArgumentNullException.ThrowIfNull(source);
        double[] measurements = [armholeDepthCm, armscyeCircumferenceCm, armscyeEaseCm];
        if (measurements.Any(value => !double.IsFinite(value)) ||
            armholeDepthCm <= 0 ||
            armscyeCircumferenceCm <= 0 ||
            armscyeEaseCm < 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(armholeDepthCm),
                "Armhole depth, armscye circumference, and armscye ease must be finite; body measurements must be positive and ease cannot be negative.");
        }

        ShirtConstructionProfileDocument sourceProfile =
            TryMeasureConstructionProfile(source) ??
            throw new InvalidOperationException("The adaptive shirt has no measurable construction profile.");
        double targetCircumference = armscyeCircumferenceCm + armscyeEaseCm;
        double targetPatternDepth = Math.Clamp(
            sourceProfile.ArmscyeDepthCm * armholeDepthCm / SourceBodyReference(source).ArmholeDepthCm,
            10,
            35);

        GarmentDocument Candidate(double scoop)
            => ShirtConstructionPatternDrafter.Apply(
                source,
                sourceProfile with
                {
                    ArmscyeDepthCm = targetPatternDepth,
                    ArmscyeScoopCm = scoop
                });

        const double minimumScoop = -12;
        const double maximumScoop = 20;
        const double coarseStep = 0.5;
        double bestScoop = sourceProfile.ArmscyeScoopCm;
        double bestError = double.PositiveInfinity;
        for (double scoop = minimumScoop; scoop <= maximumScoop + 0.001; scoop += coarseStep)
        {
            double error = Math.Abs(MeasureArmscyeCircumference(Candidate(scoop)) - targetCircumference);
            if (error < bestError)
            {
                bestError = error;
                bestScoop = scoop;
            }
        }

        double low = Math.Max(minimumScoop, bestScoop - coarseStep);
        double high = Math.Min(maximumScoop, bestScoop + coarseStep);
        for (int iteration = 0; iteration < 36; iteration++)
        {
            double left = low + (high - low) / 3;
            double right = high - (high - low) / 3;
            double leftError = Math.Abs(MeasureArmscyeCircumference(Candidate(left)) - targetCircumference);
            double rightError = Math.Abs(MeasureArmscyeCircumference(Candidate(right)) - targetCircumference);
            if (leftError <= rightError)
            {
                high = right;
                if (leftError < bestError)
                {
                    bestError = leftError;
                    bestScoop = left;
                }
            }
            else
            {
                low = left;
                if (rightError < bestError)
                {
                    bestError = rightError;
                    bestScoop = right;
                }
            }
        }
        if (bestError > 0.1)
        {
            throw new InvalidOperationException(
                $"The requested {targetCircumference:F2} cm armscye cannot be drafted at the measured {armholeDepthCm:F2} cm armhole depth; the closest supported result differs by {bestError:F2} cm.");
        }
        return sourceProfile with
        {
            ArmscyeDepthCm = targetPatternDepth,
            ArmscyeScoopCm = bestScoop
        };
    }

    public static double MeasureArmscyeCircumference(GarmentDocument source)
    {
        ArgumentNullException.ThrowIfNull(source);
        Dictionary<string, ClothPanelDocument> panelsById = source.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, PatternPieceDocument> piecesById = source.Pieces
            .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, double> circumferenceBySide = new(StringComparer.OrdinalIgnoreCase);
        foreach (GarmentSeamDocument seam in source.Seams)
        {
            Accumulate(seam.SideA, seam.SideB);
            Accumulate(seam.SideB, seam.SideA);
        }
        double[] measurements = circumferenceBySide.Values
            .Where(value => double.IsFinite(value) && value > 0)
            .ToArray();
        if (measurements.Length == 0)
        {
            throw new InvalidOperationException("The adaptive shirt has no measurable torso-to-sleeve armscye seams.");
        }
        return measurements.Average();

        void Accumulate(SeamSideDocument torsoSide, SeamSideDocument sleeveSide)
        {
            if (!panelsById.TryGetValue(torsoSide.PanelId, out ClothPanelDocument? torsoPanel) ||
                !panelsById.TryGetValue(sleeveSide.PanelId, out ClothPanelDocument? sleevePanel) ||
                !piecesById.TryGetValue(torsoPanel.PieceId, out PatternPieceDocument? torsoPiece) ||
                !piecesById.TryGetValue(sleevePanel.PieceId, out PatternPieceDocument? sleevePiece) ||
                !IsTorsoPiece(torsoPiece) ||
                !IsSleevePiece(sleevePiece))
            {
                return;
            }
            string side = sleevePiece.Id.Contains("left", StringComparison.OrdinalIgnoreCase)
                ? "left"
                : sleevePiece.Id.Contains("right", StringComparison.OrdinalIgnoreCase)
                    ? "right"
                    : "center";
            double length = torsoSide.EdgeIds.Sum(edgeId => ScaledCurveLength(torsoPiece, edgeId));
            circumferenceBySide[side] = circumferenceBySide.GetValueOrDefault(side) + length;
        }
    }

    private static ShirtConstructionProfileDocument? TryMeasureConstructionProfile(
        GarmentDocument source)
    {
        try
        {
            return source.ShirtConstructionProfile ?? ShirtConstructionPatternDrafter.Measure(source);
        }
        catch (InvalidOperationException)
        {
            return null;
        }
    }

    public static GarmentEaseProfileDocument MeasureSourceEase(GarmentDocument source)
    {
        ArgumentNullException.ThrowIfNull(source);
        if (source.EaseProfile is not null)
        {
            return source.EaseProfile;
        }
        AdaptiveShirtSourceGirths girths = MeasureSourceGirths(source);
        return new GarmentEaseProfileDocument(
            girths.ChestGirthCm - SourceBodyReference(source).ChestCm,
            girths.WaistGirthCm - SourceBodyReference(source).WaistCm,
            girths.HipGirthCm - SourceBodyReference(source).HipCm,
            5.0);
    }

    public static AdaptiveShirtSourceGirths MeasureSourceGirths(GarmentDocument source)
    {
        ArgumentNullException.ThrowIfNull(source);
        GarmentBodyReferenceDocument sourceBody = SourceBodyReference(source);
        return source.EaseProfile is null
            ? MeasureGeometryGirths(source)
            : new AdaptiveShirtSourceGirths(
                sourceBody.ChestCm + source.EaseProfile.ChestEaseCm,
                sourceBody.WaistCm + source.EaseProfile.WaistEaseCm,
                sourceBody.HipCm + source.EaseProfile.HipEaseCm);
    }

    public static AdaptiveShirtSourceGirths MeasureGeometryGirths(GarmentDocument source)
    {
        ArgumentNullException.ThrowIfNull(source);
        PatternPieceDocument[] torsoPieces = source.Pieces
            .Where(piece => !piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
                !piece.Id.Contains("collar", StringComparison.OrdinalIgnoreCase) &&
                !piece.Id.Contains("cuff", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (torsoPieces.Length == 0)
        {
            throw new InvalidOperationException("Adaptive shirt source contains no torso pieces.");
        }
        double hipGirth = MeasureTorsoGirthAtRelativeHeight(torsoPieces, 0.08);
        double waistGirth = MeasureTorsoGirthAtRelativeHeight(torsoPieces, 0.28);
        double chestGirth = MeasureTorsoGirthAtRelativeHeight(
            torsoPieces,
            MeasureChestLineRelativeHeight(source));
        return new AdaptiveShirtSourceGirths(chestGirth, waistGirth, hipGirth);
    }

    public static double MeasureChestLineRelativeHeight(GarmentDocument source)
    {
        ArgumentNullException.ThrowIfNull(source);
        Dictionary<string, ClothPanelDocument> panelsById = source.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, PatternPieceDocument> piecesById = source.Pieces
            .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, HashSet<string>> armholeCurveIds =
            new(StringComparer.OrdinalIgnoreCase);

        foreach (GarmentSeamDocument seam in source.Seams)
        {
            Accumulate(seam.SideA, seam.SideB);
            Accumulate(seam.SideB, seam.SideA);
        }

        List<double> underarmHeights = [];
        foreach (PatternPieceDocument piece in source.Pieces.Where(IsTorsoPiece))
        {
            HashSet<string> selectedCurveIds = armholeCurveIds.GetValueOrDefault(piece.Id) ?? [];
            (PatternPointDocument Start, PatternCurveDocument Curve)[] selectedEdges = piece.Boundary
                .Select((curve, index) =>
                {
                    PatternPointDocument start = index == 0
                        ? piece.Start
                        : piece.Boundary[index - 1].End;
                    return (Start: start, Curve: curve);
                })
                .Where(edge => selectedCurveIds.Contains(edge.Curve.Id) ||
                    edge.Curve.Label?.Contains("armhole", StringComparison.OrdinalIgnoreCase) == true ||
                    edge.Curve.Label?.Contains("armscye", StringComparison.OrdinalIgnoreCase) == true)
                .ToArray();
            if (selectedEdges.Length == 0)
            {
                continue;
            }

            PieceBounds bounds = GetBounds(piece);
            if (bounds.Height <= 0)
            {
                continue;
            }
            double underarmY = selectedEdges.Min(edge =>
                Math.Min(edge.Start.Y, edge.Curve.End.Y));
            underarmHeights.Add(Math.Clamp(
                (underarmY - bounds.MinimumY) / bounds.Height,
                0,
                1));
        }

        if (underarmHeights.Count == 0)
        {
            return LegacyChestRelativeHeight;
        }

        double underarmRelativeHeight = underarmHeights.Average();
        return Math.Clamp(
            underarmRelativeHeight - BustDropBelowUnderarmFraction,
            0.50,
            0.68);

        void Accumulate(SeamSideDocument torsoSide, SeamSideDocument sleeveSide)
        {
            if (!panelsById.TryGetValue(torsoSide.PanelId, out ClothPanelDocument? torsoPanel) ||
                !panelsById.TryGetValue(sleeveSide.PanelId, out ClothPanelDocument? sleevePanel) ||
                !piecesById.TryGetValue(torsoPanel.PieceId, out PatternPieceDocument? torsoPiece) ||
                !piecesById.TryGetValue(sleevePanel.PieceId, out PatternPieceDocument? sleevePiece) ||
                !IsTorsoPiece(torsoPiece) ||
                !IsSleevePiece(sleevePiece))
            {
                return;
            }

            if (!armholeCurveIds.TryGetValue(torsoPiece.Id, out HashSet<string>? curveIds))
            {
                curveIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                armholeCurveIds[torsoPiece.Id] = curveIds;
            }
            curveIds.UnionWith(torsoSide.EdgeIds);
        }
    }

    public static double MeasureSleeveOpeningCircumference(GarmentDocument source)
    {
        ArgumentNullException.ThrowIfNull(source);
        Dictionary<string, ClothPanelDocument> panelsById = source.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, PatternPieceDocument> piecesById = source.Pieces
            .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, double> openingsBySide = new(StringComparer.OrdinalIgnoreCase);

        foreach (GarmentSeamDocument seam in source.Seams)
        {
            AccumulateSleeveOpening(seam.SideA, seam.SideB);
            AccumulateSleeveOpening(seam.SideB, seam.SideA);
        }

        double[] measuredOpenings = openingsBySide.Values
            .Where(value => double.IsFinite(value) && value > 0)
            .ToArray();
        return measuredOpenings.Length > 0
            ? measuredOpenings.Average()
            : SourceBodyReference(source).UpperArmCircumferenceCm + MeasureSourceEase(source).UpperArmEaseCm;

        void AccumulateSleeveOpening(
            SeamSideDocument sleeveSide,
            SeamSideDocument accessorySide)
        {
            if (!panelsById.TryGetValue(sleeveSide.PanelId, out ClothPanelDocument? sleevePanel) ||
                !panelsById.TryGetValue(accessorySide.PanelId, out ClothPanelDocument? accessoryPanel) ||
                !piecesById.TryGetValue(sleevePanel.PieceId, out PatternPieceDocument? sleevePiece) ||
                !piecesById.TryGetValue(accessoryPanel.PieceId, out PatternPieceDocument? accessoryPiece) ||
                !IsSleevePiece(sleevePiece) ||
                !IsProtectedAccessory(accessoryPiece) ||
                !accessoryPiece.Id.Contains("cuff", StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            string side = sleevePiece.Id.Contains("left", StringComparison.OrdinalIgnoreCase)
                ? "left"
                : sleevePiece.Id.Contains("right", StringComparison.OrdinalIgnoreCase)
                    ? "right"
                    : "center";
            double length = sleeveSide.EdgeIds.Sum(edgeId => ScaledCurveLength(sleevePiece, edgeId));
            openingsBySide[side] = openingsBySide.GetValueOrDefault(side) + length;
        }
    }

    private static GarmentBodyReferenceDocument SourceBodyReference(GarmentDocument source)
        => source.BodyReference ?? LegacyBodyReference;

    public static double MeasureTorsoGirthAtRelativeHeight(
        GarmentDocument source,
        double relativeHeight)
    {
        ArgumentNullException.ThrowIfNull(source);
        PatternPieceDocument[] torsoPieces = source.Pieces
            .Where(piece => !piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
                !piece.Id.Contains("collar", StringComparison.OrdinalIgnoreCase) &&
                !piece.Id.Contains("cuff", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        return MeasureTorsoGirthAtRelativeHeight(torsoPieces, relativeHeight);
    }

    private static double MeasureTorsoGirthAtRelativeHeight(
        IReadOnlyList<PatternPieceDocument> torsoPieces,
        double relativeHeight)
    {
        if (!double.IsFinite(relativeHeight) || relativeHeight is < 0 or > 1)
        {
            throw new ArgumentOutOfRangeException(nameof(relativeHeight));
        }
        return torsoPieces.Sum(piece => WidthAtRelativeHeight(piece, relativeHeight));
    }

    private static double WidthAtRelativeHeight(PatternPieceDocument piece, double relativeHeight)
    {
        IReadOnlyList<PatternPointDocument> points = SampleBoundary(piece);
        double minimumY = points.Min(point => point.Y);
        double maximumY = points.Max(point => point.Y);
        double targetY = minimumY + (maximumY - minimumY) * relativeHeight;
        List<double> intersections = [];
        for (int index = 0; index < points.Count; index++)
        {
            PatternPointDocument first = points[index];
            PatternPointDocument second = points[(index + 1) % points.Count];
            if ((first.Y <= targetY && second.Y > targetY) ||
                (second.Y <= targetY && first.Y > targetY))
            {
                double amount = (targetY - first.Y) / (second.Y - first.Y);
                intersections.Add(first.X + (second.X - first.X) * amount);
            }
        }
        return intersections.Count >= 2 ? intersections.Max() - intersections.Min() : 0;
    }

    private static IReadOnlyList<PatternPointDocument> SampleBoundary(PatternPieceDocument piece)
    {
        List<PatternPointDocument> points = [piece.Start];
        PatternPointDocument start = piece.Start;
        foreach (PatternCurveDocument curve in piece.Boundary)
        {
            int samples = string.Equals(curve.Kind, "cubic", StringComparison.OrdinalIgnoreCase) ? 24 : 1;
            for (int sample = 1; sample <= samples; sample++)
            {
                points.Add(Evaluate(start, curve, sample / (double)samples));
            }
            start = curve.End;
        }
        return points;
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

    private static PieceBounds GetBounds(PatternPieceDocument piece)
    {
        IReadOnlyList<PatternPointDocument> points = SampleBoundary(piece);
        double minimumX = points.Min(point => point.X);
        double minimumY = points.Min(point => point.Y);
        return new PieceBounds(
            minimumX,
            minimumY,
            points.Max(point => point.X) - minimumX,
            points.Max(point => point.Y) - minimumY);
    }

    private static double WidthScaleAtHeight(
        double height,
        double hipScale,
        double waistScale,
        double chestScale,
        double shoulderScale,
        double chestRelativeHeight)
    {
        if (height <= 0.08)
        {
            return hipScale;
        }
        if (height <= 0.28)
        {
            return SmoothLerp(hipScale, waistScale, (height - 0.08) / 0.20);
        }
        if (height <= chestRelativeHeight)
        {
            return SmoothLerp(
                waistScale,
                chestScale,
                (height - 0.28) / (chestRelativeHeight - 0.28));
        }
        return SmoothLerp(
            chestScale,
            0.7 * chestScale + 0.3 * shoulderScale,
            (height - chestRelativeHeight) / (1 - chestRelativeHeight));
    }

    private static double SmoothLerp(double first, double second, double amount)
    {
        double smooth = amount * amount * (3 - 2 * amount);
        return first + (second - first) * smooth;
    }

    private static double MeasureSplitShirtHemTarget(
        GarmentDocument source,
        double waistCm,
        double hipCm,
        double torsoCm,
        double torsoLengthScale,
        GarmentEaseProfileDocument easeProfile)
    {
        double patternHeight = source.Pieces
            .Where(IsTorsoPiece)
            .Select(piece => GetBounds(piece).Height * torsoLengthScale)
            .DefaultIfEmpty(torsoCm)
            .Max();
        const double defaultWaistToHipLengthCm = 20.4;
        double hipProgress = Math.Clamp(
            (patternHeight - torsoCm) / defaultWaistToHipLengthCm,
            0,
            1);
        double bodyAtHem = waistCm + (hipCm - waistCm) * hipProgress;
        double easeAtHem = easeProfile.WaistEaseCm +
            (easeProfile.HipEaseCm - easeProfile.WaistEaseCm) * hipProgress;
        return bodyAtHem + easeAtHem;
    }

    private static IReadOnlyDictionary<string, IReadOnlySet<string>> MeasureSplitTorsoSideCurves(
        GarmentDocument source)
    {
        Dictionary<string, ClothPanelDocument> panelsById = source.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, PatternPieceDocument> piecesById = source.Pieces
            .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, HashSet<string>> result =
            new(StringComparer.OrdinalIgnoreCase);
        foreach (GarmentSeamDocument seam in source.Seams)
        {
            if (!panelsById.TryGetValue(seam.SideA.PanelId, out ClothPanelDocument? panelA) ||
                !panelsById.TryGetValue(seam.SideB.PanelId, out ClothPanelDocument? panelB) ||
                !piecesById.TryGetValue(panelA.PieceId, out PatternPieceDocument? pieceA) ||
                !piecesById.TryGetValue(panelB.PieceId, out PatternPieceDocument? pieceB) ||
                !IsSplitTorsoFront(pieceA) && !IsSplitTorsoBack(pieceA) ||
                !IsSplitTorsoFront(pieceB) && !IsSplitTorsoBack(pieceB) ||
                IsSplitTorsoFront(pieceA) == IsSplitTorsoFront(pieceB))
            {
                continue;
            }
            Add(pieceA.Id, seam.SideA.EdgeIds);
            Add(pieceB.Id, seam.SideB.EdgeIds);
        }
        return result.ToDictionary(
            item => item.Key,
            item => (IReadOnlySet<string>)item.Value,
            StringComparer.OrdinalIgnoreCase);

        void Add(string pieceId, IReadOnlyList<string> curveIds)
        {
            if (!result.TryGetValue(pieceId, out HashSet<string>? curves))
            {
                curves = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                result[pieceId] = curves;
            }
            curves.UnionWith(curveIds);
        }
    }

    private static bool IsSplitTorsoFront(PatternPieceDocument piece)
        => piece.Id.Contains("ftorso", StringComparison.OrdinalIgnoreCase);

    private static bool IsSplitTorsoBack(PatternPieceDocument piece)
        => piece.Id.Contains("btorso", StringComparison.OrdinalIgnoreCase);

    private static PatternPieceDocument ReshapeTorsoPiece(
        PatternPieceDocument piece,
        double hipScale,
        double waistScale,
        double chestScale,
        double shoulderScale,
        double lengthScale,
        double chestRelativeHeight,
        IReadOnlySet<string>? splitTorsoSideCurveIds = null)
    {
        PieceBounds bounds = GetBounds(piece);
        PatternPointDocument Transform(PatternPointDocument point)
        {
            double normalizedHeight = bounds.Height <= 0
                ? 0
                : Math.Clamp((point.Y - bounds.MinimumY) / bounds.Height, 0, 1);
            double widthScale = WidthScaleAtHeight(
                normalizedHeight,
                hipScale,
                waistScale,
                chestScale,
                shoulderScale,
                chestRelativeHeight);
            double centerX = bounds.MinimumX + bounds.Width * 0.5;
            return new PatternPointDocument(
                centerX + (point.X - centerX) * widthScale,
                bounds.MinimumY + (point.Y - bounds.MinimumY) * lengthScale);
        }
        bool isSplitTorsoPiece =
            piece.Id.Contains("ftorso", StringComparison.OrdinalIgnoreCase) ||
            piece.Id.Contains("btorso", StringComparison.OrdinalIgnoreCase);
        PatternCurveDocument TransformCurve(
            PatternPointDocument start,
            PatternCurveDocument curve)
        {
            bool shapeStraightSide =
                isSplitTorsoPiece &&
                splitTorsoSideCurveIds?.Contains(curve.Id) == true &&
                string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase) &&
                Math.Abs(curve.End.Y - start.Y) > bounds.Height * 0.35 &&
                Math.Abs(curve.End.X - start.X) < Math.Abs(curve.End.Y - start.Y) * 0.15;
            PatternPointDocument? firstControl = shapeStraightSide
                ? Transform(LerpPoint(start, curve.End, 1.0 / 3.0))
                : curve.Control1 is null ? null : Transform(curve.Control1);
            PatternPointDocument? secondControl = shapeStraightSide
                ? Transform(LerpPoint(start, curve.End, 2.0 / 3.0))
                : curve.Control2 is null ? null : Transform(curve.Control2);
            return curve with
            {
                Kind = shapeStraightSide ? "cubic" : curve.Kind,
                End = Transform(curve.End),
                Control1 = firstControl,
                Control2 = secondControl,
                GarmentCodeSource = null
            };
        }
        List<PatternCurveDocument> transformedBoundary = [];
        PatternPointDocument boundaryStart = piece.Start;
        foreach (PatternCurveDocument curve in piece.Boundary)
        {
            transformedBoundary.Add(TransformCurve(boundaryStart, curve));
            boundaryStart = curve.End;
        }
        return piece with
        {
            ScaleX = 1,
            ScaleY = 1,
            Start = Transform(piece.Start),
            Boundary = transformedBoundary,
            InternalPaths = piece.InternalPaths
                .Select(path => path with
                {
                    Start = Transform(path.Start),
                    Segments = path.Segments.Select(segment =>
                        segment with
                        {
                            End = Transform(segment.End),
                            Control1 = segment.Control1 is null ? null : Transform(segment.Control1),
                            Control2 = segment.Control2 is null ? null : Transform(segment.Control2),
                            GarmentCodeSource = null
                        }).ToArray()
                })
                .ToArray(),
            Darts = piece.Darts
                .Select(dart => dart with { Apex = Transform(dart.Apex) })
                .ToArray(),
            Grainline = piece.Grainline is null
                ? null
                : piece.Grainline with
                {
                    Start = Transform(piece.Grainline.Start),
                    End = Transform(piece.Grainline.End)
                }
        };
    }

    private static IReadOnlyDictionary<string, SleeveGradeGeometry> MeasureSleeveGradeGeometry(
        GarmentDocument source)
    {
        Dictionary<string, ClothPanelDocument> panelsById = source.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, PatternPieceDocument> piecesById = source.Pieces
            .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, List<double>> capPositionsX = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, List<double>> openingCentersX = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, List<double>> openingCentersY = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, HashSet<string>> capCurveIds = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, HashSet<string>> openingCurveIds = new(StringComparer.OrdinalIgnoreCase);

        foreach (GarmentSeamDocument seam in source.Seams)
        {
            Accumulate(seam.SideA, seam.SideB);
            Accumulate(seam.SideB, seam.SideA);
        }

        Dictionary<string, SleeveGradeGeometry> result = new(StringComparer.OrdinalIgnoreCase);
        foreach (PatternPieceDocument sleeve in source.Pieces.Where(IsSleevePiece))
        {
            if (!capPositionsX.TryGetValue(sleeve.Id, out List<double>? capPositions) ||
                capPositions.Count == 0 ||
                !openingCentersX.TryGetValue(sleeve.Id, out List<double>? centersX) ||
                centersX.Count == 0 ||
                !openingCentersY.TryGetValue(sleeve.Id, out List<double>? centersY) ||
                centersY.Count == 0 ||
                !capCurveIds.TryGetValue(sleeve.Id, out HashSet<string>? sleeveCapCurveIds) ||
                sleeveCapCurveIds.Count == 0 ||
                !openingCurveIds.TryGetValue(sleeve.Id, out HashSet<string>? sleeveOpeningCurveIds) ||
                sleeveOpeningCurveIds.Count == 0)
            {
                continue;
            }
            double openingCenterX = centersX.Average();
            double[] capDistances = capPositions
                .Select(position => Math.Abs(position - openingCenterX))
                .Where(distance => distance > 0.01)
                .ToArray();
            if (capDistances.Length == 0)
            {
                continue;
            }
            PatternPointDocument[] capBoundaryPoints = sleeveCapCurveIds
                .SelectMany(edgeId =>
                {
                    (PatternPointDocument Start, PatternCurveDocument Curve) edge =
                        FindBoundaryCurve(sleeve, edgeId);
                    return new[] { edge.Start, edge.Curve.End };
                })
                .Distinct()
                .ToArray();
            PatternPointDocument[] openingBoundaryPoints = sleeveOpeningCurveIds
                .SelectMany(edgeId =>
                {
                    (PatternPointDocument Start, PatternCurveDocument Curve) edge =
                        FindBoundaryCurve(sleeve, edgeId);
                    return new[] { edge.Start, edge.Curve.End };
                })
                .Distinct()
                .ToArray();
            PatternPointDocument shoulderPivot = capBoundaryPoints
                .MaxBy(point => Math.Abs(point.X - openingCenterX))!;
            PatternPointDocument underarmAnchor = capBoundaryPoints
                .Where(point => PointDistance(point, shoulderPivot) > 0.01)
                .MinBy(point => Math.Abs(point.X - openingCenterX))!;
            result[sleeve.Id] = new SleeveGradeGeometry(
                capDistances.Min(),
                openingCenterX,
                centersY.Average(),
                shoulderPivot,
                underarmAnchor,
                capBoundaryPoints,
                openingBoundaryPoints,
                sleeveCapCurveIds,
                sleeveOpeningCurveIds);
        }
        return result;

        void Accumulate(SeamSideDocument sleeveSide, SeamSideDocument otherSide)
        {
            if (!panelsById.TryGetValue(sleeveSide.PanelId, out ClothPanelDocument? sleevePanel) ||
                !panelsById.TryGetValue(otherSide.PanelId, out ClothPanelDocument? otherPanel) ||
                !piecesById.TryGetValue(sleevePanel.PieceId, out PatternPieceDocument? sleevePiece) ||
                !piecesById.TryGetValue(otherPanel.PieceId, out PatternPieceDocument? otherPiece) ||
                !IsSleevePiece(sleevePiece))
            {
                return;
            }

            foreach (string edgeId in sleeveSide.EdgeIds)
            {
                (PatternPointDocument Start, PatternCurveDocument Curve) edge =
                    FindBoundaryCurve(sleevePiece, edgeId);
                if (IsTorsoPiece(otherPiece))
                {
                    List<double> capPositions =
                    [
                        edge.Start.X,
                        edge.Curve.End.X
                    ];
                    if (edge.Curve.Control1 is not null)
                    {
                        capPositions.Add(edge.Curve.Control1.X);
                    }
                    if (edge.Curve.Control2 is not null)
                    {
                        capPositions.Add(edge.Curve.Control2.X);
                    }
                    capPositionsX.GetOrAdd(sleevePiece.Id).AddRange(capPositions);
                    if (!capCurveIds.TryGetValue(sleevePiece.Id, out HashSet<string>? curveIds))
                    {
                        curveIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                        capCurveIds.Add(sleevePiece.Id, curveIds);
                    }
                    curveIds.Add(edgeId);
                }
                else if (IsProtectedAccessory(otherPiece) &&
                    otherPiece.Id.Contains("cuff", StringComparison.OrdinalIgnoreCase))
                {
                    openingCentersX.GetOrAdd(sleevePiece.Id).Add(
                        0.5 * (edge.Start.X + edge.Curve.End.X));
                    openingCentersY.GetOrAdd(sleevePiece.Id).Add(
                        0.5 * (edge.Start.Y + edge.Curve.End.Y));
                    if (!openingCurveIds.TryGetValue(sleevePiece.Id, out HashSet<string>? curveIds))
                    {
                        curveIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                        openingCurveIds.Add(sleevePiece.Id, curveIds);
                    }
                    curveIds.Add(edgeId);
                }
            }
        }
    }

    private static PatternPieceDocument ReshapeSleevePiece(
        PatternPieceDocument piece,
        double lengthScale,
        double openingScale,
        SleeveGradeGeometry geometry)
    {
        PatternPointDocument originalCapVector = Subtract(
            geometry.UnderarmAnchor,
            geometry.ShoulderPivot);
        double capRadius = Math.Max(
            PointDistance(geometry.ShoulderPivot, geometry.UnderarmAnchor),
            0.000001);
        double sleeveAxisLength = Math.Max(
            Math.Abs(geometry.ShoulderPivot.X - geometry.OpeningCenterXCm),
            0.000001);
        double underarmOpeningBlend = 1.0 - Math.Clamp(
            Math.Abs(geometry.UnderarmAnchor.X - geometry.OpeningCenterXCm) /
                sleeveAxisLength,
            0,
            1);
        double smoothUnderarmBlend = underarmOpeningBlend * underarmOpeningBlend *
            (3 - 2 * underarmOpeningBlend);
        double underarmGirthScale = 1 + (openingScale - 1) * smoothUnderarmBlend;
        double targetUnderarmY = geometry.OpeningCenterYCm +
            (geometry.UnderarmAnchor.Y - geometry.OpeningCenterYCm) * underarmGirthScale;
        double targetCapDeltaY = Math.Clamp(
            targetUnderarmY - geometry.ShoulderPivot.Y,
            -capRadius + 0.000001,
            capRadius - 0.000001);
        double targetCapDeltaX = Math.CopySign(
            Math.Sqrt(Math.Max(0, capRadius * capRadius - targetCapDeltaY * targetCapDeltaY)),
            originalCapVector.X);
        double capRotation = Math.Atan2(targetCapDeltaY, targetCapDeltaX) -
            Math.Atan2(originalCapVector.Y, originalCapVector.X);
        double capCosine = Math.Cos(capRotation);
        double capSine = Math.Sin(capRotation);

        PatternPointDocument ApplyLength(PatternPointDocument point)
            => point with { X = point.X * lengthScale };
        PatternPointDocument RotateCap(PatternPointDocument point)
        {
            PatternPointDocument relative = Subtract(point, geometry.ShoulderPivot);
            return ApplyLength(new PatternPointDocument(
                geometry.ShoulderPivot.X + relative.X * capCosine - relative.Y * capSine,
                geometry.ShoulderPivot.Y + relative.X * capSine + relative.Y * capCosine));
        }
        PatternPointDocument ScaleOpening(PatternPointDocument point)
            => ApplyLength(new PatternPointDocument(
                point.X,
                geometry.OpeningCenterYCm +
                    (point.Y - geometry.OpeningCenterYCm) * openingScale));
        PatternPointDocument TransformGeneric(PatternPointDocument point)
        {
            double openingBlend = 1.0 - Math.Clamp(
                Math.Abs(point.X - geometry.OpeningCenterXCm) /
                    Math.Max(
                        Math.Abs(geometry.ShoulderPivot.X - geometry.OpeningCenterXCm),
                        0.000001),
                0,
                1);
            double smoothBlend = openingBlend * openingBlend * (3 - 2 * openingBlend);
            double girthScale = 1 + (openingScale - 1) * smoothBlend;
            return new PatternPointDocument(
                point.X * lengthScale,
                geometry.OpeningCenterYCm +
                    (point.Y - geometry.OpeningCenterYCm) * girthScale);
        }
        bool MatchesAny(
            PatternPointDocument point,
            IReadOnlyList<PatternPointDocument> candidates)
            => candidates.Any(candidate => PointDistance(point, candidate) < 0.000001);
        PatternPointDocument TransformVertex(PatternPointDocument point)
            => MatchesAny(point, geometry.CapBoundaryPoints)
                ? RotateCap(point)
                : MatchesAny(point, geometry.OpeningBoundaryPoints)
                    ? ScaleOpening(point)
                    : TransformGeneric(point);
        PatternCurveDocument TransformCurve(PatternCurveDocument curve)
        {
            Func<PatternPointDocument, PatternPointDocument> controlTransform =
                geometry.CapCurveIds.Contains(curve.Id)
                    ? RotateCap
                    : geometry.OpeningCurveIds.Contains(curve.Id)
                        ? ScaleOpening
                        : TransformGeneric;
            return curve with
            {
                End = TransformVertex(curve.End),
                Control1 = curve.Control1 is null ? null : controlTransform(curve.Control1),
                Control2 = curve.Control2 is null ? null : controlTransform(curve.Control2),
                GarmentCodeSource = null
            };
        }
        return piece with
        {
            ScaleX = 1,
            ScaleY = 1,
            Start = TransformVertex(piece.Start),
            Boundary = piece.Boundary.Select(TransformCurve).ToArray(),
            InternalPaths = piece.InternalPaths
                .Select(path => path with
                {
                    Start = TransformGeneric(path.Start),
                    Segments = path.Segments.Select(TransformCurve).ToArray()
                })
                .ToArray(),
            Darts = piece.Darts
                .Select(dart => dart with { Apex = TransformGeneric(dart.Apex) })
                .ToArray(),
            Grainline = piece.Grainline is null
                ? null
                : piece.Grainline with
                {
                    Start = TransformGeneric(piece.Grainline.Start),
                    End = TransformGeneric(piece.Grainline.End)
                }
        };
    }

    private static double ClampScale(double scale) => Math.Clamp(scale, 0.70, 1.40);

    private static bool IsSleevePiece(PatternPieceDocument piece)
        => piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
            !piece.Id.Contains("cuff", StringComparison.OrdinalIgnoreCase);

    private static PatternPieceDocument[] ApplyTorsoCorrections(
        IReadOnlyList<PatternPieceDocument> pieces,
        double hipCorrection,
        double waistCorrection,
        double chestCorrection,
        double chestRelativeHeight)
        => pieces
            .Select(piece => !IsTorsoPiece(piece)
                ? piece
                : ReshapeTorsoPiece(
                    piece,
                    hipCorrection,
                    waistCorrection,
                    chestCorrection,
                    0.7 * chestCorrection + 0.3,
                    1,
                    chestRelativeHeight))
            .ToArray();

    private static PatternPieceDocument[] MatchConstructionSeamLengths(
        GarmentDocument source,
        IReadOnlyList<PatternPieceDocument> pieces,
        bool preserveTorsoConstruction = false)
    {
        bool usesSplitTorsoBlock = source.Pieces.Count(IsTorsoPiece) >= 4;
        Dictionary<string, PatternPieceDocument> piecesById = pieces
            .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, ClothPanelDocument> panelsById = source.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);

        foreach (GarmentSeamDocument seam in source.Seams)
        {
            if (seam.SideA.EdgeIds.Count != 1 || seam.SideB.EdgeIds.Count != 1 ||
                !panelsById.TryGetValue(seam.SideA.PanelId, out ClothPanelDocument? panelA) ||
                !panelsById.TryGetValue(seam.SideB.PanelId, out ClothPanelDocument? panelB))
            {
                continue;
            }

            if (!piecesById.TryGetValue(panelA.PieceId, out PatternPieceDocument? pieceA) ||
                !piecesById.TryGetValue(panelB.PieceId, out PatternPieceDocument? pieceB))
            {
                continue;
            }
            string edgeAId = seam.SideA.EdgeIds[0];
            string edgeBId = seam.SideB.EdgeIds[0];
            double lengthA = ScaledCurveLength(pieceA, edgeAId);
            double lengthB = ScaledCurveLength(pieceB, edgeBId);
            double permittedAbsoluteDrift = Math.Max(lengthA, lengthB) < 2.0 ? 0.005 : 0.01;
            if (Math.Abs(lengthA - lengthB) < permittedAbsoluteDrift)
            {
                continue;
            }

            PatternPieceDocument receiver;
            string receiverEdgeId;
            double targetLengthCm;
            bool scaleAccessoryAlongSeam = false;
            if (IsProtectedAccessory(pieceA) && !IsProtectedAccessory(pieceB))
            {
                receiver = pieceA;
                receiverEdgeId = edgeAId;
                targetLengthCm = lengthB;
                scaleAccessoryAlongSeam = true;
            }
            else if (IsProtectedAccessory(pieceB) && !IsProtectedAccessory(pieceA))
            {
                receiver = pieceB;
                receiverEdgeId = edgeBId;
                targetLengthCm = lengthA;
                scaleAccessoryAlongSeam = true;
            }
            else if (preserveTorsoConstruction && IsTorsoAttachment(pieceA) && IsTorsoPiece(pieceB))
            {
                receiver = pieceA;
                receiverEdgeId = edgeAId;
                targetLengthCm = lengthB;
            }
            else if (preserveTorsoConstruction && IsTorsoAttachment(pieceB) && IsTorsoPiece(pieceA))
            {
                receiver = pieceB;
                receiverEdgeId = edgeBId;
                targetLengthCm = lengthA;
            }
            else if (IsTorsoAttachment(pieceA) && IsTorsoPiece(pieceB))
            {
                bool adaptSleeve = usesSplitTorsoBlock ||
                    WouldCreatePathologicalAttachment(pieceB, edgeBId, lengthA);
                receiver = adaptSleeve ? pieceA : pieceB;
                receiverEdgeId = adaptSleeve ? edgeAId : edgeBId;
                targetLengthCm = adaptSleeve ? lengthB : lengthA;
            }
            else if (IsTorsoAttachment(pieceB) && IsTorsoPiece(pieceA))
            {
                bool adaptSleeve = usesSplitTorsoBlock ||
                    WouldCreatePathologicalAttachment(pieceA, edgeAId, lengthB);
                receiver = adaptSleeve ? pieceB : pieceA;
                receiverEdgeId = adaptSleeve ? edgeBId : edgeAId;
                targetLengthCm = adaptSleeve ? lengthA : lengthB;
            }
            else if (IsTorsoPiece(pieceA) && IsTorsoPiece(pieceB))
            {
                if (preserveTorsoConstruction)
                {
                    // Once a construction profile has drafted the torso, intentional
                    // side-seam balance or ease must not be rewritten here.
                    continue;
                }
                bool aIsShorter = lengthA < lengthB;
                receiver = aIsShorter ? pieceA : pieceB;
                receiverEdgeId = aIsShorter ? edgeAId : edgeBId;
                targetLengthCm = aIsShorter ? lengthB : lengthA;
            }
            else if (IsSleevePiece(pieceA) && IsSleevePiece(pieceB))
            {
                bool aIsShorter = lengthA < lengthB;
                receiver = aIsShorter ? pieceA : pieceB;
                receiverEdgeId = aIsShorter ? edgeAId : edgeBId;
                targetLengthCm = aIsShorter ? lengthB : lengthA;
            }
            else
            {
                continue;
            }

            PatternPieceDocument matched = scaleAccessoryAlongSeam
                ? ScalePieceAlongCurve(receiver, receiverEdgeId, targetLengthCm)
                : MatchCurveLength(
                    receiver,
                    receiverEdgeId,
                    targetLengthCm,
                    allowEndpointRedraft: IsSleevePiece(receiver));
            piecesById[matched.Id] = matched;
        }

        return pieces.Select(piece => piecesById[piece.Id]).ToArray();
    }

    private static PatternPieceDocument MatchCurveLength(
        PatternPieceDocument piece,
        string curveId,
        double targetLengthCm,
        bool allowEndpointRedraft = false)
    {
        int curveIndex = piece.Boundary
            .Select((curve, index) => (curve, index))
            .FirstOrDefault(item => string.Equals(item.curve.Id, curveId, StringComparison.OrdinalIgnoreCase))
            .index;
        if (curveIndex < 0 || curveIndex >= piece.Boundary.Count ||
            !string.Equals(piece.Boundary[curveIndex].Id, curveId, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"Construction curve {piece.Id}/{curveId} does not exist.");
        }

        PatternCurveDocument curve = piece.Boundary[curveIndex];
        PatternPointDocument start = curveIndex == 0 ? piece.Start : piece.Boundary[curveIndex - 1].End;
        PatternPointDocument scaledStart = ScalePoint(piece, start);
        PatternPointDocument scaledEnd = ScalePoint(piece, curve.End);
        PatternPointDocument linearControl1 = LerpPoint(scaledStart, scaledEnd, 1.0 / 3.0);
        PatternPointDocument linearControl2 = LerpPoint(scaledStart, scaledEnd, 2.0 / 3.0);
        PatternPointDocument edge = Subtract(scaledEnd, scaledStart);
        double edgeLength = PointDistance(scaledStart, scaledEnd);
        if (edgeLength < 0.000001)
        {
            throw new InvalidOperationException($"Construction curve {piece.Id}/{curveId} has zero length.");
        }
        double orientation = SignedBoundaryArea(piece) >= 0 ? 1 : -1;
        PatternPointDocument outwardNormal = new(
            orientation * edge.Y / edgeLength,
            -orientation * edge.X / edgeLength);
        PatternPointDocument offset1;
        PatternPointDocument offset2;
        if (string.Equals(curve.Kind, "cubic", StringComparison.OrdinalIgnoreCase) &&
            curve.Control1 is not null && curve.Control2 is not null)
        {
            offset1 = Subtract(ScalePoint(piece, curve.Control1), linearControl1);
            offset2 = Subtract(ScalePoint(piece, curve.Control2), linearControl2);
        }
        else if (string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase))
        {
            offset1 = outwardNormal;
            offset2 = outwardNormal;
        }
        else
        {
            throw new InvalidOperationException(
                $"Construction curve {piece.Id}/{curveId} must be a line or cubic curve for seam-compatible grading.");
        }

        PatternCurveDocument Candidate(double factor)
            => curve with
            {
                Kind = "cubic",
                Control1 = UnscalePoint(piece, Add(linearControl1, Multiply(offset1, factor))),
                Control2 = UnscalePoint(piece, Add(linearControl2, Multiply(offset2, factor))),
                GarmentCodeSource = null
            };
        double Length(double factor) => ScaledCurveLength(piece, start, Candidate(factor));

        double minimumLength = Length(0);
        if (targetLengthCm / edgeLength > MaximumAttachmentLengthToChordRatio)
        {
            throw new InvalidOperationException(
                $"Attachment curve {piece.Id}/{curveId} would require a pathological " +
                $"{targetLengthCm / edgeLength:F2}:1 length-to-chord ratio.");
        }
        if (targetLengthCm < minimumLength - 0.01)
        {
            if (allowEndpointRedraft)
            {
                PatternPieceDocument redrafted = RedraftSleeveAttachmentEndpoint(
                    piece,
                    curveIndex,
                    targetLengthCm);
                return MatchCurveLength(
                    redrafted,
                    curveId,
                    targetLengthCm,
                    allowEndpointRedraft: false);
            }
            throw new InvalidOperationException(
                $"Attachment curve {piece.Id}/{curveId} cannot shorten to {targetLengthCm:F3} cm without moving its sewn endpoints.");
        }
        if (targetLengthCm < minimumLength)
        {
            return piece;
        }
        double low = 0;
        double high = 1;
        while (Length(high) < targetLengthCm && high < 64)
        {
            high *= 2;
        }
        if (Length(high) < targetLengthCm)
        {
            offset1 = outwardNormal;
            offset2 = outwardNormal;
            low = 0;
            high = 1;
            while (Length(high) < targetLengthCm && high < 64)
            {
                high *= 2;
            }
        }
        if (Length(high) < targetLengthCm)
        {
            throw new InvalidOperationException(
                $"Attachment curve {piece.Id}/{curveId} cannot reach the {targetLengthCm:F3} cm sewn edge.");
        }
        for (int iteration = 0; iteration < 64; iteration++)
        {
            double middle = (low + high) * 0.5;
            if (Length(middle) < targetLengthCm)
            {
                low = middle;
            }
            else
            {
                high = middle;
            }
        }

        List<PatternCurveDocument> boundary = [.. piece.Boundary];
        boundary[curveIndex] = Candidate((low + high) * 0.5);
        return piece with { Boundary = boundary };
    }

    private static PatternPieceDocument RedraftSleeveAttachmentEndpoint(
        PatternPieceDocument piece,
        int curveIndex,
        double targetLengthCm)
    {
        if (curveIndex < 0 || curveIndex >= piece.Boundary.Count - 1)
        {
            throw new InvalidOperationException(
                $"Sleeve attachment {piece.Id} cannot redraft a closing boundary endpoint.");
        }

        PatternCurveDocument curve = piece.Boundary[curveIndex];
        PatternPointDocument start = curveIndex == 0
            ? piece.Start
            : piece.Boundary[curveIndex - 1].End;
        PatternPointDocument scaledStart = ScalePoint(piece, start);
        PatternPointDocument scaledEnd = ScalePoint(piece, curve.End);
        PatternPointDocument chord = Subtract(scaledEnd, scaledStart);
        double chordLength = PointDistance(scaledStart, scaledEnd);
        if (chordLength < 0.000001)
        {
            throw new InvalidOperationException(
                $"Sleeve attachment {piece.Id}/{curve.Id} has a zero-length chord.");
        }

        double targetChordLength = Math.Max(
            targetLengthCm * 0.995,
            targetLengthCm - 0.15);
        double endpointTravel = chordLength - targetChordLength;
        if (endpointTravel <= 0 || endpointTravel > 0.75)
        {
            throw new InvalidOperationException(
                $"Sleeve attachment {piece.Id}/{curve.Id} requires {endpointTravel:F3} cm of endpoint redrafting, outside the 0.75 cm construction limit.");
        }

        PatternPointDocument newScaledEnd = Add(
            scaledStart,
            Multiply(chord, targetChordLength / chordLength));
        PatternPointDocument scaledDelta = Subtract(newScaledEnd, scaledEnd);
        PatternPointDocument DeltaPoint(PatternPointDocument point)
            => UnscalePoint(piece, Add(ScalePoint(piece, point), scaledDelta));

        List<PatternCurveDocument> boundary = [.. piece.Boundary];
        boundary[curveIndex] = curve with
        {
            End = UnscalePoint(piece, newScaledEnd),
            Control2 = curve.Control2 is null ? null : DeltaPoint(curve.Control2),
            GarmentCodeSource = null
        };
        PatternCurveDocument next = boundary[curveIndex + 1];
        boundary[curveIndex + 1] = next with
        {
            Control1 = next.Control1 is null ? null : DeltaPoint(next.Control1),
            GarmentCodeSource = null
        };
        return piece with { Boundary = boundary };
    }

    private static PatternPieceDocument ScalePieceAlongCurve(
        PatternPieceDocument piece,
        string curveId,
        double targetLengthCm)
    {
        int curveIndex = piece.Boundary
            .Select((curve, index) => (curve, index))
            .First(item => string.Equals(item.curve.Id, curveId, StringComparison.OrdinalIgnoreCase))
            .index;
        PatternPointDocument start = curveIndex == 0 ? piece.Start : piece.Boundary[curveIndex - 1].End;
        PatternPointDocument scaledStart = ScalePoint(piece, start);
        PatternPointDocument scaledEnd = ScalePoint(piece, piece.Boundary[curveIndex].End);
        PatternPointDocument edge = Subtract(scaledEnd, scaledStart);
        double edgeLength = PointDistance(scaledStart, scaledEnd);
        if (edgeLength < 0.000001)
        {
            throw new InvalidOperationException($"Accessory curve {piece.Id}/{curveId} has zero length.");
        }
        double factor = targetLengthCm / edgeLength;
        PatternPointDocument axis = new(edge.X / edgeLength, edge.Y / edgeLength);
        PatternPointDocument center = LerpPoint(scaledStart, scaledEnd, 0.5);
        PatternPointDocument Transform(PatternPointDocument point)
        {
            PatternPointDocument scaled = ScalePoint(piece, point);
            PatternPointDocument delta = Subtract(scaled, center);
            double parallel = delta.X * axis.X + delta.Y * axis.Y;
            PatternPointDocument parallelVector = Multiply(axis, parallel);
            PatternPointDocument perpendicularVector = Subtract(delta, parallelVector);
            return UnscalePoint(
                piece,
                Add(center, Add(Multiply(parallelVector, factor), perpendicularVector)));
        }
        PatternCurveDocument TransformCurve(PatternCurveDocument curve)
            => curve with
            {
                End = Transform(curve.End),
                Control1 = curve.Control1 is null ? null : Transform(curve.Control1),
                Control2 = curve.Control2 is null ? null : Transform(curve.Control2),
                GarmentCodeSource = null
            };
        return piece with
        {
            Start = Transform(piece.Start),
            Boundary = piece.Boundary.Select(TransformCurve).ToArray(),
            InternalPaths = piece.InternalPaths
                .Select(path => path with
                {
                    Start = Transform(path.Start),
                    Segments = path.Segments.Select(TransformCurve).ToArray()
                })
                .ToArray(),
            Darts = piece.Darts.Select(dart => dart with { Apex = Transform(dart.Apex) }).ToArray(),
            Grainline = piece.Grainline is null
                ? null
                : piece.Grainline with
                {
                    Start = Transform(piece.Grainline.Start),
                    End = Transform(piece.Grainline.End)
                }
        };
    }

    private static PatternPieceDocument[] RegularizeFrontNeckline(
        IReadOnlyList<PatternPieceDocument> pieces)
    {
        return pieces.Select(piece =>
        {
            if (!piece.Id.Contains("front", StringComparison.OrdinalIgnoreCase) ||
                !piece.Id.Contains("torso", StringComparison.OrdinalIgnoreCase))
            {
                return piece;
            }
            List<PatternCurveDocument> boundary = [];
            PatternPointDocument start = piece.Start;
            foreach (PatternCurveDocument curve in piece.Boundary)
            {
                bool isNeckline = curve.Label?.Contains("collar", StringComparison.OrdinalIgnoreCase) == true;
                boundary.Add(isNeckline
                    ? curve with
                    {
                        Kind = "cubic",
                        Control1 = RelativeControlPoint(start, curve.End, 0.45, 0.352),
                        Control2 = RelativeControlPoint(start, curve.End, 0.55, 0.352),
                        GarmentCodeSource = null
                    }
                    : curve);
                start = curve.End;
            }
            return piece with { Boundary = boundary };
        }).ToArray();
    }

    private static PatternPointDocument RelativeControlPoint(
        PatternPointDocument start,
        PatternPointDocument end,
        double along,
        double perpendicular)
    {
        double dx = end.X - start.X;
        double dy = end.Y - start.Y;
        return new PatternPointDocument(
            start.X + along * dx - perpendicular * dy,
            start.Y + along * dy + perpendicular * dx);
    }

    private static double SignedBoundaryArea(PatternPieceDocument piece)
    {
        IReadOnlyList<PatternPointDocument> points = SampleBoundary(piece);
        double twiceArea = 0;
        for (int index = 0; index < points.Count; index++)
        {
            PatternPointDocument first = ScalePoint(piece, points[index]);
            PatternPointDocument second = ScalePoint(piece, points[(index + 1) % points.Count]);
            twiceArea += first.X * second.Y - second.X * first.Y;
        }
        return twiceArea * 0.5;
    }

    private static double ScaledCurveLength(PatternPieceDocument piece, string curveId)
    {
        int curveIndex = piece.Boundary
            .Select((curve, index) => (curve, index))
            .First(item => string.Equals(item.curve.Id, curveId, StringComparison.OrdinalIgnoreCase))
            .index;
        PatternPointDocument start = curveIndex == 0 ? piece.Start : piece.Boundary[curveIndex - 1].End;
        return ScaledCurveLength(piece, start, piece.Boundary[curveIndex]);
    }

    private static bool WouldCreatePathologicalAttachment(
        PatternPieceDocument piece,
        string curveId,
        double targetLengthCm)
    {
        int curveIndex = piece.Boundary
            .Select((curve, index) => (curve, index))
            .First(item => string.Equals(item.curve.Id, curveId, StringComparison.OrdinalIgnoreCase))
            .index;
        PatternPointDocument start = curveIndex == 0 ? piece.Start : piece.Boundary[curveIndex - 1].End;
        double chordLength = PointDistance(
            ScalePoint(piece, start),
            ScalePoint(piece, piece.Boundary[curveIndex].End));
        return chordLength < 0.000001 ||
            targetLengthCm < chordLength - 0.01 ||
            targetLengthCm / chordLength > MaximumAttachmentLengthToChordRatio;
    }

    private static double ScaledCurveLength(
        PatternPieceDocument piece,
        PatternPointDocument start,
        PatternCurveDocument curve)
    {
        const int samples = 96;
        PatternPointDocument previous = ScalePoint(piece, start);
        double length = 0;
        for (int sample = 1; sample <= samples; sample++)
        {
            PatternPointDocument current = ScalePoint(piece, Evaluate(start, curve, sample / (double)samples));
            length += PointDistance(previous, current);
            previous = current;
        }
        return length;
    }

    private static PatternPointDocument ScalePoint(PatternPieceDocument piece, PatternPointDocument point)
        => new(point.X * piece.ScaleX, point.Y * piece.ScaleY);

    private static PatternPointDocument UnscalePoint(PatternPieceDocument piece, PatternPointDocument point)
        => new(point.X / piece.ScaleX, point.Y / piece.ScaleY);

    private static PatternPointDocument LerpPoint(
        PatternPointDocument first,
        PatternPointDocument second,
        double amount)
        => new(first.X + (second.X - first.X) * amount, first.Y + (second.Y - first.Y) * amount);

    private static PatternPointDocument Add(PatternPointDocument first, PatternPointDocument second)
        => new(first.X + second.X, first.Y + second.Y);

    private static PatternPointDocument Subtract(PatternPointDocument first, PatternPointDocument second)
        => new(first.X - second.X, first.Y - second.Y);

    private static PatternPointDocument Multiply(PatternPointDocument point, double factor)
        => new(point.X * factor, point.Y * factor);

    private static double PointDistance(PatternPointDocument first, PatternPointDocument second)
        => Math.Sqrt(
            (first.X - second.X) * (first.X - second.X) +
            (first.Y - second.Y) * (first.Y - second.Y));

    private static (PatternPointDocument Start, PatternCurveDocument Curve) FindBoundaryCurve(
        PatternPieceDocument piece,
        string curveId)
    {
        int index = piece.Boundary
            .Select((curve, curveIndex) => (curve, curveIndex))
            .First(item => string.Equals(item.curve.Id, curveId, StringComparison.OrdinalIgnoreCase))
            .curveIndex;
        return (
            index == 0 ? piece.Start : piece.Boundary[index - 1].End,
            piece.Boundary[index]);
    }

    private static double[] SolveRegularizedLeastSquares(double[,] matrix, double[] values)
    {
        const int size = 3;
        double[,] normalMatrix = new double[size, size];
        double[] normalValues = new double[size];
        double largestDiagonal = 0;
        for (int row = 0; row < size; row++)
        {
            for (int column = 0; column < size; column++)
            {
                normalValues[column] += matrix[row, column] * values[row];
                for (int inner = 0; inner < size; inner++)
                {
                    normalMatrix[column, inner] +=
                        matrix[row, column] * matrix[row, inner];
                }
            }
        }
        for (int index = 0; index < size; index++)
        {
            largestDiagonal = Math.Max(largestDiagonal, Math.Abs(normalMatrix[index, index]));
        }
        double regularization = Math.Max(1e-8, largestDiagonal * 1e-8);
        for (int index = 0; index < size; index++)
        {
            normalMatrix[index, index] += regularization;
        }

        double[,] augmented = new double[size, size + 1];
        for (int row = 0; row < size; row++)
        {
            for (int column = 0; column < size; column++)
            {
                augmented[row, column] = normalMatrix[row, column];
            }
            augmented[row, size] = normalValues[row];
        }
        for (int pivot = 0; pivot < size; pivot++)
        {
            int bestRow = pivot;
            for (int row = pivot + 1; row < size; row++)
            {
                if (Math.Abs(augmented[row, pivot]) > Math.Abs(augmented[bestRow, pivot]))
                {
                    bestRow = row;
                }
            }
            if (Math.Abs(augmented[bestRow, pivot]) < 1e-8)
            {
                return [0, 0, 0];
            }
            if (bestRow != pivot)
            {
                for (int column = pivot; column <= size; column++)
                {
                    (augmented[pivot, column], augmented[bestRow, column]) =
                        (augmented[bestRow, column], augmented[pivot, column]);
                }
            }
            double divisor = augmented[pivot, pivot];
            for (int column = pivot; column <= size; column++)
            {
                augmented[pivot, column] /= divisor;
            }
            for (int row = 0; row < size; row++)
            {
                if (row == pivot)
                {
                    continue;
                }
                double multiple = augmented[row, pivot];
                for (int column = pivot; column <= size; column++)
                {
                    augmented[row, column] -= multiple * augmented[pivot, column];
                }
            }
        }
        return [augmented[0, size], augmented[1, size], augmented[2, size]];
    }

    private static bool IsTorsoPiece(PatternPieceDocument piece)
        => !piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
            !piece.Id.Contains("collar", StringComparison.OrdinalIgnoreCase) &&
            !piece.Id.Contains("cuff", StringComparison.OrdinalIgnoreCase);

    private static bool IsTorsoAttachment(PatternPieceDocument piece)
        => piece.Id.Contains("sleeve", StringComparison.OrdinalIgnoreCase);

    private static bool IsProtectedAccessory(PatternPieceDocument piece)
        => piece.Id.Contains("collar", StringComparison.OrdinalIgnoreCase) ||
            piece.Id.Contains("cuff", StringComparison.OrdinalIgnoreCase);

    private sealed record PieceBounds(double MinimumX, double MinimumY, double Width, double Height);

    private sealed record SleeveGradeGeometry(
        double CapInnerDistanceCm,
        double OpeningCenterXCm,
        double OpeningCenterYCm,
        PatternPointDocument ShoulderPivot,
        PatternPointDocument UnderarmAnchor,
        IReadOnlyList<PatternPointDocument> CapBoundaryPoints,
        IReadOnlyList<PatternPointDocument> OpeningBoundaryPoints,
        IReadOnlySet<string> CapCurveIds,
        IReadOnlySet<string> OpeningCurveIds);
}

file static class AdaptiveShirtDictionaryExtensions
{
    public static List<double> GetOrAdd(
        this Dictionary<string, List<double>> values,
        string key)
    {
        if (!values.TryGetValue(key, out List<double>? result))
        {
            result = [];
            values.Add(key, result);
        }
        return result;
    }
}
