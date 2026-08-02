using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Patterna;

public sealed class GarmentCodeExportException : InvalidOperationException
{
    public GarmentCodeExportException(string message)
        : base(message)
    {
    }
}

public static class GarmentCodePatternExporter
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true
    };

    private static readonly JsonSerializerOptions ConstructionJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    public static string Export(GarmentDocument garment, string revision)
    {
        ArgumentNullException.ThrowIfNull(garment);
        ArgumentException.ThrowIfNullOrWhiteSpace(revision);

        if (!string.Equals(garment.Source?.Format, "GarmentCode JSON", StringComparison.OrdinalIgnoreCase))
        {
            throw new GarmentCodeExportException("Only garments imported from GarmentCode JSON can be regenerated through the GarmentCode simulation pipeline.");
        }
        if (garment.Closures.Count > 0)
        {
            throw new GarmentCodeExportException("GarmentCode regeneration does not yet support Patternal closure constraints.");
        }

        IReadOnlyList<string> validationErrors = garment.Validate();
        if (validationErrors.Count > 0)
        {
            throw new GarmentCodeExportException(string.Join(Environment.NewLine, validationErrors));
        }

        string currentStructuralSignature = ComputeStructuralSignature(garment);
        if (!string.IsNullOrWhiteSpace(garment.Source?.RawDocumentJson) &&
            string.Equals(
                garment.Source.StructuralSignature,
                currentStructuralSignature,
                StringComparison.Ordinal))
        {
            string rawSource = garment.Source.RawDocumentJson;
            return rawSource.EndsWith('\n') ? rawSource : rawSource + Environment.NewLine;
        }

        Dictionary<string, PatternPieceDocument> piecesById = garment.Pieces
            .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, ClothPanelDocument> panelsById = garment.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, string> sourceNamesByPanelId = new(StringComparer.OrdinalIgnoreCase);
        JsonObject panels = new();

        foreach (ClothPanelDocument panel in garment.Panels)
        {
            if (panel.SourcePlacement is null)
            {
                throw new GarmentCodeExportException($"Panel {panel.Id} has no GarmentCode source placement.");
            }

            PatternPieceDocument piece = piecesById[panel.PieceId];
            if (piece.ScaleX <= 0 || piece.ScaleY <= 0)
            {
                throw new GarmentCodeExportException($"Pattern piece {piece.Id} has an invalid scale.");
            }

            string sourceName = SourcePanelName(piece.Id);
            if (panels.ContainsKey(sourceName))
            {
                throw new GarmentCodeExportException($"Multiple Patternal panels map to GarmentCode panel {sourceName}.");
            }
            sourceNamesByPanelId[panel.Id] = sourceName;
            panels[sourceName] = ExportPanel(
                piece,
                panel.SourcePlacement,
                panel.SourcePatternOrigin,
                panel.SourceLabel);
        }

        JsonArray stitches = new();
        foreach (GarmentSeamDocument seam in garment.Seams)
        {
            if (seam.SideA.EdgeIds.Count == 0 || seam.SideA.EdgeIds.Count != seam.SideB.EdgeIds.Count)
            {
                throw new GarmentCodeExportException($"Seam {seam.Id} must reference the same nonzero number of edges on each side for GarmentCode regeneration.");
            }

            IReadOnlyList<string> sideBEdgeIds = seam.SideB.EdgeIds.Count == 1
                ? seam.SideB.EdgeIds
                : seam.SideB.EdgeIds.Reverse().ToArray();
            for (int edgeIndex = 0; edgeIndex < seam.SideA.EdgeIds.Count; edgeIndex++)
            {
                JsonObject sideA = ExportStitchSide(
                    seam.SideA,
                    seam.SideA.EdgeIds[edgeIndex],
                    panelsById,
                    piecesById,
                    sourceNamesByPanelId);
                JsonObject sideB = ExportStitchSide(
                    seam.SideB,
                    sideBEdgeIds[edgeIndex],
                    panelsById,
                    piecesById,
                    sourceNamesByPanelId);
                bool relativeReverse = ResolveRelativeReverse(garment, seam);
                if (relativeReverse && seam.SideB.Reverse)
                {
                    (sideA, sideB) = (sideB, sideA);
                }
                JsonArray stitch = new(sideA, sideB);
                if (!relativeReverse)
                {
                    stitch.Add("right_wrong");
                }
                stitches.Add(stitch);
            }
        }

        JsonObject patternaMetadata = new()
        {
            ["generator"] = "Patterna.GarmentCodePatternExporter",
            ["source_revision"] = garment.Source?.Revision,
            ["document_revision"] = revision
        };
        JsonObject constructionGeometry = ExportConstructionGeometry(garment.Pieces);
        if (constructionGeometry.Count > 0)
        {
            patternaMetadata["construction_geometry"] = constructionGeometry;
        }
        if (garment.EaseProfile is not null)
        {
            patternaMetadata["ease_profile"] = new JsonObject
            {
                ["chest_ease_cm"] = garment.EaseProfile.ChestEaseCm,
                ["waist_ease_cm"] = garment.EaseProfile.WaistEaseCm,
                ["hip_ease_cm"] = garment.EaseProfile.HipEaseCm,
                ["upper_arm_ease_cm"] = garment.EaseProfile.UpperArmEaseCm,
                ["armscye_ease_cm"] = garment.EaseProfile.ArmscyeEaseCm
            };
        }
        if (garment.BodyReference is not null)
        {
            GarmentBodyReferenceDocument reference = garment.BodyReference;
            patternaMetadata["body_reference"] = new JsonObject
            {
                ["chest_cm"] = reference.ChestCm,
                ["waist_cm"] = reference.WaistCm,
                ["hip_cm"] = reference.HipCm,
                ["shoulder_cm"] = reference.ShoulderCm,
                ["torso_cm"] = reference.TorsoCm,
                ["arm_length_cm"] = reference.ArmLengthCm,
                ["upper_arm_circumference_cm"] = reference.UpperArmCircumferenceCm,
                ["armhole_depth_cm"] = reference.ArmholeDepthCm,
                ["armscye_circumference_cm"] = reference.ArmscyeCircumferenceCm
            };
        }
        if (garment.ShirtConstructionProfile is not null)
        {
            ShirtConstructionProfileDocument profile = garment.ShirtConstructionProfile;
            patternaMetadata["shirt_construction_profile"] = new JsonObject
            {
                ["front_width_share_percent"] = profile.FrontWidthSharePercent,
                ["neckline_width_cm"] = profile.NecklineWidthCm,
                ["front_neck_depth_cm"] = profile.FrontNeckDepthCm,
                ["back_neck_depth_cm"] = profile.BackNeckDepthCm,
                ["shoulder_length_cm"] = profile.ShoulderLengthCm,
                ["shoulder_drop_cm"] = profile.ShoulderDropCm,
                ["armscye_depth_cm"] = profile.ArmscyeDepthCm,
                ["armscye_scoop_cm"] = profile.ArmscyeScoopCm,
                ["underarm_extension_cm"] = profile.UnderarmExtensionCm,
                ["sleeve_cap_height_cm"] = profile.SleeveCapHeightCm,
                ["front_balance_cm"] = profile.FrontBalanceCm
            };
        }
        if (garment.ShirtBustShapingProfile is not null)
        {
            ShirtBustShapingProfileDocument profile = garment.ShirtBustShapingProfile;
            patternaMetadata["shirt_bust_shaping_profile"] = new JsonObject
            {
                ["mode"] = profile.Mode,
                ["left_dart_intake_cm"] = profile.LeftDartIntakeCm,
                ["right_dart_intake_cm"] = profile.RightDartIntakeCm,
                ["bust_point_separation_cm"] = profile.BustPointSeparationCm,
                ["left_bust_height_cm"] = profile.LeftBustHeightCm,
                ["right_bust_height_cm"] = profile.RightBustHeightCm,
                ["left_bust_projection_cm"] = profile.LeftBustProjectionCm,
                ["right_bust_projection_cm"] = profile.RightBustProjectionCm,
                ["dart_tip_offset_cm"] = profile.DartTipOffsetCm,
                ["dart_mouth_drop_cm"] = profile.DartMouthDropCm,
                ["shoulder_dart_mouth_offset_cm"] = profile.ShoulderDartMouthOffsetCm,
                ["shoulder_dart_share_percent"] = profile.ShoulderDartSharePercent
            };
        }

        JsonObject root = new()
        {
            ["pattern"] = new JsonObject
            {
                ["panels"] = panels,
                ["stitches"] = stitches
            },
            ["parameters"] = new JsonObject(),
            ["parameter_order"] = new JsonArray(),
            ["properties"] = new JsonObject
            {
                ["curvature_coords"] = "relative",
                ["normalize_panel_translation"] = false,
                ["normalized_edge_loops"] = true,
                ["units_in_meter"] = 100
            },
            ["patterna"] = patternaMetadata
        };

        return root.ToJsonString(JsonOptions) + Environment.NewLine;
    }

    private static JsonObject ExportConstructionGeometry(IReadOnlyList<PatternPieceDocument> pieces)
    {
        JsonObject result = new();
        foreach (PatternPieceDocument piece in pieces)
        {
            result[piece.Id] = JsonSerializer.SerializeToNode(
                new PatternConstructionGeometryMetadata(
                    piece.Boundary.Select(curve => curve.Id).ToArray(),
                    piece.InternalPaths,
                    piece.Notches,
                    piece.Darts,
                    piece.Grainline),
                ConstructionJsonOptions);
        }
        return result;
    }

    public static string ComputeStructuralSignature(GarmentDocument garment)
    {
        ArgumentNullException.ThrowIfNull(garment);
        string canonical = JsonSerializer.Serialize(new
        {
            garment.Pieces,
            garment.Panels,
            garment.Seams,
            garment.Closures,
            garment.EaseProfile,
            garment.BodyReference,
            garment.ShirtConstructionProfile,
            garment.ShirtBustShapingProfile
        });
        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(canonical)));
    }

    private static JsonObject ExportPanel(
        PatternPieceDocument piece,
        PatternPlacement3DDocument placement,
        PatternPointDocument? sourcePatternOrigin,
        string? sourceLabel)
    {
        PatternPointDocument sourceOrigin = sourcePatternOrigin ?? new PatternPointDocument(0, 0);
        PatternPointDocument[] vertices =
        [
            ToSourcePoint(piece.Start, piece, sourceOrigin),
            .. piece.Boundary.Select(curve => ToSourcePoint(curve.End, piece, sourceOrigin))
        ];
        JsonArray vertexArray = new(vertices
            .Select(point => (JsonNode)new JsonArray(point.X, point.Y))
            .ToArray());
        JsonArray edges = new();

        PatternPointDocument start = vertices[0];
        PatternPointDocument localStart = piece.Start;
        for (int index = 0; index < piece.Boundary.Count; index++)
        {
            PatternCurveDocument curve = piece.Boundary[index];
            PatternPointDocument end = vertices[index + 1];
            int endIndex = index + 1 == vertices.Length - 1 && PointsEqual(end, vertices[0])
                ? 0
                : index + 1;
            JsonObject edge = new()
            {
                ["endpoints"] = new JsonArray(index, endIndex)
            };
            if (!string.IsNullOrWhiteSpace(curve.Label))
            {
                edge["label"] = curve.Label;
            }
            bool preservesSourceCurve = PreservesSourceCurve(piece, curve, localStart);
            if (preservesSourceCurve && curve.GarmentCodeSource?.CurvatureJson is string sourceCurvatureJson)
            {
                edge["curvature"] = JsonNode.Parse(sourceCurvatureJson)
                    ?? throw new GarmentCodeExportException($"Pattern edge {piece.Id}/{curve.Id} has invalid source curvature metadata.");
            }
            else if (string.Equals(curve.Kind, "cubic", StringComparison.OrdinalIgnoreCase))
            {
                if (curve.Control1 is null || curve.Control2 is null)
                {
                    throw new GarmentCodeExportException($"Cubic edge {piece.Id}/{curve.Id} is missing a control point.");
                }
                edge["curvature"] = new JsonObject
                {
                    ["type"] = "cubic",
                    ["params"] = new JsonArray(
                        RelativeControl(start, end, ToSourcePoint(curve.Control1, piece, sourceOrigin), piece.Id, curve.Id),
                        RelativeControl(start, end, ToSourcePoint(curve.Control2, piece, sourceOrigin), piece.Id, curve.Id))
                };
            }
            else if (!string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase))
            {
                throw new GarmentCodeExportException($"Pattern edge kind {curve.Kind} is not supported by GarmentCode export.");
            }
            edges.Add(edge);
            start = end;
            localStart = curve.End;
        }

        if (!PointsEqual(vertices[^1], vertices[0]))
        {
            throw new GarmentCodeExportException($"Pattern piece {piece.Id} is not a closed boundary.");
        }
        vertexArray.RemoveAt(vertexArray.Count - 1);

        JsonObject panel = new()
        {
            ["translation"] = new JsonArray(placement.X, placement.Y, placement.Z),
            ["rotation"] = new JsonArray(
                placement.RotationXDegrees,
                placement.RotationYDegrees,
                placement.RotationZDegrees),
            ["vertices"] = vertexArray,
            ["edges"] = edges
        };
        if (!string.IsNullOrWhiteSpace(sourceLabel))
        {
            panel["label"] = sourceLabel;
        }
        return panel;
    }

    private static JsonObject ExportStitchSide(
        SeamSideDocument side,
        string edgeId,
        IReadOnlyDictionary<string, ClothPanelDocument> panelsById,
        IReadOnlyDictionary<string, PatternPieceDocument> piecesById,
        IReadOnlyDictionary<string, string> sourceNamesByPanelId)
    {
        ClothPanelDocument panel = panelsById[side.PanelId];
        PatternPieceDocument piece = piecesById[panel.PieceId];
        int edgeIndex = piece.Boundary
            .Select((edge, index) => new { edge.Id, Index = index })
            .FirstOrDefault(item => string.Equals(item.Id, edgeId, StringComparison.OrdinalIgnoreCase))?.Index ?? -1;
        if (edgeIndex < 0)
        {
            throw new GarmentCodeExportException($"Panel {panel.Id} does not contain edge {edgeId}.");
        }
        return new JsonObject
        {
            ["panel"] = sourceNamesByPanelId[panel.Id],
            ["edge"] = edgeIndex
        };
    }

    private static PatternPointDocument ToSourcePoint(
        PatternPointDocument point,
        PatternPieceDocument piece,
        PatternPointDocument sourceOrigin)
        => new(
            point.X * piece.ScaleX + sourceOrigin.X,
            point.Y * piece.ScaleY + sourceOrigin.Y);

    private static JsonArray RelativeControl(
        PatternPointDocument start,
        PatternPointDocument end,
        PatternPointDocument control,
        string pieceId,
        string edgeId)
    {
        double dx = end.X - start.X;
        double dy = end.Y - start.Y;
        double lengthSquared = dx * dx + dy * dy;
        if (lengthSquared <= 1e-12)
        {
            throw new GarmentCodeExportException($"Pattern edge {pieceId}/{edgeId} has zero length.");
        }
        double controlX = control.X - start.X;
        double controlY = control.Y - start.Y;
        double along = (controlX * dx + controlY * dy) / lengthSquared;
        double perpendicular = (controlY * dx - controlX * dy) / lengthSquared;
        return new JsonArray(along, perpendicular);
    }

    private static bool PointsEqual(PatternPointDocument first, PatternPointDocument second)
        => Math.Abs(first.X - second.X) < 0.000001 && Math.Abs(first.Y - second.Y) < 0.000001;

    private static bool OptionalPointsEqual(PatternPointDocument? first, PatternPointDocument? second)
        => first is null && second is null || first is not null && second is not null && PointsEqual(first, second);

    private static bool PreservesSourceCurve(
        PatternPieceDocument piece,
        PatternCurveDocument curve,
        PatternPointDocument localStart)
    {
        GarmentCodeCurveSourceDocument? source = curve.GarmentCodeSource;
        return source is not null &&
            Math.Abs(piece.ScaleX - 1) < 0.000001 &&
            Math.Abs(piece.ScaleY - 1) < 0.000001 &&
            PointsEqual(localStart, source.Start) &&
            PointsEqual(curve.End, source.End) &&
            OptionalPointsEqual(curve.Control1, source.Control1) &&
            OptionalPointsEqual(curve.Control2, source.Control2);
    }

    private static string SourcePanelName(string pieceId)
        => pieceId.Replace('-', '_');

    private static bool ResolveRelativeReverse(
        GarmentDocument garment,
        GarmentSeamDocument seam)
    {
        const string prefix = "stitch-";
        if (!seam.Id.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            return seam.SideA.Reverse != seam.SideB.Reverse;
        }
        int digitCount = seam.Id[prefix.Length..]
            .TakeWhile(char.IsDigit)
            .Count();
        if (digitCount == 0 ||
            !int.TryParse(seam.Id.AsSpan(prefix.Length, digitCount), out int stitchIndex) ||
            string.IsNullOrWhiteSpace(garment.Source?.RawDocumentJson))
        {
            return seam.SideA.Reverse != seam.SideB.Reverse;
        }

        try
        {
            using JsonDocument source = JsonDocument.Parse(garment.Source.RawDocumentJson);
            JsonElement stitches = source.RootElement
                .GetProperty("pattern")
                .GetProperty("stitches");
            if (stitchIndex < 0 || stitchIndex >= stitches.GetArrayLength())
            {
                return seam.SideA.Reverse != seam.SideB.Reverse;
            }
            JsonElement stitch = stitches[stitchIndex];
            return stitch.GetArrayLength() != 3 ||
                stitch[2].ValueKind != JsonValueKind.String ||
                !string.Equals(
                    stitch[2].GetString(),
                    "right_wrong",
                    StringComparison.Ordinal);
        }
        catch (JsonException)
        {
            return seam.SideA.Reverse != seam.SideB.Reverse;
        }
        catch (KeyNotFoundException)
        {
            return seam.SideA.Reverse != seam.SideB.Reverse;
        }
        catch (InvalidOperationException)
        {
            return seam.SideA.Reverse != seam.SideB.Reverse;
        }
    }

    private sealed record PatternConstructionGeometryMetadata(
        IReadOnlyList<string> BoundaryCurveIds,
        IReadOnlyList<PatternInternalPathDocument> InternalPaths,
        IReadOnlyList<PatternNotchDocument> Notches,
        IReadOnlyList<PatternDartDocument> Darts,
        PatternGrainlineDocument? Grainline);
}
