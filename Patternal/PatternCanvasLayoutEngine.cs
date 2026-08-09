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
    double Utilization);

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
    {
        if (canvasWidth <= 0 || canvasHeight <= 0 ||
            viewportWidth <= 0 || viewportHeight <= 0 ||
            placement.Width <= 0 || placement.Height <= 0 ||
            minimumZoomFactor <= 0 || maximumZoomFactor < minimumZoomFactor)
        {
            throw new ArgumentOutOfRangeException(nameof(canvasWidth));
        }

        double availableWidth = Math.Max(1, viewportWidth - viewportPadding);
        double availableHeight = Math.Max(1, viewportHeight - viewportPadding);
        float zoomFactor = (float)Math.Clamp(
            Math.Min(availableWidth / placement.Width, availableHeight / placement.Height),
            minimumZoomFactor,
            maximumZoomFactor);
        double horizontalOffset = Math.Clamp(
            (placement.Left + placement.Width / 2) * zoomFactor - viewportWidth / 2,
            0,
            Math.Max(0, canvasWidth * zoomFactor - viewportWidth));
        double verticalOffset = Math.Clamp(
            (placement.Top + placement.Height / 2) * zoomFactor - viewportHeight / 2,
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
        double widestItem = items.Select(item => item.Width).DefaultIfEmpty(0).Max();
        double canvasWidth = Math.Max(minimumCanvasWidth, widestItem + OuterMargin * 2);
        double rightEdge = canvasWidth - OuterMargin;
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

        double contentBottom = shelves.Select(shelf => shelf.Top + shelf.Height).DefaultIfEmpty(0).Max();
        double canvasHeight = Math.Max(minimumCanvasHeight, contentBottom + OuterMargin);
        double occupiedArea = items.Sum(item => item.Width * item.Height);
        double utilization = occupiedArea / (canvasWidth * canvasHeight);
        return new PatternCanvasLayoutResult(placements, canvasWidth, canvasHeight, utilization);
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

    private sealed class Shelf(double top, double height, double nextX)
    {
        public double Top { get; } = top;

        public double Height { get; } = height;

        public double NextX { get; set; } = nextX;
    }
}
