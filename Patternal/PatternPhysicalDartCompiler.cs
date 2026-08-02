using System.Text.Json;

namespace Patterna;

public static class PatternPhysicalDartCompiler
{
    private const double ParameterEpsilon = 0.000001;
    private const double MaximumLegMismatchRatio = 0.01;
    private const double MaximumExternalSeamMismatchRatio = 0.01;

    public static GarmentDocument Compile(GarmentDocument document)
    {
        ArgumentNullException.ThrowIfNull(document);
        (string PieceId, string DartId)[] pending = document.Pieces
            .SelectMany(piece => piece.Darts
                .Where(dart =>
                    (string.Equals(
                         dart.ConstructionMode,
                         PatternDartConstructionModes.SewnFreeEdge,
                         StringComparison.OrdinalIgnoreCase) ||
                     string.Equals(
                         dart.ConstructionMode,
                         PatternDartConstructionModes.SewnEdge,
                         StringComparison.OrdinalIgnoreCase)) &&
                    !dart.Materialized)
                .Select(dart => (piece.Id, dart.Id)))
            .ToArray();
        GarmentDocument current = document;
        foreach ((string pieceId, string dartId) in pending)
        {
            PatternDartDocument dart = current.Pieces
                .Single(piece => string.Equals(piece.Id, pieceId, StringComparison.OrdinalIgnoreCase))
                .Darts.Single(item => string.Equals(item.Id, dartId, StringComparison.OrdinalIgnoreCase));
            current = string.Equals(
                dart.ConstructionMode,
                PatternDartConstructionModes.SewnEdge,
                StringComparison.OrdinalIgnoreCase)
                ? CompileSewnEdgeDart(current, pieceId, dartId)
                : CompileFreeEdgeDart(current, pieceId, dartId);
        }
        return current;
    }

    private static GarmentDocument CompileFreeEdgeDart(
        GarmentDocument document,
        string pieceId,
        string dartId)
    {
        PatternPieceDocument piece = document.Pieces.Single(item =>
            string.Equals(item.Id, pieceId, StringComparison.OrdinalIgnoreCase));
        PatternDartDocument dart = piece.Darts.Single(item =>
            string.Equals(item.Id, dartId, StringComparison.OrdinalIgnoreCase));
        if (!string.Equals(
                dart.FirstLegBoundaryCurveId,
                dart.SecondLegBoundaryCurveId,
                StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                $"Physical dart {pieceId}/{dartId} must place both legs on one unsewn boundary curve.");
        }
        double firstParameter = Math.Min(dart.FirstLegParameter, dart.SecondLegParameter);
        double secondParameter = Math.Max(dart.FirstLegParameter, dart.SecondLegParameter);
        if (firstParameter <= ParameterEpsilon ||
            secondParameter >= 1 - ParameterEpsilon ||
            secondParameter - firstParameter <= ParameterEpsilon)
        {
            throw new InvalidOperationException(
                $"Physical dart {pieceId}/{dartId} must leave material before, between, and after its two legs.");
        }
        string sourceCurveId = dart.FirstLegBoundaryCurveId;
        EnsureFreeBoundary(document, piece, sourceCurveId, dartId);

        PatternBoundarySplitResult firstSplit = PatternStructuralEditor.SplitBoundarySegment(
            document,
            pieceId,
            sourceCurveId,
            firstParameter);
        double secondLocalParameter =
            (secondParameter - firstParameter) / (1 - firstParameter);
        PatternBoundarySplitResult secondSplit = PatternStructuralEditor.SplitBoundarySegment(
            firstSplit.Document,
            pieceId,
            firstSplit.SecondCurveId,
            secondLocalParameter);
        GarmentDocument splitDocument = secondSplit.Document;
        PatternPieceDocument splitPiece = splitDocument.Pieces.Single(item =>
            string.Equals(item.Id, pieceId, StringComparison.OrdinalIgnoreCase));
        string removedMouthCurveId = secondSplit.FirstCurveId;
        if (splitPiece.Darts.Any(other =>
            !string.Equals(other.Id, dartId, StringComparison.OrdinalIgnoreCase) &&
            (string.Equals(other.FirstLegBoundaryCurveId, removedMouthCurveId, StringComparison.OrdinalIgnoreCase) ||
             string.Equals(other.SecondLegBoundaryCurveId, removedMouthCurveId, StringComparison.OrdinalIgnoreCase))))
        {
            throw new InvalidOperationException(
                $"Physical dart {pieceId}/{dartId} overlaps another dart on {sourceCurveId}.");
        }

        int mouthIndex = splitPiece.Boundary
            .Select((curve, index) => (curve, index))
            .Single(item => string.Equals(
                item.curve.Id,
                removedMouthCurveId,
                StringComparison.OrdinalIgnoreCase))
            .index;
        PatternPointDocument mouthStart = mouthIndex == 0
            ? splitPiece.Start
            : splitPiece.Boundary[mouthIndex - 1].End;
        PatternPointDocument mouthEnd = splitPiece.Boundary[mouthIndex].End;
        double firstLegLength = Distance(mouthStart, dart.Apex);
        double secondLegLength = Distance(dart.Apex, mouthEnd);
        double maximumLegLength = Math.Max(firstLegLength, secondLegLength);
        if (maximumLegLength <= ParameterEpsilon ||
            Math.Abs(firstLegLength - secondLegLength) / maximumLegLength > MaximumLegMismatchRatio)
        {
            throw new InvalidOperationException(
                $"Physical dart {pieceId}/{dartId} legs must match within {MaximumLegMismatchRatio:P0}; measured {firstLegLength:F3} and {secondLegLength:F3} cm.");
        }

        HashSet<string> boundaryIds = splitPiece.Boundary
            .Select(curve => curve.Id)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        string firstLegId = UniqueId(boundaryIds, $"{dartId}-leg-a");
        boundaryIds.Add(firstLegId);
        string secondLegId = UniqueId(boundaryIds, $"{dartId}-leg-b");
        List<PatternCurveDocument> boundary = [.. splitPiece.Boundary];
        boundary.RemoveAt(mouthIndex);
        boundary.Insert(mouthIndex, new PatternCurveDocument(firstLegId, "line", dart.Apex)
        {
            Label = $"{dart.Name} closure"
        });
        boundary.Insert(mouthIndex + 1, new PatternCurveDocument(secondLegId, "line", mouthEnd)
        {
            Label = $"{dart.Name} closure"
        });
        PatternDartDocument compiledDart = dart with
        {
            FirstLegBoundaryCurveId = firstLegId,
            FirstLegParameter = 0,
            SecondLegBoundaryCurveId = secondLegId,
            SecondLegParameter = 1,
            Materialized = true
        };
        PatternPieceDocument compiledPiece = splitPiece with
        {
            Boundary = boundary,
            Darts = splitPiece.Darts.Select(item =>
                string.Equals(item.Id, dartId, StringComparison.OrdinalIgnoreCase)
                    ? compiledDart
                    : item).ToArray()
        };
        ClothPanelDocument[] panels = splitDocument.Panels.Where(item =>
            string.Equals(item.PieceId, pieceId, StringComparison.OrdinalIgnoreCase)).ToArray();
        HashSet<string> seamIds = splitDocument.Seams
            .Select(seam => seam.Id)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        List<GarmentSeamDocument> dartSeams = [];
        foreach (ClothPanelDocument panel in panels)
        {
            string seamId = UniqueId(
                seamIds,
                panels.Length == 1
                    ? $"{dartId}-seam"
                    : $"{dartId}-{panel.Id}-seam");
            seamIds.Add(seamId);
            dartSeams.Add(new GarmentSeamDocument(
                seamId,
                $"{dart.Name} closure",
                new SeamSideDocument(panel.Id, [firstLegId], true),
                new SeamSideDocument(panel.Id, [secondLegId]),
                compiledPiece.SeamAllowanceCm));
        }
        GarmentDocument compiled = splitDocument with
        {
            Pieces = splitDocument.Pieces.Select(item =>
                string.Equals(item.Id, pieceId, StringComparison.OrdinalIgnoreCase)
                    ? compiledPiece
                    : item).ToArray(),
            Seams = [.. splitDocument.Seams, .. dartSeams]
        };
        IReadOnlyList<string> errors = compiled.Validate();
        if (errors.Count > 0)
        {
            throw new InvalidOperationException(string.Join(Environment.NewLine, errors));
        }
        return compiled;
    }

    private static GarmentDocument CompileSewnEdgeDart(
        GarmentDocument document,
        string pieceId,
        string dartId)
    {
        PatternPieceDocument piece = document.Pieces.Single(item =>
            string.Equals(item.Id, pieceId, StringComparison.OrdinalIgnoreCase));
        PatternDartDocument dart = piece.Darts.Single(item =>
            string.Equals(item.Id, dartId, StringComparison.OrdinalIgnoreCase));
        if (!string.Equals(
                dart.FirstLegBoundaryCurveId,
                dart.SecondLegBoundaryCurveId,
                StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                $"Sewn-edge dart {pieceId}/{dartId} must place both legs on one boundary curve.");
        }
        string sourceCurveId = dart.FirstLegBoundaryCurveId;
        ClothPanelDocument[] sourcePanels = document.Panels.Where(panel =>
            string.Equals(panel.PieceId, pieceId, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (sourcePanels.Length != 1)
        {
            throw new InvalidOperationException(
                $"Sewn-edge dart {pieceId}/{dartId} currently requires exactly one cloth-panel instance for its pattern piece.");
        }
        ClothPanelDocument sourcePanel = sourcePanels[0];
        (GarmentSeamDocument Seam, SeamSideDocument SourceSide, SeamSideDocument OppositeSide)[] references =
            document.Seams.SelectMany(seam =>
            {
                List<(GarmentSeamDocument, SeamSideDocument, SeamSideDocument)> found = [];
                if (string.Equals(seam.SideA.PanelId, sourcePanel.Id, StringComparison.OrdinalIgnoreCase) &&
                    seam.SideA.EdgeIds.Contains(sourceCurveId, StringComparer.OrdinalIgnoreCase))
                {
                    found.Add((seam, seam.SideA, seam.SideB));
                }
                if (string.Equals(seam.SideB.PanelId, sourcePanel.Id, StringComparison.OrdinalIgnoreCase) &&
                    seam.SideB.EdgeIds.Contains(sourceCurveId, StringComparer.OrdinalIgnoreCase))
                {
                    found.Add((seam, seam.SideB, seam.SideA));
                }
                return found;
            }).ToArray();
        if (references.Length != 1)
        {
            throw new InvalidOperationException(
                $"Sewn-edge dart {pieceId}/{dartId} requires its mouth curve to belong to exactly one permanent seam.");
        }
        (GarmentSeamDocument seam, SeamSideDocument sourceSide, SeamSideDocument oppositeSide) = references[0];
        if (sourceSide.EdgeIds.Count != 1 || oppositeSide.EdgeIds.Count != 1)
        {
            throw new InvalidOperationException(
                $"Sewn-edge dart {pieceId}/{dartId} currently requires a one-edge seam on both sides.");
        }
        ClothPanelDocument oppositePanel = document.Panels.Single(panel =>
            string.Equals(panel.Id, oppositeSide.PanelId, StringComparison.OrdinalIgnoreCase));
        if (string.Equals(oppositePanel.Id, sourcePanel.Id, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                $"Sewn-edge dart {pieceId}/{dartId} cannot target an existing same-panel seam.");
        }
        PatternPieceDocument oppositePiece = document.Pieces.Single(item =>
            string.Equals(item.Id, oppositePanel.PieceId, StringComparison.OrdinalIgnoreCase));
        string oppositeCurveId = oppositeSide.EdgeIds[0];
        bool effectiveOppositeReverse = ResolveOppositeSeamDirection(
            document,
            seam,
            piece,
            sourcePanel,
            sourceCurveId,
            sourceSide.Reverse,
            oppositePiece,
            oppositePanel,
            oppositeCurveId,
            oppositeSide.Reverse);
        EnsureExclusivelySewnBoundary(document, sourcePanel, sourceCurveId, seam.Id, dartId);
        EnsureExclusivelySewnBoundary(document, oppositePanel, oppositeCurveId, seam.Id, dartId);

        double firstParameter = Math.Min(dart.FirstLegParameter, dart.SecondLegParameter);
        double secondParameter = Math.Max(dart.FirstLegParameter, dart.SecondLegParameter);
        if (firstParameter <= ParameterEpsilon ||
            secondParameter >= 1 - ParameterEpsilon ||
            secondParameter - firstParameter <= ParameterEpsilon)
        {
            throw new InvalidOperationException(
                $"Sewn-edge dart {pieceId}/{dartId} must leave seam material before, between, and after its two legs.");
        }
        double sourceBeforeLength = CurveLength(piece, sourceCurveId, firstParameter);
        double sourceAfterLength =
            CurveLength(piece, sourceCurveId, 1) - CurveLength(piece, sourceCurveId, secondParameter);
        double oppositeLength = CurveLength(oppositePiece, oppositeCurveId, 1);
        double sourceExternalLength = sourceBeforeLength + sourceAfterLength;
        double maximumExternalLength = Math.Max(sourceExternalLength, oppositeLength);
        if (maximumExternalLength <= ParameterEpsilon ||
            Math.Abs(sourceExternalLength - oppositeLength) / maximumExternalLength >
                MaximumExternalSeamMismatchRatio)
        {
            throw new InvalidOperationException(
                $"Sewn-edge dart {pieceId}/{dartId} needs drafted intake: the two remaining source seam spans total {sourceExternalLength:F3} cm while the opposite seam is {oppositeLength:F3} cm. Match them within {MaximumExternalSeamMismatchRatio:P0} before closing the dart.");
        }
        double sourceFirstSeamLength = sourceSide.Reverse
            ? sourceAfterLength
            : sourceBeforeLength;
        double oppositeSeamPosition = Math.Clamp(
            sourceFirstSeamLength / oppositeLength,
            ParameterEpsilon,
            1 - ParameterEpsilon);
        double oppositeGeometricPosition = effectiveOppositeReverse
            ? 1 - oppositeSeamPosition
            : oppositeSeamPosition;
        double oppositeParameter = ParameterAtLengthFraction(
            oppositePiece,
            oppositeCurveId,
            oppositeGeometricPosition);

        GarmentDocument withoutOriginalSeam = document with
        {
            Seams = document.Seams.Where(item =>
                !string.Equals(item.Id, seam.Id, StringComparison.OrdinalIgnoreCase)).ToArray()
        };
        GarmentDocument dartCompiled = CompileFreeEdgeDart(
            withoutOriginalSeam,
            pieceId,
            dartId);
        PatternPieceDocument dartPiece = dartCompiled.Pieces.Single(item =>
            string.Equals(item.Id, pieceId, StringComparison.OrdinalIgnoreCase));
        PatternDartDocument materializedDart = dartPiece.Darts.Single(item =>
            string.Equals(item.Id, dartId, StringComparison.OrdinalIgnoreCase));
        int firstLegIndex = dartPiece.Boundary
            .Select((curve, index) => (curve, index))
            .Single(item => string.Equals(
                item.curve.Id,
                materializedDart.FirstLegBoundaryCurveId,
                StringComparison.OrdinalIgnoreCase)).index;
        string sourceBeforeId = dartPiece.Boundary[firstLegIndex - 1].Id;
        string sourceAfterId = dartPiece.Boundary[firstLegIndex + 2].Id;

        PatternBoundarySplitResult oppositeSplit = PatternStructuralEditor.SplitBoundarySegment(
            dartCompiled,
            oppositePiece.Id,
            oppositeCurveId,
            oppositeParameter);
        string sourceFirstId = sourceSide.Reverse ? sourceAfterId : sourceBeforeId;
        string sourceSecondId = sourceSide.Reverse ? sourceBeforeId : sourceAfterId;
        string oppositeFirstId = effectiveOppositeReverse
            ? oppositeSplit.SecondCurveId
            : oppositeSplit.FirstCurveId;
        string oppositeSecondId = effectiveOppositeReverse
            ? oppositeSplit.FirstCurveId
            : oppositeSplit.SecondCurveId;
        HashSet<string> seamIds = oppositeSplit.Document.Seams
            .Select(item => item.Id)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        string firstSeamId = UniqueId(seamIds, $"{seam.Id}-{dartId}-before");
        seamIds.Add(firstSeamId);
        string secondSeamId = UniqueId(seamIds, $"{seam.Id}-{dartId}-after");
        GarmentSeamDocument firstSeam = new(
            firstSeamId,
            $"{seam.Name} before {dart.Name}",
            new SeamSideDocument(sourcePanel.Id, [sourceFirstId], sourceSide.Reverse),
            new SeamSideDocument(oppositePanel.Id, [oppositeFirstId], effectiveOppositeReverse),
            seam.AllowanceCm,
            seam.Strength);
        GarmentSeamDocument secondSeam = new(
            secondSeamId,
            $"{seam.Name} after {dart.Name}",
            new SeamSideDocument(sourcePanel.Id, [sourceSecondId], sourceSide.Reverse),
            new SeamSideDocument(oppositePanel.Id, [oppositeSecondId], effectiveOppositeReverse),
            seam.AllowanceCm,
            seam.Strength);
        GarmentDocument compiled = oppositeSplit.Document with
        {
            Seams = [.. oppositeSplit.Document.Seams, firstSeam, secondSeam]
        };
        IReadOnlyList<string> errors = compiled.Validate();
        if (errors.Count > 0)
        {
            throw new InvalidOperationException(string.Join(Environment.NewLine, errors));
        }
        return compiled;
    }

    private static bool ResolveOppositeSeamDirection(
        GarmentDocument document,
        GarmentSeamDocument seam,
        PatternPieceDocument sourcePiece,
        ClothPanelDocument sourcePanel,
        string sourceCurveId,
        bool sourceReverse,
        PatternPieceDocument oppositePiece,
        ClothPanelDocument oppositePanel,
        string oppositeCurveId,
        bool oppositeReverse)
    {
        if (TryReadSourceRelativeReverse(document, seam.Id, out bool relativeReverse))
        {
            return sourceReverse ^ relativeReverse;
        }
        if (sourcePanel.SourcePlacement is null || oppositePanel.SourcePlacement is null)
        {
            return oppositeReverse;
        }

        (PatternPointDocument sourceStart, PatternPointDocument sourceEnd) =
            CurveEndpoints(sourcePiece, sourceCurveId, sourceReverse);
        (PatternPointDocument oppositeStart, PatternPointDocument oppositeEnd) =
            CurveEndpoints(oppositePiece, oppositeCurveId, oppositeReverse);
        ArrangedPoint sourceStart3 = TransformToSourcePlacement(
            sourceStart,
            sourcePanel.SourcePlacement);
        ArrangedPoint sourceEnd3 = TransformToSourcePlacement(
            sourceEnd,
            sourcePanel.SourcePlacement);
        ArrangedPoint oppositeStart3 = TransformToSourcePlacement(
            oppositeStart,
            oppositePanel.SourcePlacement);
        ArrangedPoint oppositeEnd3 = TransformToSourcePlacement(
            oppositeEnd,
            oppositePanel.SourcePlacement);
        double selectedGap = Distance(sourceStart3, oppositeStart3) +
            Distance(sourceEnd3, oppositeEnd3);
        double reversedGap = Distance(sourceStart3, oppositeEnd3) +
            Distance(sourceEnd3, oppositeStart3);
        return reversedGap + 0.01 < selectedGap
            ? !oppositeReverse
            : oppositeReverse;
    }

    private static bool TryReadSourceRelativeReverse(
        GarmentDocument document,
        string seamId,
        out bool relativeReverse)
    {
        relativeReverse = false;
        const string prefix = "stitch-";
        if (!seamId.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }
        int digitCount = seamId[prefix.Length..]
            .TakeWhile(char.IsDigit)
            .Count();
        if (digitCount == 0 ||
            !int.TryParse(seamId.AsSpan(prefix.Length, digitCount), out int stitchIndex) ||
            string.IsNullOrWhiteSpace(document.Source?.RawDocumentJson))
        {
            return false;
        }

        try
        {
            using JsonDocument source = JsonDocument.Parse(document.Source.RawDocumentJson);
            JsonElement stitches = source.RootElement
                .GetProperty("pattern")
                .GetProperty("stitches");
            if (stitchIndex < 0 || stitchIndex >= stitches.GetArrayLength())
            {
                return false;
            }
            JsonElement stitch = stitches[stitchIndex];
            relativeReverse = stitch.GetArrayLength() != 3 ||
                stitch[2].ValueKind != JsonValueKind.String ||
                !string.Equals(
                    stitch[2].GetString(),
                    "right_wrong",
                    StringComparison.Ordinal);
            return true;
        }
        catch (JsonException)
        {
            return false;
        }
        catch (KeyNotFoundException)
        {
            return false;
        }
        catch (InvalidOperationException)
        {
            return false;
        }
    }

    private static (PatternPointDocument Start, PatternPointDocument End) CurveEndpoints(
        PatternPieceDocument piece,
        string curveId,
        bool reverse)
    {
        int curveIndex = piece.Boundary
            .Select((curve, index) => (curve, index))
            .Single(item => string.Equals(
                item.curve.Id,
                curveId,
                StringComparison.OrdinalIgnoreCase)).index;
        PatternPointDocument start = curveIndex == 0
            ? piece.Start
            : piece.Boundary[curveIndex - 1].End;
        PatternPointDocument end = piece.Boundary[curveIndex].End;
        return reverse ? (end, start) : (start, end);
    }

    private static ArrangedPoint TransformToSourcePlacement(
        PatternPointDocument point,
        PatternPlacement3DDocument placement)
    {
        double xAngle = placement.RotationXDegrees * Math.PI / 180.0;
        double yAngle = placement.RotationYDegrees * Math.PI / 180.0;
        double zAngle = placement.RotationZDegrees * Math.PI / 180.0;
        double cx = Math.Cos(xAngle);
        double sx = Math.Sin(xAngle);
        double cy = Math.Cos(yAngle);
        double sy = Math.Sin(yAngle);
        double cz = Math.Cos(zAngle);
        double sz = Math.Sin(zAngle);
        double afterXx = point.X;
        double afterXy = point.Y * cx;
        double afterXz = point.Y * sx;
        double afterYx = afterXx * cy + afterXz * sy;
        double afterYy = afterXy;
        double afterYz = -afterXx * sy + afterXz * cy;
        return new ArrangedPoint(
            afterYx * cz - afterYy * sz + placement.X,
            afterYz + placement.Z,
            afterYx * sz + afterYy * cz + placement.Y);
    }

    private static double Distance(ArrangedPoint first, ArrangedPoint second)
        => Math.Sqrt(
            Math.Pow(second.X - first.X, 2) +
            Math.Pow(second.Y - first.Y, 2) +
            Math.Pow(second.Z - first.Z, 2));

    private readonly record struct ArrangedPoint(double X, double Y, double Z);

    private static void EnsureExclusivelySewnBoundary(
        GarmentDocument document,
        ClothPanelDocument panel,
        string curveId,
        string permittedSeamId,
        string dartId)
    {
        bool referencedByAnotherSeam = document.Seams.Any(seam =>
            !string.Equals(seam.Id, permittedSeamId, StringComparison.OrdinalIgnoreCase) &&
            (SeamReferences(seam.SideA) || SeamReferences(seam.SideB)));
        bool referencedByClosure = document.Closures.Any(closure =>
            ClosureReferences(closure.AnchorA) || ClosureReferences(closure.AnchorB));
        bool pinned = panel.PinnedEdges.Contains(curveId, StringComparer.OrdinalIgnoreCase);
        if (referencedByAnotherSeam || referencedByClosure || pinned)
        {
            throw new InvalidOperationException(
                $"Sewn-edge dart {panel.PieceId}/{dartId} targets {curveId}, which has another seam, closure, or pin relationship.");
        }
        return;

        bool SeamReferences(SeamSideDocument side)
            => string.Equals(side.PanelId, panel.Id, StringComparison.OrdinalIgnoreCase) &&
                side.EdgeIds.Contains(curveId, StringComparer.OrdinalIgnoreCase);

        bool ClosureReferences(GarmentClosureAnchorDocument anchor)
            => string.Equals(anchor.PanelId, panel.Id, StringComparison.OrdinalIgnoreCase) &&
                anchor.EdgeIds.Contains(curveId, StringComparer.OrdinalIgnoreCase);
    }

    private static double ParameterAtLengthFraction(
        PatternPieceDocument piece,
        string curveId,
        double lengthFraction)
    {
        double totalLength = CurveLength(piece, curveId, 1);
        double targetLength = Math.Clamp(lengthFraction, 0, 1) * totalLength;
        double lower = 0;
        double upper = 1;
        for (int iteration = 0; iteration < 48; iteration++)
        {
            double middle = (lower + upper) * 0.5;
            if (CurveLength(piece, curveId, middle) < targetLength)
            {
                lower = middle;
            }
            else
            {
                upper = middle;
            }
        }
        return (lower + upper) * 0.5;
    }

    private static double CurveLength(
        PatternPieceDocument piece,
        string curveId,
        double endParameter)
    {
        int curveIndex = piece.Boundary
            .Select((curve, index) => (curve, index))
            .Single(item => string.Equals(
                item.curve.Id,
                curveId,
                StringComparison.OrdinalIgnoreCase)).index;
        PatternCurveDocument curve = piece.Boundary[curveIndex];
        PatternPointDocument start = curveIndex == 0
            ? piece.Start
            : piece.Boundary[curveIndex - 1].End;
        int samples = string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase) ? 1 : 128;
        double clampedEnd = Math.Clamp(endParameter, 0, 1);
        PatternPointDocument previous = start;
        double length = 0;
        for (int sample = 1; sample <= samples; sample++)
        {
            double parameter = clampedEnd * sample / samples;
            PatternPointDocument current = Evaluate(start, curve, parameter);
            length += Distance(previous, current);
            previous = current;
        }
        return length;
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

    private static void EnsureFreeBoundary(
        GarmentDocument document,
        PatternPieceDocument piece,
        string curveId,
        string dartId)
    {
        HashSet<string> panelIds = document.Panels
            .Where(panel => string.Equals(panel.PieceId, piece.Id, StringComparison.OrdinalIgnoreCase))
            .Select(panel => panel.Id)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        bool usedBySeam = document.Seams.Any(seam =>
            SeamReferences(seam.SideA) || SeamReferences(seam.SideB));
        bool usedByClosure = document.Closures.Any(closure =>
            ClosureReferences(closure.AnchorA) || ClosureReferences(closure.AnchorB));
        bool pinned = document.Panels.Any(panel =>
            panelIds.Contains(panel.Id) &&
            panel.PinnedEdges.Contains(curveId, StringComparer.OrdinalIgnoreCase));
        if (usedBySeam || usedByClosure || pinned)
        {
            throw new InvalidOperationException(
                $"Physical dart {piece.Id}/{dartId} targets {curveId}, which is sewn, closed, or pinned. The current physical-dart compiler accepts unsewn free edges only.");
        }
        return;

        bool SeamReferences(SeamSideDocument side)
            => panelIds.Contains(side.PanelId) &&
                side.EdgeIds.Contains(curveId, StringComparer.OrdinalIgnoreCase);

        bool ClosureReferences(GarmentClosureAnchorDocument anchor)
            => panelIds.Contains(anchor.PanelId) &&
                anchor.EdgeIds.Contains(curveId, StringComparer.OrdinalIgnoreCase);
    }

    private static string UniqueId(IReadOnlySet<string> existing, string preferred)
    {
        string normalized = preferred;
        int suffix = 2;
        while (existing.Contains(normalized))
        {
            normalized = $"{preferred}-{suffix++}";
        }
        return normalized;
    }

    private static double Distance(PatternPointDocument first, PatternPointDocument second)
    {
        double dx = second.X - first.X;
        double dy = second.Y - first.Y;
        return Math.Sqrt(dx * dx + dy * dy);
    }
}
