using Patterna;
using CDT;

namespace Patterna.UnrealGarmentCompiler;

public readonly record struct StructuredPoint2(double X, double Y)
{
    public static StructuredPoint2 operator +(StructuredPoint2 first, StructuredPoint2 second)
        => new(first.X + second.X, first.Y + second.Y);

    public static StructuredPoint2 operator -(StructuredPoint2 first, StructuredPoint2 second)
        => new(first.X - second.X, first.Y - second.Y);

    public static StructuredPoint2 operator *(StructuredPoint2 point, double scale)
        => new(point.X * scale, point.Y * scale);
}

public sealed record StructuredPanelVertex(
    int Index,
    double X,
    double Y,
    double U,
    double V);

public sealed record StructuredPanelTriangle(
    int A,
    int B,
    int C,
    double AreaCm2,
    double AspectRatio);

public sealed record StructuredPanelMesh(
    string PanelId,
    string PieceId,
    int Columns,
    int Rows,
    IReadOnlyList<StructuredPanelVertex> Vertices,
    IReadOnlyList<StructuredPanelTriangle> Triangles,
    IReadOnlyDictionary<string, IReadOnlyList<int>> EdgeVertexIndices,
    double MinimumTriangleAreaCm2,
    double MaximumTriangleAspectRatio,
    double MinimumSignedDoubleAreaCm2,
    double MaximumBoundaryDeviationCm);

public static class StructuredPanelRemesher
{
    private const double AdaptiveEdgeLengthCm = 1.5;
    private const double InteriorPointBoundaryClearanceCm = 0.55;
    private sealed record PatchDefinition(
        IReadOnlyList<string> Top,
        IReadOnlyList<string> Right,
        IReadOnlyList<string> Bottom,
        IReadOnlyList<string> Left,
        int Columns,
        int Rows);

    private sealed record BoundaryChain(
        IReadOnlyList<StructuredPoint2> Points,
        IReadOnlyDictionary<string, IReadOnlyList<int>> EdgePositions);

    private static readonly IReadOnlyDictionary<string, PatchDefinition> PatchDefinitions =
        new Dictionary<string, PatchDefinition>(StringComparer.OrdinalIgnoreCase)
        {
            ["bodice-front"] = new(
                ["shoulder"],
                ["armhole", "side", "tie-anchor"],
                ["waist"],
                ["center-front", "neckline"],
                16,
                48),
            ["bodice-back"] = new(
                ["shoulder-left", "neckline", "shoulder-right"],
                ["armhole-right", "side-right", "tie-anchor-right"],
                ["waist"],
                ["tie-anchor-left", "side-left", "armhole-left"],
                48,
                56),
            ["skirt"] = new(
                ["waist"],
                ["side-outer"],
                ["hem"],
                ["wrap-edge"],
                48,
                48),
            ["skirt-back"] = new(
                ["waist"],
                ["side-right"],
                ["hem"],
                ["side-left"],
                48,
                48),
            ["waist-tie"] = new(
                ["top"],
                ["outer-end"],
                ["bottom"],
                ["inner-end"],
                72,
                8)
        };

    public static StructuredPanelMesh Remesh(CompiledPatternPanel panel)
    {
        ArgumentNullException.ThrowIfNull(panel);
        if (!PatchDefinitions.TryGetValue(panel.PieceId, out PatchDefinition? definition) ||
            !CanApplyPatchDefinition(panel, definition))
        {
            return PreserveCompiledTopology(panel);
        }

        BoundaryChain top = BuildBoundaryChain(panel, definition.Top, definition.Columns, false);
        BoundaryChain right = BuildBoundaryChain(panel, definition.Right, definition.Rows, false);
        BoundaryChain bottom = BuildBoundaryChain(panel, definition.Bottom, definition.Columns, true);
        BoundaryChain left = BuildBoundaryChain(panel, definition.Left, definition.Rows, true);

        StructuredPoint2 topLeft = top.Points[0];
        StructuredPoint2 topRight = top.Points[^1];
        StructuredPoint2 bottomLeft = bottom.Points[0];
        StructuredPoint2 bottomRight = bottom.Points[^1];
        double maximumBoundaryDeviation = new[]
        {
            Distance(topLeft, left.Points[0]),
            Distance(topRight, right.Points[0]),
            Distance(bottomLeft, left.Points[^1]),
            Distance(bottomRight, right.Points[^1])
        }.Max();
        if (maximumBoundaryDeviation > 0.001)
        {
            throw new InvalidOperationException(
                $"Panel {panel.Id} patch boundaries disagree at a corner by {maximumBoundaryDeviation:F4} cm.");
        }

        int columns = definition.Columns;
        int rows = definition.Rows;
        List<StructuredPanelVertex> vertices = new((columns + 1) * (rows + 1));
        for (int row = 0; row <= rows; row++)
        {
            double v = row / (double)rows;
            StructuredPoint2 leftPoint = left.Points[row];
            StructuredPoint2 rightPoint = right.Points[row];
            for (int column = 0; column <= columns; column++)
            {
                double u = column / (double)columns;
                StructuredPoint2 topPoint = top.Points[column];
                StructuredPoint2 bottomPoint = bottom.Points[column];
                StructuredPoint2 bilinear =
                    topLeft * ((1 - u) * (1 - v)) +
                    topRight * (u * (1 - v)) +
                    bottomLeft * ((1 - u) * v) +
                    bottomRight * (u * v);
                StructuredPoint2 point =
                    topPoint * (1 - v) +
                    bottomPoint * v +
                    leftPoint * (1 - u) +
                    rightPoint * u -
                    bilinear;
                int index = GridIndex(column, row, columns);
                vertices.Add(new StructuredPanelVertex(index, point.X, point.Y, u, v));
            }
        }

        List<StructuredPanelTriangle> triangles = new(columns * rows * 2);
        double orientation = 0;
        double minimumSignedDoubleArea = double.PositiveInfinity;
        for (int row = 0; row < rows; row++)
        {
            for (int column = 0; column < columns; column++)
            {
                int topLeftIndex = GridIndex(column, row, columns);
                int topRightIndex = GridIndex(column + 1, row, columns);
                int bottomLeftIndex = GridIndex(column, row + 1, columns);
                int bottomRightIndex = GridIndex(column + 1, row + 1, columns);
                AddTriangle(vertices, triangles, topLeftIndex, topRightIndex, bottomLeftIndex, ref orientation, ref minimumSignedDoubleArea);
                AddTriangle(vertices, triangles, topRightIndex, bottomRightIndex, bottomLeftIndex, ref orientation, ref minimumSignedDoubleArea);
            }
        }

        Dictionary<string, IReadOnlyList<int>> edgeVertexIndices = new(StringComparer.OrdinalIgnoreCase);
        AddBoundaryEdges(edgeVertexIndices, top, position => GridIndex(position, 0, columns));
        AddBoundaryEdges(edgeVertexIndices, right, position => GridIndex(columns, position, columns));
        AddBoundaryEdges(edgeVertexIndices, bottom, position => GridIndex(position, rows, columns));
        AddBoundaryEdges(edgeVertexIndices, left, position => GridIndex(0, position, columns));

        return new StructuredPanelMesh(
            panel.Id,
            panel.PieceId,
            columns,
            rows,
            vertices,
            triangles,
            edgeVertexIndices,
            triangles.Min(triangle => triangle.AreaCm2),
            triangles.Max(triangle => triangle.AspectRatio),
            minimumSignedDoubleArea,
            maximumBoundaryDeviation);
    }

    public static StructuredPanelMesh Remesh(
        CompiledPatternPanel panel,
        PatternAwareMeshDocument? patternAwareMesh)
    {
        ArgumentNullException.ThrowIfNull(panel);
        return patternAwareMesh is null
            ? Remesh(panel)
            : FromPatternAwareMesh(panel, patternAwareMesh.RequirePanel(panel.Id));
    }

    private static StructuredPanelMesh FromPatternAwareMesh(
        CompiledPatternPanel panel,
        PatternAwareMeshPanel source)
    {
        if (!source.PieceId.Equals(panel.PieceId, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                $"Pattern-aware panel {source.PanelId} belongs to piece {source.PieceId}, not {panel.PieceId}.");
        }
        string[] missingEdges = panel.Edges
            .Where(edge => !source.EdgeVertexIndices.ContainsKey(edge.Id))
            .Select(edge => edge.Id)
            .ToArray();
        if (missingEdges.Length > 0)
        {
            throw new InvalidOperationException(
                $"Pattern-aware panel {source.PanelId} omits named edges: {string.Join(", ", missingEdges)}.");
        }

        StructuredPanelVertex[] vertices = source.Vertices
            .Select((vertex, index) => new StructuredPanelVertex(
                index,
                vertex.X,
                vertex.Y,
                vertex.U,
                vertex.V))
            .ToArray();
        List<StructuredPanelTriangle> triangles = new(source.Triangles.Length);
        double orientation = 0;
        double minimumSignedDoubleArea = double.PositiveInfinity;
        foreach (int[] triangle in source.Triangles)
        {
            AddTriangle(
                vertices,
                triangles,
                triangle[0],
                triangle[1],
                triangle[2],
                ref orientation,
                ref minimumSignedDoubleArea);
        }
        return new StructuredPanelMesh(
            panel.Id,
            panel.PieceId,
            0,
            0,
            vertices,
            triangles,
            source.EdgeVertexIndices.ToDictionary(
                pair => pair.Key,
                pair => (IReadOnlyList<int>)pair.Value,
                StringComparer.OrdinalIgnoreCase),
            triangles.Min(triangle => triangle.AreaCm2),
            triangles.Max(triangle => triangle.AspectRatio),
            minimumSignedDoubleArea,
            0);
    }

    private static bool CanApplyPatchDefinition(CompiledPatternPanel panel, PatchDefinition definition)
    {
        HashSet<string> availableEdges = panel.Edges
            .Select(edge => edge.Id)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        return definition.Top
            .Concat(definition.Right)
            .Concat(definition.Bottom)
            .Concat(definition.Left)
            .All(availableEdges.Contains);
    }

    private static StructuredPanelMesh PreserveCompiledTopology(CompiledPatternPanel panel)
    {
        List<StructuredPoint2> boundary = [];
        Dictionary<string, IReadOnlyList<int>> edgeVertexIndices = new(StringComparer.OrdinalIgnoreCase);
        for (int edgeIndex = 0; edgeIndex < panel.Edges.Count; edgeIndex++)
        {
            CompiledPatternEdge edge = panel.Edges[edgeIndex];
            StructuredPoint2[] source = edge.VertexIndices
                .Select(index => new StructuredPoint2(panel.Vertices[index].X, panel.Vertices[index].Y))
                .ToArray();
            int segmentCount = Math.Max(1, (int)Math.Ceiling(edge.LengthCm / AdaptiveEdgeLengthCm));
            StructuredPoint2[] samples = ResamplePolyline(source, segmentCount + 1);
            List<int> mappedIndices = [];
            if (edgeIndex == 0)
            {
                boundary.Add(samples[0]);
            }
            mappedIndices.Add(boundary.Count - 1);
            for (int sampleIndex = 1; sampleIndex < samples.Length; sampleIndex++)
            {
                bool closesBoundary = edgeIndex == panel.Edges.Count - 1 && sampleIndex == samples.Length - 1;
                if (closesBoundary)
                {
                    mappedIndices.Add(0);
                }
                else
                {
                    boundary.Add(samples[sampleIndex]);
                    mappedIndices.Add(boundary.Count - 1);
                }
            }
            edgeVertexIndices.Add(edge.Id, mappedIndices);
        }

        double minimumX = boundary.Min(vertex => vertex.X);
        double maximumX = boundary.Max(vertex => vertex.X);
        double minimumY = boundary.Min(vertex => vertex.Y);
        double maximumY = boundary.Max(vertex => vertex.Y);
        List<V2d<double>> cdtVertices = boundary
            .Select(vertex => new V2d<double>(vertex.X, vertex.Y))
            .ToList();
        for (double y = minimumY + AdaptiveEdgeLengthCm; y < maximumY; y += AdaptiveEdgeLengthCm)
        {
            for (double x = minimumX + AdaptiveEdgeLengthCm; x < maximumX; x += AdaptiveEdgeLengthCm)
            {
                StructuredPoint2 candidate = new(x, y);
                if (PointInsidePolygon(candidate, boundary) &&
                    MinimumBoundaryDistance(candidate, boundary) >= InteriorPointBoundaryClearanceCm)
                {
                    cdtVertices.Add(new V2d<double>(x, y));
                }
            }
        }
        List<Edge> boundaryConstraints = Enumerable.Range(0, boundary.Count)
            .Select(index => new Edge(index, (index + 1) % boundary.Count))
            .ToList();
        Triangulation<double> cdt = new(VertexInsertionOrder.AsProvided);
        cdt.InsertVertices(cdtVertices);
        cdt.InsertEdges(boundaryConstraints);
        cdt.EraseOuterTriangles();

        double width = Math.Max(maximumX - minimumX, double.Epsilon);
        double height = Math.Max(maximumY - minimumY, double.Epsilon);
        V2d<double>[] triangulatedVertices = cdt.Vertices.ToArray();
        CDT.Triangle[] triangulatedTriangles = cdt.Triangles.ToArray();
        StructuredPanelVertex[] vertices = triangulatedVertices
            .Select((vertex, index) => new StructuredPanelVertex(
                index,
                vertex.X,
                vertex.Y,
                (vertex.X - minimumX) / width,
                (vertex.Y - minimumY) / height))
            .ToArray();
        List<StructuredPanelTriangle> triangles = new(triangulatedTriangles.Length);
        double orientation = 0;
        double minimumSignedDoubleArea = double.PositiveInfinity;
        foreach (CDT.Triangle triangle in triangulatedTriangles)
        {
            AddTriangle(
                vertices,
                triangles,
                triangle.V0,
                triangle.V1,
                triangle.V2,
                ref orientation,
                ref minimumSignedDoubleArea);
        }
        return new StructuredPanelMesh(
            panel.Id,
            panel.PieceId,
            0,
            0,
            vertices,
            triangles,
            edgeVertexIndices,
            triangles.Min(triangle => triangle.AreaCm2),
            triangles.Max(triangle => triangle.AspectRatio),
            minimumSignedDoubleArea,
            0);
    }

    private static bool PointInsidePolygon(StructuredPoint2 point, IReadOnlyList<StructuredPoint2> polygon)
    {
        bool inside = false;
        for (int current = 0, previous = polygon.Count - 1; current < polygon.Count; previous = current++)
        {
            StructuredPoint2 a = polygon[current];
            StructuredPoint2 b = polygon[previous];
            bool crosses = (a.Y > point.Y) != (b.Y > point.Y) &&
                point.X < (b.X - a.X) * (point.Y - a.Y) / (b.Y - a.Y) + a.X;
            if (crosses)
            {
                inside = !inside;
            }
        }
        return inside;
    }

    private static double MinimumBoundaryDistance(
        StructuredPoint2 point,
        IReadOnlyList<StructuredPoint2> boundary)
    {
        double minimum = double.PositiveInfinity;
        for (int index = 0; index < boundary.Count; index++)
        {
            minimum = Math.Min(
                minimum,
                PointSegmentDistance(point, boundary[index], boundary[(index + 1) % boundary.Count]));
        }
        return minimum;
    }

    private static double PointSegmentDistance(
        StructuredPoint2 point,
        StructuredPoint2 start,
        StructuredPoint2 end)
    {
        double dx = end.X - start.X;
        double dy = end.Y - start.Y;
        double lengthSquared = dx * dx + dy * dy;
        if (lengthSquared <= double.Epsilon)
        {
            return Distance(point, start);
        }
        double position = Math.Clamp(
            ((point.X - start.X) * dx + (point.Y - start.Y) * dy) / lengthSquared,
            0,
            1);
        return Distance(point, new StructuredPoint2(start.X + position * dx, start.Y + position * dy));
    }

    private static BoundaryChain BuildBoundaryChain(
        CompiledPatternPanel panel,
        IReadOnlyList<string> edgeIds,
        int totalSegments,
        bool reverseForGrid)
    {
        Dictionary<string, CompiledPatternEdge> edges = panel.Edges
            .ToDictionary(edge => edge.Id, StringComparer.OrdinalIgnoreCase);
        CompiledPatternEdge[] selectedEdges = edgeIds
            .Select(edgeId => edges.TryGetValue(edgeId, out CompiledPatternEdge? edge)
                ? edge
                : throw new InvalidOperationException($"Panel {panel.Id} is missing patch edge {edgeId}."))
            .ToArray();
        int[] segmentsByEdge = AllocateSegments(selectedEdges, totalSegments);

        List<StructuredPoint2> originalPoints = [];
        Dictionary<string, IReadOnlyList<int>> originalEdgePositions = new(StringComparer.OrdinalIgnoreCase);
        int positionOffset = 0;
        for (int edgeIndex = 0; edgeIndex < selectedEdges.Length; edgeIndex++)
        {
            CompiledPatternEdge edge = selectedEdges[edgeIndex];
            StructuredPoint2[] sourcePoints = edge.VertexIndices
                .Select(index => new StructuredPoint2(panel.Vertices[index].X, panel.Vertices[index].Y))
                .ToArray();
            StructuredPoint2[] sampledPoints = ResamplePolyline(sourcePoints, segmentsByEdge[edgeIndex]);
            if (originalPoints.Count > 0 && Distance(originalPoints[^1], sampledPoints[0]) > 0.001)
            {
                throw new InvalidOperationException(
                    $"Panel {panel.Id} patch edges are not contiguous before {edge.Id}.");
            }

            if (originalPoints.Count == 0)
            {
                originalPoints.AddRange(sampledPoints);
            }
            else
            {
                originalPoints.AddRange(sampledPoints.Skip(1));
            }

            originalEdgePositions[edge.Id] = Enumerable
                .Range(positionOffset, segmentsByEdge[edgeIndex] + 1)
                .ToArray();
            positionOffset += segmentsByEdge[edgeIndex];
        }

        if (originalPoints.Count != totalSegments + 1)
        {
            throw new InvalidOperationException(
                $"Panel {panel.Id} patch chain produced {originalPoints.Count - 1} segments; expected {totalSegments}.");
        }

        IReadOnlyList<StructuredPoint2> gridPoints = reverseForGrid
            ? originalPoints.AsEnumerable().Reverse().ToArray()
            : originalPoints;
        Dictionary<string, IReadOnlyList<int>> gridEdgePositions = new(StringComparer.OrdinalIgnoreCase);
        foreach ((string edgeId, IReadOnlyList<int> positions) in originalEdgePositions)
        {
            gridEdgePositions[edgeId] = positions
                .Select(position => reverseForGrid ? totalSegments - position : position)
                .ToArray();
        }

        return new BoundaryChain(gridPoints, gridEdgePositions);
    }

    private static int[] AllocateSegments(
        IReadOnlyList<CompiledPatternEdge> edges,
        int totalSegments)
    {
        if (totalSegments < edges.Count)
        {
            throw new InvalidOperationException(
                $"A patch boundary with {edges.Count} named edges requires at least {edges.Count} segments.");
        }

        int[] segments = Enumerable.Repeat(1, edges.Count).ToArray();
        int remaining = totalSegments - edges.Count;
        double totalLength = edges.Sum(edge => edge.LengthCm);
        if (remaining == 0 || totalLength <= double.Epsilon)
        {
            return segments;
        }

        (int Index, double Fraction)[] fractional = new (int, double)[edges.Count];
        int assigned = 0;
        for (int index = 0; index < edges.Count; index++)
        {
            double exact = remaining * edges[index].LengthCm / totalLength;
            int whole = (int)Math.Floor(exact);
            segments[index] += whole;
            assigned += whole;
            fractional[index] = (index, exact - whole);
        }

        foreach ((int index, _) in fractional
            .OrderByDescending(item => item.Fraction)
            .ThenBy(item => item.Index)
            .Take(remaining - assigned))
        {
            segments[index]++;
        }
        return segments;
    }

    private static StructuredPoint2[] ResamplePolyline(
        IReadOnlyList<StructuredPoint2> source,
        int segments)
    {
        if (source.Count < 2)
        {
            throw new InvalidOperationException("A named edge requires at least two source points.");
        }

        double[] cumulativeLengths = new double[source.Count];
        for (int index = 1; index < source.Count; index++)
        {
            cumulativeLengths[index] = cumulativeLengths[index - 1] + Distance(source[index - 1], source[index]);
        }
        double totalLength = cumulativeLengths[^1];
        if (totalLength <= double.Epsilon)
        {
            throw new InvalidOperationException("A named edge has zero length.");
        }

        StructuredPoint2[] result = new StructuredPoint2[segments + 1];
        result[0] = source[0];
        result[^1] = source[^1];
        int sourceSegment = 0;
        for (int sample = 1; sample < segments; sample++)
        {
            double targetLength = totalLength * sample / segments;
            while (sourceSegment + 1 < cumulativeLengths.Length - 1 &&
                cumulativeLengths[sourceSegment + 1] < targetLength)
            {
                sourceSegment++;
            }

            double segmentStart = cumulativeLengths[sourceSegment];
            double segmentEnd = cumulativeLengths[sourceSegment + 1];
            double alpha = (targetLength - segmentStart) / Math.Max(segmentEnd - segmentStart, double.Epsilon);
            result[sample] = Lerp(source[sourceSegment], source[sourceSegment + 1], alpha);
        }
        return result;
    }

    private static void AddTriangle(
        IReadOnlyList<StructuredPanelVertex> vertices,
        ICollection<StructuredPanelTriangle> triangles,
        int a,
        int b,
        int c,
        ref double orientation,
        ref double minimumSignedDoubleArea)
    {
        StructuredPanelVertex first = vertices[a];
        StructuredPanelVertex second = vertices[b];
        StructuredPanelVertex third = vertices[c];
        double signedDoubleArea =
            (second.X - first.X) * (third.Y - first.Y) -
            (second.Y - first.Y) * (third.X - first.X);
        if (Math.Abs(signedDoubleArea) <= 0.000001)
        {
            throw new InvalidOperationException(
                $"Structured remeshing produced a degenerate triangle at vertices {a}, {b}, and {c}.");
        }

        double sign = Math.Sign(signedDoubleArea);
        if (orientation == 0)
        {
            orientation = sign;
        }
        else if (sign != orientation)
        {
            throw new InvalidOperationException(
                $"Structured remeshing produced a folded triangle at vertices {a}, {b}, and {c}.");
        }

        minimumSignedDoubleArea = Math.Min(minimumSignedDoubleArea, Math.Abs(signedDoubleArea));
        double ab = Distance(first, second);
        double bc = Distance(second, third);
        double ca = Distance(third, first);
        double longest = Math.Max(ab, Math.Max(bc, ca));
        double area = Math.Abs(signedDoubleArea) * 0.5;
        double shortestAltitude = 2.0 * area / Math.Max(longest, double.Epsilon);
        double aspectRatio = longest / Math.Max(shortestAltitude, double.Epsilon);
        triangles.Add(new StructuredPanelTriangle(a, b, c, area, aspectRatio));
    }

    private static void AddBoundaryEdges(
        IDictionary<string, IReadOnlyList<int>> destination,
        BoundaryChain chain,
        Func<int, int> toVertexIndex)
    {
        foreach ((string edgeId, IReadOnlyList<int> positions) in chain.EdgePositions)
        {
            if (destination.ContainsKey(edgeId))
            {
                throw new InvalidOperationException($"Structured patch maps edge {edgeId} more than once.");
            }
            destination[edgeId] = positions.Select(toVertexIndex).ToArray();
        }
    }

    private static int GridIndex(int column, int row, int columns)
        => row * (columns + 1) + column;

    private static StructuredPoint2 Lerp(StructuredPoint2 start, StructuredPoint2 end, double alpha)
        => start * (1 - alpha) + end * alpha;

    private static double Distance(StructuredPoint2 first, StructuredPoint2 second)
        => Math.Sqrt(Math.Pow(second.X - first.X, 2) + Math.Pow(second.Y - first.Y, 2));

    private static double Distance(StructuredPanelVertex first, StructuredPanelVertex second)
        => Math.Sqrt(Math.Pow(second.X - first.X, 2) + Math.Pow(second.Y - first.Y, 2));
}
