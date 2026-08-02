using System.Text.Json;
using System.Text.RegularExpressions;

namespace Patterna;

public sealed record GarmentCodeImportOptions(
    string GarmentId,
    string GarmentName,
    FabricPhysicsDocument Fabric,
    double SeamAllowanceCm = 1.0,
    string? SourcePath = null,
    string? SourceRevision = null);

public sealed class GarmentCodeImportException : InvalidOperationException
{
    public GarmentCodeImportException(string message)
        : base(message)
    {
    }
}

public static partial class GarmentCodePatternImporter
{
    private static readonly JsonSerializerOptions ConstructionJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true
    };

    public static GarmentDocument Import(string json, GarmentCodeImportOptions options)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(json);
        ArgumentNullException.ThrowIfNull(options);

        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement root = document.RootElement;
        JsonElement pattern = RequiredProperty(root, "pattern");
        JsonElement sourcePanels = RequiredProperty(pattern, "panels");
        JsonElement sourceStitches = RequiredProperty(pattern, "stitches");
        if (sourcePanels.ValueKind != JsonValueKind.Object)
        {
            throw new GarmentCodeImportException("GarmentCode pattern.panels must be an object.");
        }
        if (sourceStitches.ValueKind != JsonValueKind.Array)
        {
            throw new GarmentCodeImportException("GarmentCode pattern.stitches must be an array.");
        }

        double coordinateScale = ReadCoordinateScale(root);
        GarmentEaseProfileDocument? easeProfile = ReadEaseProfile(root);
        GarmentBodyReferenceDocument? bodyReference = ReadBodyReference(root);
        ShirtConstructionProfileDocument? shirtConstructionProfile =
            ReadShirtConstructionProfile(root);
        ShirtBustShapingProfileDocument? shirtBustShapingProfile =
            ReadShirtBustShapingProfile(root);
        Dictionary<string, PatternConstructionGeometryMetadata> constructionGeometry =
            ReadConstructionGeometry(root);
        List<PatternPieceDocument> pieces = [];
        List<ClothPanelDocument> panels = [];
        Dictionary<string, string[]> edgeIdsByPanel = new(StringComparer.Ordinal);
        int panelOrdinal = 0;

        foreach (JsonProperty panelProperty in sourcePanels.EnumerateObject())
        {
            string sourceName = panelProperty.Name;
            string id = Slug(sourceName);
            JsonElement sourcePanel = panelProperty.Value;
            PatternPointDocument[] vertices = ReadPoints(
                RequiredProperty(sourcePanel, "vertices"),
                coordinateScale,
                $"panel {sourceName} vertices");
            JsonElement edges = RequiredProperty(sourcePanel, "edges");
            if (edges.ValueKind != JsonValueKind.Array || edges.GetArrayLength() < 3)
            {
                throw new GarmentCodeImportException($"GarmentCode panel {sourceName} must contain at least three edges.");
            }

            PatternCurveDocument[] boundary = new PatternCurveDocument[edges.GetArrayLength()];
            string[] edgeIds = new string[boundary.Length];
            int? firstVertex = null;
            int? previousEnd = null;
            int edgeIndex = 0;
            foreach (JsonElement edge in edges.EnumerateArray())
            {
                (int startIndex, int endIndex) = ReadEndpoints(edge, sourceName, edgeIndex, vertices.Length);
                if (edgeIndex == 0)
                {
                    firstVertex = startIndex;
                }
                else if (startIndex != previousEnd)
                {
                    throw new GarmentCodeImportException(
                        $"GarmentCode panel {sourceName} edge {edgeIndex} does not continue the oriented boundary loop.");
                }

                string edgeId = constructionGeometry.TryGetValue(id, out PatternConstructionGeometryMetadata? panelConstruction) &&
                    panelConstruction.BoundaryCurveIds is { } boundaryCurveIds &&
                    boundaryCurveIds.Count == edges.GetArrayLength() &&
                    !string.IsNullOrWhiteSpace(boundaryCurveIds[edgeIndex])
                        ? boundaryCurveIds[edgeIndex]
                        : $"edge-{edgeIndex}";
                edgeIds[edgeIndex] = edgeId;
                boundary[edgeIndex] = ConvertCurve(
                    edge,
                    edgeId,
                    vertices[startIndex],
                    vertices[endIndex],
                    coordinateScale);
                previousEnd = endIndex;
                edgeIndex++;
            }

            if (firstVertex != previousEnd)
            {
                throw new GarmentCodeImportException($"GarmentCode panel {sourceName} has an open boundary loop.");
            }

            double offsetX = -vertices.Min(point => point.X);
            double offsetY = -vertices.Min(point => point.Y);
            PatternPointDocument Normalize(PatternPointDocument point)
                => new(point.X + offsetX, point.Y + offsetY);
            PatternCurveDocument[] normalizedBoundary = boundary
                .Select((curve, index) =>
                {
                    PatternPointDocument normalizedStart = Normalize(index == 0
                        ? vertices[firstVertex!.Value]
                        : boundary[index - 1].End);
                    PatternPointDocument normalizedEnd = Normalize(curve.End);
                    PatternPointDocument? normalizedControl1 = curve.Control1 is null ? null : Normalize(curve.Control1);
                    PatternPointDocument? normalizedControl2 = curve.Control2 is null ? null : Normalize(curve.Control2);
                    string? sourceCurvatureJson = edges[index].TryGetProperty("curvature", out JsonElement sourceCurvature)
                        ? sourceCurvature.GetRawText()
                        : null;
                    return curve with
                    {
                        End = normalizedEnd,
                        Control1 = normalizedControl1,
                        Control2 = normalizedControl2,
                        GarmentCodeSource = new GarmentCodeCurveSourceDocument(
                            sourceCurvatureJson,
                            normalizedStart,
                            normalizedEnd,
                            normalizedControl1,
                            normalizedControl2)
                    };
                })
                .ToArray();
            (double left, double top) = LayoutPosition(panelOrdinal++);
            PatternPieceDocument piece = new(
                id,
                Humanize(sourceName),
                1,
                false,
                false,
                1,
                1,
                options.SeamAllowanceCm,
                Normalize(vertices[firstVertex!.Value]),
                normalizedBoundary,
                new PatternLayoutDocument(left, top, 2, 2, true));
            PatternPlacement3DDocument sourcePlacement = ReadPlacement(sourcePanel, coordinateScale, sourceName);
            ClothPanelDocument panel = new(
                $"{id}-panel",
                id,
                Humanize(sourceName),
                ClassifyPlacement(sourceName, sourcePlacement),
                false,
                [])
            {
                SourcePlacement = sourcePlacement,
                SourcePatternOrigin = new PatternPointDocument(
                    vertices.Min(point => point.X),
                    vertices.Min(point => point.Y)),
                SourceLabel = sourcePanel.TryGetProperty("label", out JsonElement panelLabel) &&
                    panelLabel.ValueKind == JsonValueKind.String
                        ? panelLabel.GetString()
                        : null
            };
            pieces.Add(piece);
            panels.Add(panel);
            edgeIdsByPanel.Add(sourceName, edgeIds);
        }

        pieces = ApplyConstructionGeometry(pieces, constructionGeometry);

        Dictionary<string, ClothPanelDocument> panelsBySourceName = panels
            .Zip(sourcePanels.EnumerateObject(), (panel, source) => (source.Name, Panel: panel))
            .ToDictionary(item => item.Name, item => item.Panel, StringComparer.Ordinal);
        List<GarmentSeamDocument> seams = [];
        int stitchIndex = 0;
        foreach (JsonElement stitch in sourceStitches.EnumerateArray())
        {
            if (stitch.ValueKind != JsonValueKind.Array ||
                stitch.GetArrayLength() is < 2 or > 3)
            {
                throw new GarmentCodeImportException(
                    $"GarmentCode stitch {stitchIndex} must contain two sides and an optional right_wrong marker.");
            }
            bool reverseFirstSide = true;
            if (stitch.GetArrayLength() == 3)
            {
                if (stitch[2].ValueKind != JsonValueKind.String ||
                    !string.Equals(stitch[2].GetString(), "right_wrong", StringComparison.Ordinal))
                {
                    throw new GarmentCodeImportException(
                        $"GarmentCode stitch {stitchIndex} has an unsupported direction marker.");
                }
                reverseFirstSide = false;
            }
            JsonElement sideA = stitch[0];
            JsonElement sideB = stitch[1];
            (string panelA, int edgeA) = ReadStitchSide(sideA, stitchIndex, "A", panelsBySourceName, edgeIdsByPanel);
            (string panelB, int edgeB) = ReadStitchSide(sideB, stitchIndex, "B", panelsBySourceName, edgeIdsByPanel);
            seams.Add(new GarmentSeamDocument(
                $"stitch-{stitchIndex}",
                $"Stitch {stitchIndex + 1}",
                new SeamSideDocument(
                    panelsBySourceName[panelA].Id,
                    [edgeIdsByPanel[panelA][edgeA]],
                    reverseFirstSide),
                new SeamSideDocument(panelsBySourceName[panelB].Id, [edgeIdsByPanel[panelB][edgeB]]),
                options.SeamAllowanceCm));
            stitchIndex++;
        }

        GarmentDocument result = new(
            "patterna.garment/1.1",
            options.GarmentId,
            options.GarmentName,
            "centimeters",
            pieces,
            panels,
            seams,
            options.Fabric)
        {
            EaseProfile = easeProfile,
            BodyReference = bodyReference,
            ShirtConstructionProfile = shirtConstructionProfile,
            ShirtBustShapingProfile = shirtBustShapingProfile,
            Source = new GarmentSourceDocument(
                "GarmentCode JSON",
                "garmentcode.pattern/2",
                options.SourcePath,
                options.SourceRevision)
            {
                RawDocumentJson = json
            }
        };

        result = result with
        {
            Source = result.Source! with
            {
                StructuralSignature = GarmentCodePatternExporter.ComputeStructuralSignature(result)
            }
        };

        IReadOnlyList<string> errors = result.Validate();
        if (errors.Count > 0)
        {
            throw new GarmentCodeImportException(string.Join(Environment.NewLine, errors));
        }
        return result;
    }

    private static GarmentEaseProfileDocument? ReadEaseProfile(JsonElement root)
    {
        if (!root.TryGetProperty("patterna", out JsonElement patterna) ||
            patterna.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        JsonElement values;
        if (patterna.TryGetProperty("ease_profile", out JsonElement explicitProfile) &&
            explicitProfile.ValueKind == JsonValueKind.Object)
        {
            values = explicitProfile;
        }
        else if (patterna.TryGetProperty("design", out JsonElement design) &&
            design.ValueKind == JsonValueKind.Object)
        {
            values = design;
        }
        else
        {
            return null;
        }

        static bool TryRead(JsonElement source, string name, out double value)
        {
            value = 0;
            return source.TryGetProperty(name, out JsonElement property) &&
                property.ValueKind == JsonValueKind.Number &&
                property.TryGetDouble(out value) &&
                double.IsFinite(value);
        }

        if (!TryRead(values, "chest_ease_cm", out double chest) ||
            !TryRead(values, "waist_ease_cm", out double waist) ||
            !TryRead(values, "hip_ease_cm", out double hip))
        {
            return null;
        }

        double upperArm = TryRead(values, "upper_arm_ease_cm", out double explicitUpperArm)
            ? explicitUpperArm
            : 5.0;
        double armscye = TryRead(values, "armscye_ease_cm", out double explicitArmscye)
            ? explicitArmscye
            : 2.5;
        return new GarmentEaseProfileDocument(chest, waist, hip, upperArm)
        {
            ArmscyeEaseCm = armscye
        };
    }

    private static GarmentBodyReferenceDocument? ReadBodyReference(JsonElement root)
    {
        if (!root.TryGetProperty("patterna", out JsonElement patterna) ||
            patterna.ValueKind != JsonValueKind.Object ||
            !patterna.TryGetProperty("body_reference", out JsonElement values) ||
            values.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        static double RequiredPositive(JsonElement source, string name)
        {
            if (!source.TryGetProperty(name, out JsonElement property) ||
                property.ValueKind != JsonValueKind.Number ||
                !property.TryGetDouble(out double value) ||
                !double.IsFinite(value) ||
                value <= 0)
            {
                throw new GarmentCodeImportException(
                    $"Patternal source-body value {name} must be a finite positive number.");
            }
            return value;
        }

        return new GarmentBodyReferenceDocument(
            RequiredPositive(values, "chest_cm"),
            RequiredPositive(values, "waist_cm"),
            RequiredPositive(values, "hip_cm"),
            RequiredPositive(values, "shoulder_cm"),
            RequiredPositive(values, "torso_cm"),
            RequiredPositive(values, "arm_length_cm"),
            RequiredPositive(values, "upper_arm_circumference_cm"),
            RequiredPositive(values, "armhole_depth_cm"),
            RequiredPositive(values, "armscye_circumference_cm"));
    }

    private static ShirtConstructionProfileDocument? ReadShirtConstructionProfile(JsonElement root)
    {
        if (!root.TryGetProperty("patterna", out JsonElement patterna) ||
            patterna.ValueKind != JsonValueKind.Object ||
            !patterna.TryGetProperty("shirt_construction_profile", out JsonElement values) ||
            values.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        static double RequiredFinite(JsonElement source, string name)
        {
            if (!source.TryGetProperty(name, out JsonElement property) ||
                property.ValueKind != JsonValueKind.Number ||
                !property.TryGetDouble(out double value) ||
                !double.IsFinite(value))
            {
                throw new GarmentCodeImportException(
                    $"Patternal shirt construction value {name} must be a finite number.");
            }
            return value;
        }

        static double OptionalFinite(JsonElement source, string name, double fallback)
        {
            if (!source.TryGetProperty(name, out JsonElement property))
            {
                return fallback;
            }
            if (property.ValueKind != JsonValueKind.Number ||
                !property.TryGetDouble(out double value) ||
                !double.IsFinite(value))
            {
                throw new GarmentCodeImportException(
                    $"Patternal shirt construction value {name} must be a finite number.");
            }
            return value;
        }

        return new ShirtConstructionProfileDocument(
            RequiredFinite(values, "front_width_share_percent"),
            RequiredFinite(values, "neckline_width_cm"),
            RequiredFinite(values, "front_neck_depth_cm"),
            RequiredFinite(values, "back_neck_depth_cm"),
            RequiredFinite(values, "shoulder_length_cm"),
            RequiredFinite(values, "shoulder_drop_cm"),
            RequiredFinite(values, "armscye_depth_cm"),
            RequiredFinite(values, "sleeve_cap_height_cm"),
            RequiredFinite(values, "front_balance_cm"))
        {
            ArmscyeScoopCm = OptionalFinite(values, "armscye_scoop_cm", 0),
            UnderarmExtensionCm = OptionalFinite(values, "underarm_extension_cm", 0)
        };
    }

    private static ShirtBustShapingProfileDocument? ReadShirtBustShapingProfile(JsonElement root)
    {
        if (!root.TryGetProperty("patterna", out JsonElement patterna) ||
            patterna.ValueKind != JsonValueKind.Object ||
            !patterna.TryGetProperty("shirt_bust_shaping_profile", out JsonElement values) ||
            values.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        static double RequiredFinite(JsonElement source, string name)
        {
            if (!source.TryGetProperty(name, out JsonElement property) ||
                property.ValueKind != JsonValueKind.Number ||
                !property.TryGetDouble(out double value) ||
                !double.IsFinite(value))
            {
                throw new GarmentCodeImportException(
                    $"Patternal shirt bust-shaping value {name} must be a finite number.");
            }
            return value;
        }

        static double OptionalFinite(JsonElement source, string name, double fallback)
        {
            if (!source.TryGetProperty(name, out JsonElement property))
            {
                return fallback;
            }
            if (property.ValueKind != JsonValueKind.Number ||
                !property.TryGetDouble(out double value) ||
                !double.IsFinite(value))
            {
                throw new GarmentCodeImportException(
                    $"Patternal shirt bust-shaping value {name} must be a finite number.");
            }
            return value;
        }

        if (!values.TryGetProperty("mode", out JsonElement modeValue) ||
            modeValue.ValueKind != JsonValueKind.String ||
            string.IsNullOrWhiteSpace(modeValue.GetString()))
        {
            throw new GarmentCodeImportException("Patternal shirt bust-shaping mode must be a nonempty string.");
        }
        return new ShirtBustShapingProfileDocument(
            modeValue.GetString()!,
            RequiredFinite(values, "left_dart_intake_cm"),
            RequiredFinite(values, "right_dart_intake_cm"),
            RequiredFinite(values, "bust_point_separation_cm"),
            RequiredFinite(values, "left_bust_height_cm"),
            RequiredFinite(values, "right_bust_height_cm"),
            RequiredFinite(values, "left_bust_projection_cm"),
            RequiredFinite(values, "right_bust_projection_cm"),
            RequiredFinite(values, "dart_tip_offset_cm"),
            RequiredFinite(values, "dart_mouth_drop_cm"))
        {
            ShoulderDartMouthOffsetCm = OptionalFinite(
                values,
                "shoulder_dart_mouth_offset_cm",
                5),
            ShoulderDartSharePercent = OptionalFinite(
                values,
                "shoulder_dart_share_percent",
                35)
        };
    }

    private static Dictionary<string, PatternConstructionGeometryMetadata> ReadConstructionGeometry(
        JsonElement root)
    {
        if (!root.TryGetProperty("patterna", out JsonElement patterna) ||
            patterna.ValueKind != JsonValueKind.Object ||
            !patterna.TryGetProperty("construction_geometry", out JsonElement geometry) ||
            geometry.ValueKind != JsonValueKind.Object)
        {
            return new Dictionary<string, PatternConstructionGeometryMetadata>(StringComparer.OrdinalIgnoreCase);
        }

        Dictionary<string, PatternConstructionGeometryMetadata> metadataByPiece = new(StringComparer.OrdinalIgnoreCase);
        foreach (JsonProperty property in geometry.EnumerateObject())
        {
            PatternConstructionGeometryMetadata? metadata;
            try
            {
                metadata = property.Value.Deserialize<PatternConstructionGeometryMetadata>(ConstructionJsonOptions);
            }
            catch (JsonException exception)
            {
                throw new GarmentCodeImportException(
                    $"Patternal construction geometry for {property.Name} is invalid: {exception.Message}");
            }
            if (metadata is not null)
            {
                metadataByPiece[property.Name] = metadata;
            }
        }

        return metadataByPiece;
    }

    private static List<PatternPieceDocument> ApplyConstructionGeometry(
        IReadOnlyList<PatternPieceDocument> pieces,
        IReadOnlyDictionary<string, PatternConstructionGeometryMetadata> metadataByPiece)
        => pieces
            .Select(piece => metadataByPiece.TryGetValue(piece.Id, out PatternConstructionGeometryMetadata? metadata)
                ? piece with
                {
                    InternalPaths = metadata.InternalPaths ?? [],
                    Notches = metadata.Notches ?? [],
                    Darts = metadata.Darts ?? [],
                    Grainline = metadata.Grainline
                }
                : piece)
            .ToList();

    private static PatternCurveDocument ConvertCurve(
        JsonElement edge,
        string edgeId,
        PatternPointDocument start,
        PatternPointDocument end,
        double coordinateScale)
    {
        string? label = edge.TryGetProperty("label", out JsonElement labelElement) &&
            labelElement.ValueKind == JsonValueKind.String
                ? labelElement.GetString()
                : null;
        if (!edge.TryGetProperty("curvature", out JsonElement curvature))
        {
            return new PatternCurveDocument(edgeId, "line", end) { Label = label };
        }

        string type;
        JsonElement parameters;
        if (curvature.ValueKind == JsonValueKind.Array)
        {
            type = "quadratic";
            parameters = curvature;
        }
        else
        {
            type = RequiredString(curvature, "type");
            parameters = RequiredProperty(curvature, "params");
        }

        if (type.Equals("quadratic", StringComparison.OrdinalIgnoreCase))
        {
            JsonElement relative = parameters.ValueKind == JsonValueKind.Array &&
                parameters.GetArrayLength() == 2 &&
                parameters[0].ValueKind == JsonValueKind.Number
                    ? parameters
                    : parameters[0];
            PatternPointDocument control = RelativeControl(start, end, relative);
            PatternPointDocument control1 = Lerp(start, control, 2.0 / 3.0);
            PatternPointDocument control2 = Lerp(end, control, 2.0 / 3.0);
            return new PatternCurveDocument(edgeId, "cubic", end, control1, control2) { Label = label };
        }
        if (type.Equals("cubic", StringComparison.OrdinalIgnoreCase))
        {
            if (parameters.ValueKind != JsonValueKind.Array || parameters.GetArrayLength() != 2)
            {
                throw new GarmentCodeImportException($"GarmentCode cubic edge {edgeId} must contain two controls.");
            }
            return new PatternCurveDocument(
                edgeId,
                "cubic",
                end,
                RelativeControl(start, end, parameters[0]),
                RelativeControl(start, end, parameters[1]))
            {
                Label = label
            };
        }
        if (type.Equals("circle", StringComparison.OrdinalIgnoreCase))
        {
            if (parameters.ValueKind != JsonValueKind.Array || parameters.GetArrayLength() != 3)
            {
                throw new GarmentCodeImportException($"GarmentCode circle edge {edgeId} has invalid arc parameters.");
            }
            double radius = parameters[0].GetDouble() * coordinateScale;
            bool largeArc = parameters[1].ValueKind == JsonValueKind.True ||
                (parameters[1].ValueKind == JsonValueKind.Number && parameters[1].GetDouble() != 0);
            bool sweepPositive = parameters[2].ValueKind == JsonValueKind.True ||
                (parameters[2].ValueKind == JsonValueKind.Number && parameters[2].GetDouble() != 0);
            if (largeArc)
            {
                throw new GarmentCodeImportException(
                    $"GarmentCode circle edge {edgeId} is a large arc and requires segmented cubic conversion.");
            }
            (PatternPointDocument control1, PatternPointDocument control2) =
                CircularArcControls(start, end, radius, sweepPositive, edgeId);
            return new PatternCurveDocument(edgeId, "cubic", end, control1, control2) { Label = label };
        }
        throw new GarmentCodeImportException(
            $"GarmentCode edge {edgeId} uses unsupported curvature type {type}.");
    }

    private sealed record PatternConstructionGeometryMetadata(
        IReadOnlyList<string>? BoundaryCurveIds,
        IReadOnlyList<PatternInternalPathDocument>? InternalPaths,
        IReadOnlyList<PatternNotchDocument>? Notches,
        IReadOnlyList<PatternDartDocument>? Darts,
        PatternGrainlineDocument? Grainline);

    private static (PatternPointDocument Control1, PatternPointDocument Control2) CircularArcControls(
        PatternPointDocument start,
        PatternPointDocument end,
        double radius,
        bool sweepPositive,
        string edgeId)
    {
        double dx = end.X - start.X;
        double dy = end.Y - start.Y;
        double chord = Math.Sqrt(dx * dx + dy * dy);
        if (!double.IsFinite(radius) || radius <= 0 || chord <= double.Epsilon || chord > 2 * radius + 0.0001)
        {
            throw new GarmentCodeImportException($"GarmentCode circle edge {edgeId} has an impossible radius.");
        }
        double halfChord = chord * 0.5;
        double centerOffset = Math.Sqrt(Math.Max(0, radius * radius - halfChord * halfChord));
        double midX = (start.X + end.X) * 0.5;
        double midY = (start.Y + end.Y) * 0.5;
        double perpendicularX = -dy / chord;
        double perpendicularY = dx / chord;
        PatternPointDocument firstCenter = new(
            midX + perpendicularX * centerOffset,
            midY + perpendicularY * centerOffset);
        PatternPointDocument secondCenter = new(
            midX - perpendicularX * centerOffset,
            midY - perpendicularY * centerOffset);
        (PatternPointDocument center, double delta) = SelectArcCenter(
            start,
            end,
            firstCenter,
            secondCenter,
            sweepPositive);
        double startAngle = Math.Atan2(start.Y - center.Y, start.X - center.X);
        double endAngle = startAngle + delta;
        double controlScale = 4.0 / 3.0 * Math.Tan(delta / 4.0) * radius;
        PatternPointDocument control1 = new(
            start.X + controlScale * -Math.Sin(startAngle),
            start.Y + controlScale * Math.Cos(startAngle));
        PatternPointDocument control2 = new(
            end.X - controlScale * -Math.Sin(endAngle),
            end.Y - controlScale * Math.Cos(endAngle));
        return (control1, control2);
    }

    private static (PatternPointDocument Center, double Delta) SelectArcCenter(
        PatternPointDocument start,
        PatternPointDocument end,
        PatternPointDocument firstCenter,
        PatternPointDocument secondCenter,
        bool sweepPositive)
    {
        double firstDelta = MinorArcDelta(start, end, firstCenter);
        if ((sweepPositive && firstDelta > 0) || (!sweepPositive && firstDelta < 0))
        {
            return (firstCenter, firstDelta);
        }
        return (secondCenter, MinorArcDelta(start, end, secondCenter));
    }

    private static double MinorArcDelta(
        PatternPointDocument start,
        PatternPointDocument end,
        PatternPointDocument center)
    {
        double startAngle = Math.Atan2(start.Y - center.Y, start.X - center.X);
        double endAngle = Math.Atan2(end.Y - center.Y, end.X - center.X);
        double delta = endAngle - startAngle;
        while (delta <= -Math.PI)
        {
            delta += Math.PI * 2;
        }
        while (delta > Math.PI)
        {
            delta -= Math.PI * 2;
        }
        return delta;
    }

    private static PatternPointDocument RelativeControl(
        PatternPointDocument start,
        PatternPointDocument end,
        JsonElement relative)
    {
        if (relative.ValueKind != JsonValueKind.Array || relative.GetArrayLength() != 2)
        {
            throw new GarmentCodeImportException("GarmentCode relative control points must contain two coordinates.");
        }
        double along = relative[0].GetDouble();
        double perpendicular = relative[1].GetDouble();
        double dx = end.X - start.X;
        double dy = end.Y - start.Y;
        return new PatternPointDocument(
            start.X + along * dx - perpendicular * dy,
            start.Y + along * dy + perpendicular * dx);
    }

    private static PatternPointDocument Lerp(
        PatternPointDocument first,
        PatternPointDocument second,
        double amount)
        => new(
            first.X + (second.X - first.X) * amount,
            first.Y + (second.Y - first.Y) * amount);

    private static (int Start, int End) ReadEndpoints(
        JsonElement edge,
        string panelName,
        int edgeIndex,
        int vertexCount)
    {
        JsonElement endpoints = RequiredProperty(edge, "endpoints");
        if (endpoints.ValueKind != JsonValueKind.Array || endpoints.GetArrayLength() != 2)
        {
            throw new GarmentCodeImportException($"GarmentCode panel {panelName} edge {edgeIndex} has invalid endpoints.");
        }
        int start = endpoints[0].GetInt32();
        int end = endpoints[1].GetInt32();
        if (start < 0 || start >= vertexCount || end < 0 || end >= vertexCount || start == end)
        {
            throw new GarmentCodeImportException($"GarmentCode panel {panelName} edge {edgeIndex} references invalid vertices.");
        }
        return (start, end);
    }

    private static (string Panel, int Edge) ReadStitchSide(
        JsonElement side,
        int stitchIndex,
        string sideName,
        IReadOnlyDictionary<string, ClothPanelDocument> panels,
        IReadOnlyDictionary<string, string[]> edgeIds)
    {
        string panel = RequiredString(side, "panel");
        if (!panels.ContainsKey(panel))
        {
            throw new GarmentCodeImportException($"GarmentCode stitch {stitchIndex} side {sideName} references missing panel {panel}.");
        }
        int edge = RequiredProperty(side, "edge").GetInt32();
        if (edge < 0 || edge >= edgeIds[panel].Length)
        {
            throw new GarmentCodeImportException($"GarmentCode stitch {stitchIndex} side {sideName} references missing edge {edge}.");
        }
        return (panel, edge);
    }

    private static PatternPointDocument[] ReadPoints(JsonElement array, double scale, string context)
    {
        if (array.ValueKind != JsonValueKind.Array)
        {
            throw new GarmentCodeImportException($"GarmentCode {context} must be an array.");
        }
        return array.EnumerateArray()
            .Select(point =>
            {
                if (point.ValueKind != JsonValueKind.Array || point.GetArrayLength() != 2)
                {
                    throw new GarmentCodeImportException($"GarmentCode {context} contains an invalid point.");
                }
                return new PatternPointDocument(point[0].GetDouble() * scale, point[1].GetDouble() * scale);
            })
            .ToArray();
    }

    private static PatternPlacement3DDocument ReadPlacement(
        JsonElement panel,
        double coordinateScale,
        string panelName)
    {
        JsonElement translation = RequiredProperty(panel, "translation");
        JsonElement rotation = RequiredProperty(panel, "rotation");
        if (translation.ValueKind != JsonValueKind.Array || translation.GetArrayLength() != 3 ||
            rotation.ValueKind != JsonValueKind.Array || rotation.GetArrayLength() != 3)
        {
            throw new GarmentCodeImportException($"GarmentCode panel {panelName} has an invalid 3D placement.");
        }
        return new PatternPlacement3DDocument(
            translation[0].GetDouble() * coordinateScale,
            translation[1].GetDouble() * coordinateScale,
            translation[2].GetDouble() * coordinateScale,
            rotation[0].GetDouble(),
            rotation[1].GetDouble(),
            rotation[2].GetDouble(),
            "GarmentCode intrinsic XYZ, centimeters");
    }

    private static string ClassifyPlacement(string sourceName, PatternPlacement3DDocument placement)
    {
        string name = sourceName.ToLowerInvariant();
        bool left = name.Contains("left", StringComparison.Ordinal) || name.StartsWith("l_", StringComparison.Ordinal);
        bool right = name.Contains("right", StringComparison.Ordinal) || name.StartsWith("r_", StringComparison.Ordinal);
        if (name.Contains("sleeve", StringComparison.Ordinal) ||
            name.Contains("cuff", StringComparison.Ordinal))
        {
            return left || (!right && placement.X < 0) ? "sleeveLeft" : "sleeveRight";
        }
        if (name.Contains("skirt", StringComparison.Ordinal))
        {
            return name.Contains("back", StringComparison.Ordinal) || placement.Z < 0 ? "skirtBack" : "skirtFront";
        }
        if (name.Contains("back", StringComparison.Ordinal) || name.Contains("btorso", StringComparison.Ordinal) || placement.Z < 0)
        {
            return "torsoBack";
        }
        return "torsoFront";
    }

    private static double ReadCoordinateScale(JsonElement root)
    {
        if (!root.TryGetProperty("properties", out JsonElement properties) ||
            !properties.TryGetProperty("units_in_meter", out JsonElement unitsElement))
        {
            throw new GarmentCodeImportException("GarmentCode properties.units_in_meter is required.");
        }
        double unitsInMeter = unitsElement.GetDouble();
        if (!double.IsFinite(unitsInMeter) || unitsInMeter <= 0)
        {
            throw new GarmentCodeImportException("GarmentCode units_in_meter must be finite and positive.");
        }
        return 100.0 / unitsInMeter;
    }

    private static JsonElement RequiredProperty(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out JsonElement value))
        {
            throw new GarmentCodeImportException($"GarmentCode property {name} is required.");
        }
        return value;
    }

    private static string RequiredString(JsonElement element, string name)
    {
        JsonElement value = RequiredProperty(element, name);
        if (value.ValueKind != JsonValueKind.String || string.IsNullOrWhiteSpace(value.GetString()))
        {
            throw new GarmentCodeImportException($"GarmentCode property {name} must be a nonempty string.");
        }
        return value.GetString()!;
    }

    private static (double Left, double Top) LayoutPosition(int ordinal)
        => ((ordinal % 4) * 215.0 + 20.0, (ordinal / 4) * 340.0 + 45.0);

    private static string Slug(string value)
    {
        string slug = NonSlugCharacter().Replace(value.Trim().ToLowerInvariant(), "-").Trim('-');
        return string.IsNullOrWhiteSpace(slug) ? "panel" : slug;
    }

    private static string Humanize(string value)
        => string.Join(' ', value.Split(['_', '-'], StringSplitOptions.RemoveEmptyEntries)
            .Select(word => word.ToLowerInvariant() switch
            {
                "ftorso" => "Front torso",
                "btorso" => "Back torso",
                "f" => "Front",
                "b" => "Back",
                _ => char.ToUpperInvariant(word[0]) + word[1..]
            }));

    [GeneratedRegex("[^a-z0-9]+", RegexOptions.CultureInvariant)]
    private static partial Regex NonSlugCharacter();
}
