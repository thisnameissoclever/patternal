namespace Patterna;

public static class ShirtConstructionPatternDrafter
{
    private const double PointTolerance = 0.000001;
    private const double MinimumArmscyeScoopChordCm = 2.0;

    public static ShirtConstructionProfileDocument Measure(GarmentDocument document)
    {
        ArgumentNullException.ThrowIfNull(document);
        ConstructionMap map = BuildConstructionMap(document);
        PatternPieceDocument front = document.Pieces.Single(piece => IsFrontTorso(piece.Id));
        PatternPieceDocument back = document.Pieces.Single(piece => IsBackTorso(piece.Id));
        double frontWidth = WidthAtRelativeHeight(front, 0.45);
        double backWidth = WidthAtRelativeHeight(back, 0.45);
        double totalWidth = frontWidth + backWidth;
        if (totalWidth <= PointTolerance)
        {
            throw new InvalidOperationException("The shirt torso has no measurable chest width.");
        }

        TorsoUpperMeasurements frontUpper = MeasureTorsoUpper(front, map);
        TorsoUpperMeasurements backUpper = MeasureTorsoUpper(back, map);
        double[] sleeveCapHeights = document.Pieces
            .Where(piece => IsSleeve(piece.Id))
            .Select(piece => MeasureSleeveCapHeight(piece, map))
            .Where(value => value > PointTolerance)
            .ToArray();
        if (sleeveCapHeights.Length == 0)
        {
            throw new InvalidOperationException("The shirt sewing graph has no measurable sleeve cap.");
        }

        return new ShirtConstructionProfileDocument(
            100 * frontWidth / totalWidth,
            0.5 * (frontUpper.NecklineWidthCm + backUpper.NecklineWidthCm),
            frontUpper.NeckDepthCm,
            backUpper.NeckDepthCm,
            0.5 * (frontUpper.ShoulderLengthCm + backUpper.ShoulderLengthCm),
            0.5 * (frontUpper.ShoulderDropCm + backUpper.ShoulderDropCm),
            0.5 * (frontUpper.ArmscyeDepthCm + backUpper.ArmscyeDepthCm),
            sleeveCapHeights.Average(),
            frontUpper.NeckShoulderHeightCm - backUpper.NeckShoulderHeightCm)
        {
            ArmscyeScoopCm = document.ShirtConstructionProfile?.ArmscyeScoopCm ?? 0,
            UnderarmExtensionCm = document.ShirtConstructionProfile?.UnderarmExtensionCm ?? 0
        };
    }

    public static bool AreEquivalent(
        ShirtConstructionProfileDocument first,
        ShirtConstructionProfileDocument second,
        double tolerance = 0.001)
    {
        ArgumentNullException.ThrowIfNull(first);
        ArgumentNullException.ThrowIfNull(second);
        return Math.Abs(first.FrontWidthSharePercent - second.FrontWidthSharePercent) <= tolerance &&
            Math.Abs(first.NecklineWidthCm - second.NecklineWidthCm) <= tolerance &&
            Math.Abs(first.FrontNeckDepthCm - second.FrontNeckDepthCm) <= tolerance &&
            Math.Abs(first.BackNeckDepthCm - second.BackNeckDepthCm) <= tolerance &&
            Math.Abs(first.ShoulderLengthCm - second.ShoulderLengthCm) <= tolerance &&
            Math.Abs(first.ShoulderDropCm - second.ShoulderDropCm) <= tolerance &&
            Math.Abs(first.ArmscyeDepthCm - second.ArmscyeDepthCm) <= tolerance &&
            Math.Abs(first.ArmscyeScoopCm - second.ArmscyeScoopCm) <= tolerance &&
            Math.Abs(first.UnderarmExtensionCm - second.UnderarmExtensionCm) <= tolerance &&
            Math.Abs(first.SleeveCapHeightCm - second.SleeveCapHeightCm) <= tolerance &&
            Math.Abs(first.FrontBalanceCm - second.FrontBalanceCm) <= tolerance;
    }

    public static GarmentDocument Apply(
        GarmentDocument document,
        ShirtConstructionProfileDocument profile)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(profile);
        ConstructionMap map = BuildConstructionMap(document);
        ShirtConstructionProfileDocument source = Measure(document);
        double armscyeScoopDeltaCm = profile.ArmscyeScoopCm - source.ArmscyeScoopCm;
        double underarmExtensionDeltaCm =
            profile.UnderarmExtensionCm - source.UnderarmExtensionCm;
        double frontWidthFactor = profile.FrontWidthSharePercent / source.FrontWidthSharePercent;
        double backWidthFactor =
            (100 - profile.FrontWidthSharePercent) /
            (100 - source.FrontWidthSharePercent);

        PatternPieceDocument[] pieces = document.Pieces
            .Select(piece => IsFrontTorso(piece.Id)
                ? ShapeTorso(
                    TransformUpperTorso(piece, frontWidthFactor, profile.FrontBalanceCm - source.FrontBalanceCm),
                    map,
                    profile.FrontNeckDepthCm,
                    profile,
                    armscyeScoopDeltaCm,
                    underarmExtensionDeltaCm)
                : IsBackTorso(piece.Id)
                    ? ShapeTorso(
                        TransformUpperTorso(piece, backWidthFactor, 0),
                        map,
                        profile.BackNeckDepthCm,
                        profile,
                        armscyeScoopDeltaCm,
                        underarmExtensionDeltaCm)
                    : IsSleeve(piece.Id)
                        ? ShapeSleeveCap(
                            piece,
                            map,
                            profile.SleeveCapHeightCm / source.SleeveCapHeightCm)
                        : piece)
            .ToArray();

        GarmentDocument drafted = document with
        {
            Pieces = pieces,
            ShirtConstructionProfile = profile
        };
        GarmentDocument distributionBase = drafted;
        double targetShare = profile.FrontWidthSharePercent;
        double low = -0.35;
        double high = 0.35;
        for (int iteration = 0; iteration < 36; iteration++)
        {
            double middle = 0.5 * (low + high);
            GarmentDocument candidate = ApplyDistribution(
                distributionBase,
                Math.Exp(middle),
                Math.Exp(-middle));
            double measuredShare = Measure(candidate).FrontWidthSharePercent;
            if (measuredShare < targetShare)
            {
                low = middle;
            }
            else
            {
                high = middle;
            }
        }
        double solved = 0.5 * (low + high);
        drafted = ApplyDistribution(distributionBase, Math.Exp(solved), Math.Exp(-solved));
        return drafted;

        GarmentDocument ApplyDistribution(
            GarmentDocument input,
            double frontFactor,
            double backFactor)
            => input with
            {
                Pieces = input.Pieces.Select(piece => IsFrontTorso(piece.Id)
                    ? ShapeTorso(
                        TransformWidth(piece, frontFactor),
                        map,
                        profile.FrontNeckDepthCm,
                        profile,
                        0,
                        0)
                    : IsBackTorso(piece.Id)
                        ? ShapeTorso(
                        TransformWidth(piece, backFactor),
                        map,
                        profile.BackNeckDepthCm,
                        profile,
                        0,
                        0)
                        : piece).ToArray()
            };

    }

    private static PatternPieceDocument TransformUpperTorso(
        PatternPieceDocument piece,
        double widthFactor,
        double balanceDeltaCm)
    {
        PieceBounds bounds = GetBounds(piece);
        PatternPointDocument Transform(PatternPointDocument point)
        {
            double height = bounds.Height <= PointTolerance
                ? 0
                : Math.Clamp((point.Y - bounds.MinimumY) / bounds.Height, 0, 1);
            double chestWeight = height <= 0.12
                ? 0
                : height <= 0.45
                    ? SmoothStep((height - 0.12) / 0.33)
                    : 1 - SmoothStep((height - 0.45) / 0.27);
            double balanceWeight = height <= 0.28
                ? 0
                : SmoothStep((height - 0.28) / 0.72);
            double xScale = 1 + (widthFactor - 1) * chestWeight;
            double centerX = bounds.MinimumX + bounds.Width * 0.5;
            return new PatternPointDocument(
                centerX + (point.X - centerX) * xScale,
                point.Y + balanceDeltaCm * balanceWeight);
        }
        return TransformPiece(piece, Transform);
    }

    private static PatternPieceDocument TransformWidth(
        PatternPieceDocument piece,
        double widthFactor)
    {
        PieceBounds bounds = GetBounds(piece);
        PatternPointDocument Transform(PatternPointDocument point)
        {
            double centerX = bounds.MinimumX + bounds.Width * 0.5;
            return point with { X = centerX + (point.X - centerX) * widthFactor };
        }
        return TransformPiece(piece, Transform);
    }

    private static PatternPieceDocument ShapeTorso(
        PatternPieceDocument piece,
        ConstructionMap map,
        double neckDepthCm,
        ShirtConstructionProfileDocument profile,
        double armscyeScoopDeltaCm,
        double underarmExtensionDeltaCm)
    {
        HashSet<int> neckCurves = CurveIndices(piece, map.NecklineEdgesByPiece);
        HashSet<int> armholeCurves = CurveIndices(piece, map.ArmholeEdgesByPiece);
        if (neckCurves.Count != 2 || armholeCurves.Count == 0)
        {
            throw new InvalidOperationException(
                $"Shirt piece {piece.Id} does not expose two neckline curves and sewn armscye curves.");
        }

        PatternPointDocument[] oldVertices = BoundaryVertices(piece);
        PatternPointDocument[] vertices = oldVertices.ToArray();
        int[] neckVertexIndices = CurveVertexIndices(neckCurves, vertices.Length).Distinct().ToArray();
        int centerIndex = neckVertexIndices.MinBy(index => vertices[index].Y);
        int[] outerNeckIndices = neckVertexIndices.Where(index => index != centerIndex).ToArray();
        if (outerNeckIndices.Length != 2)
        {
            throw new InvalidOperationException($"Shirt piece {piece.Id} has an ambiguous neckline center.");
        }

        double centerX = 0.5 * (vertices[outerNeckIndices[0]].X + vertices[outerNeckIndices[1]].X);
        double neckShoulderY = outerNeckIndices.Average(index => vertices[index].Y);
        vertices[centerIndex] = new PatternPointDocument(centerX, neckShoulderY - neckDepthCm);
        foreach (int outerIndex in outerNeckIndices)
        {
            double side = vertices[outerIndex].X < centerX ? -1 : 1;
            vertices[outerIndex] = vertices[outerIndex] with
            {
                X = centerX + side * profile.NecklineWidthCm * 0.5
            };
        }

        foreach (int outerNeckIndex in outerNeckIndices)
        {
            double side = vertices[outerNeckIndex].X < centerX ? -1 : 1;
            int[] sideArmholeVertices = CurveVertexIndices(armholeCurves, vertices.Length)
                .Distinct()
                .Where(index => Math.Sign(vertices[index].X - centerX) == Math.Sign(side))
                .ToArray();
            if (sideArmholeVertices.Length < 2)
            {
                throw new InvalidOperationException($"Shirt piece {piece.Id} has an ambiguous {side} armscye.");
            }
            int shoulderIndex = sideArmholeVertices.MaxBy(index => vertices[index].Y);
            int underarmIndex = sideArmholeVertices.MinBy(index => vertices[index].Y);
            PatternPointDocument oldShoulder = vertices[shoulderIndex];
            PatternPointDocument oldUnderarm = vertices[underarmIndex];
            double horizontalShoulder = Math.Sqrt(Math.Max(
                PointTolerance,
                profile.ShoulderLengthCm * profile.ShoulderLengthCm -
                    profile.ShoulderDropCm * profile.ShoulderDropCm));
            PatternPointDocument newShoulder = new(
                vertices[outerNeckIndex].X + side * horizontalShoulder,
                vertices[outerNeckIndex].Y - profile.ShoulderDropCm);
            PatternPointDocument newUnderarm = oldUnderarm with
            {
                X = oldUnderarm.X + side * underarmExtensionDeltaCm,
                Y = newShoulder.Y - profile.ArmscyeDepthCm
            };
            double oldDepth = Math.Max(oldShoulder.Y - oldUnderarm.Y, PointTolerance);
            foreach (int index in sideArmholeVertices)
            {
                double depthRatio = Math.Clamp(
                    (oldShoulder.Y - vertices[index].Y) / oldDepth,
                    0,
                    1);
                vertices[index] = new PatternPointDocument(
                    vertices[index].X +
                        (newShoulder.X - oldShoulder.X) * (1 - depthRatio) +
                        (newUnderarm.X - oldUnderarm.X) * depthRatio,
                    newShoulder.Y + (newUnderarm.Y - newShoulder.Y) * depthRatio);
            }
            vertices[shoulderIndex] = newShoulder;
            vertices[underarmIndex] = newUnderarm;
        }

        PatternPieceDocument rebuilt = RebuildBoundary(piece, oldVertices, vertices);
        if (Math.Abs(armscyeScoopDeltaCm) <= PointTolerance)
        {
            return rebuilt;
        }
        PatternCurveDocument[] boundary = rebuilt.Boundary.ToArray();
        foreach (int curveIndex in armholeCurves)
        {
            PatternCurveDocument curve = boundary[curveIndex];
            PatternPointDocument start = curveIndex == 0
                ? rebuilt.Start
                : boundary[curveIndex - 1].End;
            if (Distance(start, curve.End) < MinimumArmscyeScoopChordCm)
            {
                // Short junction connectors partition the sewn armscye but are not
                // shaping arcs. Offsetting their controls creates a looping cusp.
                continue;
            }
            double midpointX = 0.5 * (start.X + curve.End.X);
            double side = Math.Sign(midpointX - centerX);
            if (side == 0)
            {
                continue;
            }
            double xOffset = -side * armscyeScoopDeltaCm;
            boundary[curveIndex] = curve with
            {
                Control1 = curve.Control1 is null
                    ? null
                    : curve.Control1 with { X = curve.Control1.X + xOffset },
                Control2 = curve.Control2 is null
                    ? null
                    : curve.Control2 with { X = curve.Control2.X + xOffset },
                GarmentCodeSource = null
            };
        }
        return rebuilt with { Boundary = boundary };
    }

    private static PatternPieceDocument ShapeSleeveCap(
        PatternPieceDocument piece,
        ConstructionMap map,
        double heightFactor)
    {
        HashSet<int> capCurves = CurveIndices(piece, map.ArmholeEdgesByPiece);
        if (capCurves.Count == 0 || Math.Abs(heightFactor - 1) < PointTolerance)
        {
            return piece;
        }
        PatternPointDocument[] oldVertices = BoundaryVertices(piece);
        PatternPointDocument[] vertices = oldVertices.ToArray();
        int[] capVertices = CurveVertexIndices(capCurves, vertices.Length).Distinct().ToArray();
        double anchorY = capVertices.Max(index => vertices[index].Y);
        foreach (int index in capVertices)
        {
            vertices[index] = vertices[index] with
            {
                Y = anchorY + (vertices[index].Y - anchorY) * heightFactor
            };
        }
        return RebuildBoundary(piece, oldVertices, vertices);
    }

    private static PatternPieceDocument RebuildBoundary(
        PatternPieceDocument piece,
        IReadOnlyList<PatternPointDocument> oldVertices,
        IReadOnlyList<PatternPointDocument> newVertices)
    {
        PatternCurveDocument[] boundary = new PatternCurveDocument[piece.Boundary.Count];
        for (int index = 0; index < boundary.Length; index++)
        {
            PatternPointDocument oldStart = oldVertices[index];
            PatternPointDocument oldEnd = oldVertices[(index + 1) % oldVertices.Count];
            PatternPointDocument newStart = newVertices[index];
            PatternPointDocument newEnd = newVertices[(index + 1) % newVertices.Count];
            PatternCurveDocument curve = piece.Boundary[index];
            boundary[index] = curve with
            {
                End = newEnd,
                Control1 = curve.Control1 is null
                    ? null
                    : RemapControl(oldStart, oldEnd, curve.Control1, newStart, newEnd),
                Control2 = curve.Control2 is null
                    ? null
                    : RemapControl(oldStart, oldEnd, curve.Control2, newStart, newEnd),
                GarmentCodeSource = null
            };
        }
        return piece with { Start = newVertices[0], Boundary = boundary };
    }

    private static PatternPointDocument RemapControl(
        PatternPointDocument oldStart,
        PatternPointDocument oldEnd,
        PatternPointDocument control,
        PatternPointDocument newStart,
        PatternPointDocument newEnd)
    {
        double oldDx = oldEnd.X - oldStart.X;
        double oldDy = oldEnd.Y - oldStart.Y;
        double oldLength = Math.Sqrt(oldDx * oldDx + oldDy * oldDy);
        double newDx = newEnd.X - newStart.X;
        double newDy = newEnd.Y - newStart.Y;
        double newLength = Math.Sqrt(newDx * newDx + newDy * newDy);
        if (oldLength <= PointTolerance || newLength <= PointTolerance)
        {
            return new PatternPointDocument(
                newStart.X + control.X - oldStart.X,
                newStart.Y + control.Y - oldStart.Y);
        }
        double oldAxisX = oldDx / oldLength;
        double oldAxisY = oldDy / oldLength;
        double relativeX = control.X - oldStart.X;
        double relativeY = control.Y - oldStart.Y;
        double along = (relativeX * oldAxisX + relativeY * oldAxisY) / oldLength;
        double perpendicular = (-relativeX * oldAxisY + relativeY * oldAxisX) / oldLength;
        double newAxisX = newDx / newLength;
        double newAxisY = newDy / newLength;
        return new PatternPointDocument(
            newStart.X + newLength * (along * newAxisX - perpendicular * newAxisY),
            newStart.Y + newLength * (along * newAxisY + perpendicular * newAxisX));
    }

    private static TorsoUpperMeasurements MeasureTorsoUpper(
        PatternPieceDocument piece,
        ConstructionMap map)
    {
        HashSet<int> neckCurves = CurveIndices(piece, map.NecklineEdgesByPiece);
        HashSet<int> armholeCurves = CurveIndices(piece, map.ArmholeEdgesByPiece);
        PatternPointDocument[] vertices = BoundaryVertices(piece);
        int[] neckVertices = CurveVertexIndices(neckCurves, vertices.Length).Distinct().ToArray();
        if (neckCurves.Count != 2 || neckVertices.Length != 3)
        {
            throw new InvalidOperationException($"Shirt piece {piece.Id} has an ambiguous neckline.");
        }
        int centerIndex = neckVertices.MinBy(index => vertices[index].Y);
        int[] outerIndices = neckVertices.Where(index => index != centerIndex).ToArray();
        double centerX = vertices[centerIndex].X;
        double neckWidth = Math.Abs(vertices[outerIndices[1]].X - vertices[outerIndices[0]].X);
        double shoulderY = outerIndices.Average(index => vertices[index].Y);
        double neckDepth = shoulderY - vertices[centerIndex].Y;
        List<double> shoulderLengths = [];
        List<double> shoulderDrops = [];
        List<double> armscyeDepths = [];
        foreach (int outerIndex in outerIndices)
        {
            double side = vertices[outerIndex].X < centerX ? -1 : 1;
            int[] sideArmholeVertices = CurveVertexIndices(armholeCurves, vertices.Length)
                .Distinct()
                .Where(index => Math.Sign(vertices[index].X - centerX) == Math.Sign(side))
                .ToArray();
            int armShoulder = sideArmholeVertices.MaxBy(index => vertices[index].Y);
            int underarm = sideArmholeVertices.MinBy(index => vertices[index].Y);
            shoulderLengths.Add(Distance(vertices[outerIndex], vertices[armShoulder]));
            shoulderDrops.Add(vertices[outerIndex].Y - vertices[armShoulder].Y);
            armscyeDepths.Add(vertices[armShoulder].Y - vertices[underarm].Y);
        }
        return new TorsoUpperMeasurements(
            neckWidth,
            neckDepth,
            shoulderLengths.Average(),
            shoulderDrops.Average(),
            armscyeDepths.Average(),
            shoulderY);
    }

    private static double MeasureSleeveCapHeight(PatternPieceDocument piece, ConstructionMap map)
    {
        HashSet<int> capCurves = CurveIndices(piece, map.ArmholeEdgesByPiece);
        PatternPointDocument[] vertices = BoundaryVertices(piece);
        PatternPointDocument[] capPoints = capCurves
            .SelectMany(index =>
            {
                PatternCurveDocument curve = piece.Boundary[index];
                return new PatternPointDocument?[]
                {
                    vertices[index],
                    vertices[(index + 1) % vertices.Length],
                    curve.Control1,
                    curve.Control2
                };
            })
            .Where(point => point is not null)
            .Cast<PatternPointDocument>()
            .ToArray();
        return capPoints.Length == 0 ? 0 : capPoints.Max(point => point.Y) - capPoints.Min(point => point.Y);
    }

    private static ConstructionMap BuildConstructionMap(GarmentDocument document)
    {
        Dictionary<string, ClothPanelDocument> panels = document.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, PatternPieceDocument> pieces = document.Pieces
            .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, HashSet<string>> neckline = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, HashSet<string>> armhole = new(StringComparer.OrdinalIgnoreCase);
        foreach (GarmentSeamDocument seam in document.Seams)
        {
            Accumulate(seam.SideA, seam.SideB);
            Accumulate(seam.SideB, seam.SideA);
        }
        return new ConstructionMap(neckline, armhole);

        void Accumulate(SeamSideDocument side, SeamSideDocument other)
        {
            if (!panels.TryGetValue(side.PanelId, out ClothPanelDocument? panel) ||
                !panels.TryGetValue(other.PanelId, out ClothPanelDocument? otherPanel) ||
                !pieces.TryGetValue(panel.PieceId, out PatternPieceDocument? piece) ||
                !pieces.TryGetValue(otherPanel.PieceId, out PatternPieceDocument? otherPiece))
            {
                return;
            }
            if (IsTorso(piece.Id) && otherPiece.Id.Contains("collar", StringComparison.OrdinalIgnoreCase))
            {
                GetOrAdd(neckline, piece.Id).UnionWith(side.EdgeIds);
            }
            if ((IsTorso(piece.Id) && IsSleeve(otherPiece.Id)) ||
                (IsSleeve(piece.Id) && IsTorso(otherPiece.Id)))
            {
                GetOrAdd(armhole, piece.Id).UnionWith(side.EdgeIds);
            }
        }
    }

    private static HashSet<int> CurveIndices(
        PatternPieceDocument piece,
        IReadOnlyDictionary<string, HashSet<string>> edgesByPiece)
    {
        if (!edgesByPiece.TryGetValue(piece.Id, out HashSet<string>? edgeIds))
        {
            return [];
        }
        return piece.Boundary
            .Select((curve, index) => (curve.Id, index))
            .Where(item => edgeIds.Contains(item.Id))
            .Select(item => item.index)
            .ToHashSet();
    }

    private static IEnumerable<int> CurveVertexIndices(IEnumerable<int> curves, int vertexCount)
        => curves.SelectMany(index => new[] { index, (index + 1) % vertexCount });

    private static PatternPointDocument[] BoundaryVertices(PatternPieceDocument piece)
        => [piece.Start, .. piece.Boundary.Take(piece.Boundary.Count - 1).Select(curve => curve.End)];

    private static PatternPieceDocument TransformPiece(
        PatternPieceDocument piece,
        Func<PatternPointDocument, PatternPointDocument> transform)
    {
        PatternCurveDocument TransformCurve(PatternCurveDocument curve)
            => curve with
            {
                End = transform(curve.End),
                Control1 = curve.Control1 is null ? null : transform(curve.Control1),
                Control2 = curve.Control2 is null ? null : transform(curve.Control2),
                GarmentCodeSource = null
            };
        return piece with
        {
            ScaleX = 1,
            ScaleY = 1,
            Start = transform(piece.Start),
            Boundary = piece.Boundary.Select(TransformCurve).ToArray(),
            InternalPaths = piece.InternalPaths.Select(path => path with
            {
                Start = transform(path.Start),
                Segments = path.Segments.Select(TransformCurve).ToArray()
            }).ToArray(),
            Darts = piece.Darts.Select(dart => dart with { Apex = transform(dart.Apex) }).ToArray(),
            Grainline = piece.Grainline is null ? null : piece.Grainline with
            {
                Start = transform(piece.Grainline.Start),
                End = transform(piece.Grainline.End)
            }
        };
    }

    private static double WidthAtRelativeHeight(PatternPieceDocument piece, double relativeHeight)
    {
        PatternPointDocument[] samples = SampleBoundary(piece).ToArray();
        double minimumY = samples.Min(point => point.Y);
        double maximumY = samples.Max(point => point.Y);
        double targetY = minimumY + (maximumY - minimumY) * relativeHeight;
        double[] intersections = samples
            .Zip(samples.Skip(1).Append(samples[0]), (first, second) => (first, second))
            .Where(segment => targetY >= Math.Min(segment.first.Y, segment.second.Y) &&
                targetY < Math.Max(segment.first.Y, segment.second.Y) &&
                Math.Abs(segment.second.Y - segment.first.Y) > PointTolerance)
            .Select(segment => segment.first.X +
                (targetY - segment.first.Y) *
                (segment.second.X - segment.first.X) /
                (segment.second.Y - segment.first.Y))
            .Order()
            .ToArray();
        return intersections.Length < 2 ? 0 : intersections[^1] - intersections[0];
    }

    private static IEnumerable<PatternPointDocument> SampleBoundary(PatternPieceDocument piece)
    {
        PatternPointDocument start = piece.Start;
        foreach (PatternCurveDocument curve in piece.Boundary)
        {
            for (int sample = 0; sample < 24; sample++)
            {
                yield return Evaluate(start, curve, sample / 24.0);
            }
            start = curve.End;
        }
    }

    private static PatternPointDocument Evaluate(
        PatternPointDocument start,
        PatternCurveDocument curve,
        double amount)
    {
        if (!string.Equals(curve.Kind, "cubic", StringComparison.OrdinalIgnoreCase) ||
            curve.Control1 is null || curve.Control2 is null)
        {
            return new PatternPointDocument(
                start.X + (curve.End.X - start.X) * amount,
                start.Y + (curve.End.Y - start.Y) * amount);
        }
        double inverse = 1 - amount;
        return new PatternPointDocument(
            inverse * inverse * inverse * start.X +
                3 * inverse * inverse * amount * curve.Control1.X +
                3 * inverse * amount * amount * curve.Control2.X +
                amount * amount * amount * curve.End.X,
            inverse * inverse * inverse * start.Y +
                3 * inverse * inverse * amount * curve.Control1.Y +
                3 * inverse * amount * amount * curve.Control2.Y +
                amount * amount * amount * curve.End.Y);
    }

    private static PieceBounds GetBounds(PatternPieceDocument piece)
    {
        PatternPointDocument[] points = SampleBoundary(piece).ToArray();
        double minimumX = points.Min(point => point.X);
        double minimumY = points.Min(point => point.Y);
        return new PieceBounds(
            minimumX,
            minimumY,
            points.Max(point => point.X) - minimumX,
            points.Max(point => point.Y) - minimumY);
    }

    private static HashSet<string> GetOrAdd(
        IDictionary<string, HashSet<string>> dictionary,
        string key)
    {
        if (!dictionary.TryGetValue(key, out HashSet<string>? values))
        {
            values = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            dictionary.Add(key, values);
        }
        return values;
    }

    private static double SmoothStep(double amount)
    {
        double clamped = Math.Clamp(amount, 0, 1);
        return clamped * clamped * (3 - 2 * clamped);
    }

    private static double Distance(PatternPointDocument first, PatternPointDocument second)
    {
        double dx = second.X - first.X;
        double dy = second.Y - first.Y;
        return Math.Sqrt(dx * dx + dy * dy);
    }

    private static bool IsTorso(string id)
        => id.Contains("torso", StringComparison.OrdinalIgnoreCase);

    private static bool IsFrontTorso(string id)
        => IsTorso(id) && id.Contains("front", StringComparison.OrdinalIgnoreCase);

    private static bool IsBackTorso(string id)
        => IsTorso(id) && id.Contains("back", StringComparison.OrdinalIgnoreCase);

    private static bool IsSleeve(string id)
        => id.Contains("sleeve", StringComparison.OrdinalIgnoreCase) &&
            !id.Contains("cuff", StringComparison.OrdinalIgnoreCase);

    private sealed record ConstructionMap(
        IReadOnlyDictionary<string, HashSet<string>> NecklineEdgesByPiece,
        IReadOnlyDictionary<string, HashSet<string>> ArmholeEdgesByPiece);

    private sealed record TorsoUpperMeasurements(
        double NecklineWidthCm,
        double NeckDepthCm,
        double ShoulderLengthCm,
        double ShoulderDropCm,
        double ArmscyeDepthCm,
        double NeckShoulderHeightCm);

    private sealed record PieceBounds(double MinimumX, double MinimumY, double Width, double Height);
}
