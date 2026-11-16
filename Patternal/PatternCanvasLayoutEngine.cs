namespace Patterna;

public sealed record PatternCanvasPlacement(
    double Left,
    double Top,
    double Width,
    double Height,
    double ContentOffsetX,
    double ContentOffsetY);

public sealed record PatternCanvasLayoutResult(
    IReadOnlyDictionary<string, PatternCanvasPlacement> Placements,
    double CanvasWidth,
    double CanvasHeight,
    PatternCanvasBounds ContentBounds,
    double Utilization);

public sealed record PatternCanvasBounds(
    double Left,
    double Top,
    double Width,
    double Height);

public sealed record PatternCanvasFrameResult(
    float ZoomFactor,
    double HorizontalOffset,
    double VerticalOffset);

public static class PatternCanvasLayoutEngine
{
    private const double OuterMargin = 18;
    private const double ItemGap = 12;
    private const double HeaderHeight = 26;
    private const double ContentPadding = 10;
    private const double MinimumItemWidth = 132;

    public static PatternCanvasFrameResult Frame(
        PatternCanvasPlacement placement,
        double canvasWidth,
        double canvasHeight,
        double viewportWidth,
        double viewportHeight,
        float minimumZoomFactor,
        float maximumZoomFactor,
        double viewportPadding = 48)
        => FrameBounds(
            new PatternCanvasBounds(
                placement.Left,
                placement.Top,
                placement.Width,
                placement.Height),
            canvasWidth,
            canvasHeight,
            viewportWidth,
            viewportHeight,
            minimumZoomFactor,
            maximumZoomFactor,
            viewportPadding);

    public static PatternCanvasFrameResult FrameAll(
        PatternCanvasLayoutResult layout,
        double viewportWidth,
        double viewportHeight,
        float minimumZoomFactor,
        float maximumZoomFactor,
        double viewportPadding = 48)
        => FrameBounds(
            layout.ContentBounds,
            layout.CanvasWidth,
            layout.CanvasHeight,
            viewportWidth,
            viewportHeight,
            minimumZoomFactor,
            maximumZoomFactor,
            viewportPadding);

    private static PatternCanvasFrameResult FrameBounds(
        PatternCanvasBounds bounds,
        double canvasWidth,
        double canvasHeight,
        double viewportWidth,
        double viewportHeight,
        float minimumZoomFactor,
        float maximumZoomFactor,
        double viewportPadding)
    {
        if (canvasWidth <= 0 || canvasHeight <= 0 ||
            viewportWidth <= 0 || viewportHeight <= 0 ||
            bounds.Width <= 0 || bounds.Height <= 0 ||
            bounds.Left < 0 || bounds.Top < 0 ||
            bounds.Left + bounds.Width > canvasWidth ||
            bounds.Top + bounds.Height > canvasHeight ||
            minimumZoomFactor <= 0 || maximumZoomFactor < minimumZoomFactor ||
            viewportPadding < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(canvasWidth));
        }

        double availableWidth = Math.Max(1, viewportWidth - viewportPadding);
        double availableHeight = Math.Max(1, viewportHeight - viewportPadding);
        float zoomFactor = (float)Math.Clamp(
            Math.Min(availableWidth / bounds.Width, availableHeight / bounds.Height),
            minimumZoomFactor,
            maximumZoomFactor);
        double horizontalOffset = Math.Clamp(
            (bounds.Left + bounds.Width / 2) * zoomFactor - viewportWidth / 2,
            0,
            Math.Max(0, canvasWidth * zoomFactor - viewportWidth));
        double verticalOffset = Math.Clamp(
            (bounds.Top + bounds.Height / 2) * zoomFactor - viewportHeight / 2,
            0,
            Math.Max(0, canvasHeight * zoomFactor - viewportHeight));
        return new PatternCanvasFrameResult(zoomFactor, horizontalOffset, verticalOffset);
    }

    public static PatternCanvasLayoutResult Arrange(
        IReadOnlyList<PatternPieceDocument> pieces,
        double minimumCanvasWidth,
        double minimumCanvasHeight,
        double pixelsPerCentimeter)
    {
        if (minimumCanvasWidth <= 0 || minimumCanvasHeight <= 0 || pixelsPerCentimeter <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(minimumCanvasWidth));
        }

        LayoutItem[] items = pieces
            .Select(piece => CreateItem(piece, pixelsPerCentimeter))
            .OrderByDescending(item => item.Height)
            .ThenByDescending(item => item.Width)
            .ThenBy(item => item.Piece.Id, StringComparer.Ordinal)
            .ToArray();
        double occupiedArea = items.Sum(item => item.Width * item.Height);
        double widestItem = items.Select(item => item.Width).DefaultIfEmpty(0).Max();
        double targetAspectRatio = minimumCanvasWidth / minimumCanvasHeight;
        double idealPackingWidth = Math.Sqrt(
            Math.Max(1, occupiedArea) / 0.58 * targetAspectRatio);
        double minimumPackingWidth = Math.Max(
            widestItem + OuterMargin * 2,
            Math.Min(minimumCanvasWidth, idealPackingWidth * 0.65));
        double maximumPackingWidth = Math.Max(
            minimumCanvasWidth,
            Math.Max(minimumPackingWidth, idealPackingWidth * 1.35));
        PackingCandidate? best = null;
        const int candidateCount = 25;
        for (int index = 0; index < candidateCount; index++)
        {
            double amount = candidateCount == 1 ? 0 : (double)index / (candidateCount - 1);
            double packingWidth = minimumPackingWidth + (maximumPackingWidth - minimumPackingWidth) * amount;
            PackingCandidate candidate = Pack(items, packingWidth, targetAspectRatio, occupiedArea);
            if (best is null ||
                candidate.Score < best.Score - 0.000001 ||
                Math.Abs(candidate.Score - best.Score) <= 0.000001 && candidate.Area < best.Area)
            {
                best = candidate;
            }
        }

        PackingCandidate packed = best ?? Pack(
            items,
            Math.Max(minimumCanvasWidth, widestItem + OuterMargin * 2),
            targetAspectRatio,
            occupiedArea);
        double canvasWidth = Math.Max(
            minimumCanvasWidth,
            packed.ContentBounds.Left + packed.ContentBounds.Width + OuterMargin);
        double canvasHeight = Math.Max(
            minimumCanvasHeight,
            packed.ContentBounds.Top + packed.ContentBounds.Height + OuterMargin);
        double utilization = occupiedArea / (canvasWidth * canvasHeight);
        return new PatternCanvasLayoutResult(
            packed.Placements,
            canvasWidth,
            canvasHeight,
            packed.ContentBounds,
            utilization);
    }

    private static PackingCandidate Pack(
        IReadOnlyList<LayoutItem> items,
        double packingWidth,
        double targetAspectRatio,
        double occupiedArea)
    {
        double rightEdge = packingWidth - OuterMargin;
        List<Shelf> shelves = [];
        Dictionary<string, PatternCanvasPlacement> placements = new(StringComparer.OrdinalIgnoreCase);
        foreach (LayoutItem item in items)
        {
            Shelf? shelf = shelves
                .Where(candidate => item.Height <= candidate.Height && candidate.NextX + item.Width <= rightEdge)
                .OrderBy(candidate => rightEdge - candidate.NextX - item.Width)
                .FirstOrDefault();
            if (shelf is null)
            {
                double top = shelves.Count == 0
                    ? OuterMargin
                    : shelves.Max(candidate => candidate.Top + candidate.Height) + ItemGap;
                shelf = new Shelf(top, item.Height, OuterMargin);
                shelves.Add(shelf);
            }

            placements[item.Piece.Id] = new PatternCanvasPlacement(
                shelf.NextX,
                shelf.Top,
                item.Width,
                item.Height,
                ContentPadding - item.MinimumX,
                HeaderHeight + ContentPadding - item.MinimumY);
            shelf.NextX += item.Width + ItemGap;
        }

        double contentRight = placements.Values
            .Select(placement => placement.Left + placement.Width)
            .DefaultIfEmpty(OuterMargin + 1)
            .Max();
        double contentBottom = placements.Values
            .Select(placement => placement.Top + placement.Height)
            .DefaultIfEmpty(OuterMargin + 1)
            .Max();
        PatternCanvasBounds bounds = new(
            OuterMargin,
            OuterMargin,
            Math.Max(1, contentRight - OuterMargin),
            Math.Max(1, contentBottom - OuterMargin));
        double area = bounds.Width * bounds.Height;
        double aspectRatio = bounds.Width / bounds.Height;
        double aspectError = Math.Abs(Math.Log(aspectRatio / targetAspectRatio));
        double contentUtilization = Math.Clamp(occupiedArea / area, 0, 1);
        double score = aspectError + (1 - contentUtilization) * 0.18;
        return new PackingCandidate(placements, bounds, area, score);
    }

    private static LayoutItem CreateItem(PatternPieceDocument piece, double pixelsPerCentimeter)
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

        double minimumX = points.Min(point => point.X) * piece.ScaleX * pixelsPerCentimeter;
        double maximumX = points.Max(point => point.X) * piece.ScaleX * pixelsPerCentimeter;
        double minimumY = points.Min(point => point.Y) * piece.ScaleY * pixelsPerCentimeter;
        double maximumY = points.Max(point => point.Y) * piece.ScaleY * pixelsPerCentimeter;
        double estimatedLabelWidth = Math.Clamp(piece.Name.Length * 7.2 + 24, MinimumItemWidth, 220);
        return new LayoutItem(
            piece,
            Math.Max(estimatedLabelWidth, maximumX - minimumX + ContentPadding * 2),
            HeaderHeight + maximumY - minimumY + ContentPadding * 2,
            minimumX,
            minimumY);
    }

    private sealed record LayoutItem(
        PatternPieceDocument Piece,
        double Width,
        double Height,
        double MinimumX,
        double MinimumY);

    private sealed record PackingCandidate(
        IReadOnlyDictionary<string, PatternCanvasPlacement> Placements,
        PatternCanvasBounds ContentBounds,
        double Area,
        double Score);

    private sealed class Shelf(double top, double height, double nextX)
    {
        public double Top { get; } = top;

        public double Height { get; } = height;

        public double NextX { get; set; } = nextX;
    }
}
