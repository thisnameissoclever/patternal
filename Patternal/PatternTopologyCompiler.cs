using System.Text.Json;

namespace Patterna;

public sealed record PatternTopologyCompilerOptions(
    double MaximumCurveSegmentLengthCm = 1.0,
    double ClosureToleranceCm = 0.001,
    double MinimumTriangleAreaCm2 = 0.00001,
    double MaximumSeamLengthMismatchRatio = 0.25);

public enum PatternTopologyDiagnosticSeverity
{
    Information,
    Warning
}

public sealed record PatternTopologyDiagnostic(
    PatternTopologyDiagnosticSeverity Severity,
    string Code,
    string Message,
    string? SourceId = null);

public sealed record CompiledPatternVertex(
    string Id,
    double X,
    double Y);

public sealed record CompiledPatternTriangle(
    int A,
    int B,
    int C,
    double AreaCm2);

public sealed record CompiledPatternEdge(
    string Id,
    IReadOnlyList<int> VertexIndices,
    double LengthCm);

public sealed record CompiledPatternPanel(
    string Id,
    string PieceId,
    string Name,
    string Placement,
    bool ReverseWinding,
    IReadOnlyList<string> PinnedEdges,
    IReadOnlyList<CompiledPatternVertex> Vertices,
    IReadOnlyList<CompiledPatternTriangle> Triangles,
    IReadOnlyList<CompiledPatternEdge> Edges,
    double SignedAreaCm2)
{
    public PatternPlacement3DDocument? SourcePlacement { get; init; }
}

public sealed record CompiledSeamVertexPair(
    int VertexA,
    int VertexB,
    double NormalizedPosition);

public sealed record CompiledPatternSeam(
    string Id,
    string Name,
    string PanelA,
    string PanelB,
    IReadOnlyList<string> EdgeIdsA,
    IReadOnlyList<string> EdgeIdsB,
    bool ReverseA,
    bool ReverseB,
    double LengthACm,
    double LengthBCm,
    double LengthMismatchCm,
    double LengthMismatchRatio,
    IReadOnlyList<CompiledSeamVertexPair> VertexPairs,
    double AllowanceCm,
    double Strength);

public sealed record CompiledClosureAnchor(
    string PanelId,
    IReadOnlyList<string> EdgeIds,
    bool Reverse,
    double StartPosition,
    double EndPosition);

public sealed record CompiledClosureConstraint(
    int VertexA,
    int VertexB,
    double NormalizedPosition);

public sealed record CompiledPatternClosure(
    string Id,
    string Name,
    string Kind,
    string State,
    CompiledClosureAnchor AnchorA,
    CompiledClosureAnchor AnchorB,
    IReadOnlyList<CompiledClosureConstraint> Constraints,
    double TargetDistanceCm,
    double Strength);

public sealed record PatternTopologyCompilation(
    string SchemaVersion,
    string GarmentId,
    IReadOnlyList<CompiledPatternPanel> Panels,
    IReadOnlyList<CompiledPatternSeam> Seams,
    IReadOnlyList<CompiledPatternClosure> Closures,
    IReadOnlyList<PatternTopologyDiagnostic> Diagnostics)
{
    public int VertexCount => Panels.Sum(panel => panel.Vertices.Count);

    public int TriangleCount => Panels.Sum(panel => panel.Triangles.Count);
}

public sealed class PatternTopologyException : InvalidOperationException
{
    public PatternTopologyException(IReadOnlyList<string> errors)
        : base(string.Join(Environment.NewLine, errors))
    {
        Errors = errors;
    }

    public IReadOnlyList<string> Errors { get; }
}

public static class PatternTopologyCompiler
{
    private const double GeometryEpsilon = 0.0000001;

    public static PatternTopologyCompilation Compile(
        GarmentDocument document,
        PatternTopologyCompilerOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(document);
        options ??= new PatternTopologyCompilerOptions();
        ValidateOptions(options);

        List<string> errors = [.. document.Validate()];
        if (!string.Equals(document.Units, "centimeters", StringComparison.OrdinalIgnoreCase))
        {
            errors.Add($"Pattern topology compilation requires centimeters; received {document.Units}.");
        }

        Dictionary<string, PatternPieceDocument> piecesById = document.Pieces
            .GroupBy(piece => piece.Id, StringComparer.OrdinalIgnoreCase)
            .Where(group => group.Count() == 1)
            .ToDictionary(group => group.Key, group => group.Single(), StringComparer.OrdinalIgnoreCase);

        Dictionary<string, PieceTopology> pieceTopologies = new(StringComparer.OrdinalIgnoreCase);
        foreach (PatternPieceDocument piece in document.Pieces)
        {
            if (pieceTopologies.ContainsKey(piece.Id))
            {
                continue;
            }

            try
            {
                pieceTopologies.Add(piece.Id, CompilePiece(piece, options));
            }
            catch (PatternTopologyException exception)
            {
                errors.AddRange(exception.Errors);
            }
        }

        if (errors.Count > 0)
        {
            throw new PatternTopologyException(errors);
        }

        List<CompiledPatternPanel> panels = [];
        Dictionary<string, CompiledPatternPanel> panelsById = new(StringComparer.OrdinalIgnoreCase);
        foreach (ClothPanelDocument panel in document.Panels)
        {
            if (!piecesById.ContainsKey(panel.PieceId) ||
                !pieceTopologies.TryGetValue(panel.PieceId, out PieceTopology? pieceTopology))
            {
                continue;
            }

            CompiledPatternTriangle[] triangles = pieceTopology.Triangles
                .Select(triangle => panel.ReverseWinding
                    ? new CompiledPatternTriangle(triangle.A, triangle.C, triangle.B, triangle.AreaCm2)
                    : triangle)
                .ToArray();
            CompiledPatternPanel compiledPanel = new(
                panel.Id,
                panel.PieceId,
                panel.Name,
                panel.Placement,
                panel.ReverseWinding,
                panel.PinnedEdges.ToArray(),
                pieceTopology.Vertices,
                triangles,
                pieceTopology.Edges,
                pieceTopology.SignedAreaCm2)
            {
                SourcePlacement = panel.SourcePlacement
            };
            panels.Add(compiledPanel);
            panelsById.Add(compiledPanel.Id, compiledPanel);
        }

        List<PatternTopologyDiagnostic> diagnostics = [];
        List<CompiledPatternSeam> seams = [];
        foreach (GarmentSeamDocument seam in document.Seams)
        {
            try
            {
                CompiledPatternSeam compiledSeam = CompileSeam(document, seam, panelsById);
                seams.Add(compiledSeam);
                if (compiledSeam.LengthMismatchRatio > options.MaximumSeamLengthMismatchRatio)
                {
                    diagnostics.Add(new PatternTopologyDiagnostic(
                        PatternTopologyDiagnosticSeverity.Warning,
                        "seam-length-mismatch",
                        $"Seam {seam.Id} differs by {compiledSeam.LengthMismatchCm:F2} cm ({compiledSeam.LengthMismatchRatio:P1}).",
                        seam.Id));
                }
            }
            catch (PatternTopologyException exception)
            {
                errors.AddRange(exception.Errors);
            }
        }

        if (errors.Count > 0)
        {
            throw new PatternTopologyException(errors);
        }

        List<CompiledPatternClosure> closures = [];
        foreach (GarmentClosureDocument closure in document.Closures)
        {
            try
            {
                closures.Add(CompileClosure(closure, panelsById));
            }
            catch (PatternTopologyException exception)
            {
                errors.AddRange(exception.Errors);
            }
        }

        if (errors.Count > 0)
        {
            throw new PatternTopologyException(errors);
        }

        diagnostics.Add(new PatternTopologyDiagnostic(
            PatternTopologyDiagnosticSeverity.Information,
            "topology-summary",
            $"Compiled {panels.Count} panels, {panels.Sum(panel => panel.Vertices.Count)} vertices, {panels.Sum(panel => panel.Triangles.Count)} triangles, {seams.Count} seams, and {closures.Count} closures."));

        return new PatternTopologyCompilation(
            "patterna.topology/1.1",
            document.Id,
            panels,
            seams,
            closures,
            diagnostics);
    }

    private static void ValidateOptions(PatternTopologyCompilerOptions options)
    {
        if (!double.IsFinite(options.MaximumCurveSegmentLengthCm) ||
            options.MaximumCurveSegmentLengthCm <= 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                "Maximum curve segment length must be finite and positive.");
        }

        if (!double.IsFinite(options.ClosureToleranceCm) || options.ClosureToleranceCm <= 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                "Closure tolerance must be finite and positive.");
        }

        if (!double.IsFinite(options.MinimumTriangleAreaCm2) ||
            options.MinimumTriangleAreaCm2 <= 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                "Minimum triangle area must be finite and positive.");
        }

        if (!double.IsFinite(options.MaximumSeamLengthMismatchRatio) ||
            options.MaximumSeamLengthMismatchRatio < 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                "Maximum seam mismatch ratio must be finite and nonnegative.");
        }
    }

    private static PieceTopology CompilePiece(
        PatternPieceDocument piece,
        PatternTopologyCompilerOptions options)
    {
        List<string> errors = [];
        if (!IsFinite(piece.Start))
        {
            errors.Add($"Pattern piece {piece.Id} has a non-finite start point.");
        }

        List<CompiledPatternVertex> vertices = [];
        List<CompiledPatternEdge> edges = [];
        PatternPointDocument scaledStart = ScalePoint(piece, piece.Start);
        vertices.Add(new CompiledPatternVertex($"{piece.Id}:start", scaledStart.X, scaledStart.Y));
        PatternPointDocument current = scaledStart;

        for (int curveIndex = 0; curveIndex < piece.Boundary.Count; curveIndex++)
        {
            PatternCurveDocument curve = piece.Boundary[curveIndex];
            PatternPointDocument end = ScalePoint(piece, curve.End);
            if (!IsFinite(end))
            {
                errors.Add($"Pattern piece {piece.Id} edge {curve.Id} has a non-finite endpoint.");
                current = end;
                continue;
            }

            List<PatternPointDocument> samples;
            if (string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase))
            {
                samples = [current, end];
            }
            else if (string.Equals(curve.Kind, "cubic", StringComparison.OrdinalIgnoreCase))
            {
                if (curve.Control1 is null || curve.Control2 is null)
                {
                    errors.Add($"Pattern piece {piece.Id} cubic edge {curve.Id} is missing a control point.");
                    current = end;
                    continue;
                }

                PatternPointDocument control1 = ScalePoint(piece, curve.Control1);
                PatternPointDocument control2 = ScalePoint(piece, curve.Control2);
                if (!IsFinite(control1) || !IsFinite(control2))
                {
                    errors.Add($"Pattern piece {piece.Id} cubic edge {curve.Id} has a non-finite control point.");
                    current = end;
                    continue;
                }

                samples = SampleCubic(
                    current,
                    control1,
                    control2,
                    end,
                    options.MaximumCurveSegmentLengthCm,
                    2);
            }
            else
            {
                errors.Add($"Pattern piece {piece.Id} edge {curve.Id} uses unsupported curve kind {curve.Kind}.");
                current = end;
                continue;
            }

            List<int> edgeVertexIndices = [vertices.Count - 1];
            for (int sampleIndex = 1; sampleIndex < samples.Count; sampleIndex++)
            {
                PatternPointDocument sample = samples[sampleIndex];
                bool closesBoundary = curveIndex == piece.Boundary.Count - 1 &&
                    sampleIndex == samples.Count - 1 &&
                    Distance(sample, scaledStart) <= options.ClosureToleranceCm;
                if (closesBoundary)
                {
                    edgeVertexIndices.Add(0);
                    continue;
                }

                if (Distance(sample, ToPoint(vertices[^1])) <= GeometryEpsilon)
                {
                    errors.Add($"Pattern piece {piece.Id} edge {curve.Id} contains coincident consecutive samples.");
                    continue;
                }

                int vertexIndex = vertices.Count;
                vertices.Add(new CompiledPatternVertex(
                    $"{piece.Id}:{curve.Id}:{sampleIndex}/{samples.Count - 1}",
                    sample.X,
                    sample.Y));
                edgeVertexIndices.Add(vertexIndex);
            }

            edges.Add(new CompiledPatternEdge(
                curve.Id,
                edgeVertexIndices,
                ChainLength(edgeVertexIndices, vertices)));
            current = end;
        }

        if (Distance(current, scaledStart) > options.ClosureToleranceCm)
        {
            errors.Add(
                $"Pattern piece {piece.Id} is open by {Distance(current, scaledStart):F4} cm. " +
                "The final boundary endpoint must meet the start point.");
        }

        if (vertices.Count < 3)
        {
            errors.Add($"Pattern piece {piece.Id} produced fewer than three distinct vertices.");
        }

        if (errors.Count == 0)
        {
            ValidateSimpleBoundary(piece.Id, vertices, errors);
        }

        double signedArea = errors.Count == 0 ? SignedArea(vertices) : 0;
        if (Math.Abs(signedArea) <= options.MinimumTriangleAreaCm2)
        {
            errors.Add($"Pattern piece {piece.Id} has zero or negligible signed area.");
        }

        List<CompiledPatternTriangle> triangles = [];
        if (errors.Count == 0)
        {
            triangles = Triangulate(piece.Id, vertices, signedArea, options.MinimumTriangleAreaCm2);
            ValidateTriangleCoverage(piece.Id, vertices, triangles, signedArea, options, errors);
        }

        if (errors.Count > 0)
        {
            throw new PatternTopologyException(errors);
        }

        return new PieceTopology(vertices.ToArray(), triangles.ToArray(), edges.ToArray(), signedArea);
    }

    private static List<PatternPointDocument> SampleCubic(
        PatternPointDocument start,
        PatternPointDocument control1,
        PatternPointDocument control2,
        PatternPointDocument end,
        double maximumSegmentLengthCm,
        int minimumSegments)
    {
        const int lengthProbeSegments = 24;
        double approximateLength = 0;
        PatternPointDocument previous = start;
        for (int index = 1; index <= lengthProbeSegments; index++)
        {
            PatternPointDocument point = EvaluateCubic(
                start,
                control1,
                control2,
                end,
                (double)index / lengthProbeSegments);
            approximateLength += Distance(previous, point);
            previous = point;
        }

        const double maximumCurveLengthExcessPerSegmentSquaredCm = 0.005;
        double chordLength = Distance(start, end);
        double controlPolygonLength =
            Distance(start, control1) +
            Distance(control1, control2) +
            Distance(control2, end);
        double curveLengthExcess = Math.Max(0, controlPolygonLength - chordLength);
        int curvatureSegments = (int)Math.Ceiling(Math.Sqrt(
            curveLengthExcess / maximumCurveLengthExcessPerSegmentSquaredCm));
        int segments = Math.Clamp(
            Math.Max(
                (int)Math.Ceiling(approximateLength / maximumSegmentLengthCm),
                curvatureSegments),
            minimumSegments,
            256);
        List<PatternPointDocument> samples = new(segments + 1);
        for (int index = 0; index <= segments; index++)
        {
            samples.Add(EvaluateCubic(
                start,
                control1,
                control2,
                end,
                (double)index / segments));
        }

        return samples;
    }

    private static PatternPointDocument EvaluateCubic(
        PatternPointDocument start,
        PatternPointDocument control1,
        PatternPointDocument control2,
        PatternPointDocument end,
        double t)
    {
        double inverse = 1 - t;
        double startWeight = inverse * inverse * inverse;
        double control1Weight = 3 * inverse * inverse * t;
        double control2Weight = 3 * inverse * t * t;
        double endWeight = t * t * t;
        return new PatternPointDocument(
            (start.X * startWeight) + (control1.X * control1Weight) +
            (control2.X * control2Weight) + (end.X * endWeight),
            (start.Y * startWeight) + (control1.Y * control1Weight) +
            (control2.Y * control2Weight) + (end.Y * endWeight));
    }

    private static void ValidateSimpleBoundary(
        string pieceId,
        IReadOnlyList<CompiledPatternVertex> vertices,
        ICollection<string> errors)
    {
        for (int first = 0; first < vertices.Count; first++)
        {
            int firstNext = (first + 1) % vertices.Count;
            PatternPointDocument firstA = ToPoint(vertices[first]);
            PatternPointDocument firstB = ToPoint(vertices[firstNext]);
            for (int second = first + 1; second < vertices.Count; second++)
            {
                int secondNext = (second + 1) % vertices.Count;
                bool adjacent = first == second || firstNext == second || secondNext == first;
                if (adjacent)
                {
                    continue;
                }

                if (SegmentsIntersect(
                    firstA,
                    firstB,
                    ToPoint(vertices[second]),
                    ToPoint(vertices[secondNext])))
                {
                    errors.Add(
                        $"Pattern piece {pieceId} self-intersects between boundary segments " +
                        $"{first} and {second}.");
                    return;
                }
            }
        }
    }

    private static List<CompiledPatternTriangle> Triangulate(
        string pieceId,
        IReadOnlyList<CompiledPatternVertex> vertices,
        double signedArea,
        double minimumTriangleAreaCm2)
    {
        int orientation = signedArea > 0 ? 1 : -1;
        List<int> remaining = Enumerable.Range(0, vertices.Count).ToList();
        List<CompiledPatternTriangle> triangles = [];
        List<(int Vertex, int Previous, int Next)> deferredCollinearVertices = [];
        bool removedCollinearVertex;
        do
        {
            removedCollinearVertex = false;
            for (int position = 0; position < remaining.Count && remaining.Count > 3; position++)
            {
                int previous = remaining[(position - 1 + remaining.Count) % remaining.Count];
                int current = remaining[position];
                int next = remaining[(position + 1) % remaining.Count];
                if (Math.Abs(Cross(vertices[previous], vertices[current], vertices[next])) > GeometryEpsilon ||
                    !PointOnSegment(ToPoint(vertices[current]), ToPoint(vertices[previous]), ToPoint(vertices[next])))
                {
                    continue;
                }

                deferredCollinearVertices.Add((current, previous, next));
                remaining.RemoveAt(position);
                removedCollinearVertex = true;
                break;
            }
        }
        while (removedCollinearVertex);
        int iterationBudget = vertices.Count * vertices.Count;

        while (remaining.Count > 3 && iterationBudget-- > 0)
        {
            bool clippedEar = false;
            for (int position = 0; position < remaining.Count; position++)
            {
                int previous = remaining[(position - 1 + remaining.Count) % remaining.Count];
                int current = remaining[position];
                int next = remaining[(position + 1) % remaining.Count];
                double twiceArea = Cross(vertices[previous], vertices[current], vertices[next]);
                if ((orientation * twiceArea) <= (2 * minimumTriangleAreaCm2))
                {
                    continue;
                }

                bool containsVertex = false;
                foreach (int candidate in remaining)
                {
                    if (candidate == previous || candidate == current || candidate == next)
                    {
                        continue;
                    }

                    if (PointStrictlyInsideTriangle(
                        vertices[candidate],
                        vertices[previous],
                        vertices[current],
                        vertices[next]))
                    {
                        containsVertex = true;
                        break;
                    }
                }

                if (containsVertex)
                {
                    continue;
                }

                triangles.Add(new CompiledPatternTriangle(
                    previous,
                    current,
                    next,
                    Math.Abs(twiceArea) * 0.5));
                remaining.RemoveAt(position);
                clippedEar = true;
                break;
            }

            if (!clippedEar)
            {
                bool deferredCollinearVertex = false;
                for (int position = 0; position < remaining.Count; position++)
                {
                    int previous = remaining[(position - 1 + remaining.Count) % remaining.Count];
                    int current = remaining[position];
                    int next = remaining[(position + 1) % remaining.Count];
                    if (Math.Abs(Cross(vertices[previous], vertices[current], vertices[next])) > GeometryEpsilon ||
                        !PointOnSegment(ToPoint(vertices[current]), ToPoint(vertices[previous]), ToPoint(vertices[next])))
                    {
                        continue;
                    }

                    deferredCollinearVertices.Add((current, previous, next));
                    remaining.RemoveAt(position);
                    deferredCollinearVertex = true;
                    break;
                }

                if (!deferredCollinearVertex)
                {
                    throw new PatternTopologyException([
                        $"Pattern piece {pieceId} could not be triangulated without a degenerate or overlapping ear."
                    ]);
                }
            }
        }

        if (remaining.Count == 3)
        {
            double twiceArea = Cross(
                vertices[remaining[0]],
                vertices[remaining[1]],
                vertices[remaining[2]]);
            double area = Math.Abs(twiceArea) * 0.5;
            if (area <= minimumTriangleAreaCm2)
            {
                int middlePosition = FindMiddleCollinearPosition(remaining, vertices);
                if (middlePosition < 0)
                {
                    throw new PatternTopologyException([
                        $"Pattern piece {pieceId} ended with a degenerate final triangle."
                    ]);
                }
                int previousPosition = (middlePosition - 1 + remaining.Count) % remaining.Count;
                int nextPosition = (middlePosition + 1) % remaining.Count;
                deferredCollinearVertices.Add((
                    remaining[middlePosition],
                    remaining[previousPosition],
                    remaining[nextPosition]));
            }
            else
            {
                triangles.Add(new CompiledPatternTriangle(
                    remaining[0],
                    remaining[1],
                    remaining[2],
                    area));
            }
        }

        for (int deferredIndex = deferredCollinearVertices.Count - 1; deferredIndex >= 0; deferredIndex--)
        {
            (int vertex, int previous, int next) = deferredCollinearVertices[deferredIndex];
            int triangleIndex = triangles.FindIndex(triangle =>
                TriangleContainsEdge(triangle, previous, next));
            if (triangleIndex < 0)
            {
                throw new PatternTopologyException([
                    $"Pattern piece {pieceId} could not restore collinear boundary vertex {vertex}."
                ]);
            }

            CompiledPatternTriangle original = triangles[triangleIndex];
            int opposite = TriangleOppositeVertex(original, previous, next);
            CompiledPatternTriangle first = CreateTriangle(
                vertices,
                previous,
                vertex,
                opposite,
                orientation,
                minimumTriangleAreaCm2,
                pieceId);
            CompiledPatternTriangle second = CreateTriangle(
                vertices,
                vertex,
                next,
                opposite,
                orientation,
                minimumTriangleAreaCm2,
                pieceId);
            triangles[triangleIndex] = first;
            triangles.Add(second);
        }

        return triangles;
    }

    private static int FindMiddleCollinearPosition(
        IReadOnlyList<int> indices,
        IReadOnlyList<CompiledPatternVertex> vertices)
    {
        for (int position = 0; position < indices.Count; position++)
        {
            int previous = indices[(position - 1 + indices.Count) % indices.Count];
            int current = indices[position];
            int next = indices[(position + 1) % indices.Count];
            if (PointOnSegment(ToPoint(vertices[current]), ToPoint(vertices[previous]), ToPoint(vertices[next])))
            {
                return position;
            }
        }
        return -1;
    }

    private static bool TriangleContainsEdge(CompiledPatternTriangle triangle, int first, int second)
        => (triangle.A == first || triangle.B == first || triangle.C == first) &&
           (triangle.A == second || triangle.B == second || triangle.C == second);

    private static int TriangleOppositeVertex(CompiledPatternTriangle triangle, int first, int second)
        => triangle.A != first && triangle.A != second
            ? triangle.A
            : triangle.B != first && triangle.B != second
                ? triangle.B
                : triangle.C;

    private static CompiledPatternTriangle CreateTriangle(
        IReadOnlyList<CompiledPatternVertex> vertices,
        int first,
        int second,
        int third,
        int orientation,
        double minimumTriangleAreaCm2,
        string pieceId)
    {
        double twiceArea = Cross(vertices[first], vertices[second], vertices[third]);
        double area = Math.Abs(twiceArea) * 0.5;
        if (area <= minimumTriangleAreaCm2)
        {
            throw new PatternTopologyException([
                $"Pattern piece {pieceId} produced a degenerate triangle while restoring collinear boundary " +
                $"landmark {vertices[second].Id} between {vertices[first].Id} and {vertices[third].Id}; " +
                $"area {area:F8} cm2."
            ]);
        }
        return orientation * twiceArea > 0
            ? new CompiledPatternTriangle(first, second, third, area)
            : new CompiledPatternTriangle(first, third, second, area);
    }

    private static void ValidateTriangleCoverage(
        string pieceId,
        IReadOnlyList<CompiledPatternVertex> vertices,
        IReadOnlyList<CompiledPatternTriangle> triangles,
        double signedArea,
        PatternTopologyCompilerOptions options,
        ICollection<string> errors)
    {
        if (triangles.Count != vertices.Count - 2)
        {
            errors.Add(
                $"Pattern piece {pieceId} produced {triangles.Count} triangles for " +
                $"{vertices.Count} vertices; expected {vertices.Count - 2}.");
        }

        double triangleArea = triangles.Sum(triangle => triangle.AreaCm2);
        double polygonArea = Math.Abs(signedArea);
        double areaTolerance = Math.Max(options.MinimumTriangleAreaCm2, polygonArea * 0.000001);
        if (Math.Abs(triangleArea - polygonArea) > areaTolerance)
        {
            errors.Add(
                $"Pattern piece {pieceId} triangle area {triangleArea:F6} cm2 does not cover " +
                $"polygon area {polygonArea:F6} cm2.");
        }

        foreach (CompiledPatternTriangle triangle in triangles)
        {
            if (triangle.AreaCm2 <= options.MinimumTriangleAreaCm2)
            {
                errors.Add($"Pattern piece {pieceId} contains a degenerate triangle.");
                break;
            }
        }

        Dictionary<(int A, int B), int> edgeUse = [];
        foreach (CompiledPatternTriangle triangle in triangles)
        {
            AddTriangleEdge(edgeUse, triangle.A, triangle.B);
            AddTriangleEdge(edgeUse, triangle.B, triangle.C);
            AddTriangleEdge(edgeUse, triangle.C, triangle.A);
        }

        if (edgeUse.Values.Any(count => count is < 1 or > 2))
        {
            errors.Add($"Pattern piece {pieceId} produced a non-manifold triangle edge.");
        }
    }

    private static CompiledPatternSeam CompileSeam(
        GarmentDocument document,
        GarmentSeamDocument seam,
        IReadOnlyDictionary<string, CompiledPatternPanel> panelsById)
    {
        if (!panelsById.TryGetValue(seam.SideA.PanelId, out CompiledPatternPanel? panelA) ||
            !panelsById.TryGetValue(seam.SideB.PanelId, out CompiledPatternPanel? panelB))
        {
            throw new PatternTopologyException([
                $"Seam {seam.Id} references a panel that was not compiled."
            ]);
        }

        bool reverseA = seam.SideA.Reverse;
        bool reverseB = TryReadSourceRelativeReverse(document, seam.Id, out bool relativeReverse)
            ? reverseA ^ relativeReverse
            : seam.SideB.Reverse;
        SeamSideDocument effectiveSideB = seam.SideB with { Reverse = reverseB };
        SeamChain sideA = BuildSeamChain(seam.Id, "A", seam.SideA, panelA);
        SeamChain sideB = BuildSeamChain(seam.Id, "B", effectiveSideB, panelB);
        int pairCount = Math.Max(sideA.VertexIndices.Count, sideB.VertexIndices.Count);
        if (pairCount < 2)
        {
            throw new PatternTopologyException([
                $"Seam {seam.Id} requires at least two vertices on both sides."
            ]);
        }

        List<CompiledSeamVertexPair> pairs = new(pairCount);
        for (int pairIndex = 0; pairIndex < pairCount; pairIndex++)
        {
            double normalized = pairCount == 1 ? 0 : (double)pairIndex / (pairCount - 1);
            int indexA = sideA.VertexIndices[(int)Math.Round(normalized * (sideA.VertexIndices.Count - 1))];
            int indexB = sideB.VertexIndices[(int)Math.Round(normalized * (sideB.VertexIndices.Count - 1))];
            pairs.Add(new CompiledSeamVertexPair(indexA, indexB, normalized));
        }

        double mismatch = Math.Abs(sideA.LengthCm - sideB.LengthCm);
        double denominator = Math.Max(Math.Max(sideA.LengthCm, sideB.LengthCm), GeometryEpsilon);
        return new CompiledPatternSeam(
            seam.Id,
            seam.Name,
            panelA.Id,
            panelB.Id,
            seam.SideA.EdgeIds.ToArray(),
            seam.SideB.EdgeIds.ToArray(),
            reverseA,
            reverseB,
            sideA.LengthCm,
            sideB.LengthCm,
            mismatch,
            mismatch / denominator,
            pairs,
            seam.AllowanceCm,
            seam.Strength);
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

    private static CompiledPatternClosure CompileClosure(
        GarmentClosureDocument closure,
        IReadOnlyDictionary<string, CompiledPatternPanel> panelsById)
    {
        if (!panelsById.TryGetValue(closure.AnchorA.PanelId, out CompiledPatternPanel? panelA) ||
            !panelsById.TryGetValue(closure.AnchorB.PanelId, out CompiledPatternPanel? panelB))
        {
            throw new PatternTopologyException([
                $"Closure {closure.Id} references a panel that did not compile."
            ]);
        }

        SeamSideDocument sideA = new(
            closure.AnchorA.PanelId,
            closure.AnchorA.EdgeIds,
            closure.AnchorA.Reverse);
        SeamSideDocument sideB = new(
            closure.AnchorB.PanelId,
            closure.AnchorB.EdgeIds,
            closure.AnchorB.Reverse);
        SeamChain chainA = BuildSeamChain(closure.Id, "anchor A", sideA, panelA);
        SeamChain chainB = BuildSeamChain(closure.Id, "anchor B", sideB, panelB);
        List<CompiledClosureConstraint> constraints = [];
        for (int index = 0; index < closure.ConstraintCount; index++)
        {
            double normalized = closure.ConstraintCount == 1
                ? 0.5
                : index / (double)(closure.ConstraintCount - 1);
            double positionA = Lerp(closure.AnchorA.StartPosition, closure.AnchorA.EndPosition, normalized);
            double positionB = Lerp(closure.AnchorB.StartPosition, closure.AnchorB.EndPosition, normalized);
            int vertexA = chainA.VertexIndices[(int)Math.Round(positionA * (chainA.VertexIndices.Count - 1))];
            int vertexB = chainB.VertexIndices[(int)Math.Round(positionB * (chainB.VertexIndices.Count - 1))];
            constraints.Add(new CompiledClosureConstraint(vertexA, vertexB, normalized));
        }

        return new CompiledPatternClosure(
            closure.Id,
            closure.Name,
            closure.Kind,
            closure.State,
            new CompiledClosureAnchor(
                panelA.Id,
                closure.AnchorA.EdgeIds.ToArray(),
                closure.AnchorA.Reverse,
                closure.AnchorA.StartPosition,
                closure.AnchorA.EndPosition),
            new CompiledClosureAnchor(
                panelB.Id,
                closure.AnchorB.EdgeIds.ToArray(),
                closure.AnchorB.Reverse,
                closure.AnchorB.StartPosition,
                closure.AnchorB.EndPosition),
            constraints,
            closure.TargetDistanceCm,
            closure.Strength);
    }

    private static double Lerp(double first, double second, double amount)
        => first + (second - first) * amount;

    private static SeamChain BuildSeamChain(
        string seamId,
        string sideName,
        SeamSideDocument side,
        CompiledPatternPanel panel)
    {
        if (side.EdgeIds.Count == 0)
        {
            throw new PatternTopologyException([
                $"Seam {seamId} side {sideName} contains no edges."
            ]);
        }

        Dictionary<string, CompiledPatternEdge> edgesById = panel.Edges
            .ToDictionary(edge => edge.Id, StringComparer.OrdinalIgnoreCase);
        List<int> indices = [];
        double length = 0;
        foreach (string edgeId in side.EdgeIds)
        {
            if (!edgesById.TryGetValue(edgeId, out CompiledPatternEdge? edge))
            {
                throw new PatternTopologyException([
                    $"Seam {seamId} side {sideName} references missing compiled edge {edgeId}."
                ]);
            }

            if (indices.Count > 0 && indices[^1] != edge.VertexIndices[0])
            {
                throw new PatternTopologyException([
                    $"Seam {seamId} side {sideName} has noncontiguous edge sequence before {edgeId}."
                ]);
            }

            int startOffset = indices.Count == 0 ? 0 : 1;
            indices.AddRange(edge.VertexIndices.Skip(startOffset));
            length += edge.LengthCm;
        }

        if (side.Reverse)
        {
            indices.Reverse();
        }

        return new SeamChain(indices, length);
    }

    private static PatternPointDocument ScalePoint(
        PatternPieceDocument piece,
        PatternPointDocument point)
        => new(point.X * piece.ScaleX, point.Y * piece.ScaleY);

    private static bool IsFinite(PatternPointDocument point)
        => double.IsFinite(point.X) && double.IsFinite(point.Y);

    private static PatternPointDocument ToPoint(CompiledPatternVertex vertex)
        => new(vertex.X, vertex.Y);

    private static double Distance(PatternPointDocument first, PatternPointDocument second)
        => Math.Sqrt(
            ((first.X - second.X) * (first.X - second.X)) +
            ((first.Y - second.Y) * (first.Y - second.Y)));

    private static double ChainLength(
        IReadOnlyList<int> indices,
        IReadOnlyList<CompiledPatternVertex> vertices)
    {
        double length = 0;
        for (int index = 1; index < indices.Count; index++)
        {
            length += Distance(ToPoint(vertices[indices[index - 1]]), ToPoint(vertices[indices[index]]));
        }

        return length;
    }

    private static double SignedArea(IReadOnlyList<CompiledPatternVertex> vertices)
    {
        double twiceArea = 0;
        for (int index = 0; index < vertices.Count; index++)
        {
            CompiledPatternVertex current = vertices[index];
            CompiledPatternVertex next = vertices[(index + 1) % vertices.Count];
            twiceArea += (current.X * next.Y) - (next.X * current.Y);
        }

        return twiceArea * 0.5;
    }

    private static double Cross(
        CompiledPatternVertex first,
        CompiledPatternVertex second,
        CompiledPatternVertex third)
        => ((second.X - first.X) * (third.Y - first.Y)) -
           ((second.Y - first.Y) * (third.X - first.X));

    private static double Cross(
        PatternPointDocument first,
        PatternPointDocument second,
        PatternPointDocument third)
        => ((second.X - first.X) * (third.Y - first.Y)) -
           ((second.Y - first.Y) * (third.X - first.X));

    private static bool PointStrictlyInsideTriangle(
        CompiledPatternVertex point,
        CompiledPatternVertex first,
        CompiledPatternVertex second,
        CompiledPatternVertex third)
    {
        double firstCross = Cross(first, second, point);
        double secondCross = Cross(second, third, point);
        double thirdCross = Cross(third, first, point);
        bool positive = firstCross > GeometryEpsilon &&
            secondCross > GeometryEpsilon && thirdCross > GeometryEpsilon;
        bool negative = firstCross < -GeometryEpsilon &&
            secondCross < -GeometryEpsilon && thirdCross < -GeometryEpsilon;
        return positive || negative;
    }

    private static bool SegmentsIntersect(
        PatternPointDocument firstA,
        PatternPointDocument firstB,
        PatternPointDocument secondA,
        PatternPointDocument secondB)
    {
        double cross1 = Cross(firstA, firstB, secondA);
        double cross2 = Cross(firstA, firstB, secondB);
        double cross3 = Cross(secondA, secondB, firstA);
        double cross4 = Cross(secondA, secondB, firstB);
        bool properIntersection =
            ((cross1 > GeometryEpsilon && cross2 < -GeometryEpsilon) ||
             (cross1 < -GeometryEpsilon && cross2 > GeometryEpsilon)) &&
            ((cross3 > GeometryEpsilon && cross4 < -GeometryEpsilon) ||
             (cross3 < -GeometryEpsilon && cross4 > GeometryEpsilon));
        if (properIntersection)
        {
            return true;
        }

        return (Math.Abs(cross1) <= GeometryEpsilon && PointOnSegment(secondA, firstA, firstB)) ||
               (Math.Abs(cross2) <= GeometryEpsilon && PointOnSegment(secondB, firstA, firstB)) ||
               (Math.Abs(cross3) <= GeometryEpsilon && PointOnSegment(firstA, secondA, secondB)) ||
               (Math.Abs(cross4) <= GeometryEpsilon && PointOnSegment(firstB, secondA, secondB));
    }

    private static bool PointOnSegment(
        PatternPointDocument point,
        PatternPointDocument start,
        PatternPointDocument end)
        => point.X >= Math.Min(start.X, end.X) - GeometryEpsilon &&
           point.X <= Math.Max(start.X, end.X) + GeometryEpsilon &&
           point.Y >= Math.Min(start.Y, end.Y) - GeometryEpsilon &&
           point.Y <= Math.Max(start.Y, end.Y) + GeometryEpsilon;

    private static void AddTriangleEdge(
        IDictionary<(int A, int B), int> edgeUse,
        int first,
        int second)
    {
        (int A, int B) edge = first < second ? (first, second) : (second, first);
        edgeUse.TryGetValue(edge, out int count);
        edgeUse[edge] = count + 1;
    }

    private sealed record PieceTopology(
        IReadOnlyList<CompiledPatternVertex> Vertices,
        IReadOnlyList<CompiledPatternTriangle> Triangles,
        IReadOnlyList<CompiledPatternEdge> Edges,
        double SignedAreaCm2);

    private sealed record SeamChain(IReadOnlyList<int> VertexIndices, double LengthCm);
}
