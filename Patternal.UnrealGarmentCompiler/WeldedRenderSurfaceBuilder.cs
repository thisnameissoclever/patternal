namespace Patterna.UnrealGarmentCompiler;

public sealed record RenderSurfaceVertex(
    int Index,
    double X,
    double Y,
    double Z);

public sealed record RenderSurfaceTriangle(
    int A,
    int B,
    int C,
    StructuredPoint2 UvA,
    StructuredPoint2 UvB,
    StructuredPoint2 UvC);

public sealed record WeldedRenderSurface(
    IReadOnlyList<RenderSurfaceVertex> Vertices,
    IReadOnlyList<RenderSurfaceTriangle> Triangles,
    int SourceVertexCount,
    int WeldedBaseVertexCount,
    int WeldedConstructionStitchCount,
    int UnweldedConstructionStitchCount,
    double MaximumWeldedGapCm,
    int SubdivisionLevel,
    string RefinementAlgorithm,
    int ProtectedBoundaryVertexCount,
    int ProtectedNonManifoldVertexCount,
    double MaximumBaseVertexDisplacementCm,
    double AverageBaseVertexDisplacementCm);

public static class WeldedRenderSurfaceBuilder
{
    private const double MaximumRenderWeldGapCm = 0.25;
    private const double MaximumBaseVertexDisplacementCm = 0.75;
    private const int SurfaceFairingPasses = 3;
    private const double SurfaceFairingForwardWeight = 0.45;
    private const double SurfaceFairingReverseWeight = -0.47;

    private sealed record EdgeTopology(
        int A,
        int B,
        List<int> OppositeVertices);

    private sealed class DisjointSet
    {
        private readonly int[] parent;
        private readonly byte[] rank;

        public DisjointSet(int count)
        {
            parent = Enumerable.Range(0, count).ToArray();
            rank = new byte[count];
        }

        public int Find(int value)
        {
            int root = value;
            while (parent[root] != root)
            {
                root = parent[root];
            }
            while (parent[value] != value)
            {
                int next = parent[value];
                parent[value] = root;
                value = next;
            }
            return root;
        }

        public void Union(int first, int second)
        {
            int rootA = Find(first);
            int rootB = Find(second);
            if (rootA == rootB)
            {
                return;
            }
            if (rank[rootA] < rank[rootB])
            {
                parent[rootA] = rootB;
            }
            else if (rank[rootA] > rank[rootB])
            {
                parent[rootB] = rootA;
            }
            else
            {
                parent[rootB] = rootA;
                rank[rootA]++;
            }
        }
    }

    public static WeldedRenderSurface Build(
        FullGarmentArrangementReport arrangement,
        int subdivisionLevel = 1)
    {
        ArgumentNullException.ThrowIfNull(arrangement);
        if (subdivisionLevel is < 0 or > 2)
        {
            throw new ArgumentOutOfRangeException(
                nameof(subdivisionLevel),
                "Render subdivision must be between zero and two levels.");
        }

        Dictionary<string, int> panelOffsets = new(StringComparer.OrdinalIgnoreCase);
        int sourceVertexCount = 0;
        foreach (ArrangedPanelMesh panel in arrangement.Panels)
        {
            panelOffsets.Add(panel.PanelId, sourceVertexCount);
            sourceVertexCount += panel.Vertices.Count;
        }

        DisjointSet weldGroups = new(sourceVertexCount);
        int weldedStitches = 0;
        int unweldedStitches = 0;
        double maximumWeldedGapCm = 0;
        foreach (ArrangedSeamStitch stitch in arrangement.Stitches)
        {
            if (stitch.GapCm > MaximumRenderWeldGapCm)
            {
                unweldedStitches++;
                continue;
            }
            weldGroups.Union(
                panelOffsets[stitch.PanelA] + stitch.VertexA,
                panelOffsets[stitch.PanelB] + stitch.VertexB);
            weldedStitches++;
            maximumWeldedGapCm = Math.Max(maximumWeldedGapCm, stitch.GapCm);
        }

        ArrangedPoint3[] sourcePoints = new ArrangedPoint3[sourceVertexCount];
        foreach (ArrangedPanelMesh panel in arrangement.Panels)
        {
            int offset = panelOffsets[panel.PanelId];
            foreach (ArrangedPanelVertex vertex in panel.Vertices)
            {
                sourcePoints[offset + vertex.Index] = new ArrangedPoint3(
                    vertex.X,
                    vertex.Y,
                    vertex.Z);
            }
        }

        Dictionary<int, List<int>> membersByRoot = [];
        for (int sourceIndex = 0; sourceIndex < sourceVertexCount; ++sourceIndex)
        {
            int root = weldGroups.Find(sourceIndex);
            if (!membersByRoot.TryGetValue(root, out List<int>? members))
            {
                members = [];
                membersByRoot.Add(root, members);
            }
            members.Add(sourceIndex);
        }

        Dictionary<int, int> renderIndexByRoot = [];
        List<RenderSurfaceVertex> vertices = [];
        foreach ((int root, List<int> members) in membersByRoot.OrderBy(group => group.Key))
        {
            ArrangedPoint3 average = members
                .Select(index => sourcePoints[index])
                .Aggregate(new ArrangedPoint3(0, 0, 0), (sum, point) => sum + point) /
                members.Count;
            int renderIndex = vertices.Count;
            renderIndexByRoot.Add(root, renderIndex);
            vertices.Add(new RenderSurfaceVertex(
                renderIndex,
                average.X,
                average.Y,
                average.Z));
        }

        int RenderIndex(string panelId, int localVertex) =>
            renderIndexByRoot[weldGroups.Find(panelOffsets[panelId] + localVertex)];

        double restScaleX = arrangement.Panels.Max(panel =>
            panel.Vertices.Max(vertex => vertex.RestX) - panel.Vertices.Min(vertex => vertex.RestX));
        double restScaleY = arrangement.Panels.Max(panel =>
            panel.Vertices.Max(vertex => vertex.RestY) - panel.Vertices.Min(vertex => vertex.RestY));
        List<RenderSurfaceTriangle> triangles = [];
        foreach (ArrangedPanelMesh panel in arrangement.Panels)
        {
            double minimumX = panel.Vertices.Min(vertex => vertex.RestX);
            double minimumY = panel.Vertices.Min(vertex => vertex.RestY);
            StructuredPoint2 Uv(int localIndex)
            {
                ArrangedPanelVertex vertex = panel.Vertices[localIndex];
                return new StructuredPoint2(
                    (vertex.RestX - minimumX) / Math.Max(restScaleX, 0.000001),
                    1.0 - (vertex.RestY - minimumY) / Math.Max(restScaleY, 0.000001));
            }

            foreach (StructuredPanelTriangle sourceTriangle in panel.Triangles)
            {
                int localA = sourceTriangle.A;
                int localB = sourceTriangle.B;
                int localC = sourceTriangle.C;
                if (!panel.ReverseWinding)
                {
                    (localB, localC) = (localC, localB);
                }
                int a = RenderIndex(panel.PanelId, localA);
                int b = RenderIndex(panel.PanelId, localB);
                int c = RenderIndex(panel.PanelId, localC);
                if (a == b || b == c || c == a)
                {
                    throw new InvalidOperationException(
                        $"Render seam welding collapsed a triangle on panel {panel.PanelId}.");
                }
                triangles.Add(new RenderSurfaceTriangle(
                    a,
                    b,
                    c,
                    Uv(localA),
                    Uv(localB),
                    Uv(localC)));
            }
        }

        int weldedBaseVertexCount = vertices.Count;
        RenderSurfaceVertex[] weldedBaseVertices = vertices.ToArray();
        (int protectedBoundaryVertexCount, int protectedNonManifoldVertexCount) =
            FairBaseSurface(
                vertices,
                triangles,
                weldedBaseVertices,
                SurfaceFairingPasses,
                MaximumBaseVertexDisplacementCm);
        for (int level = 0; level < subdivisionLevel; ++level)
        {
            LoopSubdivide(
                vertices,
                triangles,
                weldedBaseVertices,
                MaximumBaseVertexDisplacementCm);
        }

        double[] baseDisplacements = Enumerable.Range(0, weldedBaseVertexCount)
            .Select(index => Distance(weldedBaseVertices[index], vertices[index]))
            .ToArray();

        return new WeldedRenderSurface(
            vertices,
            triangles,
            sourceVertexCount,
            weldedBaseVertexCount,
            weldedStitches,
            unweldedStitches,
            maximumWeldedGapCm,
            subdivisionLevel,
            "boundary-constrained Taubin fairing and Loop subdivision",
            protectedBoundaryVertexCount,
            protectedNonManifoldVertexCount,
            baseDisplacements.DefaultIfEmpty(0).Max(),
            baseDisplacements.DefaultIfEmpty(0).Average());
    }

    private static (int BoundaryVertexCount, int NonManifoldVertexCount) FairBaseSurface(
        List<RenderSurfaceVertex> vertices,
        IReadOnlyList<RenderSurfaceTriangle> triangles,
        IReadOnlyList<RenderSurfaceVertex> anchors,
        int passes,
        double maximumVertexDisplacementCm)
    {
        (Dictionary<(int A, int B), EdgeTopology> _, HashSet<int>[] neighbors,
            HashSet<int> boundaryVertices, HashSet<int> nonManifoldVertices) =
            BuildTopology(vertices.Count, triangles);

        void Smooth(double weight)
        {
            RenderSurfaceVertex[] source = vertices.ToArray();
            for (int index = 0; index < source.Length; ++index)
            {
                if (boundaryVertices.Contains(index) ||
                    nonManifoldVertices.Contains(index) ||
                    neighbors[index].Count < 3)
                {
                    continue;
                }

                RenderSurfaceVertex vertex = source[index];
                double averageX = neighbors[index].Average(neighbor => source[neighbor].X);
                double averageY = neighbors[index].Average(neighbor => source[neighbor].Y);
                double averageZ = neighbors[index].Average(neighbor => source[neighbor].Z);
                RenderSurfaceVertex candidate = new(
                    vertex.Index,
                    vertex.X + weight * (averageX - vertex.X),
                    vertex.Y + weight * (averageY - vertex.Y),
                    vertex.Z + weight * (averageZ - vertex.Z));
                vertices[index] = ClampDisplacement(
                    anchors[index],
                    candidate,
                    maximumVertexDisplacementCm);
            }
        }

        for (int pass = 0; pass < passes; ++pass)
        {
            Smooth(SurfaceFairingForwardWeight);
            Smooth(SurfaceFairingReverseWeight);
        }
        return (boundaryVertices.Count, nonManifoldVertices.Count);
    }

    private static void LoopSubdivide(
        List<RenderSurfaceVertex> vertices,
        List<RenderSurfaceTriangle> triangles,
        IReadOnlyList<RenderSurfaceVertex> baseAnchors,
        double maximumVertexDisplacementCm)
    {
        (Dictionary<(int A, int B), EdgeTopology> topologyByEdge,
            HashSet<int>[] neighbors, HashSet<int> boundaryVertices,
            HashSet<int> nonManifoldVertices) = BuildTopology(vertices.Count, triangles);

        RenderSurfaceVertex[] sourceVertices = vertices.ToArray();
        RenderSurfaceVertex[] repositionedVertices = new RenderSurfaceVertex[sourceVertices.Length];
        for (int index = 0; index < sourceVertices.Length; ++index)
        {
            RenderSurfaceVertex source = sourceVertices[index];
            if (boundaryVertices.Contains(index) ||
                nonManifoldVertices.Contains(index) ||
                neighbors[index].Count < 3)
            {
                repositionedVertices[index] = source;
                continue;
            }

            int valence = neighbors[index].Count;
            double beta = valence == 3 ? 3.0 / 16.0 : 3.0 / (8.0 * valence);
            RenderSurfaceVertex candidate = new(
                source.Index,
                (1.0 - valence * beta) * source.X + beta * neighbors[index].Sum(neighbor => sourceVertices[neighbor].X),
                (1.0 - valence * beta) * source.Y + beta * neighbors[index].Sum(neighbor => sourceVertices[neighbor].Y),
                (1.0 - valence * beta) * source.Z + beta * neighbors[index].Sum(neighbor => sourceVertices[neighbor].Z));
            repositionedVertices[index] = ClampDisplacement(
                index < baseAnchors.Count ? baseAnchors[index] : source,
                candidate,
                maximumVertexDisplacementCm);
        }

        vertices.Clear();
        vertices.AddRange(repositionedVertices);

        Dictionary<(int A, int B), int> edgeVertexByEdge = [];
        int EdgeVertex(int first, int second)
        {
            (int A, int B) key = first < second ? (first, second) : (second, first);
            if (edgeVertexByEdge.TryGetValue(key, out int existing))
            {
                return existing;
            }

            EdgeTopology topology = topologyByEdge[key];
            RenderSurfaceVertex a = sourceVertices[key.A];
            RenderSurfaceVertex b = sourceVertices[key.B];
            double x = (a.X + b.X) * 0.5;
            double y = (a.Y + b.Y) * 0.5;
            double z = (a.Z + b.Z) * 0.5;
            if (topology.OppositeVertices.Count == 2)
            {
                RenderSurfaceVertex c = sourceVertices[topology.OppositeVertices[0]];
                RenderSurfaceVertex d = sourceVertices[topology.OppositeVertices[1]];
                x = 0.375 * (a.X + b.X) + 0.125 * (c.X + d.X);
                y = 0.375 * (a.Y + b.Y) + 0.125 * (c.Y + d.Y);
                z = 0.375 * (a.Z + b.Z) + 0.125 * (c.Z + d.Z);
            }

            int index = vertices.Count;
            vertices.Add(new RenderSurfaceVertex(index, x, y, z));
            edgeVertexByEdge.Add(key, index);
            return index;
        }

        List<RenderSurfaceTriangle> subdivided = new(triangles.Count * 4);
        foreach (RenderSurfaceTriangle triangle in triangles)
        {
            int ab = EdgeVertex(triangle.A, triangle.B);
            int bc = EdgeVertex(triangle.B, triangle.C);
            int ca = EdgeVertex(triangle.C, triangle.A);
            StructuredPoint2 uvAb = UvMidpoint(triangle.UvA, triangle.UvB);
            StructuredPoint2 uvBc = UvMidpoint(triangle.UvB, triangle.UvC);
            StructuredPoint2 uvCa = UvMidpoint(triangle.UvC, triangle.UvA);
            subdivided.Add(new RenderSurfaceTriangle(
                triangle.A, ab, ca, triangle.UvA, uvAb, uvCa));
            subdivided.Add(new RenderSurfaceTriangle(
                ab, triangle.B, bc, uvAb, triangle.UvB, uvBc));
            subdivided.Add(new RenderSurfaceTriangle(
                ca, bc, triangle.C, uvCa, uvBc, triangle.UvC));
            subdivided.Add(new RenderSurfaceTriangle(
                ab, bc, ca, uvAb, uvBc, uvCa));
        }
        triangles.Clear();
        triangles.AddRange(subdivided);
    }

    private static (
        Dictionary<(int A, int B), EdgeTopology> Edges,
        HashSet<int>[] Neighbors,
        HashSet<int> BoundaryVertices,
        HashSet<int> NonManifoldVertices) BuildTopology(
            int vertexCount,
            IReadOnlyList<RenderSurfaceTriangle> triangles)
    {
        Dictionary<(int A, int B), EdgeTopology> topologyByEdge = [];
        HashSet<int>[] neighbors = Enumerable.Range(0, vertexCount)
            .Select(_ => new HashSet<int>())
            .ToArray();

        void AddEdge(int first, int second, int opposite)
        {
            (int A, int B) key = first < second ? (first, second) : (second, first);
            if (!topologyByEdge.TryGetValue(key, out EdgeTopology? topology))
            {
                topology = new EdgeTopology(key.A, key.B, []);
                topologyByEdge.Add(key, topology);
            }
            topology.OppositeVertices.Add(opposite);
            neighbors[first].Add(second);
            neighbors[second].Add(first);
        }

        foreach (RenderSurfaceTriangle triangle in triangles)
        {
            AddEdge(triangle.A, triangle.B, triangle.C);
            AddEdge(triangle.B, triangle.C, triangle.A);
            AddEdge(triangle.C, triangle.A, triangle.B);
        }

        HashSet<int> boundaryVertices = topologyByEdge.Values
            .Where(edge => edge.OppositeVertices.Count == 1)
            .SelectMany(edge => new[] { edge.A, edge.B })
            .ToHashSet();
        HashSet<int> nonManifoldVertices = topologyByEdge.Values
            .Where(edge => edge.OppositeVertices.Count > 2)
            .SelectMany(edge => new[] { edge.A, edge.B })
            .ToHashSet();
        return (topologyByEdge, neighbors, boundaryVertices, nonManifoldVertices);
    }

    private static RenderSurfaceVertex ClampDisplacement(
        RenderSurfaceVertex source,
        RenderSurfaceVertex candidate,
        double maximumDisplacementCm)
    {
        double distance = Distance(source, candidate);
        if (distance <= maximumDisplacementCm || distance <= 0.0000001)
        {
            return candidate;
        }
        double scale = maximumDisplacementCm / distance;
        return new RenderSurfaceVertex(
            source.Index,
            source.X + (candidate.X - source.X) * scale,
            source.Y + (candidate.Y - source.Y) * scale,
            source.Z + (candidate.Z - source.Z) * scale);
    }

    private static double Distance(RenderSurfaceVertex a, RenderSurfaceVertex b)
    {
        double x = b.X - a.X;
        double y = b.Y - a.Y;
        double z = b.Z - a.Z;
        return Math.Sqrt(x * x + y * y + z * z);
    }

    private static StructuredPoint2 UvMidpoint(StructuredPoint2 a, StructuredPoint2 b) =>
        new((a.X + b.X) * 0.5, (a.Y + b.Y) * 0.5);
}
