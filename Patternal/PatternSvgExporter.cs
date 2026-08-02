using System.Globalization;
using System.Net;
using System.Text;

namespace Patterna;

public sealed record PatternSvgExportOptions(
    bool ShowSeamAllowance = true,
    bool ShowConstruction = true,
    double PageWidthMm = 1200,
    double MarginMm = 20,
    double PieceGapMm = 20);

public static class PatternSvgExporter
{
    private const double MillimetersPerCentimeter = 10;

    public static string Export(
        GarmentDocument document,
        string metadata,
        PatternSvgExportOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(document);
        options ??= new PatternSvgExportOptions();
        ValidateOptions(options);
        IReadOnlyList<string> errors = document.Validate();
        if (errors.Count > 0)
        {
            throw new InvalidOperationException(string.Join(Environment.NewLine, errors));
        }

        IReadOnlyDictionary<string, PiecePlacement> placements = PackPieces(document.Pieces, options, out double pageHeightMm);
        StringBuilder svg = new();
        svg.AppendLine("<?xml version=\"1.0\" encoding=\"UTF-8\"?>");
        svg.AppendLine(
            $"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{Number(options.PageWidthMm)}mm\" " +
            $"height=\"{Number(pageHeightMm)}mm\" viewBox=\"0 0 {Number(options.PageWidthMm)} {Number(pageHeightMm)}\">");
        svg.AppendLine($"  <metadata>{WebUtility.HtmlEncode(metadata)}</metadata>");
        svg.AppendLine("  <g id=\"pattern-pieces\" fill=\"none\" stroke-linejoin=\"round\">");
        foreach (PatternPieceDocument piece in document.Pieces)
        {
            PiecePlacement placement = placements[piece.Id];
            string boundary = BuildPath(piece, piece.Start, piece.Boundary, true, placement);
            if (options.ShowSeamAllowance && piece.SeamAllowanceCm > 0)
            {
                svg.AppendLine(
                    $"    <path class=\"seam-allowance-zone\" data-piece-id=\"{Attribute(piece.Id)}\" " +
                    $"data-seam-allowance-cm=\"{Number(piece.SeamAllowanceCm)}\" d=\"{boundary}\" " +
                    $"stroke=\"#8a829f\" stroke-width=\"{Number(piece.SeamAllowanceCm * MillimetersPerCentimeter * 2)}\" " +
                    "stroke-dasharray=\"5 5\" stroke-opacity=\"0.28\" />");
            }
            svg.AppendLine(
                $"    <path class=\"seam-line\" data-piece-id=\"{Attribute(piece.Id)}\" d=\"{boundary}\" " +
                "stroke=\"#241f38\" stroke-width=\"0.45\" />");
        }
        svg.AppendLine("  </g>");

        if (options.ShowConstruction)
        {
            AppendConstruction(svg, document.Pieces, placements);
        }
        AppendLabels(svg, document.Pieces, placements);
        svg.AppendLine("</svg>");
        return svg.ToString();
    }

    private static void AppendConstruction(
        StringBuilder svg,
        IReadOnlyList<PatternPieceDocument> pieces,
        IReadOnlyDictionary<string, PiecePlacement> placements)
    {
        svg.AppendLine("  <g id=\"construction\" fill=\"none\" stroke=\"#655d79\" stroke-width=\"0.35\">");
        foreach (PatternPieceDocument piece in pieces)
        {
            PiecePlacement placement = placements[piece.Id];
            foreach (PatternInternalPathDocument path in piece.InternalPaths)
            {
                string dash = path.Kind is PatternInternalPathKinds.Construction or PatternInternalPathKinds.Fold
                    ? " stroke-dasharray=\"4 3\""
                    : string.Empty;
                svg.AppendLine(
                    $"    <path class=\"internal-{Attribute(path.Kind)}\" data-path-id=\"{Attribute(path.Id)}\" " +
                    $"d=\"{BuildPath(piece, path.Start, path.Segments, path.Closed, placement)}\"{dash} />");
            }
            foreach (PatternDartDocument dart in piece.Darts)
            {
                PatternPointDocument first = EvaluateBoundaryPoint(piece, dart.FirstLegBoundaryCurveId, dart.FirstLegParameter);
                PatternPointDocument second = EvaluateBoundaryPoint(piece, dart.SecondLegBoundaryCurveId, dart.SecondLegParameter);
                ExportPoint firstPoint = Transform(first, piece, placement);
                ExportPoint secondPoint = Transform(second, piece, placement);
                ExportPoint apexPoint = Transform(dart.Apex, piece, placement);
                svg.AppendLine(
                    $"    <path class=\"dart\" data-dart-id=\"{Attribute(dart.Id)}\" " +
                    $"d=\"M {Number(firstPoint.X)} {Number(firstPoint.Y)} L {Number(apexPoint.X)} {Number(apexPoint.Y)} " +
                    $"M {Number(secondPoint.X)} {Number(secondPoint.Y)} L {Number(apexPoint.X)} {Number(apexPoint.Y)}\" " +
                    "stroke-dasharray=\"3 2\" />");
            }
            if (piece.Grainline is not null && piece.Layout.ShowGrainline)
            {
                ExportPoint start = Transform(piece.Grainline.Start, piece, placement);
                ExportPoint end = Transform(piece.Grainline.End, piece, placement);
                svg.AppendLine(
                    $"    <line class=\"grainline\" x1=\"{Number(start.X)}\" y1=\"{Number(start.Y)}\" " +
                    $"x2=\"{Number(end.X)}\" y2=\"{Number(end.Y)}\" />");
            }
            AppendNotches(svg, piece, placement);
        }
        svg.AppendLine("  </g>");
    }

    private static void AppendNotches(StringBuilder svg, PatternPieceDocument piece, PiecePlacement placement)
    {
        foreach (PatternNotchDocument notch in piece.Notches)
        {
            int curveIndex = piece.Boundary
                .Select((curve, index) => new { curve.Id, Index = index })
                .First(item => string.Equals(item.Id, notch.BoundaryCurveId, StringComparison.OrdinalIgnoreCase))
                .Index;
            PatternPointDocument curveStart = curveIndex == 0 ? piece.Start : piece.Boundary[curveIndex - 1].End;
            PatternCurveDocument curve = piece.Boundary[curveIndex];
            PatternPointDocument point = EvaluateCurvePoint(curveStart, curve, notch.Parameter);
            PatternPointDocument tangent = EvaluateCurveTangent(curveStart, curve, notch.Parameter);
            double tangentLength = Math.Sqrt(tangent.X * tangent.X + tangent.Y * tangent.Y);
            if (tangentLength < 0.000001)
            {
                continue;
            }
            double tangentX = tangent.X / tangentLength;
            double tangentY = tangent.Y / tangentLength;
            double normalX = -tangentY;
            double normalY = tangentX;
            double spacing = Math.Max(0.16, notch.WidthCm);
            for (int index = 0; index < notch.Count; index++)
            {
                double tangentOffset = (index - (notch.Count - 1) * 0.5) * spacing;
                PatternPointDocument localStart = new(
                    point.X + tangentX * tangentOffset - normalX * notch.DepthCm * 0.15,
                    point.Y + tangentY * tangentOffset - normalY * notch.DepthCm * 0.15);
                PatternPointDocument localEnd = new(
                    point.X + tangentX * tangentOffset + normalX * notch.DepthCm,
                    point.Y + tangentY * tangentOffset + normalY * notch.DepthCm);
                ExportPoint start = Transform(localStart, piece, placement);
                ExportPoint end = Transform(localEnd, piece, placement);
                svg.AppendLine(
                    $"    <line class=\"notch\" data-notch-id=\"{Attribute(notch.Id)}\" " +
                    $"x1=\"{Number(start.X)}\" y1=\"{Number(start.Y)}\" " +
                    $"x2=\"{Number(end.X)}\" y2=\"{Number(end.Y)}\" stroke-width=\"0.55\" />");
            }
        }
    }

    private static void AppendLabels(
        StringBuilder svg,
        IReadOnlyList<PatternPieceDocument> pieces,
        IReadOnlyDictionary<string, PiecePlacement> placements)
    {
        svg.AppendLine("  <g id=\"labels\" fill=\"#241f38\" font-family=\"Segoe UI\" font-size=\"4\">");
        foreach (PatternPieceDocument piece in pieces)
        {
            PiecePlacement placement = placements[piece.Id];
            double x = placement.OffsetX + placement.WidthMm * 0.5;
            double y = placement.OffsetY + placement.HeightMm * 0.5;
            string instruction = piece.CutOnFold
                ? $"{piece.Name.ToUpperInvariant()} | CUT {piece.CutQuantity} ON FOLD"
                : $"{piece.Name.ToUpperInvariant()} | CUT {piece.CutQuantity}{(piece.Mirrored ? " MIRRORED" : string.Empty)}";
            svg.AppendLine(
                $"    <text x=\"{Number(x)}\" y=\"{Number(y)}\" text-anchor=\"middle\">{WebUtility.HtmlEncode(instruction)}</text>");
        }
        svg.AppendLine("  </g>");
    }

    private static string BuildPath(
        PatternPieceDocument piece,
        PatternPointDocument start,
        IReadOnlyList<PatternCurveDocument> curves,
        bool closed,
        PiecePlacement placement)
    {
        StringBuilder path = new();
        ExportPoint exportStart = Transform(start, piece, placement);
        path.Append($"M {Number(exportStart.X)} {Number(exportStart.Y)}");
        foreach (PatternCurveDocument curve in curves)
        {
            ExportPoint end = Transform(curve.End, piece, placement);
            if (string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase))
            {
                path.Append($" L {Number(end.X)} {Number(end.Y)}");
            }
            else if (curve.Control1 is not null && curve.Control2 is not null)
            {
                ExportPoint control1 = Transform(curve.Control1, piece, placement);
                ExportPoint control2 = Transform(curve.Control2, piece, placement);
                path.Append(
                    $" C {Number(control1.X)} {Number(control1.Y)}" +
                    $" {Number(control2.X)} {Number(control2.Y)}" +
                    $" {Number(end.X)} {Number(end.Y)}");
            }
        }
        if (closed)
        {
            path.Append(" Z");
        }
        return path.ToString();
    }

    private static IReadOnlyDictionary<string, PiecePlacement> PackPieces(
        IReadOnlyList<PatternPieceDocument> pieces,
        PatternSvgExportOptions options,
        out double pageHeightMm)
    {
        Dictionary<string, PiecePlacement> placements = new(StringComparer.OrdinalIgnoreCase);
        double x = options.MarginMm;
        double y = options.MarginMm;
        double rowHeight = 0;
        double availableRight = options.PageWidthMm - options.MarginMm;
        foreach (PatternPieceDocument piece in pieces)
        {
            PieceBounds bounds = GetBounds(piece);
            double widthMm = Math.Max(1, bounds.Width * piece.ScaleX * MillimetersPerCentimeter);
            double heightMm = Math.Max(1, bounds.Height * piece.ScaleY * MillimetersPerCentimeter);
            if (x > options.MarginMm && x + widthMm > availableRight)
            {
                x = options.MarginMm;
                y += rowHeight + options.PieceGapMm;
                rowHeight = 0;
            }
            if (widthMm > options.PageWidthMm - options.MarginMm * 2)
            {
                throw new InvalidOperationException($"Pattern piece {piece.Id} is wider than the configured SVG page.");
            }
            placements.Add(piece.Id, new PiecePlacement(x, y, bounds.MinX, bounds.MinY, widthMm, heightMm));
            x += widthMm + options.PieceGapMm;
            rowHeight = Math.Max(rowHeight, heightMm);
        }
        pageHeightMm = Math.Max(options.MarginMm * 2 + 1, y + rowHeight + options.MarginMm);
        return placements;
    }

    private static PieceBounds GetBounds(PatternPieceDocument piece)
    {
        List<PatternPointDocument> points = [piece.Start];
        foreach (PatternCurveDocument curve in piece.Boundary)
        {
            points.Add(curve.End);
            if (curve.Control1 is not null)
            {
                points.Add(curve.Control1);
            }
            if (curve.Control2 is not null)
            {
                points.Add(curve.Control2);
            }
        }
        double minX = points.Min(point => point.X);
        double minY = points.Min(point => point.Y);
        double maxX = points.Max(point => point.X);
        double maxY = points.Max(point => point.Y);
        return new PieceBounds(minX, minY, maxX, maxY);
    }

    private static ExportPoint Transform(
        PatternPointDocument point,
        PatternPieceDocument piece,
        PiecePlacement placement)
        => new(
            placement.OffsetX + (point.X - placement.MinX) * piece.ScaleX * MillimetersPerCentimeter,
            placement.OffsetY + (point.Y - placement.MinY) * piece.ScaleY * MillimetersPerCentimeter);

    private static PatternPointDocument EvaluateBoundaryPoint(
        PatternPieceDocument piece,
        string curveId,
        double parameter)
    {
        int curveIndex = piece.Boundary
            .Select((curve, index) => new { curve.Id, Index = index })
            .First(item => string.Equals(item.Id, curveId, StringComparison.OrdinalIgnoreCase))
            .Index;
        PatternPointDocument start = curveIndex == 0 ? piece.Start : piece.Boundary[curveIndex - 1].End;
        return EvaluateCurvePoint(start, piece.Boundary[curveIndex], parameter);
    }

    private static PatternPointDocument EvaluateCurvePoint(
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

    private static PatternPointDocument EvaluateCurveTangent(
        PatternPointDocument start,
        PatternCurveDocument curve,
        double parameter)
    {
        if (string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase))
        {
            return new PatternPointDocument(curve.End.X - start.X, curve.End.Y - start.Y);
        }
        PatternPointDocument control1 = curve.Control1
            ?? throw new InvalidOperationException($"Cubic curve {curve.Id} is missing its first control point.");
        PatternPointDocument control2 = curve.Control2
            ?? throw new InvalidOperationException($"Cubic curve {curve.Id} is missing its second control point.");
        double inverse = 1 - parameter;
        return new PatternPointDocument(
            3 * inverse * inverse * (control1.X - start.X) +
                6 * inverse * parameter * (control2.X - control1.X) +
                3 * parameter * parameter * (curve.End.X - control2.X),
            3 * inverse * inverse * (control1.Y - start.Y) +
                6 * inverse * parameter * (control2.Y - control1.Y) +
                3 * parameter * parameter * (curve.End.Y - control2.Y));
    }

    private static void ValidateOptions(PatternSvgExportOptions options)
    {
        if (!double.IsFinite(options.PageWidthMm) || options.PageWidthMm <= 0 ||
            !double.IsFinite(options.MarginMm) || options.MarginMm < 0 ||
            !double.IsFinite(options.PieceGapMm) || options.PieceGapMm < 0 ||
            options.PageWidthMm <= options.MarginMm * 2)
        {
            throw new ArgumentOutOfRangeException(nameof(options), "SVG page dimensions are invalid.");
        }
    }

    private static string Number(double value)
        => value.ToString("0.###", CultureInfo.InvariantCulture);

    private static string Attribute(string value)
        => WebUtility.HtmlEncode(value);

    private sealed record PieceBounds(double MinX, double MinY, double MaxX, double MaxY)
    {
        public double Width => MaxX - MinX;
        public double Height => MaxY - MinY;
    }

    private sealed record PiecePlacement(
        double OffsetX,
        double OffsetY,
        double MinX,
        double MinY,
        double WidthMm,
        double HeightMm);

    private sealed record ExportPoint(double X, double Y);
}
