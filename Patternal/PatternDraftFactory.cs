namespace Patterna;

public enum PatternDraftShape
{
    Rectangle,
    Ellipse,
    Polygon
}

public static class PatternDraftFactory
{
    private const double CircleBezierFactor = 0.5522847498307936;

    public static PatternPieceDocument CreatePiece(
        string id,
        string name,
        PatternDraftShape shape,
        double widthCm,
        double heightCm,
        double seamAllowanceCm,
        int cutQuantity,
        bool mirrored,
        bool cutOnFold,
        double layoutLeft,
        double layoutTop,
        double layoutScale = 2)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            throw new ArgumentException("A drafted piece requires an ID.", nameof(id));
        }
        if (string.IsNullOrWhiteSpace(name))
        {
            throw new ArgumentException("A drafted piece requires a name.", nameof(name));
        }
        if (!double.IsFinite(widthCm) || widthCm <= 0 ||
            !double.IsFinite(heightCm) || heightCm <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(widthCm), "Drafted width and height must be finite and positive.");
        }
        if (!double.IsFinite(seamAllowanceCm) || seamAllowanceCm < 0 || seamAllowanceCm > 10)
        {
            throw new ArgumentOutOfRangeException(nameof(seamAllowanceCm), "Seam allowance must be from 0 through 10 centimeters.");
        }
        if (cutQuantity is < 1 or > 20)
        {
            throw new ArgumentOutOfRangeException(nameof(cutQuantity), "Cut quantity must be from 1 through 20.");
        }
        if (!double.IsFinite(layoutLeft) || !double.IsFinite(layoutTop) ||
            !double.IsFinite(layoutScale) || layoutScale <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(layoutScale), "Drafted layout values must be finite and use a positive scale.");
        }

        (PatternPointDocument start, IReadOnlyList<PatternCurveDocument> boundary) = shape switch
        {
            PatternDraftShape.Rectangle => RectangleBoundary(widthCm, heightCm),
            PatternDraftShape.Ellipse => EllipseBoundary(widthCm, heightCm),
            PatternDraftShape.Polygon => throw new InvalidOperationException("Use CreatePolygonPiece with explicit vertices for polygon drafting."),
            _ => throw new ArgumentOutOfRangeException(nameof(shape))
        };

        return new PatternPieceDocument(
            id,
            name.Trim(),
            cutQuantity,
            mirrored,
            cutOnFold,
            1,
            1,
            seamAllowanceCm,
            start,
            boundary,
            new PatternLayoutDocument(
                layoutLeft,
                layoutTop,
                widthCm * layoutScale,
                heightCm * layoutScale,
                true))
        {
            Grainline = new PatternGrainlineDocument(
                new PatternPointDocument(widthCm * 0.5, heightCm * 0.2),
                new PatternPointDocument(widthCm * 0.5, heightCm * 0.8))
        };
    }

    public static PatternPieceDocument CreatePolygonPiece(
        string id,
        string name,
        IReadOnlyList<PatternPointDocument> vertices,
        double seamAllowanceCm,
        int cutQuantity,
        bool mirrored,
        bool cutOnFold,
        double layoutLeft,
        double layoutTop)
    {
        ArgumentNullException.ThrowIfNull(vertices);
        ValidateCommonInputs(id, name, seamAllowanceCm, cutQuantity, layoutLeft, layoutTop);
        PatternPointDocument[] polygon = NormalizePolygon(vertices);
        double minX = polygon.Min(point => point.X);
        double minY = polygon.Min(point => point.Y);
        double maxX = polygon.Max(point => point.X);
        double maxY = polygon.Max(point => point.Y);
        IReadOnlyList<PatternCurveDocument> boundary = Enumerable.Range(1, polygon.Length)
            .Select(index => new PatternCurveDocument(
                $"edge-{index}",
                "line",
                polygon[index % polygon.Length]))
            .ToArray();
        double centerX = (minX + maxX) * 0.5;
        double height = maxY - minY;
        return new PatternPieceDocument(
            id,
            name.Trim(),
            cutQuantity,
            mirrored,
            cutOnFold,
            1,
            1,
            seamAllowanceCm,
            polygon[0],
            boundary,
            new PatternLayoutDocument(
                layoutLeft,
                layoutTop,
                (centerX - minX) * 4,
                height * 2,
                true))
        {
            Grainline = new PatternGrainlineDocument(
                new PatternPointDocument(centerX, minY + height * 0.2),
                new PatternPointDocument(centerX, minY + height * 0.8))
        };
    }

    public static PatternPieceDocument CreateCanvasPolygonPiece(
        string id,
        string name,
        IReadOnlyList<PatternPointDocument> canvasPointsCm,
        double pixelsPerCentimeter,
        double seamAllowanceCm,
        int cutQuantity,
        bool mirrored,
        bool cutOnFold)
    {
        ArgumentNullException.ThrowIfNull(canvasPointsCm);
        if (!double.IsFinite(pixelsPerCentimeter) || pixelsPerCentimeter <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(pixelsPerCentimeter));
        }
        if (canvasPointsCm.Count == 0)
        {
            throw new ArgumentException("Canvas polygon drafting requires points.", nameof(canvasPointsCm));
        }
        double minX = canvasPointsCm.Min(point => point.X);
        double minY = canvasPointsCm.Min(point => point.Y);
        PatternPointDocument[] localVertices = canvasPointsCm
            .Select(point => new PatternPointDocument(point.X - minX, point.Y - minY))
            .ToArray();
        return CreatePolygonPiece(
            id,
            name,
            localVertices,
            seamAllowanceCm,
            cutQuantity,
            mirrored,
            cutOnFold,
            minX * pixelsPerCentimeter,
            minY * pixelsPerCentimeter);
    }

    private static void ValidateCommonInputs(
        string id,
        string name,
        double seamAllowanceCm,
        int cutQuantity,
        double layoutLeft,
        double layoutTop)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            throw new ArgumentException("A drafted piece requires an ID.", nameof(id));
        }
        if (string.IsNullOrWhiteSpace(name))
        {
            throw new ArgumentException("A drafted piece requires a name.", nameof(name));
        }
        if (!double.IsFinite(seamAllowanceCm) || seamAllowanceCm < 0 || seamAllowanceCm > 10)
        {
            throw new ArgumentOutOfRangeException(nameof(seamAllowanceCm), "Seam allowance must be from 0 through 10 centimeters.");
        }
        if (cutQuantity is < 1 or > 20)
        {
            throw new ArgumentOutOfRangeException(nameof(cutQuantity), "Cut quantity must be from 1 through 20.");
        }
        if (!double.IsFinite(layoutLeft) || !double.IsFinite(layoutTop))
        {
            throw new ArgumentOutOfRangeException(nameof(layoutLeft), "Drafted layout values must be finite.");
        }
    }

    private static PatternPointDocument[] NormalizePolygon(IReadOnlyList<PatternPointDocument> vertices)
    {
        List<PatternPointDocument> polygon = vertices.ToList();
        if (polygon.Count > 1 && PointsEqual(polygon[0], polygon[^1]))
        {
            polygon.RemoveAt(polygon.Count - 1);
        }
        if (polygon.Count < 3 || polygon.Any(point => !double.IsFinite(point.X) || !double.IsFinite(point.Y)))
        {
            throw new ArgumentException("A polygon requires at least three finite vertices.", nameof(vertices));
        }
        if (polygon.Select(PointKey).Distinct(StringComparer.Ordinal).Count() != polygon.Count)
        {
            throw new ArgumentException("A polygon cannot contain duplicate vertices.", nameof(vertices));
        }
        for (int index = 0; index < polygon.Count; index++)
        {
            PatternPointDocument previous = polygon[(index - 1 + polygon.Count) % polygon.Count];
            PatternPointDocument current = polygon[index];
            PatternPointDocument next = polygon[(index + 1) % polygon.Count];
            double incomingX = current.X - previous.X;
            double incomingY = current.Y - previous.Y;
            double outgoingX = next.X - current.X;
            double outgoingY = next.Y - current.Y;
            if (Math.Abs(Cross(previous, current, next)) < 0.000000001 &&
                incomingX * outgoingX + incomingY * outgoingY < 0)
            {
                throw new ArgumentException("A polygon boundary cannot reverse across an overlapping edge.", nameof(vertices));
            }
        }
        double signedArea = 0;
        for (int index = 0; index < polygon.Count; index++)
        {
            PatternPointDocument current = polygon[index];
            PatternPointDocument next = polygon[(index + 1) % polygon.Count];
            signedArea += current.X * next.Y - next.X * current.Y;
        }
        if (Math.Abs(signedArea) < 0.000001)
        {
            throw new ArgumentException("A polygon must enclose a nonzero area.", nameof(vertices));
        }
        for (int first = 0; first < polygon.Count; first++)
        {
            int firstNext = (first + 1) % polygon.Count;
            for (int second = first + 1; second < polygon.Count; second++)
            {
                int secondNext = (second + 1) % polygon.Count;
                bool adjacent = first == second || firstNext == second || secondNext == first;
                if (!adjacent && SegmentsIntersect(
                    polygon[first],
                    polygon[firstNext],
                    polygon[second],
                    polygon[secondNext]))
                {
                    throw new ArgumentException("A polygon boundary cannot intersect itself.", nameof(vertices));
                }
            }
        }
        if (signedArea < 0)
        {
            polygon.Reverse();
        }
        return polygon.ToArray();
    }

    private static bool SegmentsIntersect(
        PatternPointDocument a,
        PatternPointDocument b,
        PatternPointDocument c,
        PatternPointDocument d)
    {
        double abC = Cross(a, b, c);
        double abD = Cross(a, b, d);
        double cdA = Cross(c, d, a);
        double cdB = Cross(c, d, b);
        if ((abC > 0 && abD < 0 || abC < 0 && abD > 0) &&
            (cdA > 0 && cdB < 0 || cdA < 0 && cdB > 0))
        {
            return true;
        }
        const double epsilon = 0.000000001;
        return Math.Abs(abC) < epsilon && PointOnSegment(a, b, c) ||
            Math.Abs(abD) < epsilon && PointOnSegment(a, b, d) ||
            Math.Abs(cdA) < epsilon && PointOnSegment(c, d, a) ||
            Math.Abs(cdB) < epsilon && PointOnSegment(c, d, b);
    }

    private static bool PointOnSegment(
        PatternPointDocument start,
        PatternPointDocument end,
        PatternPointDocument point)
    {
        const double epsilon = 0.000000001;
        return point.X >= Math.Min(start.X, end.X) - epsilon &&
            point.X <= Math.Max(start.X, end.X) + epsilon &&
            point.Y >= Math.Min(start.Y, end.Y) - epsilon &&
            point.Y <= Math.Max(start.Y, end.Y) + epsilon;
    }

    private static double Cross(PatternPointDocument a, PatternPointDocument b, PatternPointDocument c)
        => (b.X - a.X) * (c.Y - a.Y) - (b.Y - a.Y) * (c.X - a.X);

    private static string PointKey(PatternPointDocument point)
        => FormattableString.Invariant($"{Math.Round(point.X, 9):R}|{Math.Round(point.Y, 9):R}");

    private static bool PointsEqual(PatternPointDocument first, PatternPointDocument second)
        => Math.Abs(first.X - second.X) < 0.000000001 && Math.Abs(first.Y - second.Y) < 0.000000001;

    public static ClothPanelDocument CreatePanel(
        string panelId,
        PatternPieceDocument piece,
        int placementIndex)
    {
        if (string.IsNullOrWhiteSpace(panelId))
        {
            throw new ArgumentException("A drafted cloth panel requires an ID.", nameof(panelId));
        }
        ArgumentNullException.ThrowIfNull(piece);
        if (placementIndex < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(placementIndex));
        }

        return new ClothPanelDocument(
            panelId,
            piece.Id,
            piece.Name,
            "user-drafted",
            false,
            [])
        {
            SourcePlacement = new PatternPlacement3DDocument(
                (placementIndex % 2 == 0 ? -1 : 1) * 24,
                0,
                105,
                0,
                placementIndex % 2 == 0 ? -90 : 90,
                0,
                "GarmentCode"),
            SourcePatternOrigin = new PatternPointDocument(0, 0),
            SourceLabel = piece.Id.Replace('-', '_')
        };
    }

    private static (PatternPointDocument Start, IReadOnlyList<PatternCurveDocument> Boundary) RectangleBoundary(
        double widthCm,
        double heightCm)
        => (
            new PatternPointDocument(0, 0),
            [
                new PatternCurveDocument("top", "line", new PatternPointDocument(widthCm, 0)),
                new PatternCurveDocument("right", "line", new PatternPointDocument(widthCm, heightCm)),
                new PatternCurveDocument("bottom", "line", new PatternPointDocument(0, heightCm)),
                new PatternCurveDocument("left", "line", new PatternPointDocument(0, 0))
            ]);

    private static (PatternPointDocument Start, IReadOnlyList<PatternCurveDocument> Boundary) EllipseBoundary(
        double widthCm,
        double heightCm)
    {
        double radiusX = widthCm * 0.5;
        double radiusY = heightCm * 0.5;
        double controlX = radiusX * CircleBezierFactor;
        double controlY = radiusY * CircleBezierFactor;
        return (
            new PatternPointDocument(radiusX, 0),
            [
                new PatternCurveDocument(
                    "upper-right",
                    "cubic",
                    new PatternPointDocument(widthCm, radiusY),
                    new PatternPointDocument(radiusX + controlX, 0),
                    new PatternPointDocument(widthCm, radiusY - controlY)),
                new PatternCurveDocument(
                    "lower-right",
                    "cubic",
                    new PatternPointDocument(radiusX, heightCm),
                    new PatternPointDocument(widthCm, radiusY + controlY),
                    new PatternPointDocument(radiusX + controlX, heightCm)),
                new PatternCurveDocument(
                    "lower-left",
                    "cubic",
                    new PatternPointDocument(0, radiusY),
                    new PatternPointDocument(radiusX - controlX, heightCm),
                    new PatternPointDocument(0, radiusY + controlY)),
                new PatternCurveDocument(
                    "upper-left",
                    "cubic",
                    new PatternPointDocument(radiusX, 0),
                    new PatternPointDocument(0, radiusY - controlY),
                    new PatternPointDocument(radiusX - controlX, 0))
            ]);
    }
}
