using System.Text.Json.Serialization;

namespace Patterna;

[JsonPolymorphic(TypeDiscriminatorPropertyName = "$edit")]
[JsonDerivedType(typeof(PatternBoundarySplitCommand), "split-boundary")]
[JsonDerivedType(typeof(PatternNotchCommand), "add-notch")]
[JsonDerivedType(typeof(PatternPieceCreateCommand), "create-piece")]
[JsonDerivedType(typeof(PatternSeamCreateCommand), "create-seam")]
[JsonDerivedType(typeof(PatternInternalPathCreateCommand), "create-internal-path")]
[JsonDerivedType(typeof(PatternDartCreateCommand), "create-dart")]
[JsonDerivedType(typeof(PatternPiecePropertiesCommand), "update-piece-properties")]
[JsonDerivedType(typeof(PatternInternalPathUpdateCommand), "update-internal-path")]
[JsonDerivedType(typeof(PatternInternalPathDeleteCommand), "delete-internal-path")]
[JsonDerivedType(typeof(PatternDartUpdateCommand), "update-dart")]
[JsonDerivedType(typeof(PatternDartDeleteCommand), "delete-dart")]
[JsonDerivedType(typeof(PatternBoundaryCurveKindCommand), "set-boundary-curve-kind")]
public abstract record PatternStructuralEditCommand;

public sealed record PatternBoundarySplitCommand(
    string PieceId,
    string CurveId,
    double Parameter) : PatternStructuralEditCommand;

public sealed record PatternNotchCommand(
    string PieceId,
    string CurveId,
    double Parameter,
    double DepthCm = 0.4,
    double WidthCm = 0,
    int Count = 1) : PatternStructuralEditCommand;

public sealed record PatternPieceCreateCommand(
    PatternPieceDocument Piece,
    ClothPanelDocument Panel) : PatternStructuralEditCommand;

public sealed record PatternSeamCreateCommand(
    GarmentSeamDocument Seam) : PatternStructuralEditCommand;

public sealed record PatternInternalPathCreateCommand(
    string PieceId,
    PatternInternalPathDocument Path) : PatternStructuralEditCommand;

public sealed record PatternDartCreateCommand(
    string PieceId,
    PatternDartDocument Dart) : PatternStructuralEditCommand;

public sealed record PatternPiecePropertiesCommand(
    string PieceId,
    string Name,
    int CutQuantity,
    bool Mirrored,
    bool CutOnFold,
    double SeamAllowanceCm,
    PatternGrainlineDocument? Grainline) : PatternStructuralEditCommand;

public sealed record PatternInternalPathUpdateCommand(
    string PieceId,
    string PathId,
    PatternInternalPathDocument Path) : PatternStructuralEditCommand;

public sealed record PatternInternalPathDeleteCommand(
    string PieceId,
    string PathId) : PatternStructuralEditCommand;

public sealed record PatternDartUpdateCommand(
    string PieceId,
    string DartId,
    PatternDartDocument Dart) : PatternStructuralEditCommand;

public sealed record PatternDartDeleteCommand(
    string PieceId,
    string DartId) : PatternStructuralEditCommand;

public sealed record PatternBoundaryCurveKindCommand(
    string PieceId,
    string CurveId,
    string Kind) : PatternStructuralEditCommand;

public sealed record PatternBoundarySplitMapping(
    string PieceId,
    string OriginalCurveId,
    string FirstCurveId,
    string SecondCurveId);

public sealed record PatternBoundarySplitResult(
    GarmentDocument Document,
    string FirstCurveId,
    string SecondCurveId,
    IReadOnlyList<PatternBoundarySplitMapping> Mappings);

public static class PatternStructuralEditor
{
    private const double ParameterEpsilon = 0.000001;
    private const int LengthSamples = 96;

    public static PatternBoundarySplitResult Apply(
        GarmentDocument document,
        IEnumerable<PatternBoundarySplitCommand> commands)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(commands);

        PatternBoundarySplitResult? lastResult = null;
        GarmentDocument current = document;
        foreach (PatternBoundarySplitCommand command in commands)
        {
            lastResult = SplitBoundarySegment(
                current,
                command.PieceId,
                command.CurveId,
                command.Parameter);
            current = lastResult.Document;
        }

        return lastResult ?? new PatternBoundarySplitResult(current, string.Empty, string.Empty, []);
    }

    public static GarmentDocument ApplyEdits(
        GarmentDocument document,
        IEnumerable<PatternStructuralEditCommand> commands)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(commands);

        GarmentDocument current = document;
        foreach (PatternStructuralEditCommand command in commands)
        {
            current = command switch
            {
                PatternBoundarySplitCommand split => SplitBoundarySegment(
                    current,
                    split.PieceId,
                    split.CurveId,
                    split.Parameter).Document,
                PatternNotchCommand notch => AddNotch(current, notch),
                PatternPieceCreateCommand createPiece => CreatePiece(current, createPiece),
                PatternSeamCreateCommand createSeam => CreateSeam(current, createSeam),
                PatternInternalPathCreateCommand createPath => CreateInternalPath(current, createPath),
                PatternDartCreateCommand createDart => CreateDart(current, createDart),
                PatternPiecePropertiesCommand properties => UpdatePieceProperties(current, properties),
                PatternInternalPathUpdateCommand updatePath => UpdateInternalPath(current, updatePath),
                PatternInternalPathDeleteCommand deletePath => DeleteInternalPath(current, deletePath),
                PatternDartUpdateCommand updateDart => UpdateDart(current, updateDart),
                PatternDartDeleteCommand deleteDart => DeleteDart(current, deleteDart),
                PatternBoundaryCurveKindCommand curveKind => SetBoundaryCurveKind(current, curveKind),
                _ => throw new InvalidOperationException($"Unsupported structural edit {command.GetType().Name}.")
            };
        }
        return current;
    }

    public static GarmentDocument AddNotch(GarmentDocument document, PatternNotchCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ValidateParameter(command.Parameter);
        if (!double.IsFinite(command.DepthCm) || command.DepthCm <= 0 ||
            !double.IsFinite(command.WidthCm) || command.WidthCm < 0 ||
            command.Count is < 1 or > 3)
        {
            throw new ArgumentOutOfRangeException(nameof(command), "Notch dimensions or count are invalid.");
        }

        PatternPieceDocument piece = document.Pieces.FirstOrDefault(item =>
            string.Equals(item.Id, command.PieceId, StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidOperationException($"Pattern piece {command.PieceId} does not exist.");
        if (FindCurveIndex(piece, command.CurveId) < 0)
        {
            throw new InvalidOperationException($"Pattern curve {command.PieceId}/{command.CurveId} does not exist.");
        }
        HashSet<string> notchIds = piece.Notches
            .Select(notch => notch.Id)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        string notchId = UniqueId(notchIds, $"{command.CurveId}-notch");
        PatternNotchDocument notch = new(
            notchId,
            command.CurveId,
            command.Parameter,
            command.DepthCm,
            command.WidthCm,
            command.Count);
        PatternPieceDocument editedPiece = piece with { Notches = [.. piece.Notches, notch] };
        GarmentDocument edited = document with
        {
            Pieces = document.Pieces
                .Select(item => string.Equals(item.Id, piece.Id, StringComparison.OrdinalIgnoreCase) ? editedPiece : item)
                .ToArray()
        };
        IReadOnlyList<string> errors = edited.Validate();
        if (errors.Count > 0)
        {
            throw new InvalidOperationException(string.Join(Environment.NewLine, errors));
        }
        return edited;
    }

    public static GarmentDocument CreatePiece(
        GarmentDocument document,
        PatternPieceCreateCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ArgumentNullException.ThrowIfNull(command.Piece);
        ArgumentNullException.ThrowIfNull(command.Panel);
        if (!string.Equals(command.Panel.PieceId, command.Piece.Id, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("A created cloth panel must reference the created pattern piece.");
        }
        if (document.Pieces.Any(piece => string.Equals(piece.Id, command.Piece.Id, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException($"Pattern piece {command.Piece.Id} already exists.");
        }
        if (document.Panels.Any(panel => string.Equals(panel.Id, command.Panel.Id, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException($"Cloth panel {command.Panel.Id} already exists.");
        }
        GarmentDocument edited = document with
        {
            Pieces = [.. document.Pieces, command.Piece],
            Panels = [.. document.Panels, command.Panel]
        };
        EnsureValid(edited);
        return edited;
    }

    public static GarmentDocument CreateSeam(
        GarmentDocument document,
        PatternSeamCreateCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ArgumentNullException.ThrowIfNull(command.Seam);
        if (document.Seams.Any(seam => string.Equals(seam.Id, command.Seam.Id, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException($"Garment seam {command.Seam.Id} already exists.");
        }
        GarmentDocument edited = document with { Seams = [.. document.Seams, command.Seam] };
        EnsureValid(edited);
        return edited;
    }

    public static GarmentDocument CreateInternalPath(
        GarmentDocument document,
        PatternInternalPathCreateCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.PieceId);
        ArgumentNullException.ThrowIfNull(command.Path);
        PatternPieceDocument piece = FindPiece(document, command.PieceId);
        if (piece.InternalPaths.Any(path => string.Equals(path.Id, command.Path.Id, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException($"Pattern internal path {command.PieceId}/{command.Path.Id} already exists.");
        }
        PatternPieceDocument editedPiece = piece with
        {
            InternalPaths = [.. piece.InternalPaths, command.Path]
        };
        return ReplacePieceAndValidate(document, editedPiece);
    }

    public static GarmentDocument CreateDart(
        GarmentDocument document,
        PatternDartCreateCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.PieceId);
        ArgumentNullException.ThrowIfNull(command.Dart);
        PatternPieceDocument piece = FindPiece(document, command.PieceId);
        if (piece.Darts.Any(dart => string.Equals(dart.Id, command.Dart.Id, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException($"Pattern dart {command.PieceId}/{command.Dart.Id} already exists.");
        }
        PatternPieceDocument editedPiece = piece with
        {
            Darts = [.. piece.Darts, command.Dart]
        };
        return ReplacePieceAndValidate(document, editedPiece);
    }

    public static GarmentDocument UpdatePieceProperties(
        GarmentDocument document,
        PatternPiecePropertiesCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.PieceId);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.Name);
        if (command.CutQuantity is < 1 or > 20)
        {
            throw new ArgumentOutOfRangeException(nameof(command), "Cut quantity must be from one through twenty.");
        }
        if (!double.IsFinite(command.SeamAllowanceCm) || command.SeamAllowanceCm is < 0 or > 10)
        {
            throw new ArgumentOutOfRangeException(nameof(command), "Seam allowance must be from zero through ten centimeters.");
        }
        if (command.CutOnFold && command.Mirrored)
        {
            throw new InvalidOperationException("A cut-on-fold piece cannot also request mirrored cutting.");
        }
        PatternPieceDocument piece = FindPiece(document, command.PieceId);
        PatternPieceDocument editedPiece = piece with
        {
            Name = command.Name.Trim(),
            CutQuantity = command.CutQuantity,
            Mirrored = command.Mirrored,
            CutOnFold = command.CutOnFold,
            SeamAllowanceCm = command.SeamAllowanceCm,
            Grainline = command.Grainline
        };
        return ReplacePieceAndValidate(document, editedPiece);
    }

    public static GarmentDocument UpdateInternalPath(
        GarmentDocument document,
        PatternInternalPathUpdateCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.PieceId);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.PathId);
        ArgumentNullException.ThrowIfNull(command.Path);
        PatternPieceDocument piece = FindPiece(document, command.PieceId);
        int index = FindInternalPathIndex(piece, command.PathId);
        if (!string.Equals(command.PathId, command.Path.Id, StringComparison.OrdinalIgnoreCase) &&
            piece.InternalPaths.Any(path => string.Equals(path.Id, command.Path.Id, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException($"Pattern internal path {command.PieceId}/{command.Path.Id} already exists.");
        }
        PatternInternalPathDocument[] paths = piece.InternalPaths.ToArray();
        paths[index] = command.Path;
        return ReplacePieceAndValidate(document, piece with { InternalPaths = paths });
    }

    public static GarmentDocument DeleteInternalPath(
        GarmentDocument document,
        PatternInternalPathDeleteCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.PieceId);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.PathId);
        PatternPieceDocument piece = FindPiece(document, command.PieceId);
        int index = FindInternalPathIndex(piece, command.PathId);
        return ReplacePieceAndValidate(document, piece with
        {
            InternalPaths = piece.InternalPaths.Where((_, itemIndex) => itemIndex != index).ToArray()
        });
    }

    public static GarmentDocument UpdateDart(
        GarmentDocument document,
        PatternDartUpdateCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.PieceId);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.DartId);
        ArgumentNullException.ThrowIfNull(command.Dart);
        PatternPieceDocument piece = FindPiece(document, command.PieceId);
        int index = FindDartIndex(piece, command.DartId);
        if (!string.Equals(command.DartId, command.Dart.Id, StringComparison.OrdinalIgnoreCase) &&
            piece.Darts.Any(dart => string.Equals(dart.Id, command.Dart.Id, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException($"Pattern dart {command.PieceId}/{command.Dart.Id} already exists.");
        }
        PatternDartDocument[] darts = piece.Darts.ToArray();
        darts[index] = command.Dart;
        return ReplacePieceAndValidate(document, piece with { Darts = darts });
    }

    public static GarmentDocument DeleteDart(
        GarmentDocument document,
        PatternDartDeleteCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.PieceId);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.DartId);
        PatternPieceDocument piece = FindPiece(document, command.PieceId);
        int index = FindDartIndex(piece, command.DartId);
        return ReplacePieceAndValidate(document, piece with
        {
            Darts = piece.Darts.Where((_, itemIndex) => itemIndex != index).ToArray()
        });
    }

    public static GarmentDocument SetBoundaryCurveKind(
        GarmentDocument document,
        PatternBoundaryCurveKindCommand command)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(command);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.PieceId);
        ArgumentException.ThrowIfNullOrWhiteSpace(command.CurveId);
        if (command.Kind is not "line" and not "cubic")
        {
            throw new ArgumentOutOfRangeException(nameof(command), "Boundary curve kind must be line or cubic.");
        }
        PatternPieceDocument piece = FindPiece(document, command.PieceId);
        int curveIndex = FindCurveIndex(piece, command.CurveId);
        if (curveIndex < 0)
        {
            throw new InvalidOperationException($"Pattern curve {piece.Id}/{command.CurveId} does not exist.");
        }
        PatternCurveDocument currentCurve = piece.Boundary[curveIndex];
        if (string.Equals(currentCurve.Kind, command.Kind, StringComparison.OrdinalIgnoreCase))
        {
            return document;
        }
        PatternPointDocument start = curveIndex == 0 ? piece.Start : piece.Boundary[curveIndex - 1].End;
        PatternCurveDocument editedCurve = command.Kind == "cubic"
            ? currentCurve with
            {
                Kind = "cubic",
                Control1 = Interpolate(start, currentCurve.End, 1.0 / 3.0),
                Control2 = Interpolate(start, currentCurve.End, 2.0 / 3.0),
                GarmentCodeSource = null
            }
            : currentCurve with
            {
                Kind = "line",
                Control1 = null,
                Control2 = null,
                GarmentCodeSource = null
            };
        PatternCurveDocument[] boundary = piece.Boundary.ToArray();
        boundary[curveIndex] = editedCurve;
        return ReplacePieceAndValidate(document, piece with { Boundary = boundary });
    }

    private static PatternPointDocument Interpolate(
        PatternPointDocument start,
        PatternPointDocument end,
        double parameter)
        => new(
            start.X + (end.X - start.X) * parameter,
            start.Y + (end.Y - start.Y) * parameter);

    private static int FindInternalPathIndex(PatternPieceDocument piece, string pathId)
    {
        int index = piece.InternalPaths
            .Select((path, itemIndex) => new { path.Id, Index = itemIndex })
            .Where(item => string.Equals(item.Id, pathId, StringComparison.OrdinalIgnoreCase))
            .Select(item => item.Index)
            .DefaultIfEmpty(-1)
            .First();
        return index >= 0
            ? index
            : throw new InvalidOperationException($"Pattern internal path {piece.Id}/{pathId} does not exist.");
    }

    private static int FindDartIndex(PatternPieceDocument piece, string dartId)
    {
        int index = piece.Darts
            .Select((dart, itemIndex) => new { dart.Id, Index = itemIndex })
            .Where(item => string.Equals(item.Id, dartId, StringComparison.OrdinalIgnoreCase))
            .Select(item => item.Index)
            .DefaultIfEmpty(-1)
            .First();
        return index >= 0
            ? index
            : throw new InvalidOperationException($"Pattern dart {piece.Id}/{dartId} does not exist.");
    }

    private static PatternPieceDocument FindPiece(GarmentDocument document, string pieceId)
        => document.Pieces.FirstOrDefault(piece =>
            string.Equals(piece.Id, pieceId, StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidOperationException($"Pattern piece {pieceId} does not exist.");

    private static GarmentDocument ReplacePieceAndValidate(
        GarmentDocument document,
        PatternPieceDocument editedPiece)
    {
        GarmentDocument edited = document with
        {
            Pieces = document.Pieces
                .Select(piece => string.Equals(piece.Id, editedPiece.Id, StringComparison.OrdinalIgnoreCase)
                    ? editedPiece
                    : piece)
                .ToArray()
        };
        EnsureValid(edited);
        return edited;
    }

    public static PatternBoundarySplitResult SplitBoundarySegment(
        GarmentDocument document,
        string pieceId,
        string curveId,
        double parameter)
    {
        ArgumentNullException.ThrowIfNull(document);
        ArgumentException.ThrowIfNullOrWhiteSpace(pieceId);
        ArgumentException.ThrowIfNullOrWhiteSpace(curveId);
        ValidateParameter(parameter);

        Dictionary<string, PatternPieceDocument> piecesById = document.Pieces
            .ToDictionary(piece => piece.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, ClothPanelDocument> panelsById = document.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        if (!piecesById.TryGetValue(pieceId, out PatternPieceDocument? primaryPiece))
        {
            throw new InvalidOperationException($"Pattern piece {pieceId} does not exist.");
        }

        int primaryIndex = FindCurveIndex(primaryPiece, curveId);
        if (primaryIndex < 0)
        {
            throw new InvalidOperationException($"Pattern curve {pieceId}/{curveId} does not exist.");
        }

        List<SplitTarget> targets = [new(pieceId, curveId, parameter, true)];
        foreach (GarmentSeamDocument seam in document.Seams)
        {
            AddSynchronizedTarget(
                document,
                piecesById,
                panelsById,
                seam.SideA,
                seam.SideB,
                pieceId,
                curveId,
                parameter,
                targets);
            AddSynchronizedTarget(
                document,
                piecesById,
                panelsById,
                seam.SideB,
                seam.SideA,
                pieceId,
                curveId,
                parameter,
                targets);
        }

        GarmentDocument current = document;
        List<PatternBoundarySplitMapping> mappings = [];
        foreach (SplitTarget target in targets
            .GroupBy(target => $"{target.PieceId}\u001f{target.CurveId}", StringComparer.OrdinalIgnoreCase)
            .Select(group => group.First()))
        {
            (current, PatternBoundarySplitMapping mapping) = SplitSingleBoundarySegment(
                current,
                target.PieceId,
                target.CurveId,
                target.Parameter);
            mappings.Add(mapping);
        }

        PatternBoundarySplitMapping primaryMapping = mappings.First(mapping =>
            string.Equals(mapping.PieceId, pieceId, StringComparison.OrdinalIgnoreCase) &&
            string.Equals(mapping.OriginalCurveId, curveId, StringComparison.OrdinalIgnoreCase));
        return new PatternBoundarySplitResult(
            current,
            primaryMapping.FirstCurveId,
            primaryMapping.SecondCurveId,
            mappings);
    }

    private static void AddSynchronizedTarget(
        GarmentDocument document,
        IReadOnlyDictionary<string, PatternPieceDocument> piecesById,
        IReadOnlyDictionary<string, ClothPanelDocument> panelsById,
        SeamSideDocument selectedSide,
        SeamSideDocument oppositeSide,
        string selectedPieceId,
        string selectedCurveId,
        double selectedParameter,
        ICollection<SplitTarget> targets)
    {
        if (!panelsById.TryGetValue(selectedSide.PanelId, out ClothPanelDocument? selectedPanel) ||
            !string.Equals(selectedPanel.PieceId, selectedPieceId, StringComparison.OrdinalIgnoreCase) ||
            !selectedSide.EdgeIds.Contains(selectedCurveId, StringComparer.OrdinalIgnoreCase))
        {
            return;
        }
        if (!panelsById.TryGetValue(oppositeSide.PanelId, out ClothPanelDocument? oppositePanel) ||
            !piecesById.TryGetValue(oppositePanel.PieceId, out PatternPieceDocument? oppositePiece))
        {
            return;
        }

        PatternPieceDocument selectedPiece = piecesById[selectedPieceId];
        double seamPosition = NormalizedPositionOnSide(
            selectedPiece,
            selectedSide,
            selectedCurveId,
            selectedParameter);
        double oppositeGeometricPosition = oppositeSide.Reverse ? 1 - seamPosition : seamPosition;
        (string oppositeCurveId, double oppositeParameter) = LocatePositionOnSide(
            oppositePiece,
            oppositeSide.EdgeIds,
            oppositeGeometricPosition);

        if (string.Equals(oppositePiece.Id, selectedPieceId, StringComparison.OrdinalIgnoreCase) &&
            string.Equals(oppositeCurveId, selectedCurveId, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }
        targets.Add(new SplitTarget(oppositePiece.Id, oppositeCurveId, oppositeParameter, false));
    }

    private static double NormalizedPositionOnSide(
        PatternPieceDocument piece,
        SeamSideDocument side,
        string curveId,
        double parameter)
    {
        double precedingLength = 0;
        double selectedLength = 0;
        double totalLength = 0;
        foreach (string edgeId in side.EdgeIds)
        {
            int curveIndex = FindCurveIndex(piece, edgeId);
            if (curveIndex < 0)
            {
                throw new InvalidOperationException($"Seam side references missing curve {piece.Id}/{edgeId}.");
            }
            PatternCurveDocument curve = piece.Boundary[curveIndex];
            PatternPointDocument start = CurveStart(piece, curveIndex);
            double length = CurveLength(start, curve, 1);
            if (string.Equals(edgeId, curveId, StringComparison.OrdinalIgnoreCase))
            {
                selectedLength = CurveLength(start, curve, parameter);
            }
            else if (selectedLength == 0)
            {
                precedingLength += length;
            }
            totalLength += length;
        }
        if (totalLength <= ParameterEpsilon)
        {
            throw new InvalidOperationException($"Seam side on {piece.Id} has zero length.");
        }
        double geometricPosition = (precedingLength + selectedLength) / totalLength;
        return side.Reverse ? 1 - geometricPosition : geometricPosition;
    }

    private static (string CurveId, double Parameter) LocatePositionOnSide(
        PatternPieceDocument piece,
        IReadOnlyList<string> edgeIds,
        double normalizedPosition)
    {
        List<(string Id, PatternPointDocument Start, PatternCurveDocument Curve, double Length)> edges = [];
        double totalLength = 0;
        foreach (string edgeId in edgeIds)
        {
            int curveIndex = FindCurveIndex(piece, edgeId);
            if (curveIndex < 0)
            {
                throw new InvalidOperationException($"Seam side references missing curve {piece.Id}/{edgeId}.");
            }
            PatternCurveDocument curve = piece.Boundary[curveIndex];
            PatternPointDocument start = CurveStart(piece, curveIndex);
            double length = CurveLength(start, curve, 1);
            edges.Add((edgeId, start, curve, length));
            totalLength += length;
        }
        if (totalLength <= ParameterEpsilon)
        {
            throw new InvalidOperationException($"Seam side on {piece.Id} has zero length.");
        }

        double targetLength = Math.Clamp(normalizedPosition, ParameterEpsilon, 1 - ParameterEpsilon) * totalLength;
        double precedingLength = 0;
        foreach ((string id, PatternPointDocument start, PatternCurveDocument curve, double length) in edges)
        {
            if (targetLength < precedingLength + length - ParameterEpsilon ||
                string.Equals(id, edges[^1].Id, StringComparison.OrdinalIgnoreCase))
            {
                double localLength = Math.Clamp(targetLength - precedingLength, ParameterEpsilon, length - ParameterEpsilon);
                return (id, ParameterAtLength(start, curve, localLength));
            }
            precedingLength += length;
        }
        throw new InvalidOperationException($"Could not locate a split point on seam side {piece.Id}.");
    }

    private static (GarmentDocument Document, PatternBoundarySplitMapping Mapping) SplitSingleBoundarySegment(
        GarmentDocument document,
        string pieceId,
        string curveId,
        double parameter)
    {
        PatternPieceDocument piece = document.Pieces.First(item =>
            string.Equals(item.Id, pieceId, StringComparison.OrdinalIgnoreCase));
        int curveIndex = FindCurveIndex(piece, curveId);
        if (curveIndex < 0)
        {
            throw new InvalidOperationException($"Pattern curve {pieceId}/{curveId} does not exist.");
        }

        PatternCurveDocument curve = piece.Boundary[curveIndex];
        PatternPointDocument start = CurveStart(piece, curveIndex);
        HashSet<string> ids = piece.Boundary.Select(item => item.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        string firstId = UniqueId(ids, $"{curve.Id}-a");
        ids.Add(firstId);
        string secondId = UniqueId(ids, $"{curve.Id}-b");
        (PatternCurveDocument first, PatternCurveDocument second) = SplitCurve(curve, start, parameter, firstId, secondId);

        List<PatternCurveDocument> boundary = [.. piece.Boundary];
        boundary.RemoveAt(curveIndex);
        boundary.Insert(curveIndex, first);
        boundary.Insert(curveIndex + 1, second);
        PatternPieceDocument editedPiece = piece with
        {
            Boundary = boundary,
            Notches = piece.Notches
                .Select(notch => RemapNotch(notch, curveId, parameter, firstId, secondId))
                .ToArray(),
            Darts = piece.Darts
                .Select(dart => RemapDart(dart, curveId, parameter, firstId, secondId))
                .ToArray()
        };

        PatternPieceDocument[] pieces = document.Pieces
            .Select(item => string.Equals(item.Id, pieceId, StringComparison.OrdinalIgnoreCase) ? editedPiece : item)
            .ToArray();
        HashSet<string> affectedPanelIds = document.Panels
            .Where(panel => string.Equals(panel.PieceId, pieceId, StringComparison.OrdinalIgnoreCase))
            .Select(panel => panel.Id)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        ClothPanelDocument[] panels = document.Panels
            .Select(panel => affectedPanelIds.Contains(panel.Id)
                ? panel with { PinnedEdges = ReplaceEdgeReference(panel.PinnedEdges, curveId, firstId, secondId) }
                : panel)
            .ToArray();
        GarmentSeamDocument[] seams = document.Seams
            .Select(seam => seam with
            {
                SideA = ReplaceEdgeReference(seam.SideA, affectedPanelIds, curveId, firstId, secondId),
                SideB = ReplaceEdgeReference(seam.SideB, affectedPanelIds, curveId, firstId, secondId)
            })
            .ToArray();
        GarmentClosureDocument[] closures = document.Closures
            .Select(closure => closure with
            {
                AnchorA = ReplaceEdgeReference(closure.AnchorA, affectedPanelIds, curveId, firstId, secondId),
                AnchorB = ReplaceEdgeReference(closure.AnchorB, affectedPanelIds, curveId, firstId, secondId)
            })
            .ToArray();

        GarmentDocument edited = document with
        {
            Pieces = pieces,
            Panels = panels,
            Seams = seams,
            Closures = closures
        };
        IReadOnlyList<string> validationErrors = edited.Validate();
        if (validationErrors.Count > 0)
        {
            throw new InvalidOperationException(string.Join(Environment.NewLine, validationErrors));
        }
        return (
            edited,
            new PatternBoundarySplitMapping(pieceId, curveId, firstId, secondId));
    }

    private static (PatternCurveDocument First, PatternCurveDocument Second) SplitCurve(
        PatternCurveDocument curve,
        PatternPointDocument start,
        double parameter,
        string firstId,
        string secondId)
    {
        if (string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase))
        {
            PatternPointDocument split = Lerp(start, curve.End, parameter);
            return (
                new PatternCurveDocument(firstId, "line", split) { Label = curve.Label },
                new PatternCurveDocument(secondId, "line", curve.End) { Label = curve.Label });
        }
        if (!string.Equals(curve.Kind, "cubic", StringComparison.OrdinalIgnoreCase) ||
            curve.Control1 is null ||
            curve.Control2 is null)
        {
            throw new InvalidOperationException($"Pattern curve {curve.Id} is not a complete line or cubic segment.");
        }

        PatternPointDocument p01 = Lerp(start, curve.Control1, parameter);
        PatternPointDocument p12 = Lerp(curve.Control1, curve.Control2, parameter);
        PatternPointDocument p23 = Lerp(curve.Control2, curve.End, parameter);
        PatternPointDocument p012 = Lerp(p01, p12, parameter);
        PatternPointDocument p123 = Lerp(p12, p23, parameter);
        PatternPointDocument splitPoint = Lerp(p012, p123, parameter);
        return (
            new PatternCurveDocument(firstId, "cubic", splitPoint, p01, p012) { Label = curve.Label },
            new PatternCurveDocument(secondId, "cubic", curve.End, p123, p23) { Label = curve.Label });
    }

    private static PatternNotchDocument RemapNotch(
        PatternNotchDocument notch,
        string oldId,
        double splitParameter,
        string firstId,
        string secondId)
    {
        if (!string.Equals(notch.BoundaryCurveId, oldId, StringComparison.OrdinalIgnoreCase))
        {
            return notch;
        }
        return notch.Parameter <= splitParameter
            ? notch with
            {
                BoundaryCurveId = firstId,
                Parameter = notch.Parameter / splitParameter
            }
            : notch with
            {
                BoundaryCurveId = secondId,
                Parameter = (notch.Parameter - splitParameter) / (1 - splitParameter)
            };
    }

    private static PatternDartDocument RemapDart(
        PatternDartDocument dart,
        string oldId,
        double splitParameter,
        string firstId,
        string secondId)
    {
        (string firstLegCurve, double firstLegParameter) = RemapBoundaryAnchor(
            dart.FirstLegBoundaryCurveId,
            dart.FirstLegParameter,
            oldId,
            splitParameter,
            firstId,
            secondId);
        (string secondLegCurve, double secondLegParameter) = RemapBoundaryAnchor(
            dart.SecondLegBoundaryCurveId,
            dart.SecondLegParameter,
            oldId,
            splitParameter,
            firstId,
            secondId);
        return dart with
        {
            FirstLegBoundaryCurveId = firstLegCurve,
            FirstLegParameter = firstLegParameter,
            SecondLegBoundaryCurveId = secondLegCurve,
            SecondLegParameter = secondLegParameter
        };
    }

    private static (string CurveId, double Parameter) RemapBoundaryAnchor(
        string curveId,
        double parameter,
        string oldId,
        double splitParameter,
        string firstId,
        string secondId)
    {
        if (!string.Equals(curveId, oldId, StringComparison.OrdinalIgnoreCase))
        {
            return (curveId, parameter);
        }
        return parameter <= splitParameter
            ? (firstId, parameter / splitParameter)
            : (secondId, (parameter - splitParameter) / (1 - splitParameter));
    }

    private static SeamSideDocument ReplaceEdgeReference(
        SeamSideDocument side,
        IReadOnlySet<string> affectedPanelIds,
        string oldId,
        string firstId,
        string secondId)
        => affectedPanelIds.Contains(side.PanelId)
            ? side with { EdgeIds = ReplaceEdgeReference(side.EdgeIds, oldId, firstId, secondId) }
            : side;

    private static GarmentClosureAnchorDocument ReplaceEdgeReference(
        GarmentClosureAnchorDocument anchor,
        IReadOnlySet<string> affectedPanelIds,
        string oldId,
        string firstId,
        string secondId)
        => affectedPanelIds.Contains(anchor.PanelId)
            ? anchor with { EdgeIds = ReplaceEdgeReference(anchor.EdgeIds, oldId, firstId, secondId) }
            : anchor;

    private static IReadOnlyList<string> ReplaceEdgeReference(
        IReadOnlyList<string> ids,
        string oldId,
        string firstId,
        string secondId)
    {
        List<string> result = [];
        foreach (string id in ids)
        {
            if (string.Equals(id, oldId, StringComparison.OrdinalIgnoreCase))
            {
                result.Add(firstId);
                result.Add(secondId);
            }
            else
            {
                result.Add(id);
            }
        }
        return result;
    }

    private static double ParameterAtLength(
        PatternPointDocument start,
        PatternCurveDocument curve,
        double targetLength)
    {
        double low = ParameterEpsilon;
        double high = 1 - ParameterEpsilon;
        for (int iteration = 0; iteration < 28; iteration++)
        {
            double middle = (low + high) * 0.5;
            if (CurveLength(start, curve, middle) < targetLength)
            {
                low = middle;
            }
            else
            {
                high = middle;
            }
        }
        return (low + high) * 0.5;
    }

    private static double CurveLength(
        PatternPointDocument start,
        PatternCurveDocument curve,
        double endParameter)
    {
        PatternPointDocument previous = start;
        double length = 0;
        for (int sample = 1; sample <= LengthSamples; sample++)
        {
            double parameter = endParameter * sample / LengthSamples;
            PatternPointDocument point = Evaluate(start, curve, parameter);
            length += Distance(previous, point);
            previous = point;
        }
        return length;
    }

    private static PatternPointDocument Evaluate(
        PatternPointDocument start,
        PatternCurveDocument curve,
        double parameter)
    {
        if (string.Equals(curve.Kind, "line", StringComparison.OrdinalIgnoreCase))
        {
            return Lerp(start, curve.End, parameter);
        }
        if (curve.Control1 is null || curve.Control2 is null)
        {
            throw new InvalidOperationException($"Cubic curve {curve.Id} is missing a control point.");
        }
        double inverse = 1 - parameter;
        return new PatternPointDocument(
            inverse * inverse * inverse * start.X +
                3 * inverse * inverse * parameter * curve.Control1.X +
                3 * inverse * parameter * parameter * curve.Control2.X +
                parameter * parameter * parameter * curve.End.X,
            inverse * inverse * inverse * start.Y +
                3 * inverse * inverse * parameter * curve.Control1.Y +
                3 * inverse * parameter * parameter * curve.Control2.Y +
                parameter * parameter * parameter * curve.End.Y);
    }

    private static PatternPointDocument CurveStart(PatternPieceDocument piece, int curveIndex)
        => curveIndex == 0 ? piece.Start : piece.Boundary[curveIndex - 1].End;

    private static int FindCurveIndex(PatternPieceDocument piece, string curveId)
        => piece.Boundary
            .Select((curve, index) => new { curve.Id, Index = index })
            .FirstOrDefault(item => string.Equals(item.Id, curveId, StringComparison.OrdinalIgnoreCase))?.Index ?? -1;

    private static string UniqueId(IReadOnlySet<string> ids, string desired)
    {
        if (!ids.Contains(desired))
        {
            return desired;
        }
        for (int suffix = 2; suffix < int.MaxValue; suffix++)
        {
            string candidate = $"{desired}-{suffix}";
            if (!ids.Contains(candidate))
            {
                return candidate;
            }
        }
        throw new InvalidOperationException($"Could not generate a unique edge id from {desired}.");
    }

    private static PatternPointDocument Lerp(
        PatternPointDocument first,
        PatternPointDocument second,
        double amount)
        => new(
            first.X + (second.X - first.X) * amount,
            first.Y + (second.Y - first.Y) * amount);

    private static double Distance(PatternPointDocument first, PatternPointDocument second)
        => Math.Sqrt(
            (first.X - second.X) * (first.X - second.X) +
            (first.Y - second.Y) * (first.Y - second.Y));

    private static void ValidateParameter(double parameter)
    {
        if (!double.IsFinite(parameter) || parameter <= ParameterEpsilon || parameter >= 1 - ParameterEpsilon)
        {
            throw new ArgumentOutOfRangeException(nameof(parameter), "Split parameter must be strictly between zero and one.");
        }
    }

    private static void EnsureValid(GarmentDocument document)
    {
        IReadOnlyList<string> errors = document.Validate();
        if (errors.Count > 0)
        {
            throw new InvalidOperationException(string.Join(Environment.NewLine, errors));
        }
    }

    private sealed record SplitTarget(
        string PieceId,
        string CurveId,
        double Parameter,
        bool IsPrimary);
}
