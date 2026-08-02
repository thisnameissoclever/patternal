using System.Security.Cryptography;
using System.Text.Json;

namespace Patterna.UnrealGarmentCompiler;

public sealed record PatternAwareMeshVertex(double X, double Y, double U, double V);

public sealed record PatternAwareMeshPanel(
    string SourcePanelName,
    string PanelId,
    string PieceId,
    PatternAwareMeshVertex[] Vertices,
    int[][] Triangles,
    Dictionary<string, int[]> EdgeVertexIndices);

public sealed record PatternAwareMeshSeam(
    string SeamId,
    string PanelA,
    string EdgeA,
    string PanelB,
    string EdgeB,
    int VertexCount);

public sealed record PatternAwareMeshDocument(
    string SchemaVersion,
    string SourcePatternSha256,
    double MeshResolutionCm,
    string Generator,
    PatternAwareMeshPanel[] Panels,
    PatternAwareMeshSeam[] Seams)
{
    public const string CurrentSchemaVersion = "patterna.garmentcode-pattern-mesh/1.0";

    public static PatternAwareMeshDocument Load(string path, string sourcePatternPath)
    {
        string resolvedPath = Path.GetFullPath(path);
        string resolvedSourcePath = Path.GetFullPath(sourcePatternPath);
        JsonSerializerOptions options = new()
        {
            PropertyNameCaseInsensitive = true
        };
        PatternAwareMeshDocument document = JsonSerializer.Deserialize<PatternAwareMeshDocument>(
            File.ReadAllText(resolvedPath),
            options) ?? throw new InvalidDataException("The pattern-aware mesh sidecar is empty.");
        document.Validate(resolvedSourcePath);
        return document;
    }

    public PatternAwareMeshPanel RequirePanel(string panelId)
        => Panels.FirstOrDefault(panel => panel.PanelId.Equals(
            panelId,
            StringComparison.OrdinalIgnoreCase)) ??
            throw new InvalidDataException($"Pattern-aware mesh has no panel {panelId}.");

    private void Validate(string sourcePatternPath)
    {
        if (!SchemaVersion.Equals(CurrentSchemaVersion, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"Unsupported pattern-aware mesh schema {SchemaVersion}.");
        }
        string sourceHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(sourcePatternPath)))
            .ToLowerInvariant();
        if (!sourceHash.Equals(SourcePatternSha256, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException(
                "Pattern-aware mesh sidecar does not match the GarmentCode source pattern.");
        }
        if (!double.IsFinite(MeshResolutionCm) || MeshResolutionCm <= 0)
        {
            throw new InvalidDataException("Pattern-aware mesh resolution must be positive.");
        }
        if (Panels.Length == 0 || Panels.Select(panel => panel.PanelId).Distinct(
            StringComparer.OrdinalIgnoreCase).Count() != Panels.Length)
        {
            throw new InvalidDataException("Pattern-aware mesh panel identifiers must be nonempty and unique.");
        }
        foreach (PatternAwareMeshPanel panel in Panels)
        {
            if (panel.Vertices.Length < 3 || panel.Triangles.Length == 0)
            {
                throw new InvalidDataException($"Pattern-aware panel {panel.PanelId} has no usable mesh.");
            }
            foreach (int[] triangle in panel.Triangles)
            {
                if (triangle.Length != 3 || triangle.Any(index => index < 0 || index >= panel.Vertices.Length))
                {
                    throw new InvalidDataException($"Pattern-aware panel {panel.PanelId} has an invalid triangle.");
                }
            }
            foreach ((string edgeId, int[] indices) in panel.EdgeVertexIndices)
            {
                if (indices.Length < 2 || indices.Any(index => index < 0 || index >= panel.Vertices.Length))
                {
                    throw new InvalidDataException(
                        $"Pattern-aware panel {panel.PanelId} edge {edgeId} has invalid vertex indices.");
                }
            }
        }
        foreach (PatternAwareMeshSeam seam in Seams)
        {
            PatternAwareMeshPanel panelA = RequirePanel(seam.PanelA);
            PatternAwareMeshPanel panelB = RequirePanel(seam.PanelB);
            if (!panelA.EdgeVertexIndices.TryGetValue(seam.EdgeA, out int[]? edgeA) ||
                !panelB.EdgeVertexIndices.TryGetValue(seam.EdgeB, out int[]? edgeB) ||
                edgeA.Length != edgeB.Length ||
                edgeA.Length != seam.VertexCount)
            {
                throw new InvalidDataException(
                    $"Pattern-aware seam {seam.SeamId} is not stitch matched.");
            }
        }
    }
}
