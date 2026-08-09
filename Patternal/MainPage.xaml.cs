using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.Text;
using System.Text.Json;
using Microsoft.UI;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Shapes;
using Microsoft.Web.WebView2.Core;
using Windows.Foundation;
using Windows.Storage;
using Windows.Storage.Pickers;

namespace Patterna;

public sealed partial class MainPage : Page
{
    private const double PatternPixelsPerCentimeter = 4.0;
    private const double DefaultHeight = 167;
    private const double DefaultChest = 112;
    private const double DefaultWaist = 82;
    private const double DefaultHip = 108;
    private const double DefaultShoulder = 37;
    private const double DefaultTorso = 44;
    private const double DefaultChestEase = 6;
    private const double DefaultWaistEase = 6;
    private const double DefaultHipEase = 8;
    private const double DefaultUpperArmEase = 5;
    private const double DefaultArmscyeEase = 2.5;
    private const int BustShapingDefaultVersion = 2;
    private const int DefaultBodyTemplateIndex = 1;
    private const string AdaptiveShirtTemplate = "adaptive-shirt";
    private const string WrapDressTemplate = "wrap-dress";

    private bool _pageReady;
    private bool _webReady;
    private bool _updatingLinkedMeasurements;
    private bool _constructionProfileRestored;
    private bool _constructionProfileEdited;
    private bool _updatingConstructionControls;
    private bool _bustShapingProfileRestored;
    private bool _updatingBustShapingControls;
    private string _selectedPieceId = "front-torso";
    private string _garmentTemplateKey = AdaptiveShirtTemplate;
    private string _fabricKey = "cotton";
    private int _photoCount;
    private GarmentDocument? _garmentDocument;
    private GarmentDocument? _adaptiveShirtDocument;
    private readonly Dictionary<string, PatternPointDocument> _patternPointOffsets = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<PatternStructuralEditCommand> _patternStructuralEdits = [];
    private readonly Dictionary<string, bool> _seamSideBReverseOverrides = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, string> _closureStateOverrides = new(StringComparer.OrdinalIgnoreCase);
    private readonly Stack<PatternEditSnapshot> _patternUndoStack = new();
    private readonly Stack<PatternEditSnapshot> _patternRedoStack = new();
    private PatternPointHandle? _selectedPatternPoint;
    private PatternEdgeHandle? _pendingSewingEdge;
    private AssemblyRelationshipHandle? _selectedAssemblyRelationship;
    private PatternPointHandle? _draggingPatternPoint;
    private PatternPointDocument? _dragStartPoint;
    private PatternPointDocument? _dragPreviewPoint;
    private Point _dragStartPointer;
    private Ellipse? _draggingHandleVisual;
    private CanvasDraftTool _canvasDraftTool;
    private readonly List<PatternPointDocument> _canvasDraftPoints = [];
    private readonly List<UIElement> _canvasDraftPreviewElements = [];
    private PatternPointDocument? _canvasDraftPointer;
    private bool _updatingPatternPointInspector;
    private bool _updatingAssemblyInspector;
    private readonly SemaphoreSlim _unrealBridgeWriteLock = new(1, 1);
    private string? _currentSimulationRevision;
    private string? _acceptedSimulationRevision;
    private SimulationFitEvidence? _bundledSimulationFitEvidence;
    private string? _displayedSimulationRevision;
    private string? _pendingViewportAssetRevision;
    private TaskCompletionSource<ViewportAssetLoadResult>? _pendingViewportAssetLoad;
    private CancellationTokenSource? _simulationCancellation;

    private static readonly JsonSerializerOptions GarmentJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    private static readonly JsonSerializerOptions UnrealBridgeJsonOptions = new(GarmentJsonOptions)
    {
        WriteIndented = true
    };

    public ObservableCollection<MeasurementGroup> MeasurementGroups { get; } = BuildMeasurementGroups();

    public ObservableCollection<PatternPieceListItem> PatternPieceItems { get; } = [];

    public ObservableCollection<CustomMeasurement> CustomMeasurements { get; } =
    [
        new CustomMeasurement("Custom landmark", 0, "cm")
    ];

    public string DetailedMeasurementCountText =>
        $"{6 + MeasurementGroups.Sum(group => group.Measurements.Count)} editable body and landmark parameters";

    private static MeasurementParameter P(
        string key,
        string label,
        double value,
        double minimum,
        double maximum,
        double increment = 0.1,
        string unit = "cm")
        => new(key, label, value, minimum, maximum, increment, unit);

    private static ObservableCollection<MeasurementGroup> BuildMeasurementGroups()
        =>
        [
            new(
                "Head, face and neck",
                "Surface dimensions and landmarks for collars, hoods, headwear, and upper-body alignment.",
                [
                    P("headCirc", "Head circumference", 56.2, 45, 70),
                    P("headHeight", "Head height", 23.1, 17, 30),
                    P("crownChin", "Crown to chin", 22.4, 16, 30),
                    P("faceWidth", "Temple width", 14.2, 10, 20),
                    P("bizygomaticWidth", "Cheekbone width", 13.8, 9, 20),
                    P("jawWidth", "Jaw width", 11.2, 7, 18),
                    P("faceDepth", "Face depth", 18.1, 12, 25),
                    P("jawDepth", "Jaw depth", 10.4, 6, 16),
                    P("earToEar", "Ear to ear over crown", 31.8, 22, 42),
                    P("skullBackProjection", "Back skull projection", 2.1, 0, 6),
                    P("neckCirc", "Neck circumference", 34.5, 24, 58),
                    P("neckBaseCirc", "Neck base circumference", 39.4, 28, 68),
                    P("neckLengthFront", "Front neck length", 8.4, 4, 16),
                    P("neckLengthBack", "Back neck length", 9.1, 4, 17),
                    P("neckForward", "Head forward offset", 1.2, -4, 8),
                    P("chinNeck", "Chin to neck point", 9.3, 4, 17)
                ],
                true),
            new(
                "Shoulders, chest, bust and back",
                "Front, back, depth, projection, and independently adjustable shoulder landmarks.",
                [
                    P("highChestCirc", "High chest circumference", 96.0, 58, 150),
                    P("underBust", "Underbust circumference", 84.0, 52, 145),
                    P("ribCirc", "Lower rib circumference", 82.0, 50, 145),
                    P("acrossFront", "Across front width", 36.7, 22, 55),
                    P("acrossBack", "Across back width", 37.0, 24, 60),
                    P("chestDepth", "Bust front-to-back depth", 31.0, 14, 42),
                    P("underBustDepth", "Underbust depth", 23.0, 12, 38),
                    P("bustSupport", "Supported bust shaping", 100, 0, 100, 1, "%"),
                    P("upperBustFullness", "Upper bust fullness", 85, 0, 100, 1, "%"),
                    P("frontWaistLength", "Front neck to waist", 47.0, 28, 65),
                    P("backWaistLength", "Back neck to waist", 41.8, 27, 64),
                    P("backNeckWaist", "Nape to natural waist", 40.6, 25, 62),
                    P("shoulderLengthL", "Left shoulder length", 12.4, 7, 22),
                    P("shoulderLengthR", "Right shoulder length", 12.3, 7, 22),
                    P("shoulderSlopeL", "Left shoulder slope", 22.0, -2, 30, 0.1, "deg"),
                    P("shoulderSlopeR", "Right shoulder slope", 21.5, -2, 30, 0.1, "deg"),
                    P("bustSeparation", "Bust point separation", 19.0, 8, 34),
                    P("bustHeightL", "Left shoulder to bust point", 24.8, 14, 42),
                    P("bustHeightR", "Right shoulder to bust point", 24.6, 14, 42),
                    P("bustProjectionL", "Left bust projection", 9.6, 0, 14),
                    P("bustProjectionR", "Right bust projection", 9.4, 0, 14),
                    P("sternumWaist", "Sternum to waist", 33.0, 18, 48)
                ]),
            new(
                "Waist, abdomen, pelvis and seat",
                "Circumferences, arcs, rises, depths, and soft-tissue projections around the garment support zone.",
                [
                    P("waistDepth", "Natural waist depth", 21.0, 10, 38),
                    P("highHipCirc", "High hip circumference", 98.0, 58, 155),
                    P("highHipDepth", "High hip depth", 24.0, 12, 42),
                    P("hipDepth", "Full hip depth", 28.0, 14, 46),
                    P("abdomenCirc", "Abdomen circumference", 90.0, 50, 165),
                    P("abdomenDepth", "Abdomen depth", 22.5, 10, 45),
                    P("abdomenProjection", "Abdomen projection", 2.4, -4, 12),
                    P("pelvicWidth", "Bony pelvis width", 31.0, 18, 48),
                    P("bodyRise", "Seated body rise", 26.7, 18, 42),
                    P("crotchDepth", "Crotch depth", 25.1, 16, 40),
                    P("crotchLength", "Total crotch length", 70.4, 48, 105),
                    P("frontRise", "Front waist to crotch", 30.8, 19, 48),
                    P("backRise", "Back waist to crotch", 39.6, 25, 62),
                    P("frontHipArc", "Front hip arc", 51.5, 28, 82),
                    P("backHipArc", "Back hip arc", 56.5, 30, 88),
                    P("gluteProjectionL", "Left seat projection", 5.6, 0, 13),
                    P("gluteProjectionR", "Right seat projection", 5.5, 0, 13),
                    P("hipDipL", "Left hip dip", 0.7, 0, 5),
                    P("hipDipR", "Right hip dip", 0.6, 0, 5),
                    P("waistHipLengthL", "Left waist to hip", 20.4, 12, 32),
                    P("waistHipLengthR", "Right waist to hip", 20.3, 12, 32)
                ]),
            LimbGroup("Left arm and hand", "L", true),
            LimbGroup("Right arm and hand", "R", false),
            LegGroup("Left leg and foot", "L", true),
            LegGroup("Right leg and foot", "R", false),
            new(
                "Posture, alignment and surface shape",
                "Angles and local surface controls that circumference-only sizing cannot represent.",
                [
                    P("pelvicTilt", "Pelvic tilt", 8.0, -20, 30, 0.1, "deg"),
                    P("lumbarCurve", "Lumbar curve depth", 2.4, -2, 8),
                    P("thoracicCurve", "Thoracic curve depth", 2.2, -2, 8),
                    P("cervicalCurve", "Cervical curve depth", 1.3, -2, 6),
                    P("torsoLean", "Torso lean", 0.0, -15, 20, 0.1, "deg"),
                    P("torsoTwist", "Torso twist", 0.0, -20, 20, 0.1, "deg"),
                    P("ribFlareL", "Left rib flare", 0.4, -3, 7),
                    P("ribFlareR", "Right rib flare", 0.4, -3, 7),
                    P("shoulderRollL", "Left shoulder roll", 1.0, -20, 25, 0.1, "deg"),
                    P("shoulderRollR", "Right shoulder roll", 0.5, -20, 25, 0.1, "deg"),
                    P("scapulaProjectionL", "Left scapula projection", 0.7, -2, 6),
                    P("scapulaProjectionR", "Right scapula projection", 0.6, -2, 6),
                    P("kneeAngleL", "Left knee alignment", 0.0, -15, 15, 0.1, "deg"),
                    P("kneeAngleR", "Right knee alignment", 0.0, -15, 15, 0.1, "deg"),
                    P("footAngleL", "Left foot rotation", 4.0, -25, 35, 0.1, "deg"),
                    P("footAngleR", "Right foot rotation", 4.0, -25, 35, 0.1, "deg"),
                    P("muscleDefinition", "Muscle definition", 0, 0, 100, 1, "%"),
                    P("softTissue", "Soft-tissue fullness", 58, 0, 100, 1, "%"),
                    P("upperBodyDistribution", "Torso V-shape", 42, 0, 100, 1, "%"),
                    P("lowerBodyDistribution", "Lower-body fullness", 58, 0, 100, 1, "%")
                ])
        ];

    private static MeasurementGroup LimbGroup(string title, string side, bool expanded)
    {
        string sideName = side == "L" ? "Left" : "Right";
        return new(
            title,
            "Segment lengths, girths, widths, and hand dimensions are independent from the opposite side.",
            [
                P($"armLength{side}", $"{sideName} total arm length", 57.3, 38, 82),
                P($"shoulderElbow{side}", $"{sideName} shoulder to elbow", 31.8, 20, 48),
                P($"elbowWrist{side}", $"{sideName} elbow to wrist", 25.5, 16, 40),
                P($"upperArmCirc{side}", $"{sideName} upper arm circumference", 26.0, 18, 62),
                P($"bicepDepth{side}", $"{sideName} upper arm depth", 9.2, 5, 20),
                P($"deltoidProminence{side}", $"{sideName} deltoid cap prominence", 0, 0, 100, 1, "%"),
                P($"upperArmSoftTissue{side}", $"{sideName} upper arm soft-tissue fullness", 20, 0, 100, 1, "%"),
                P($"elbowCirc{side}", $"{sideName} elbow circumference", 24.5, 17, 44),
                P($"forearmCirc{side}", $"{sideName} forearm circumference", 24.0, 15, 43),
                P($"wristCirc{side}", $"{sideName} wrist circumference", 15.8, 11, 28),
                P($"handLength{side}", $"{sideName} hand length", 17.9, 12, 26),
                P($"palmWidth{side}", $"{sideName} palm width", 7.7, 5, 13),
                P($"palmCirc{side}", $"{sideName} palm circumference", 18.4, 13, 30),
                P($"thumbBaseCirc{side}", $"{sideName} thumb base circumference", 6.3, 4, 11),
                P($"armholeDepth{side}", $"{sideName} armhole depth", 21.8, 13, 34),
                P($"armscyeCirc{side}", $"{sideName} armscye circumference", 45.5, 28, 70)
            ],
            expanded);
    }

    private static MeasurementGroup LegGroup(string title, string side, bool expanded)
    {
        string sideName = side == "L" ? "Left" : "Right";
        return new(
            title,
            "Rise, segment lengths, girths, knee alignment, and foot dimensions remain side-specific.",
            [
                P($"outseam{side}", $"{sideName} waist to floor", 103.0, 70, 135),
                P($"inseam{side}", $"{sideName} inseam", 77.0, 48, 105),
                P($"waistKnee{side}", $"{sideName} waist to knee", 59.4, 38, 82),
                P($"crotchKnee{side}", $"{sideName} crotch to knee", 34.8, 20, 53),
                P($"thighUpperCirc{side}", $"{sideName} upper thigh circumference", 62.0, 32, 95),
                P($"thighMidCirc{side}", $"{sideName} mid-thigh circumference", 50.2, 28, 85),
                P($"kneeCirc{side}", $"{sideName} knee circumference", 38.0, 24, 62),
                P($"calfCirc{side}", $"{sideName} calf circumference", 36.4, 22, 65),
                P($"ankleCirc{side}", $"{sideName} ankle circumference", 22.5, 15, 40),
                P($"kneeHeight{side}", $"{sideName} knee height", 48.2, 30, 68),
                P($"lowerLegLength{side}", $"{sideName} knee to ankle", 40.8, 25, 58),
                P($"footLength{side}", $"{sideName} foot length", 24.1, 18, 34),
                P($"footWidth{side}", $"{sideName} foot width", 9.2, 6, 15),
                P($"ballGirth{side}", $"{sideName} ball girth", 22.6, 16, 35),
                P($"heelGirth{side}", $"{sideName} heel girth", 31.8, 22, 45),
                P($"archHeight{side}", $"{sideName} arch height", 2.1, 0, 6),
                P($"legOffset{side}", $"{sideName} hip socket offset", 0.0, -4, 4)
            ],
            expanded);
    }

    public MainPage()
    {
        InitializeComponent();
    }

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        RestoreSnapshot();
        ApplySelectedFabricPreset();
        await LoadAuthoritativeGarmentSourcesAsync();
        await LoadBundledSimulationFitEvidenceAsync();
        GarmentTemplateComboBox.SelectedIndex = _garmentTemplateKey == WrapDressTemplate ? 1 : 0;
        RefreshPatternWorkspaceMetadata();
        _pageReady = true;
        UpdateMeasurementLabels();
        RenderPattern();
        UpdateFitIntelligence();
        UpdateDrapeSurfaceHeight();
        await InitializeDrapeViewportAsync();
        await UpdateDrapeViewportAsync();
    }

    private async Task LoadAuthoritativeGarmentSourcesAsync()
    {
        try
        {
            string sourceJson = await ReadBundledTextAsync(
                "Assets/GarmentCode/PatternaProductionCrewNeck.specification.json");
            FabricPhysicsDocument fabric = GarmentDocumentFactory.CreateFabric(
                _fabricKey,
                FabricWeightSlider.Value,
                FabricStretchSlider.Value,
                double.IsNaN(BendNumberBox.Value) ? 8 : BendNumberBox.Value,
                double.IsNaN(FrictionNumberBox.Value) ? 0.4 : FrictionNumberBox.Value);
            _adaptiveShirtDocument = GarmentCodePatternImporter.Import(
                sourceJson,
                new GarmentCodeImportOptions(
                    "adaptive-female-crew-neck",
                    "Full-bust adaptive crew-neck shirt",
                    fabric,
                    SourcePath: "PatternaUnreal/SourceAssets/GarmentCode/PatternaProductionCrewNeck.specification.json",
                    SourceRevision: "e3469c92cdc0ae6e019527ff90f32f8c096884a35f95696a5e3f4c325891b3e3"));
            _bundledSimulationFitEvidence = null;
            AlignUnmodifiedEaseControlsToBundledSource();
            AlignConstructionControlsToBundledSource();
            AlignBustShapingControlsToBundledSource();
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException or GarmentCodeImportException)
        {
            _adaptiveShirtDocument = null;
            _garmentTemplateKey = WrapDressTemplate;
            ShowStatus(
                "Authoritative shirt source unavailable",
                $"Patternal kept the wrap-dress editor available. {exception.Message}",
                InfoBarSeverity.Error);
        }
    }

    private async Task LoadBundledSimulationFitEvidenceAsync()
    {
        _bundledSimulationFitEvidence = null;
        try
        {
            string reportJson = await ReadBundledTextAsync(
                "Assets/Production/patterna-production-crew-neck.fit.json");
            using JsonDocument report = JsonDocument.Parse(reportJson);
            if (SimulationPipeline.TryParseFitEvidence(report.RootElement, out SimulationFitEvidence? evidence))
            {
                _bundledSimulationFitEvidence = evidence;
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            System.Diagnostics.Debug.WriteLine($"Patternal bundled fit evidence unavailable: {exception.Message}");
        }
    }

    private static async Task<string> ReadBundledTextAsync(string relativePath)
    {
        string normalizedRelativePath = relativePath.Replace('/', System.IO.Path.DirectorySeparatorChar);
        string deployedPath = System.IO.Path.Combine(AppContext.BaseDirectory, normalizedRelativePath);
        if (File.Exists(deployedPath))
        {
            return await File.ReadAllTextAsync(deployedPath);
        }

        string appResourcePath = relativePath.Replace(System.IO.Path.DirectorySeparatorChar, '/');
        StorageFile packagedFile = await StorageFile.GetFileFromApplicationUriAsync(
            new Uri($"ms-appx:///{appResourcePath}"));
        return await FileIO.ReadTextAsync(packagedFile);
    }

    private void AlignUnmodifiedEaseControlsToBundledSource()
    {
        if (_adaptiveShirtDocument is null)
        {
            return;
        }

        GarmentEaseProfileDocument sourceEase =
            AdaptiveShirtPatternGrader.MeasureSourceEase(_adaptiveShirtDocument);
        bool hasLegacyDefaultEase =
            Math.Abs(ChestEaseNumberBox.Value - DefaultChestEase) <= 0.001 &&
            Math.Abs(WaistEaseNumberBox.Value - DefaultWaistEase) <= 0.001 &&
            Math.Abs(HipEaseNumberBox.Value - 6) <= 0.001 &&
            Math.Abs(UpperArmEaseNumberBox.Value - 4) <= 0.001 &&
            Math.Abs(ArmscyeEaseNumberBox.Value - DefaultArmscyeEase) <= 0.001;
        bool hasDefectiveUpstreamEase =
            Math.Abs(ChestEaseNumberBox.Value - 9) <= 0.001 &&
            Math.Abs(WaistEaseNumberBox.Value - 39) <= 0.001 &&
            Math.Abs(HipEaseNumberBox.Value - 13) <= 0.001 &&
            Math.Abs(UpperArmEaseNumberBox.Value - 5) <= 0.001 &&
            Math.Abs(ArmscyeEaseNumberBox.Value - DefaultArmscyeEase) <= 0.001;
        bool hasLegacyClampedSourceEase =
            Math.Abs(ChestEaseNumberBox.Value - Math.Max(sourceEase.ChestEaseCm, -6)) <= 0.001 &&
            Math.Abs(WaistEaseNumberBox.Value - Math.Max(sourceEase.WaistEaseCm, -6)) <= 0.001 &&
            Math.Abs(HipEaseNumberBox.Value - Math.Max(sourceEase.HipEaseCm, -6)) <= 0.001 &&
            Math.Abs(UpperArmEaseNumberBox.Value - sourceEase.UpperArmEaseCm) <= 0.001 &&
            Math.Abs(ArmscyeEaseNumberBox.Value - sourceEase.ArmscyeEaseCm) <= 0.001;
        bool hasEditRecords =
            _patternPointOffsets.Count > 0 ||
            _patternStructuralEdits.Count > 0 ||
            _seamSideBReverseOverrides.Count > 0 ||
            _closureStateOverrides.Count > 0;
        bool shouldAlign = hasLegacyClampedSourceEase ||
            (!hasEditRecords && (hasLegacyDefaultEase || hasDefectiveUpstreamEase));
        if (!shouldAlign)
        {
            return;
        }

        ChestEaseNumberBox.Value = sourceEase.ChestEaseCm;
        WaistEaseNumberBox.Value = sourceEase.WaistEaseCm;
        HipEaseNumberBox.Value = sourceEase.HipEaseCm;
        UpperArmEaseNumberBox.Value = sourceEase.UpperArmEaseCm;
        ArmscyeEaseNumberBox.Value = sourceEase.ArmscyeEaseCm;
    }

    private void AlignConstructionControlsToBundledSource()
    {
        if (_adaptiveShirtDocument is null || _constructionProfileRestored || _constructionProfileEdited)
        {
            return;
        }
        SetConstructionControls(MeasurementAwareConstructionProfile());
    }

    private void SetConstructionControls(ShirtConstructionProfileDocument profile)
    {
        _updatingConstructionControls = true;
        try
        {
            FrontWidthShareNumberBox.Value = profile.FrontWidthSharePercent;
            NecklineWidthNumberBox.Value = profile.NecklineWidthCm;
            FrontNeckDepthNumberBox.Value = profile.FrontNeckDepthCm;
            BackNeckDepthNumberBox.Value = profile.BackNeckDepthCm;
            ShoulderLengthNumberBox.Value = profile.ShoulderLengthCm;
            ShoulderDropNumberBox.Value = profile.ShoulderDropCm;
            ArmscyeDepthNumberBox.Value = profile.ArmscyeDepthCm;
            ArmscyeScoopNumberBox.Value = profile.ArmscyeScoopCm;
            UnderarmExtensionNumberBox.Value = profile.UnderarmExtensionCm;
            SleeveCapHeightNumberBox.Value = profile.SleeveCapHeightCm;
            FrontBalanceNumberBox.Value = profile.FrontBalanceCm;
        }
        finally
        {
            _updatingConstructionControls = false;
        }
    }

    private ShirtConstructionProfileDocument MeasurementAwareConstructionProfile()
    {
        if (_adaptiveShirtDocument is null)
        {
            return DefaultShirtConstructionProfile();
        }
        if (IsBodyAtSourceReference())
        {
            ShirtConstructionProfileDocument? sourceProfile =
                TryMeasureShirtConstructionProfile(_adaptiveShirtDocument);
            if (sourceProfile is not null)
            {
                return sourceProfile;
            }
            return DefaultShirtConstructionProfile();
        }
        double armholeDepth = AverageDetailedMeasurement("armholeDepthL", "armholeDepthR", DefaultChest * 0.225);
        double armscyeCircumference = AverageDetailedMeasurement("armscyeCircL", "armscyeCircR", DefaultChest * 0.457);
        return AdaptiveShirtPatternGrader.FitArmscyeConstructionProfile(
            _adaptiveShirtDocument,
            armholeDepth,
            armscyeCircumference,
            CurrentGarmentEaseProfile().ArmscyeEaseCm);
    }

    private void AlignBustShapingControlsToBundledSource()
    {
        if (_adaptiveShirtDocument is null || _bustShapingProfileRestored)
        {
            return;
        }
        ShirtBustShapingProfileDocument estimate = EstimateCurrentBustShapingProfile() with
        {
            Mode = ShirtBustShapingModes.SideDarts
        };
        SetBustShapingControls(estimate);
    }

    private void SetBustShapingControls(ShirtBustShapingProfileDocument profile)
    {
        _updatingBustShapingControls = true;
        try
        {
            SelectComboBoxByTag(BustShapingModeComboBox, profile.Mode);
            LeftDartIntakeNumberBox.Value = profile.LeftDartIntakeCm;
            RightDartIntakeNumberBox.Value = profile.RightDartIntakeCm;
            BustPointSeparationNumberBox.Value = profile.BustPointSeparationCm;
            LeftBustHeightNumberBox.Value = profile.LeftBustHeightCm;
            RightBustHeightNumberBox.Value = profile.RightBustHeightCm;
            LeftBustProjectionNumberBox.Value = profile.LeftBustProjectionCm;
            RightBustProjectionNumberBox.Value = profile.RightBustProjectionCm;
            DartTipOffsetNumberBox.Value = profile.DartTipOffsetCm;
            DartMouthDropNumberBox.Value = profile.DartMouthDropCm;
            ShoulderDartMouthOffsetNumberBox.Value = profile.ShoulderDartMouthOffsetCm;
            ShoulderDartShareNumberBox.Value = profile.ShoulderDartSharePercent;
        }
        finally
        {
            _updatingBustShapingControls = false;
        }
    }

    private void RefreshPatternWorkspaceMetadata()
    {
        GarmentDocument document = BuildStructurallyEditedBaseDocument();
        if (!document.Pieces.Any(piece => string.Equals(piece.Id, _selectedPieceId, StringComparison.OrdinalIgnoreCase)))
        {
            _selectedPieceId = document.Pieces[0].Id;
        }

        GarmentTitleText.Text = _garmentTemplateKey == AdaptiveShirtTemplate
            ? "Adaptive crew-neck shirt"
            : "Wrap dress prototype";
        PatternPieceCountText.Text = $"{document.Pieces.Count} pieces";
        PatternPieceItems.Clear();
        for (int index = 0; index < document.Pieces.Count; index++)
        {
            PatternPieceDocument piece = document.Pieces[index];
            List<string> construction = [$"Cut {piece.CutQuantity}"];
            if (piece.Mirrored)
            {
                construction.Add("mirrored");
            }
            if (piece.CutOnFold)
            {
                construction.Add("on fold");
            }
            PatternPieceItems.Add(new PatternPieceListItem(
                piece.Id,
                piece.Name,
                string.Join(" · ", construction),
                index % 2 == 0
                    ? ResourceBrush("PatternPieceFillBrush")
                    : ResourceBrush("PatternPieceSecondaryFillBrush")));
        }

        PatternPiecesList.SelectedItem = PatternPieceItems.FirstOrDefault(item =>
            string.Equals(item.Id, _selectedPieceId, StringComparison.OrdinalIgnoreCase));
        bool shirtAccepted = _garmentTemplateKey == AdaptiveShirtTemplate && _adaptiveShirtDocument is not null;
        HighFidelityPreviewImage.Visibility = Visibility.Collapsed;
        AcceptedShirtControls.Visibility = Visibility.Collapsed;
        AcceptedEquilibriumCard.Visibility = Visibility.Collapsed;
        StaleSimulationNotice.Visibility = shirtAccepted ? Visibility.Visible : Visibility.Collapsed;
        UnacceptedGarmentNotice.Visibility = shirtAccepted ? Visibility.Collapsed : Visibility.Visible;
        SimulationStatusText.Text = shirtAccepted
            ? "Checking whether the accepted cloth matches this document"
            : "3D blocked · dress equilibrium has not passed the visual and strain gates";
    }

    private Brush ResourceBrush(string key)
    {
        if (Application.Current.Resources.TryGetValue(key, out object? value) && value is Brush brush)
        {
            return brush;
        }

        return new SolidColorBrush(Colors.White);
    }

    private void RenderPattern()
    {
        if (!_pageReady || _updatingBustShapingControls)
        {
            return;
        }

        PatternCanvas.Children.Clear();
        DrawGrid();

        _garmentDocument = BuildCurrentGarmentDocument();
        for (int index = 0; index < _garmentDocument.Pieces.Count; index++)
        {
            PatternPieceDocument piece = _garmentDocument.Pieces[index];
            Brush fill = index % 2 == 0
                ? ResourceBrush("PatternPieceFillBrush")
                : ResourceBrush("PatternPieceSecondaryFillBrush");
            DrawPiece(piece, fill);
        }

        if (_garmentTemplateKey == WrapDressTemplate)
        {
            PatternPieceDocument bodiceFront = _garmentDocument.Pieces.First(piece => piece.Id == "bodice-front");
            PatternPieceDocument skirt = _garmentDocument.Pieces.First(piece => piece.Id == "skirt");
            DrawDimension(72, 60, 246 * bodiceFront.ScaleX, $"¼ chest + ease  {(ChestSlider.Value / 4 + 3.6):0.0} cm");
            DrawDimension(107, 682, 282 * skirt.ScaleX, $"hip contour  {HipSlider.Value:0.#} cm");
        }
        DrawCanvasDraftPreview();
    }

    private GarmentDocument BuildCurrentGarmentDocument()
        => PatternPhysicalDartCompiler.Compile(
            ApplyAssemblyOverrides(ApplyPatternPointOffsets(BuildStructurallyEditedBaseDocument())));

    private GarmentDocument BuildStructurallyEditedBaseDocument()
        => PatternStructuralEditor.ApplyEdits(BuildBaseGarmentDocument(), _patternStructuralEdits);

    private GarmentDocument BuildBaseGarmentDocument()
    {
        double bend = double.IsNaN(BendNumberBox.Value) ? 8 : BendNumberBox.Value;
        double friction = double.IsNaN(FrictionNumberBox.Value) ? 0.4 : FrictionNumberBox.Value;
        if (_garmentTemplateKey == AdaptiveShirtTemplate && _adaptiveShirtDocument is not null)
        {
            GarmentDocument source = _adaptiveShirtDocument with
            {
                Fabric = GarmentDocumentFactory.CreateFabric(
                    _fabricKey,
                    FabricWeightSlider.Value,
                    FabricStretchSlider.Value,
                    bend,
                    friction)
            };
            if (IsUnmodifiedSourcePattern())
            {
                return source;
            }
            double armLength = AverageDetailedMeasurement("armLengthL", "armLengthR", DefaultHeight * 0.343);
            double upperArmCircumference = AverageDetailedMeasurement("upperArmCircL", "upperArmCircR", DefaultChest * 0.32);
            double armholeDepth = AverageDetailedMeasurement("armholeDepthL", "armholeDepthR", DefaultChest * 0.225);
            double armscyeCircumference = AverageDetailedMeasurement("armscyeCircL", "armscyeCircR", DefaultChest * 0.457);
            ShirtConstructionProfileDocument? measurableConstruction =
                TryMeasureShirtConstructionProfile(source);
            GarmentDocument graded = AdaptiveShirtPatternGrader.Adapt(
                source,
                ChestSlider.Value,
                WaistSlider.Value,
                HipSlider.Value,
                ShoulderSlider.Value,
                TorsoSlider.Value,
                armLength,
                upperArmCircumference,
                armholeDepth,
                armscyeCircumference,
                CurrentGarmentEaseProfile(),
                measurableConstruction is null ? null : CurrentShirtConstructionProfile(),
                highHipCircumferenceCm: FindDetailedMeasurement("highHipCirc")?.Value ??
                    WaistSlider.Value + (HipSlider.Value - WaistSlider.Value) * 0.57).Document;
            return AdaptiveShirtBustShaper.Apply(
                graded,
                CurrentShirtBustShapingProfile()).Document;
        }

        return GarmentDocumentFactory.CreateWrapDress(
            HeightSlider.Value,
            ChestSlider.Value,
            WaistSlider.Value,
            HipSlider.Value,
            ShoulderSlider.Value,
            TorsoSlider.Value,
            _fabricKey,
            FabricWeightSlider.Value,
            FabricStretchSlider.Value,
            bend,
            friction);
    }

    private GarmentDocument BuildBundledProductionGarmentDocument()
    {
        if (_adaptiveShirtDocument is null)
        {
            throw new InvalidOperationException("The bundled production shirt is unavailable.");
        }

        GarmentDocument source = _adaptiveShirtDocument with
        {
            Fabric = GarmentDocumentFactory.CreateFabric("cotton", 180, 35, 8, 0.4)
        };
        GarmentEaseProfileDocument ease = AdaptiveShirtPatternGrader.MeasureSourceEase(source);
        double armLength = AverageDefaultDetailedMeasurement("armLengthL", "armLengthR", DefaultHeight * 0.343);
        double upperArmCircumference = AverageDefaultDetailedMeasurement("upperArmCircL", "upperArmCircR", DefaultChest * 0.32);
        double armholeDepth = AverageDefaultDetailedMeasurement("armholeDepthL", "armholeDepthR", DefaultChest * 0.225);
        double armscyeCircumference = AverageDefaultDetailedMeasurement("armscyeCircL", "armscyeCircR", DefaultChest * 0.457);
        GarmentDocument graded = AdaptiveShirtPatternGrader.Adapt(
            source,
            DefaultChest,
            DefaultWaist,
            DefaultHip,
            DefaultShoulder,
            DefaultTorso,
            armLength,
            upperArmCircumference,
            armholeDepth,
            armscyeCircumference,
            ease,
            constructionProfile: null,
            highHipCircumferenceCm: DefaultDetailedMeasurement(
                "highHipCirc",
                DefaultWaist + (DefaultHip - DefaultWaist) * 0.57)).Document;
        return PatternPhysicalDartCompiler.Compile(
            AdaptiveShirtBustShaper.Apply(
                graded,
                EstimateDefaultBustShapingProfile()).Document);
    }

    private bool IsBodyAtSourceReference()
    {
        GarmentBodyReferenceDocument? reference = _adaptiveShirtDocument?.BodyReference;
        if (reference is null || _photoCount != 0)
        {
            return false;
        }
        return NearlyEqual(ChestSlider.Value, reference.ChestCm) &&
            NearlyEqual(WaistSlider.Value, reference.WaistCm) &&
            NearlyEqual(HipSlider.Value, reference.HipCm) &&
            NearlyEqual(ShoulderSlider.Value, reference.ShoulderCm) &&
            NearlyEqual(TorsoSlider.Value, reference.TorsoCm) &&
            NearlyEqual(AverageDetailedMeasurement("armLengthL", "armLengthR", reference.ArmLengthCm), reference.ArmLengthCm) &&
            NearlyEqual(AverageDetailedMeasurement("upperArmCircL", "upperArmCircR", reference.UpperArmCircumferenceCm), reference.UpperArmCircumferenceCm) &&
            NearlyEqual(AverageDetailedMeasurement("armholeDepthL", "armholeDepthR", reference.ArmholeDepthCm), reference.ArmholeDepthCm) &&
            NearlyEqual(AverageDetailedMeasurement("armscyeCircL", "armscyeCircR", reference.ArmscyeCircumferenceCm), reference.ArmscyeCircumferenceCm);
    }

    private bool IsUnmodifiedSourcePattern()
    {
        if (_adaptiveShirtDocument is null || !IsBodyAtSourceReference())
        {
            return false;
        }
        GarmentEaseProfileDocument sourceEase = AdaptiveShirtPatternGrader.MeasureSourceEase(_adaptiveShirtDocument);
        GarmentEaseProfileDocument currentEase = CurrentGarmentEaseProfile();
        ShirtBustShapingProfileDocument shaping = CurrentShirtBustShapingProfile();
        ShirtConstructionProfileDocument? sourceConstruction =
            TryMeasureShirtConstructionProfile(_adaptiveShirtDocument);
        ShirtConstructionProfileDocument effectiveSourceConstruction =
            sourceConstruction ?? DefaultShirtConstructionProfile();
        bool constructionUnchanged =
            (!_constructionProfileEdited && !_constructionProfileRestored) ||
            ShirtConstructionPatternDrafter.AreEquivalent(
                CurrentShirtConstructionProfile(),
                effectiveSourceConstruction);
        return NearlyEqual(currentEase.ChestEaseCm, sourceEase.ChestEaseCm) &&
            NearlyEqual(currentEase.WaistEaseCm, sourceEase.WaistEaseCm) &&
            NearlyEqual(currentEase.HipEaseCm, sourceEase.HipEaseCm) &&
            NearlyEqual(currentEase.UpperArmEaseCm, sourceEase.UpperArmEaseCm) &&
            NearlyEqual(currentEase.ArmscyeEaseCm, sourceEase.ArmscyeEaseCm) &&
            constructionUnchanged &&
            string.Equals(shaping.Mode, ShirtBustShapingModes.None, StringComparison.OrdinalIgnoreCase) &&
            NearlyEqual(shaping.LeftDartIntakeCm, 0) &&
            NearlyEqual(shaping.RightDartIntakeCm, 0);
    }

    private static bool NearlyEqual(double first, double second)
        => Math.Abs(first - second) < 0.001;

    private static ShirtConstructionProfileDocument? TryMeasureShirtConstructionProfile(
        GarmentDocument document)
    {
        if (document.ShirtConstructionProfile is not null)
        {
            return document.ShirtConstructionProfile;
        }
        try
        {
            return ShirtConstructionPatternDrafter.Measure(document);
        }
        catch (InvalidOperationException)
        {
            return null;
        }
    }

    private double AverageDetailedMeasurement(string leftKey, string rightKey, double fallback)
    {
        MeasurementParameter? left = FindDetailedMeasurement(leftKey);
        MeasurementParameter? right = FindDetailedMeasurement(rightKey);
        return left is not null && right is not null
            ? (left.Value + right.Value) * 0.5
            : fallback;
    }

    private double AverageDefaultDetailedMeasurement(string leftKey, string rightKey, double fallback)
    {
        MeasurementParameter? left = FindDetailedMeasurement(leftKey);
        MeasurementParameter? right = FindDetailedMeasurement(rightKey);
        return left is not null && right is not null
            ? (left.DefaultValue + right.DefaultValue) * 0.5
            : fallback;
    }

    private double DefaultDetailedMeasurement(string key, double fallback)
        => FindDetailedMeasurement(key)?.DefaultValue ?? fallback;

    private GarmentEaseProfileDocument CurrentGarmentEaseProfile()
        => new(
            double.IsNaN(ChestEaseNumberBox.Value) ? DefaultChestEase : ChestEaseNumberBox.Value,
            double.IsNaN(WaistEaseNumberBox.Value) ? DefaultWaistEase : WaistEaseNumberBox.Value,
            double.IsNaN(HipEaseNumberBox.Value) ? DefaultHipEase : HipEaseNumberBox.Value,
            double.IsNaN(UpperArmEaseNumberBox.Value) ? DefaultUpperArmEase : UpperArmEaseNumberBox.Value)
        {
            ArmscyeEaseCm = double.IsNaN(ArmscyeEaseNumberBox.Value)
                ? DefaultArmscyeEase
                : ArmscyeEaseNumberBox.Value
        };

    private ShirtConstructionProfileDocument CurrentShirtConstructionProfile()
    {
        ShirtConstructionProfileDocument fallback = _adaptiveShirtDocument is null
            ? DefaultShirtConstructionProfile()
            : TryMeasureShirtConstructionProfile(_adaptiveShirtDocument) ?? DefaultShirtConstructionProfile();
        return new ShirtConstructionProfileDocument(
            double.IsNaN(FrontWidthShareNumberBox.Value)
                ? fallback.FrontWidthSharePercent
                : FrontWidthShareNumberBox.Value,
            double.IsNaN(NecklineWidthNumberBox.Value)
                ? fallback.NecklineWidthCm
                : NecklineWidthNumberBox.Value,
            double.IsNaN(FrontNeckDepthNumberBox.Value)
                ? fallback.FrontNeckDepthCm
                : FrontNeckDepthNumberBox.Value,
            double.IsNaN(BackNeckDepthNumberBox.Value)
                ? fallback.BackNeckDepthCm
                : BackNeckDepthNumberBox.Value,
            double.IsNaN(ShoulderLengthNumberBox.Value)
                ? fallback.ShoulderLengthCm
                : ShoulderLengthNumberBox.Value,
            double.IsNaN(ShoulderDropNumberBox.Value)
                ? fallback.ShoulderDropCm
                : ShoulderDropNumberBox.Value,
            double.IsNaN(ArmscyeDepthNumberBox.Value)
                ? fallback.ArmscyeDepthCm
                : ArmscyeDepthNumberBox.Value,
            double.IsNaN(SleeveCapHeightNumberBox.Value)
                ? fallback.SleeveCapHeightCm
                : SleeveCapHeightNumberBox.Value,
            double.IsNaN(FrontBalanceNumberBox.Value)
                ? fallback.FrontBalanceCm
                : FrontBalanceNumberBox.Value)
        {
            ArmscyeScoopCm = double.IsNaN(ArmscyeScoopNumberBox.Value)
                ? fallback.ArmscyeScoopCm
                : ArmscyeScoopNumberBox.Value,
            UnderarmExtensionCm = double.IsNaN(UnderarmExtensionNumberBox.Value)
                ? fallback.UnderarmExtensionCm
                : UnderarmExtensionNumberBox.Value
        };
    }

    private static ShirtConstructionProfileDocument DefaultShirtConstructionProfile()
        => new(52.5, 14.2, 9.1, 4.1, 11.7, 2.4, 21.8, 15.2, 0);

    private ShirtBustShapingProfileDocument EstimateCurrentBustShapingProfile()
        => AdaptiveShirtBustShaper.Estimate(
            ChestSlider.Value,
            FindDetailedMeasurement("underBust")?.Value ?? ChestSlider.Value * 0.867,
            FindDetailedMeasurement("bustSeparation")?.Value ?? ChestSlider.Value * 0.202,
            FindDetailedMeasurement("bustHeightL")?.Value ?? HeightSlider.Value * 0.154,
            FindDetailedMeasurement("bustHeightR")?.Value ?? HeightSlider.Value * 0.154,
            FindDetailedMeasurement("bustProjectionL")?.Value ?? ChestSlider.Value * 0.052,
            FindDetailedMeasurement("bustProjectionR")?.Value ?? ChestSlider.Value * 0.052);

    private ShirtBustShapingProfileDocument EstimateDefaultBustShapingProfile()
        => AdaptiveShirtBustShaper.Estimate(
            DefaultChest,
            DefaultDetailedMeasurement("underBust", DefaultChest * 0.867),
            DefaultDetailedMeasurement("bustSeparation", DefaultChest * 0.202),
            DefaultDetailedMeasurement("bustHeightL", DefaultHeight * 0.154),
            DefaultDetailedMeasurement("bustHeightR", DefaultHeight * 0.154),
            DefaultDetailedMeasurement("bustProjectionL", DefaultChest * 0.052),
            DefaultDetailedMeasurement("bustProjectionR", DefaultChest * 0.052));

    private ShirtBustShapingProfileDocument CurrentShirtBustShapingProfile()
    {
        ShirtBustShapingProfileDocument fallback = EstimateCurrentBustShapingProfile();
        string mode = (BustShapingModeComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ??
            ShirtBustShapingModes.SideDarts;
        return new ShirtBustShapingProfileDocument(
            mode,
            double.IsNaN(LeftDartIntakeNumberBox.Value)
                ? fallback.LeftDartIntakeCm
                : LeftDartIntakeNumberBox.Value,
            double.IsNaN(RightDartIntakeNumberBox.Value)
                ? fallback.RightDartIntakeCm
                : RightDartIntakeNumberBox.Value,
            double.IsNaN(BustPointSeparationNumberBox.Value)
                ? fallback.BustPointSeparationCm
                : BustPointSeparationNumberBox.Value,
            double.IsNaN(LeftBustHeightNumberBox.Value)
                ? fallback.LeftBustHeightCm
                : LeftBustHeightNumberBox.Value,
            double.IsNaN(RightBustHeightNumberBox.Value)
                ? fallback.RightBustHeightCm
                : RightBustHeightNumberBox.Value,
            double.IsNaN(LeftBustProjectionNumberBox.Value)
                ? fallback.LeftBustProjectionCm
                : LeftBustProjectionNumberBox.Value,
            double.IsNaN(RightBustProjectionNumberBox.Value)
                ? fallback.RightBustProjectionCm
                : RightBustProjectionNumberBox.Value,
            double.IsNaN(DartTipOffsetNumberBox.Value)
                ? fallback.DartTipOffsetCm
                : DartTipOffsetNumberBox.Value,
            double.IsNaN(DartMouthDropNumberBox.Value)
                ? fallback.DartMouthDropCm
                : DartMouthDropNumberBox.Value)
        {
            ShoulderDartMouthOffsetCm = double.IsNaN(ShoulderDartMouthOffsetNumberBox.Value)
                ? fallback.ShoulderDartMouthOffsetCm
                : ShoulderDartMouthOffsetNumberBox.Value,
            ShoulderDartSharePercent = double.IsNaN(ShoulderDartShareNumberBox.Value)
                ? fallback.ShoulderDartSharePercent
                : ShoulderDartShareNumberBox.Value
        };
    }

    private GarmentDocument ApplyPatternPointOffsets(GarmentDocument document)
    {
        PatternPieceDocument[] pieces = document.Pieces
            .Select(piece => piece with
            {
                Start = ApplyPatternPointOffset(piece.Id, null, PatternPointRole.Start, piece.Start),
                Boundary = piece.Boundary
                    .Select(curve => curve with
                    {
                        End = ApplyPatternPointOffset(piece.Id, curve.Id, PatternPointRole.End, curve.End),
                        Control1 = curve.Control1 is null
                            ? null
                            : ApplyPatternPointOffset(piece.Id, curve.Id, PatternPointRole.Control1, curve.Control1),
                        Control2 = curve.Control2 is null
                            ? null
                            : ApplyPatternPointOffset(piece.Id, curve.Id, PatternPointRole.Control2, curve.Control2)
                    })
                    .ToArray()
            })
            .ToArray();

        return document with { Pieces = pieces };
    }

    private GarmentDocument ApplyAssemblyOverrides(GarmentDocument document)
    {
        GarmentSeamDocument[] seams = document.Seams
            .Select(seam => _seamSideBReverseOverrides.TryGetValue(seam.Id, out bool reverse)
                ? seam with { SideB = seam.SideB with { Reverse = reverse } }
                : seam)
            .ToArray();
        GarmentClosureDocument[] closures = document.Closures
            .Select(closure => _closureStateOverrides.TryGetValue(closure.Id, out string? state)
                ? closure with { State = state }
                : closure)
            .ToArray();
        return document with { Seams = seams, Closures = closures };
    }

    private PatternPointDocument ApplyPatternPointOffset(
        string pieceId,
        string? curveId,
        PatternPointRole role,
        PatternPointDocument point)
    {
        string key = PatternPointKey(pieceId, curveId, role);
        return _patternPointOffsets.TryGetValue(key, out PatternPointDocument? offset)
            ? new(point.X + offset.X, point.Y + offset.Y)
            : point;
    }

    private static string PatternPointKey(string pieceId, string? curveId, PatternPointRole role)
        => $"{pieceId}|{curveId ?? "_"}|{role}";

    private static Dictionary<string, PatternPointDocument> ClonePatternPointOffsets(
        IReadOnlyDictionary<string, PatternPointDocument> source)
        => source.ToDictionary(
            item => item.Key,
            item => new PatternPointDocument(item.Value.X, item.Value.Y),
            StringComparer.OrdinalIgnoreCase);

    private PatternPointDocument? GetPatternPoint(GarmentDocument document, PatternPointHandle handle)
    {
        PatternPieceDocument? piece = document.Pieces.FirstOrDefault(item => item.Id == handle.PieceId);
        if (piece is null)
        {
            return null;
        }

        if (handle.Role == PatternPointRole.Start)
        {
            return piece.Start;
        }

        PatternCurveDocument? curve = piece.Boundary.FirstOrDefault(item => item.Id == handle.CurveId);
        return handle.Role switch
        {
            PatternPointRole.End => curve?.End,
            PatternPointRole.Control1 => curve?.Control1,
            PatternPointRole.Control2 => curve?.Control2,
            _ => null
        };
    }

    private PatternPointDocument? GetCurrentPatternPoint(PatternPointHandle handle)
        => GetPatternPoint(BuildCurrentGarmentDocument(), handle);

    private PatternPointDocument? GetGeneratedPatternPoint(PatternPointHandle handle)
        => GetPatternPoint(BuildStructurallyEditedBaseDocument(), handle);

    private PatternPointDocument? GetSegmentStart(GarmentDocument document, PatternPointHandle handle)
    {
        if (handle.Role != PatternPointRole.End)
        {
            return null;
        }

        PatternPieceDocument? piece = document.Pieces.FirstOrDefault(item => item.Id == handle.PieceId);
        if (piece is null)
        {
            return null;
        }

        int curveIndex = piece.Boundary
            .Select((curve, index) => new { curve.Id, Index = index })
            .FirstOrDefault(item => item.Id == handle.CurveId)?.Index ?? -1;
        if (curveIndex < 0)
        {
            return null;
        }

        return curveIndex == 0 ? piece.Start : piece.Boundary[curveIndex - 1].End;
    }

    private void SetPatternPointAbsolute(PatternPointHandle handle, PatternPointDocument point)
    {
        PatternPointDocument? generated = GetGeneratedPatternPoint(handle);
        if (generated is null)
        {
            return;
        }

        string key = PatternPointKey(handle.PieceId, handle.CurveId, handle.Role);
        PatternPointDocument offset = new(point.X - generated.X, point.Y - generated.Y);
        if (Math.Abs(offset.X) < 0.0001 && Math.Abs(offset.Y) < 0.0001)
        {
            _patternPointOffsets.Remove(key);
            return;
        }

        _patternPointOffsets[key] = offset;
    }

    private PatternEditSnapshot CapturePatternEditSnapshot()
        => new(
            ClonePatternPointOffsets(_patternPointOffsets),
            _patternStructuralEdits.ToArray(),
            new Dictionary<string, bool>(_seamSideBReverseOverrides, StringComparer.OrdinalIgnoreCase),
            new Dictionary<string, string>(_closureStateOverrides, StringComparer.OrdinalIgnoreCase));

    private void PushPatternEditUndo()
    {
        _patternUndoStack.Push(CapturePatternEditSnapshot());
        _patternRedoStack.Clear();
        UpdatePatternHistoryButtons();
    }

    private void RestorePatternEditSnapshot(PatternEditSnapshot snapshot)
    {
        _patternPointOffsets.Clear();
        foreach ((string key, PatternPointDocument offset) in snapshot.PatternPointOffsets)
        {
            _patternPointOffsets[key] = new PatternPointDocument(offset.X, offset.Y);
        }
        _patternStructuralEdits.Clear();
        _patternStructuralEdits.AddRange(snapshot.StructuralEdits);
        _seamSideBReverseOverrides.Clear();
        foreach ((string key, bool value) in snapshot.SeamSideBReverseOverrides)
        {
            _seamSideBReverseOverrides[key] = value;
        }
        _closureStateOverrides.Clear();
        foreach ((string key, string value) in snapshot.ClosureStateOverrides)
        {
            _closureStateOverrides[key] = value;
        }
    }

    private void RestorePatternPointOffsets(IReadOnlyDictionary<string, PatternPointDocument> offsets)
    {
        _patternPointOffsets.Clear();
        foreach ((string key, PatternPointDocument offset) in offsets)
        {
            _patternPointOffsets[key] = new PatternPointDocument(offset.X, offset.Y);
        }
    }

    private void UpdatePatternHistoryButtons()
    {
        UndoPatternEditButton.IsEnabled = _patternUndoStack.Count > 0;
        RedoPatternEditButton.IsEnabled = _patternRedoStack.Count > 0;
    }

    private void UpdatePatternPointInspector()
    {
        bool canEdit = EditPatternPointsButton.IsChecked == true && _selectedPatternPoint is not null;
        PatternPointInspector.Visibility = EditPatternPointsButton.IsChecked == true
            ? Visibility.Visible
            : Visibility.Collapsed;
        SelectedPatternPointXNumberBox.IsEnabled = canEdit;
        SelectedPatternPointYNumberBox.IsEnabled = canEdit;
        bool canEditSegment = canEdit && _selectedPatternPoint?.Role == PatternPointRole.End;
        SelectedPatternSegmentLengthNumberBox.IsEnabled = canEditSegment;
        SelectedPatternSegmentAngleNumberBox.IsEnabled = canEditSegment;
        SplitPatternSegmentButton.IsEnabled = canEditSegment;
        PatternCurveDocument? selectedCurve = canEditSegment && _selectedPatternPoint?.CurveId is not null
            ? BuildCurrentGarmentDocument().Pieces
                .FirstOrDefault(piece => string.Equals(piece.Id, _selectedPatternPoint.PieceId, StringComparison.OrdinalIgnoreCase))?
                .Boundary.FirstOrDefault(curve => string.Equals(curve.Id, _selectedPatternPoint.CurveId, StringComparison.OrdinalIgnoreCase))
            : null;
        ConvertPatternSegmentToCurveButton.IsEnabled = selectedCurve is not null &&
            string.Equals(selectedCurve.Kind, "line", StringComparison.OrdinalIgnoreCase);
        ConvertPatternSegmentToLineButton.IsEnabled = selectedCurve is not null &&
            string.Equals(selectedCurve.Kind, "cubic", StringComparison.OrdinalIgnoreCase);
        AddPatternNotchButton.IsEnabled = canEditSegment;
        MarkSewingEdgeButton.IsEnabled = canEditSegment;
        CompleteSewingEdgeButton.IsEnabled = canEditSegment &&
            _pendingSewingEdge is not null &&
            !(_pendingSewingEdge.PieceId.Equals(_selectedPatternPoint?.PieceId, StringComparison.OrdinalIgnoreCase) &&
                _pendingSewingEdge.CurveId.Equals(_selectedPatternPoint?.CurveId, StringComparison.OrdinalIgnoreCase));
        PendingSewingEdgeText.Text = _pendingSewingEdge is null
            ? "Free sewing: select an edge, mark it, then select its partner."
            : $"First sewing side: {_pendingSewingEdge.PieceId} / {_pendingSewingEdge.CurveId}";
        ResetPatternPointButton.IsEnabled = canEdit;
        SelectedPatternPointText.Text = _selectedPatternPoint?.DisplayName ?? "Select an anchor or curve control";

        if (!canEdit || _selectedPatternPoint is null)
        {
            return;
        }

        PatternPointDocument? point = GetCurrentPatternPoint(_selectedPatternPoint);
        if (point is null)
        {
            return;
        }

        _updatingPatternPointInspector = true;
        try
        {
            SelectedPatternPointXNumberBox.Value = Math.Round(point.X, 2);
            SelectedPatternPointYNumberBox.Value = Math.Round(point.Y, 2);
            PatternPointDocument? segmentStart = GetSegmentStart(BuildCurrentGarmentDocument(), _selectedPatternPoint);
            if (segmentStart is not null)
            {
                double deltaX = point.X - segmentStart.X;
                double deltaY = point.Y - segmentStart.Y;
                SelectedPatternSegmentLengthNumberBox.Value = Math.Round(Math.Sqrt(deltaX * deltaX + deltaY * deltaY), 2);
                SelectedPatternSegmentAngleNumberBox.Value = Math.Round(Math.Atan2(deltaY, deltaX) * 180 / Math.PI, 2);
            }
            else
            {
                SelectedPatternSegmentLengthNumberBox.Value = double.NaN;
                SelectedPatternSegmentAngleNumberBox.Value = double.NaN;
            }
        }
        finally
        {
            _updatingPatternPointInspector = false;
        }
    }

    private static PatternPointDocument SnapPatternPoint(PatternPointDocument point, bool bypassSnap)
        => bypassSnap
            ? point
            : new(
                Math.Round(point.X * 10, MidpointRounding.AwayFromZero) / 10,
                Math.Round(point.Y * 10, MidpointRounding.AwayFromZero) / 10);

    private void DrawGrid()
    {
        Brush gridBrush = ResourceBrush("PatternGridBrush");
        for (int x = 0; x <= 960; x += 40)
        {
            PatternCanvas.Children.Add(new Line
            {
                X1 = x,
                X2 = x,
                Y1 = 0,
                Y2 = 720,
                Stroke = gridBrush,
                StrokeThickness = x % 200 == 0 ? 1.2 : 0.6
            });
        }

        for (int y = 0; y <= 720; y += 40)
        {
            PatternCanvas.Children.Add(new Line
            {
                X1 = 0,
                X2 = 960,
                Y1 = y,
                Y2 = y,
                Stroke = gridBrush,
                StrokeThickness = y % 200 == 0 ? 1.2 : 0.6
            });
        }
    }

    private void DrawPiece(PatternPieceDocument piece, Brush fill)
    {
        PathGeometry geometry = BuildGeometry(piece);
        Point labelPoint = ToCanvasPoint(piece, new(piece.Layout.LabelX / PatternPixelsPerCentimeter, piece.Layout.LabelY / PatternPixelsPerCentimeter));
        Canvas holder = new()
        {
            Width = 370,
            Height = 310
        };

        bool isSelected = string.Equals(_selectedPieceId, piece.Id, StringComparison.OrdinalIgnoreCase);
        Brush stroke = isSelected ? ResourceBrush("AccentStrongBrush") : ResourceBrush("PatternPieceStrokeBrush");

        if (SeamAllowanceToggle.IsOn)
        {
            holder.Children.Add(new Microsoft.UI.Xaml.Shapes.Path
            {
                Data = CloneGeometry(geometry),
                Fill = null,
                Stroke = ResourceBrush("PatternDimensionBrush"),
                StrokeThickness = 10,
                StrokeDashArray = new DoubleCollection { 2, 2 },
                Opacity = 0.65
            });
        }

        holder.Children.Add(new Microsoft.UI.Xaml.Shapes.Path
        {
            Data = geometry,
            Fill = fill,
            Stroke = stroke,
            StrokeThickness = isSelected ? 3 : 1.7,
            Opacity = 0.96
        });

        DrawConstructionGeometry(holder, piece);

        if (isSelected && EditPatternPointsButton.IsChecked == true)
        {
            DrawPatternPointHandles(holder, piece);
        }

        if (EditAssemblyButton.IsChecked == true)
        {
            DrawAssemblyOverlays(holder, piece);
        }

        if (GrainlinesToggle.IsOn && piece.Layout.ShowGrainline)
        {
            Line grainline = new()
            {
                X1 = labelPoint.X + 42,
                X2 = labelPoint.X + 42,
                Y1 = labelPoint.Y + 32,
                Y2 = labelPoint.Y + 105,
                Stroke = ResourceBrush("PatternDimensionBrush"),
                StrokeThickness = 1.4
            };
            holder.Children.Add(grainline);

            holder.Children.Add(new Polygon
            {
                Points = new PointCollection
                {
                    new(labelPoint.X + 36, labelPoint.Y + 40),
                    new(labelPoint.X + 42, labelPoint.Y + 28),
                    new(labelPoint.X + 48, labelPoint.Y + 40)
                },
                Fill = ResourceBrush("PatternDimensionBrush")
            });

            holder.Children.Add(new Line
            {
                X1 = 8,
                X2 = 18,
                Y1 = 142,
                Y2 = 148,
                Stroke = ResourceBrush("PatternPieceStrokeBrush"),
                StrokeThickness = 2
            });
        }

        TextBlock labelBlock = new()
        {
            Text = piece.Name.ToUpperInvariant(),
            FontSize = 12,
            FontWeight = FontWeights.SemiBold,
            Foreground = ResourceBrush("PatternPieceStrokeBrush"),
            CharacterSpacing = 60
        };
        Canvas.SetLeft(labelBlock, labelPoint.X);
        Canvas.SetTop(labelBlock, labelPoint.Y);
        holder.Children.Add(labelBlock);

        Canvas.SetLeft(holder, piece.Layout.Left);
        Canvas.SetTop(holder, piece.Layout.Top);
        PatternCanvas.Children.Add(holder);
    }

    private void DrawConstructionGeometry(Canvas holder, PatternPieceDocument piece)
    {
        Brush constructionBrush = ResourceBrush("PatternDimensionBrush");
        foreach (PatternInternalPathDocument path in piece.InternalPaths)
        {
            holder.Children.Add(new Microsoft.UI.Xaml.Shapes.Path
            {
                Data = BuildInternalPathGeometry(piece, path),
                Fill = null,
                Stroke = constructionBrush,
                StrokeThickness = path.Kind == PatternInternalPathKinds.Cut ? 2 : 1.4,
                StrokeDashArray = path.Kind is PatternInternalPathKinds.Construction or PatternInternalPathKinds.Fold
                    ? new DoubleCollection { 4, 3 }
                    : null
            });
        }

        foreach (PatternDartDocument dart in piece.Darts)
        {
            PatternPointDocument firstLeg = EvaluateBoundaryPoint(
                piece,
                dart.FirstLegBoundaryCurveId,
                dart.FirstLegParameter);
            PatternPointDocument secondLeg = EvaluateBoundaryPoint(
                piece,
                dart.SecondLegBoundaryCurveId,
                dart.SecondLegParameter);
            Point firstCanvas = ToCanvasPoint(piece, firstLeg);
            Point secondCanvas = ToCanvasPoint(piece, secondLeg);
            Point apexCanvas = ToCanvasPoint(piece, dart.Apex);
            holder.Children.Add(new Line
            {
                X1 = firstCanvas.X,
                Y1 = firstCanvas.Y,
                X2 = apexCanvas.X,
                Y2 = apexCanvas.Y,
                Stroke = constructionBrush,
                StrokeThickness = 1.4,
                StrokeDashArray = new DoubleCollection { 3, 2 }
            });
            holder.Children.Add(new Line
            {
                X1 = secondCanvas.X,
                Y1 = secondCanvas.Y,
                X2 = apexCanvas.X,
                Y2 = apexCanvas.Y,
                Stroke = constructionBrush,
                StrokeThickness = 1.4,
                StrokeDashArray = new DoubleCollection { 3, 2 }
            });
        }

        foreach (PatternNotchDocument notch in piece.Notches)
        {
            DrawNotch(holder, piece, notch, constructionBrush);
        }
    }

    private static PathGeometry BuildInternalPathGeometry(
        PatternPieceDocument piece,
        PatternInternalPathDocument path)
    {
        PathFigure figure = new()
        {
            StartPoint = ToCanvasPoint(piece, path.Start),
            IsClosed = path.Closed,
            IsFilled = false
        };
        foreach (PatternCurveDocument curve in path.Segments)
        {
            PathSegment segment = curve.Kind switch
            {
                "line" => new LineSegment { Point = ToCanvasPoint(piece, curve.End) },
                "cubic" when curve.Control1 is not null && curve.Control2 is not null => new BezierSegment
                {
                    Point1 = ToCanvasPoint(piece, curve.Control1),
                    Point2 = ToCanvasPoint(piece, curve.Control2),
                    Point3 = ToCanvasPoint(piece, curve.End)
                },
                _ => throw new NotSupportedException($"Unsupported internal curve kind: {curve.Kind}")
            };
            figure.Segments.Add(segment);
        }
        PathGeometry geometry = new();
        geometry.Figures.Add(figure);
        return geometry;
    }

    private static void DrawNotch(
        Canvas holder,
        PatternPieceDocument piece,
        PatternNotchDocument notch,
        Brush brush)
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
            return;
        }
        double tangentX = tangent.X / tangentLength;
        double tangentY = tangent.Y / tangentLength;
        double normalX = -tangentY;
        double normalY = tangentX;
        double spacing = Math.Max(0.16, notch.WidthCm);
        for (int index = 0; index < notch.Count; index++)
        {
            double tangentOffset = (index - (notch.Count - 1) * 0.5) * spacing;
            PatternPointDocument start = new(
                point.X + tangentX * tangentOffset - normalX * notch.DepthCm * 0.15,
                point.Y + tangentY * tangentOffset - normalY * notch.DepthCm * 0.15);
            PatternPointDocument end = new(
                point.X + tangentX * tangentOffset + normalX * notch.DepthCm,
                point.Y + tangentY * tangentOffset + normalY * notch.DepthCm);
            Point canvasStart = ToCanvasPoint(piece, start);
            Point canvasEnd = ToCanvasPoint(piece, end);
            holder.Children.Add(new Line
            {
                X1 = canvasStart.X,
                Y1 = canvasStart.Y,
                X2 = canvasEnd.X,
                Y2 = canvasEnd.Y,
                Stroke = brush,
                StrokeThickness = 2
            });
        }
    }

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

    private void DrawPatternPointHandles(Canvas holder, PatternPieceDocument piece)
    {
        PatternPointDocument segmentStart = piece.Start;
        foreach (PatternCurveDocument curve in piece.Boundary)
        {
            if (curve.Control1 is not null)
            {
                DrawPatternControlGuide(holder, piece, segmentStart, curve.Control1);
            }

            if (curve.Control2 is not null)
            {
                DrawPatternControlGuide(holder, piece, curve.End, curve.Control2);
            }

            segmentStart = curve.End;
        }

        AddPatternPointHandle(
            holder,
            piece,
            new PatternPointHandle(piece.Id, null, PatternPointRole.Start, $"{piece.Name} start"),
            piece.Start);

        foreach (PatternCurveDocument curve in piece.Boundary)
        {
            AddPatternPointHandle(
                holder,
                piece,
                new PatternPointHandle(piece.Id, curve.Id, PatternPointRole.End, $"{curve.Id} endpoint"),
                curve.End);
            if (curve.Control1 is not null)
            {
                AddPatternPointHandle(
                    holder,
                    piece,
                    new PatternPointHandle(piece.Id, curve.Id, PatternPointRole.Control1, $"{curve.Id} first Bezier control"),
                    curve.Control1);
            }

            if (curve.Control2 is not null)
            {
                AddPatternPointHandle(
                    holder,
                    piece,
                    new PatternPointHandle(piece.Id, curve.Id, PatternPointRole.Control2, $"{curve.Id} second Bezier control"),
                    curve.Control2);
            }
        }
    }

    private void DrawAssemblyOverlays(Canvas holder, PatternPieceDocument piece)
    {
        GarmentDocument document = BuildCurrentGarmentDocument();
        Dictionary<string, ClothPanelDocument> panelsById = document.Panels
            .ToDictionary(panel => panel.Id, StringComparer.OrdinalIgnoreCase);
        List<(AssemblyRelationshipHandle Handle, string EdgeId)> relationships = [];

        foreach (GarmentSeamDocument seam in document.Seams)
        {
            AddRelationshipEdges(relationships, panelsById, piece.Id, new(seam.Id, AssemblyRelationshipKind.Seam, seam.Name), seam.SideA.PanelId, seam.SideA.EdgeIds);
            AddRelationshipEdges(relationships, panelsById, piece.Id, new(seam.Id, AssemblyRelationshipKind.Seam, seam.Name), seam.SideB.PanelId, seam.SideB.EdgeIds);
        }

        foreach (GarmentClosureDocument closure in document.Closures)
        {
            AddRelationshipEdges(relationships, panelsById, piece.Id, new(closure.Id, AssemblyRelationshipKind.Closure, closure.Name), closure.AnchorA.PanelId, closure.AnchorA.EdgeIds);
            AddRelationshipEdges(relationships, panelsById, piece.Id, new(closure.Id, AssemblyRelationshipKind.Closure, closure.Name), closure.AnchorB.PanelId, closure.AnchorB.EdgeIds);
        }

        foreach ((AssemblyRelationshipHandle handle, string edgeId) in relationships
            .DistinctBy(item => $"{item.Handle.Kind}|{item.Handle.Id}|{item.EdgeId}", StringComparer.OrdinalIgnoreCase))
        {
            PatternCurveDocument? curve = piece.Boundary.FirstOrDefault(item =>
                string.Equals(item.Id, edgeId, StringComparison.OrdinalIgnoreCase));
            if (curve is null)
            {
                continue;
            }

            bool selected = _selectedAssemblyRelationship is not null &&
                _selectedAssemblyRelationship.Kind == handle.Kind &&
                string.Equals(_selectedAssemblyRelationship.Id, handle.Id, StringComparison.OrdinalIgnoreCase);
            SolidColorBrush color = new(handle.Kind == AssemblyRelationshipKind.Closure
                ? Colors.Gold
                : Colors.DeepSkyBlue);
            Microsoft.UI.Xaml.Shapes.Path overlay = new()
            {
                Data = BuildCurveGeometry(piece, curve),
                Fill = null,
                Stroke = color,
                StrokeThickness = selected ? 8 : 5,
                Opacity = selected ? 1 : 0.62,
                Tag = handle
            };
            if (handle.Kind == AssemblyRelationshipKind.Closure)
            {
                overlay.StrokeDashArray = new DoubleCollection { 2, 1.3 };
            }
            ToolTipService.SetToolTip(overlay, $"{handle.DisplayName}: {edgeId}");
            overlay.PointerPressed += OnAssemblyOverlayPointerPressed;
            holder.Children.Add(overlay);
        }
    }

    private static void AddRelationshipEdges(
        ICollection<(AssemblyRelationshipHandle Handle, string EdgeId)> relationships,
        IReadOnlyDictionary<string, ClothPanelDocument> panelsById,
        string pieceId,
        AssemblyRelationshipHandle handle,
        string panelId,
        IEnumerable<string> edgeIds)
    {
        if (!panelsById.TryGetValue(panelId, out ClothPanelDocument? panel) ||
            !string.Equals(panel.PieceId, pieceId, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        foreach (string edgeId in edgeIds)
        {
            relationships.Add((handle, edgeId));
        }
    }

    private static PathGeometry BuildCurveGeometry(PatternPieceDocument piece, PatternCurveDocument curve)
    {
        int curveIndex = piece.Boundary
            .Select((candidate, index) => new { candidate.Id, Index = index })
            .First(item => string.Equals(item.Id, curve.Id, StringComparison.OrdinalIgnoreCase))
            .Index;
        PatternPointDocument start = curveIndex == 0
            ? piece.Start
            : piece.Boundary[curveIndex - 1].End;
        PathFigure figure = new()
        {
            StartPoint = ToCanvasPoint(piece, start),
            IsClosed = false,
            IsFilled = false
        };
        PathSegment segment = curve.Kind switch
        {
            "line" => new LineSegment { Point = ToCanvasPoint(piece, curve.End) },
            "cubic" when curve.Control1 is not null && curve.Control2 is not null => new BezierSegment
            {
                Point1 = ToCanvasPoint(piece, curve.Control1),
                Point2 = ToCanvasPoint(piece, curve.Control2),
                Point3 = ToCanvasPoint(piece, curve.End)
            },
            _ => throw new NotSupportedException($"Unsupported pattern curve kind: {curve.Kind}")
        };
        figure.Segments.Add(segment);
        PathGeometry geometry = new();
        geometry.Figures.Add(figure);
        return geometry;
    }

    private void OnAssemblyOverlayPointerPressed(object sender, PointerRoutedEventArgs e)
    {
        if (sender is not Microsoft.UI.Xaml.Shapes.Path { Tag: AssemblyRelationshipHandle handle })
        {
            return;
        }

        _selectedAssemblyRelationship = handle;
        SelectAssemblyRelationshipInComboBox(handle);
        RenderPattern();
        UpdateAssemblyInspector(false);
        ShowStatus("Assembly relationship selected", $"{handle.DisplayName} is active in the authoritative seam graph.", InfoBarSeverity.Informational);
        e.Handled = true;
    }

    private void DrawPatternControlGuide(
        Canvas holder,
        PatternPieceDocument piece,
        PatternPointDocument anchor,
        PatternPointDocument control)
    {
        Point start = ToCanvasPoint(piece, anchor);
        Point end = ToCanvasPoint(piece, control);
        holder.Children.Add(new Line
        {
            X1 = start.X,
            Y1 = start.Y,
            X2 = end.X,
            Y2 = end.Y,
            Stroke = ResourceBrush("PatternDimensionBrush"),
            StrokeThickness = 1,
            StrokeDashArray = new DoubleCollection { 3, 3 },
            Opacity = 0.8
        });
    }

    private void AddPatternPointHandle(
        Canvas holder,
        PatternPieceDocument piece,
        PatternPointHandle handle,
        PatternPointDocument point)
    {
        bool isControl = handle.Role is PatternPointRole.Control1 or PatternPointRole.Control2;
        double size = isControl ? 10 : 14;
        Point canvasPoint = ToCanvasPoint(piece, point);
        Ellipse visual = new()
        {
            Width = size,
            Height = size,
            Fill = isControl ? ResourceBrush("PatternDimensionBrush") : ResourceBrush("AccentStrongBrush"),
            Stroke = ResourceBrush("PatternCanvasBackgroundBrush"),
            StrokeThickness = 2,
            Tag = handle,
            CanDrag = false
        };
        ToolTipService.SetToolTip(visual, handle.DisplayName);
        visual.PointerPressed += OnPatternPointPointerPressed;
        visual.PointerMoved += OnPatternPointPointerMoved;
        visual.PointerReleased += OnPatternPointPointerReleased;
        visual.PointerCanceled += OnPatternPointPointerCanceled;
        Canvas.SetLeft(visual, canvasPoint.X - size / 2);
        Canvas.SetTop(visual, canvasPoint.Y - size / 2);
        holder.Children.Add(visual);
    }

    private void OnEditPatternPointsClicked(object sender, RoutedEventArgs e)
    {
        if (EditPatternPointsButton.IsChecked == true)
        {
            EditAssemblyButton.IsChecked = false;
            _selectedAssemblyRelationship = null;
        }
        if (EditPatternPointsButton.IsChecked != true)
        {
            _selectedPatternPoint = null;
        }

        RenderPattern();
        UpdatePatternPointInspector();
        UpdateAssemblyInspector();
        ShowStatus(
            EditPatternPointsButton.IsChecked == true ? "Pattern point editing enabled" : "Pattern point editing disabled",
            EditPatternPointsButton.IsChecked == true
                ? "Select or drag an anchor or Bézier control on the active piece."
                : "The generated pattern remains synchronized with body measurements.",
            InfoBarSeverity.Informational);
    }

    private void OnEditAssemblyClicked(object sender, RoutedEventArgs e)
    {
        if (EditAssemblyButton.IsChecked == true)
        {
            EditPatternPointsButton.IsChecked = false;
            _selectedPatternPoint = null;
            GarmentDocument document = BuildCurrentGarmentDocument();
            _selectedAssemblyRelationship ??= document.Seams.Count > 0
                ? new(document.Seams[0].Id, AssemblyRelationshipKind.Seam, document.Seams[0].Name)
                : document.Closures.Count > 0
                    ? new(document.Closures[0].Id, AssemblyRelationshipKind.Closure, document.Closures[0].Name)
                    : null;
        }
        else
        {
            _selectedAssemblyRelationship = null;
        }

        RenderPattern();
        UpdatePatternPointInspector();
        UpdateAssemblyInspector();
        ShowStatus(
            EditAssemblyButton.IsChecked == true ? "Assembly editing enabled" : "Assembly editing disabled",
            EditAssemblyButton.IsChecked == true
                ? "Permanent seams are cyan and temporary closures are gold. Select a colored edge to inspect or edit its relationship."
                : "The seam graph remains part of the saved garment document.",
            InfoBarSeverity.Informational);
    }

    private void UpdateAssemblyInspector(bool rebuildRelationships = true)
    {
        bool editing = EditAssemblyButton.IsChecked == true;
        AssemblyInspector.Visibility = editing ? Visibility.Visible : Visibility.Collapsed;
        PatternViewbox.Margin = editing
            ? new Thickness(12, 12, 324, 12)
            : new Thickness(12);
        if (!editing)
        {
            return;
        }

        GarmentDocument document = BuildCurrentGarmentDocument();
        bool selectedRelationshipExists = _selectedAssemblyRelationship is not null &&
            (_selectedAssemblyRelationship.Kind == AssemblyRelationshipKind.Seam
                ? document.Seams.Any(seam => string.Equals(seam.Id, _selectedAssemblyRelationship.Id, StringComparison.OrdinalIgnoreCase))
                : document.Closures.Any(closure => string.Equals(closure.Id, _selectedAssemblyRelationship.Id, StringComparison.OrdinalIgnoreCase)));
        if (!selectedRelationshipExists)
        {
            _selectedAssemblyRelationship = document.Seams.Count > 0
                ? new(document.Seams[0].Id, AssemblyRelationshipKind.Seam, document.Seams[0].Name)
                : document.Closures.Count > 0
                    ? new(document.Closures[0].Id, AssemblyRelationshipKind.Closure, document.Closures[0].Name)
                    : null;
        }
        AssemblySummaryText.Text = $"{document.Seams.Count} permanent seams · {document.Closures.Count} closures";
        _updatingAssemblyInspector = true;
        try
        {
            if (rebuildRelationships)
            {
                AssemblyRelationshipComboBox.Items.Clear();
                foreach (GarmentSeamDocument seam in document.Seams)
                {
                    AssemblyRelationshipComboBox.Items.Add(new ComboBoxItem
                    {
                        Content = $"{seam.Name} · seam",
                        Tag = new AssemblyRelationshipHandle(seam.Id, AssemblyRelationshipKind.Seam, seam.Name)
                    });
                }
                foreach (GarmentClosureDocument closure in document.Closures)
                {
                    AssemblyRelationshipComboBox.Items.Add(new ComboBoxItem
                    {
                        Content = $"{closure.Name} · {closure.Kind}",
                        Tag = new AssemblyRelationshipHandle(closure.Id, AssemblyRelationshipKind.Closure, closure.Name)
                    });
                }
                if (_selectedAssemblyRelationship is not null)
                {
                    SelectAssemblyRelationshipInComboBox(_selectedAssemblyRelationship);
                }
            }

            GarmentSeamDocument? selectedSeam = _selectedAssemblyRelationship?.Kind == AssemblyRelationshipKind.Seam
                ? document.Seams.FirstOrDefault(seam => string.Equals(seam.Id, _selectedAssemblyRelationship.Id, StringComparison.OrdinalIgnoreCase))
                : null;
            GarmentClosureDocument? selectedClosure = _selectedAssemblyRelationship?.Kind == AssemblyRelationshipKind.Closure
                ? document.Closures.FirstOrDefault(closure => string.Equals(closure.Id, _selectedAssemblyRelationship.Id, StringComparison.OrdinalIgnoreCase))
                : null;

            ReverseSeamSideBToggle.IsEnabled = selectedSeam is not null;
            ReverseSeamSideBToggle.IsOn = selectedSeam?.SideB.Reverse ?? false;
            ClosureStateToggle.IsEnabled = selectedClosure is not null;
            ClosureStateToggle.IsOn = selectedClosure is not null &&
                string.Equals(selectedClosure.State, GarmentClosureStates.Closed, StringComparison.OrdinalIgnoreCase);
            ResetAssemblyEditButton.IsEnabled = _selectedAssemblyRelationship is not null &&
                (_seamSideBReverseOverrides.ContainsKey(_selectedAssemblyRelationship.Id) ||
                 _closureStateOverrides.ContainsKey(_selectedAssemblyRelationship.Id));

            if (selectedSeam is not null)
            {
                AssemblyRelationshipTypeText.Text = $"Permanent construction seam · {selectedSeam.AllowanceCm:0.##} cm allowance · {selectedSeam.Strength:P0} strength";
                AssemblyRelationshipLocationText.Text = $"{selectedSeam.SideA.PanelId}: {string.Join(", ", selectedSeam.SideA.EdgeIds)} ↔ {selectedSeam.SideB.PanelId}: {string.Join(", ", selectedSeam.SideB.EdgeIds)}";
                UpdateSeamFitDiagnostics(document, selectedSeam);
            }
            else if (selectedClosure is not null)
            {
                AssemblySeamFitCard.Visibility = Visibility.Collapsed;
                AssemblyRelationshipTypeText.Text = $"Temporary {selectedClosure.Kind} · {selectedClosure.ConstraintCount} constraint · {selectedClosure.State}";
                AssemblyRelationshipLocationText.Text = $"{selectedClosure.AnchorA.PanelId}: {string.Join(", ", selectedClosure.AnchorA.EdgeIds)} ↔ {selectedClosure.AnchorB.PanelId}: {string.Join(", ", selectedClosure.AnchorB.EdgeIds)}";
            }
            else
            {
                AssemblySeamFitCard.Visibility = Visibility.Collapsed;
                AssemblyRelationshipTypeText.Text = "Select a colored edge or relationship";
                AssemblyRelationshipLocationText.Text = "Permanent seams are cyan. Closures are gold.";
            }
        }
        finally
        {
            _updatingAssemblyInspector = false;
        }
    }

    private void UpdateSeamFitDiagnostics(
        GarmentDocument document,
        GarmentSeamDocument selectedSeam)
    {
        AssemblySeamFitCard.Visibility = Visibility.Visible;
        try
        {
            CompiledPatternSeam compiled = PatternTopologyCompiler
                .Compile(document)
                .Seams
                .Single(seam => string.Equals(
                    seam.Id,
                    selectedSeam.Id,
                    StringComparison.OrdinalIgnoreCase));
            AssemblySeamLengthText.Text =
                $"Side A {compiled.LengthACm:0.00} cm · Side B {compiled.LengthBCm:0.00} cm";
            string classification = compiled.LengthMismatchRatio switch
            {
                <= 0.005 => "Matched",
                <= 0.03 => "Controlled ease",
                _ => "Mismatch requires correction"
            };
            AssemblySeamMismatchText.Text =
                $"{classification}: {compiled.LengthMismatchCm:0.00} cm · {compiled.LengthMismatchRatio:P1}";
        }
        catch (Exception exception) when (exception is PatternTopologyException or InvalidOperationException)
        {
            AssemblySeamLengthText.Text = "Sewn lengths unavailable";
            AssemblySeamMismatchText.Text =
                $"Resolve the pattern topology first: {exception.Message}";
        }
    }

    private void SelectAssemblyRelationshipInComboBox(AssemblyRelationshipHandle handle)
    {
        for (int index = 0; index < AssemblyRelationshipComboBox.Items.Count; index++)
        {
            if (AssemblyRelationshipComboBox.Items[index] is ComboBoxItem { Tag: AssemblyRelationshipHandle item } &&
                item.Kind == handle.Kind &&
                string.Equals(item.Id, handle.Id, StringComparison.OrdinalIgnoreCase))
            {
                AssemblyRelationshipComboBox.SelectedIndex = index;
                return;
            }
        }
    }

    private void OnAssemblyRelationshipSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_updatingAssemblyInspector ||
            AssemblyRelationshipComboBox.SelectedItem is not ComboBoxItem { Tag: AssemblyRelationshipHandle handle })
        {
            return;
        }

        _selectedAssemblyRelationship = handle;
        RenderPattern();
        UpdateAssemblyInspector(false);
    }

    private void OnReverseSeamSideBToggled(object sender, RoutedEventArgs e)
    {
        if (_updatingAssemblyInspector ||
            _selectedAssemblyRelationship is not { Kind: AssemblyRelationshipKind.Seam } handle)
        {
            return;
        }

        GarmentSeamDocument? generated = BuildBaseGarmentDocument().Seams.FirstOrDefault(seam =>
            string.Equals(seam.Id, handle.Id, StringComparison.OrdinalIgnoreCase));
        if (generated is null)
        {
            return;
        }

        bool next = ReverseSeamSideBToggle.IsOn;
        bool current = BuildCurrentGarmentDocument().Seams.First(seam =>
            string.Equals(seam.Id, handle.Id, StringComparison.OrdinalIgnoreCase)).SideB.Reverse;
        if (current == next)
        {
            return;
        }

        PushPatternEditUndo();
        if (next == generated.SideB.Reverse)
        {
            _seamSideBReverseOverrides.Remove(handle.Id);
        }
        else
        {
            _seamSideBReverseOverrides[handle.Id] = next;
        }
        RenderPattern();
        UpdateAssemblyInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus("Seam direction updated", $"{handle.DisplayName} side B direction is now {(next ? "reversed" : "forward")}.", InfoBarSeverity.Success);
    }

    private void OnClosureStateToggled(object sender, RoutedEventArgs e)
    {
        if (_updatingAssemblyInspector ||
            _selectedAssemblyRelationship is not { Kind: AssemblyRelationshipKind.Closure } handle)
        {
            return;
        }

        GarmentClosureDocument? generated = BuildBaseGarmentDocument().Closures.FirstOrDefault(closure =>
            string.Equals(closure.Id, handle.Id, StringComparison.OrdinalIgnoreCase));
        if (generated is null)
        {
            return;
        }

        string next = ClosureStateToggle.IsOn ? GarmentClosureStates.Closed : GarmentClosureStates.Open;
        string current = BuildCurrentGarmentDocument().Closures.First(closure =>
            string.Equals(closure.Id, handle.Id, StringComparison.OrdinalIgnoreCase)).State;
        if (string.Equals(current, next, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        PushPatternEditUndo();
        if (string.Equals(next, generated.State, StringComparison.OrdinalIgnoreCase))
        {
            _closureStateOverrides.Remove(handle.Id);
        }
        else
        {
            _closureStateOverrides[handle.Id] = next;
        }
        RenderPattern();
        UpdateAssemblyInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus("Closure state updated", $"{handle.DisplayName} is now {next} in the garment document.", InfoBarSeverity.Success);
    }

    private void OnResetAssemblyEditClicked(object sender, RoutedEventArgs e)
    {
        if (_selectedAssemblyRelationship is null ||
            (!_seamSideBReverseOverrides.ContainsKey(_selectedAssemblyRelationship.Id) &&
             !_closureStateOverrides.ContainsKey(_selectedAssemblyRelationship.Id)))
        {
            return;
        }

        PushPatternEditUndo();
        _seamSideBReverseOverrides.Remove(_selectedAssemblyRelationship.Id);
        _closureStateOverrides.Remove(_selectedAssemblyRelationship.Id);
        RenderPattern();
        UpdateAssemblyInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus("Assembly relationship reset", "The selected relationship now follows its generated pattern definition.", InfoBarSeverity.Success);
    }

    private void OnPatternPointPointerPressed(object sender, PointerRoutedEventArgs e)
    {
        if (sender is not Ellipse visual || visual.Tag is not PatternPointHandle handle)
        {
            return;
        }

        PatternPointDocument? current = GetCurrentPatternPoint(handle);
        if (current is null)
        {
            return;
        }

        _selectedPatternPoint = handle;
        _draggingPatternPoint = handle;
        _dragStartPoint = current;
        _dragPreviewPoint = current;
        _dragStartPointer = e.GetCurrentPoint(PatternCanvas).Position;
        _draggingHandleVisual = visual;
        visual.CapturePointer(e.Pointer);
        UpdatePatternPointInspector();
        e.Handled = true;
    }

    private void OnPatternPointPointerMoved(object sender, PointerRoutedEventArgs e)
    {
        if (_draggingPatternPoint is null || _dragStartPoint is null || _draggingHandleVisual is null)
        {
            return;
        }

        GarmentDocument document = BuildCurrentGarmentDocument();
        PatternPieceDocument? piece = document.Pieces.FirstOrDefault(item => item.Id == _draggingPatternPoint.PieceId);
        if (piece is null)
        {
            return;
        }

        Point pointer = e.GetCurrentPoint(PatternCanvas).Position;
        PatternPointDocument candidate = new(
            _dragStartPoint.X + (pointer.X - _dragStartPointer.X) / (piece.ScaleX * PatternPixelsPerCentimeter),
            _dragStartPoint.Y + (pointer.Y - _dragStartPointer.Y) / (piece.ScaleY * PatternPixelsPerCentimeter));
        _dragPreviewPoint = SnapPatternPoint(
            candidate,
            e.KeyModifiers.HasFlag(Windows.System.VirtualKeyModifiers.Shift));

        Point localPoint = ToCanvasPoint(piece, _dragPreviewPoint);
        Canvas.SetLeft(_draggingHandleVisual, localPoint.X - _draggingHandleVisual.Width / 2);
        Canvas.SetTop(_draggingHandleVisual, localPoint.Y - _draggingHandleVisual.Height / 2);

        _updatingPatternPointInspector = true;
        try
        {
            SelectedPatternPointXNumberBox.Value = Math.Round(_dragPreviewPoint.X, 2);
            SelectedPatternPointYNumberBox.Value = Math.Round(_dragPreviewPoint.Y, 2);
        }
        finally
        {
            _updatingPatternPointInspector = false;
        }

        e.Handled = true;
    }

    private void OnPatternPointPointerReleased(object sender, PointerRoutedEventArgs e)
    {
        if (_draggingPatternPoint is null || _dragStartPoint is null || _dragPreviewPoint is null)
        {
            return;
        }

        PatternPointHandle handle = _draggingPatternPoint;
        bool changed = Math.Abs(_dragPreviewPoint.X - _dragStartPoint.X) > 0.0001 ||
            Math.Abs(_dragPreviewPoint.Y - _dragStartPoint.Y) > 0.0001;
        if (changed)
        {
            PushPatternEditUndo();
            SetPatternPointAbsolute(handle, _dragPreviewPoint);
        }

        if (sender is UIElement visual)
        {
            visual.ReleasePointerCapture(e.Pointer);
        }

        ClearPatternPointDrag();
        RenderPattern();
        UpdatePatternPointInspector();
        if (changed)
        {
            _ = UpdateDrapeViewportAsync();
            ShowStatus("Pattern geometry updated", $"{handle.DisplayName} was moved and synchronized with the 3D garment document.", InfoBarSeverity.Success);
        }

        e.Handled = true;
    }

    private void OnPatternPointPointerCanceled(object sender, PointerRoutedEventArgs e)
    {
        ClearPatternPointDrag();
        RenderPattern();
        UpdatePatternPointInspector();
        e.Handled = true;
    }

    private void ClearPatternPointDrag()
    {
        _draggingPatternPoint = null;
        _dragStartPoint = null;
        _dragPreviewPoint = null;
        _draggingHandleVisual = null;
    }

    private void OnSelectedPatternPointValueChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_updatingPatternPointInspector || _selectedPatternPoint is null ||
            double.IsNaN(SelectedPatternPointXNumberBox.Value) ||
            double.IsNaN(SelectedPatternPointYNumberBox.Value))
        {
            return;
        }

        PatternPointDocument? current = GetCurrentPatternPoint(_selectedPatternPoint);
        PatternPointDocument next = new(
            SelectedPatternPointXNumberBox.Value,
            SelectedPatternPointYNumberBox.Value);
        if (current is null ||
            (Math.Abs(current.X - next.X) < 0.0001 && Math.Abs(current.Y - next.Y) < 0.0001))
        {
            return;
        }

        PushPatternEditUndo();
        SetPatternPointAbsolute(_selectedPatternPoint, next);
        RenderPattern();
        UpdatePatternPointInspector();
        _ = UpdateDrapeViewportAsync();
    }

    private void OnSelectedPatternSegmentValueChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_updatingPatternPointInspector || _selectedPatternPoint is null ||
            _selectedPatternPoint.Role != PatternPointRole.End ||
            double.IsNaN(SelectedPatternSegmentLengthNumberBox.Value) ||
            double.IsNaN(SelectedPatternSegmentAngleNumberBox.Value))
        {
            return;
        }

        GarmentDocument currentDocument = BuildCurrentGarmentDocument();
        PatternPointDocument? current = GetPatternPoint(currentDocument, _selectedPatternPoint);
        PatternPointDocument? segmentStart = GetSegmentStart(currentDocument, _selectedPatternPoint);
        if (current is null || segmentStart is null)
        {
            return;
        }

        double angleRadians = SelectedPatternSegmentAngleNumberBox.Value * Math.PI / 180;
        double length = SelectedPatternSegmentLengthNumberBox.Value;
        PatternPointDocument next = new(
            segmentStart.X + Math.Cos(angleRadians) * length,
            segmentStart.Y + Math.Sin(angleRadians) * length);
        if (Math.Abs(current.X - next.X) < 0.0001 && Math.Abs(current.Y - next.Y) < 0.0001)
        {
            return;
        }

        PushPatternEditUndo();
        SetPatternPointAbsolute(_selectedPatternPoint, next);
        RenderPattern();
        UpdatePatternPointInspector();
        _ = UpdateDrapeViewportAsync();
    }

    private void OnResetPatternPointClicked(object sender, RoutedEventArgs e)
    {
        if (_selectedPatternPoint is null)
        {
            return;
        }

        string key = PatternPointKey(
            _selectedPatternPoint.PieceId,
            _selectedPatternPoint.CurveId,
            _selectedPatternPoint.Role);
        if (!_patternPointOffsets.ContainsKey(key))
        {
            return;
        }

        PushPatternEditUndo();
        _patternPointOffsets.Remove(key);
        RenderPattern();
        UpdatePatternPointInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus("Pattern point reset", "The selected point now follows its generated measurement-driven position.", InfoBarSeverity.Success);
    }

    private void OnSplitPatternSegmentClicked(object sender, RoutedEventArgs e)
    {
        if (_selectedPatternPoint is not { Role: PatternPointRole.End, CurveId: not null } selected)
        {
            return;
        }

        GarmentDocument currentBeforeSplit = BuildCurrentGarmentDocument();
        PushPatternEditUndo();
        PatternBoundarySplitCommand command = new(selected.PieceId, selected.CurveId, 0.5);
        PatternBoundarySplitResult currentSplit = PatternStructuralEditor.SplitBoundarySegment(
            currentBeforeSplit,
            command.PieceId,
            command.CurveId,
            command.Parameter);
        _patternStructuralEdits.Add(command);
        GarmentDocument generatedAfterSplit = BuildStructurallyEditedBaseDocument();

        foreach (PatternBoundarySplitMapping mapping in currentSplit.Mappings)
        {
            foreach (PatternPointRole role in Enum.GetValues<PatternPointRole>())
            {
                _patternPointOffsets.Remove(PatternPointKey(mapping.PieceId, mapping.OriginalCurveId, role));
            }

            PreserveSplitCurveOffsets(currentSplit.Document, generatedAfterSplit, mapping.PieceId, mapping.FirstCurveId);
            PreserveSplitCurveOffsets(currentSplit.Document, generatedAfterSplit, mapping.PieceId, mapping.SecondCurveId);
        }

        _selectedPatternPoint = new PatternPointHandle(
            selected.PieceId,
            currentSplit.SecondCurveId,
            PatternPointRole.End,
            $"{currentSplit.SecondCurveId} endpoint");
        RenderPattern();
        UpdatePatternPointInspector();
        UpdateAssemblyInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus(
            "Pattern segment split",
            currentSplit.Mappings.Count > 1
                ? "The curve and its sewn partner were split without changing either shape. Seam, pin, and closure references were preserved."
                : "The curve was split without changing its shape. Pin and closure references were preserved.",
            InfoBarSeverity.Success);
    }

    private void OnConvertPatternSegmentToCurveClicked(object sender, RoutedEventArgs e)
        => SetSelectedBoundaryCurveKind("cubic");

    private void OnConvertPatternSegmentToLineClicked(object sender, RoutedEventArgs e)
        => SetSelectedBoundaryCurveKind("line");

    private void SetSelectedBoundaryCurveKind(string kind)
    {
        if (_selectedPatternPoint is not { Role: PatternPointRole.End, CurveId: not null } selected)
        {
            return;
        }
        GarmentDocument current = BuildCurrentGarmentDocument();
        PatternCurveDocument? curve = current.Pieces
            .FirstOrDefault(piece => string.Equals(piece.Id, selected.PieceId, StringComparison.OrdinalIgnoreCase))?
            .Boundary.FirstOrDefault(item => string.Equals(item.Id, selected.CurveId, StringComparison.OrdinalIgnoreCase));
        if (curve is null || string.Equals(curve.Kind, kind, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }
        PushPatternEditUndo();
        _patternPointOffsets.Remove(PatternPointKey(selected.PieceId, selected.CurveId, PatternPointRole.Control1));
        _patternPointOffsets.Remove(PatternPointKey(selected.PieceId, selected.CurveId, PatternPointRole.Control2));
        _patternStructuralEdits.Add(new PatternBoundaryCurveKindCommand(selected.PieceId, selected.CurveId, kind));
        RefreshPatternWorkspaceMetadata();
        RenderPattern();
        UpdatePatternPointInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus(
            kind == "cubic" ? "Segment converted to curve" : "Segment converted to line",
            kind == "cubic"
                ? $"{selected.CurveId} now has two directly editable Bezier controls while keeping its edge identity and sewing references."
                : $"{selected.CurveId} is now a straight segment while keeping its edge identity and sewing references.",
            InfoBarSeverity.Success);
    }

    private void OnAddPatternNotchClicked(object sender, RoutedEventArgs e)
    {
        if (_selectedPatternPoint is not { Role: PatternPointRole.End, CurveId: not null } selected)
        {
            return;
        }

        PushPatternEditUndo();
        _patternStructuralEdits.Add(new PatternNotchCommand(
            selected.PieceId,
            selected.CurveId,
            0.5));
        RenderPattern();
        UpdatePatternPointInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus(
            "Construction notch added",
            "The notch is anchored to the selected curve and will follow later curve edits and exact segment splits.",
            InfoBarSeverity.Success);
    }

    private void OnMarkSewingEdgeClicked(object sender, RoutedEventArgs e)
    {
        if (_selectedPatternPoint is not { Role: PatternPointRole.End, CurveId: not null } selected)
        {
            return;
        }
        _pendingSewingEdge = new PatternEdgeHandle(selected.PieceId, selected.CurveId);
        UpdatePatternPointInspector();
        ShowStatus(
            "First sewing edge marked",
            "Select the partner edge and choose Sew edges. The relationship remains editable in Assembly mode.",
            InfoBarSeverity.Informational);
    }

    private void OnCompleteSewingEdgeClicked(object sender, RoutedEventArgs e)
    {
        if (_pendingSewingEdge is null ||
            _selectedPatternPoint is not { Role: PatternPointRole.End, CurveId: not null } selected)
        {
            return;
        }
        PatternEdgeHandle second = new(selected.PieceId, selected.CurveId);
        if (_pendingSewingEdge == second)
        {
            return;
        }
        GarmentDocument current = BuildCurrentGarmentDocument();
        ClothPanelDocument firstPanel = current.Panels.First(panel =>
            string.Equals(panel.PieceId, _pendingSewingEdge.PieceId, StringComparison.OrdinalIgnoreCase));
        ClothPanelDocument secondPanel = current.Panels.First(panel =>
            string.Equals(panel.PieceId, second.PieceId, StringComparison.OrdinalIgnoreCase));
        HashSet<string> seamIds = current.Seams.Select(seam => seam.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        string seamId = UniqueDocumentId(seamIds, $"seam-{_pendingSewingEdge.PieceId}-{second.PieceId}");
        double allowance = 0.5 * (
            current.Pieces.First(piece => string.Equals(piece.Id, _pendingSewingEdge.PieceId, StringComparison.OrdinalIgnoreCase)).SeamAllowanceCm +
            current.Pieces.First(piece => string.Equals(piece.Id, second.PieceId, StringComparison.OrdinalIgnoreCase)).SeamAllowanceCm);
        PatternSeamCreateCommand command = new(new GarmentSeamDocument(
            seamId,
            $"{_pendingSewingEdge.PieceId} to {second.PieceId}",
            new SeamSideDocument(firstPanel.Id, [_pendingSewingEdge.CurveId]),
            new SeamSideDocument(secondPanel.Id, [second.CurveId]),
            allowance));
        PushPatternEditUndo();
        _patternStructuralEdits.Add(command);
        _pendingSewingEdge = null;
        RenderPattern();
        RefreshPatternWorkspaceMetadata();
        UpdatePatternPointInspector();
        UpdateAssemblyInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus(
            "Pattern edges sewn",
            "The new seam is part of the garment assembly graph and will export to simulation.",
            InfoBarSeverity.Success);
    }

    private void PreserveSplitCurveOffsets(
        GarmentDocument currentDocument,
        GarmentDocument generatedDocument,
        string pieceId,
        string curveId)
    {
        PatternPieceDocument currentPiece = currentDocument.Pieces.First(piece =>
            string.Equals(piece.Id, pieceId, StringComparison.OrdinalIgnoreCase));
        PatternPieceDocument generatedPiece = generatedDocument.Pieces.First(piece =>
            string.Equals(piece.Id, pieceId, StringComparison.OrdinalIgnoreCase));
        PatternCurveDocument currentCurve = currentPiece.Boundary.First(curve =>
            string.Equals(curve.Id, curveId, StringComparison.OrdinalIgnoreCase));
        PatternCurveDocument generatedCurve = generatedPiece.Boundary.First(curve =>
            string.Equals(curve.Id, curveId, StringComparison.OrdinalIgnoreCase));

        SetPatternPointOffset(pieceId, curveId, PatternPointRole.End, currentCurve.End, generatedCurve.End);
        if (currentCurve.Control1 is not null && generatedCurve.Control1 is not null)
        {
            SetPatternPointOffset(pieceId, curveId, PatternPointRole.Control1, currentCurve.Control1, generatedCurve.Control1);
        }
        if (currentCurve.Control2 is not null && generatedCurve.Control2 is not null)
        {
            SetPatternPointOffset(pieceId, curveId, PatternPointRole.Control2, currentCurve.Control2, generatedCurve.Control2);
        }
    }

    private void SetPatternPointOffset(
        string pieceId,
        string curveId,
        PatternPointRole role,
        PatternPointDocument current,
        PatternPointDocument generated)
    {
        string key = PatternPointKey(pieceId, curveId, role);
        PatternPointDocument offset = new(current.X - generated.X, current.Y - generated.Y);
        if (Math.Abs(offset.X) < 0.0001 && Math.Abs(offset.Y) < 0.0001)
        {
            _patternPointOffsets.Remove(key);
        }
        else
        {
            _patternPointOffsets[key] = offset;
        }
    }

    private void OnUndoPatternEditClicked(object sender, RoutedEventArgs e)
    {
        if (_patternUndoStack.Count == 0)
        {
            return;
        }

        _patternRedoStack.Push(CapturePatternEditSnapshot());
        RestorePatternEditSnapshot(_patternUndoStack.Pop());
        UpdatePatternHistoryButtons();
        RenderPattern();
        UpdatePatternPointInspector();
        RefreshAssemblyInspectorAfterHistoryChange();
        _ = UpdateDrapeViewportAsync();
        ShowStatus("Pattern edit undone", "The previous pattern geometry state was restored.", InfoBarSeverity.Informational);
    }

    private void OnRedoPatternEditClicked(object sender, RoutedEventArgs e)
    {
        if (_patternRedoStack.Count == 0)
        {
            return;
        }

        _patternUndoStack.Push(CapturePatternEditSnapshot());
        RestorePatternEditSnapshot(_patternRedoStack.Pop());
        UpdatePatternHistoryButtons();
        RenderPattern();
        UpdatePatternPointInspector();
        RefreshAssemblyInspectorAfterHistoryChange();
        _ = UpdateDrapeViewportAsync();
        ShowStatus("Pattern edit redone", "The next pattern geometry state was restored.", InfoBarSeverity.Informational);
    }

    private void RefreshAssemblyInspectorAfterHistoryChange()
    {
        UpdateAssemblyInspector();
        if (EditAssemblyButton.IsChecked == true)
        {
            DispatcherQueue.TryEnqueue(() => UpdateAssemblyInspector(false));
        }
    }

    private void DrawDimension(double left, double top, double length, string text)
    {
        Brush brush = ResourceBrush("PatternDimensionBrush");
        Line line = new()
        {
            X1 = left,
            X2 = left + length,
            Y1 = top,
            Y2 = top,
            Stroke = brush,
            StrokeThickness = 1
        };
        PatternCanvas.Children.Add(line);

        PatternCanvas.Children.Add(new Line { X1 = left, X2 = left, Y1 = top - 6, Y2 = top + 6, Stroke = brush });
        PatternCanvas.Children.Add(new Line { X1 = left + length, X2 = left + length, Y1 = top - 6, Y2 = top + 6, Stroke = brush });

        TextBlock annotation = new()
        {
            Text = text,
            FontSize = 12,
            Foreground = brush
        };
        Canvas.SetLeft(annotation, left + 8);
        Canvas.SetTop(annotation, top - 25);
        PatternCanvas.Children.Add(annotation);
    }

    private static PathGeometry BuildGeometry(PatternPieceDocument piece)
    {
        PathFigure figure = new()
        {
            StartPoint = ToCanvasPoint(piece, piece.Start),
            IsClosed = true,
            IsFilled = true
        };
        foreach (PatternCurveDocument curve in piece.Boundary)
        {
            PathSegment segment = curve.Kind switch
            {
                "line" => new LineSegment { Point = ToCanvasPoint(piece, curve.End) },
                "cubic" when curve.Control1 is not null && curve.Control2 is not null => new BezierSegment
                {
                    Point1 = ToCanvasPoint(piece, curve.Control1),
                    Point2 = ToCanvasPoint(piece, curve.Control2),
                    Point3 = ToCanvasPoint(piece, curve.End)
                },
                _ => throw new NotSupportedException($"Unsupported pattern curve kind: {curve.Kind}")
            };
            figure.Segments.Add(segment);
        }

        PathGeometry geometry = new();
        geometry.Figures.Add(figure);
        return geometry;
    }

    private static Point ToCanvasPoint(PatternPieceDocument piece, PatternPointDocument point)
        => new(
            point.X * piece.ScaleX * PatternPixelsPerCentimeter,
            point.Y * piece.ScaleY * PatternPixelsPerCentimeter);

    private static PathGeometry CloneGeometry(PathGeometry source)
    {
        PathGeometry clone = new();
        foreach (PathFigure sourceFigure in source.Figures)
        {
            PathFigure figure = new()
            {
                StartPoint = sourceFigure.StartPoint,
                IsClosed = sourceFigure.IsClosed,
                IsFilled = sourceFigure.IsFilled
            };

            foreach (PathSegment sourceSegment in sourceFigure.Segments)
            {
                PathSegment segment = sourceSegment switch
                {
                    LineSegment line => new LineSegment { Point = line.Point },
                    BezierSegment bezier => new BezierSegment
                    {
                        Point1 = bezier.Point1,
                        Point2 = bezier.Point2,
                        Point3 = bezier.Point3
                    },
                    _ => throw new NotSupportedException($"Unsupported pattern segment type: {sourceSegment.GetType().Name}")
                };
                figure.Segments.Add(segment);
            }

            clone.Figures.Add(figure);
        }

        return clone;
    }

    private void OnMeasurementChanged(object sender, RangeBaseValueChangedEventArgs e)
    {
        if (!_pageReady || _updatingBustShapingControls)
        {
            return;
        }

        ApplyLinkedBaselineMeasurements();
        AlignConstructionControlsToBundledSource();
        UpdateMeasurementLabels();
        RenderPattern();
        UpdateFitIntelligence();
        _ = UpdateDrapeViewportAsync();
    }

    private void OnDetailedMeasurementChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (!_pageReady || _updatingLinkedMeasurements)
        {
            return;
        }

        if (sender.DataContext is MeasurementParameter measurement)
        {
            measurement.MarkUserEntered();
            if (measurement.Key is "armholeDepthL" or "armholeDepthR" or "armscyeCircL" or "armscyeCircR")
            {
                AlignConstructionControlsToBundledSource();
            }
        }

        RenderPattern();
        UpdatePatternPointInspector();
        UpdateFitIntelligence();
        _ = UpdateDrapeViewportAsync();
    }

    private void OnCustomMeasurementChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_pageReady)
        {
            _ = UpdateDrapeViewportAsync();
        }
    }

    private void OnLinkProportionsToggled(object sender, RoutedEventArgs e)
    {
        if (!_pageReady || LinkProportionsToggle.IsOn is false)
        {
            return;
        }

        ApplyLinkedBaselineMeasurements();
        _ = UpdateDrapeViewportAsync();
    }

    private void OnAvatarDisplayOptionToggled(object sender, RoutedEventArgs e)
    {
        if (!_pageReady)
        {
            return;
        }

        _ = UpdateAvatarDisplayOptionsAsync();
    }

    private Task UpdateAvatarDisplayOptionsAsync()
        => ExecuteDrapeScriptAsync(
            $"window.patterna.updateAvatar({{showBra:{JsonSerializer.Serialize(ShowBraToggle.IsOn)}}});");

    private void ApplyLinkedBaselineMeasurements()
    {
        if (_updatingLinkedMeasurements || LinkProportionsToggle.IsOn is false)
        {
            return;
        }

        _updatingLinkedMeasurements = true;
        try
        {
            double height = HeightSlider.Value;
            double chest = ChestSlider.Value;
            double waist = WaistSlider.Value;
            double hip = HipSlider.Value;
            double shoulder = ShoulderSlider.Value;
            double torso = TorsoSlider.Value;

            SetEstimatedDetailedValue("headHeight", height * 0.138);
            SetEstimatedDetailedValue("crownChin", height * 0.134);
            SetEstimatedDetailedValue("headCirc", height * 0.337);
            SetEstimatedDetailedValue("neckCirc", chest * 0.375);
            SetEstimatedDetailedValue("neckBaseCirc", chest * 0.428);
            SetEstimatedDetailedValue("highChestCirc", chest * (96.0 / 112.0));
            SetEstimatedDetailedValue("underBust", chest * (84.0 / 112.0));
            SetEstimatedDetailedValue("ribCirc", chest * (82.0 / 112.0));
            SetEstimatedDetailedValue("acrossFront", shoulder * (36.7 / 37.0));
            SetEstimatedDetailedValue("acrossBack", shoulder * (37.0 / 37.0));
            SetEstimatedDetailedValue("chestDepth", chest * (31.0 / 112.0));
            SetEstimatedDetailedValue("underBustDepth", chest * (23.0 / 112.0));
            SetEstimatedDetailedValue("frontWaistLength", torso * 1.036);
            SetEstimatedDetailedValue("backWaistLength", torso * 0.995);
            SetEstimatedDetailedValue("backNeckWaist", torso * 0.967);
            SetEstimatedDetailedValue("shoulderLengthL", shoulder * 0.318);
            SetEstimatedDetailedValue("shoulderLengthR", shoulder * 0.315);
            SetEstimatedDetailedValue("highHipCirc", waist + (hip - waist) * 0.57);
            SetEstimatedDetailedValue("abdomenCirc", waist + (hip - waist) * 0.39);
            SetEstimatedDetailedValue("pelvicWidth", hip * 0.295);
            SetEstimatedDetailedValue("frontHipArc", hip * 0.481);
            SetEstimatedDetailedValue("backHipArc", hip * 0.519);
            SetEstimatedDetailedValue("waistHipLengthL", height * 0.122);
            SetEstimatedDetailedValue("waistHipLengthR", height * 0.1215);

            foreach (string side in new[] { "L", "R" })
            {
                SetEstimatedDetailedValue($"armLength{side}", height * 0.343);
                SetEstimatedDetailedValue($"shoulderElbow{side}", height * 0.190);
                SetEstimatedDetailedValue($"elbowWrist{side}", height * 0.153);
                SetEstimatedDetailedValue($"upperArmCirc{side}", Math.Clamp(26.0 + (chest - 112.0) * 0.12, 18, 62));
                SetEstimatedDetailedValue($"elbowCirc{side}", Math.Clamp(24.5 + (chest - 112.0) * 0.08, 17, 44));
                SetEstimatedDetailedValue($"forearmCirc{side}", Math.Clamp(24.0 + (chest - 112.0) * 0.07, 15, 43));
                SetEstimatedDetailedValue($"wristCirc{side}", Math.Clamp(15.8 + (chest - 112.0) * 0.03, 11, 28));
                SetEstimatedDetailedValue($"armholeDepth{side}", chest * (21.8 / 112.0));
                SetEstimatedDetailedValue($"armscyeCirc{side}", chest * (45.5 / 112.0));
                SetEstimatedDetailedValue($"outseam{side}", height * 0.617);
                SetEstimatedDetailedValue($"inseam{side}", height * 0.461);
                SetEstimatedDetailedValue($"waistKnee{side}", height * 0.356);
                SetEstimatedDetailedValue($"crotchKnee{side}", height * 0.208);
                SetEstimatedDetailedValue($"thighUpperCirc{side}", hip * 0.580);
                SetEstimatedDetailedValue($"thighMidCirc{side}", hip * 0.507);
                SetEstimatedDetailedValue($"kneeCirc{side}", hip * 0.372);
                SetEstimatedDetailedValue($"calfCirc{side}", hip * 0.368);
                SetEstimatedDetailedValue($"ankleCirc{side}", hip * 0.227);
                SetEstimatedDetailedValue($"kneeHeight{side}", height * 0.289);
                SetEstimatedDetailedValue($"lowerLegLength{side}", height * 0.244);
                SetEstimatedDetailedValue($"footLength{side}", height * 0.144);
            }
        }
        finally
        {
            _updatingLinkedMeasurements = false;
        }
    }

    private MeasurementParameter? FindDetailedMeasurement(string key)
        => MeasurementGroups
            .SelectMany(group => group.Measurements)
            .FirstOrDefault(item => item.Key == key);

    private void SetEstimatedDetailedValue(string key, double value)
    {
        FindDetailedMeasurement(key)?.SetEstimatedValue(value);
    }

    private void RestoreDetailedValue(string key, double value, bool isUserOverride)
    {
        FindDetailedMeasurement(key)?.Restore(value, isUserOverride);
    }

    private void OnAddCustomMeasurementClicked(object sender, RoutedEventArgs e)
    {
        CustomMeasurements.Add(new CustomMeasurement($"Custom measurement {CustomMeasurements.Count + 1}", 0, "cm"));
    }

    private void OnRemoveCustomMeasurementClicked(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: CustomMeasurement measurement } && CustomMeasurements.Count > 1)
        {
            CustomMeasurements.Remove(measurement);
            _ = UpdateDrapeViewportAsync();
        }
    }

    private void UpdateMeasurementLabels()
    {
        HeightValueText.Text = $"{HeightSlider.Value:0.#} cm";
        ChestValueText.Text = $"{ChestSlider.Value:0.#} cm";
        WaistValueText.Text = $"{WaistSlider.Value:0.#} cm";
        HipValueText.Text = $"{HipSlider.Value:0.#} cm";
        ShoulderValueText.Text = $"{ShoulderSlider.Value:0.#} cm";
        TorsoValueText.Text = $"{TorsoSlider.Value:0.#} cm";
    }

    private void UpdateFitIntelligence()
    {
        UpdateGarmentEaseReadout();
        SimulationFitEvidence? evidence = null;
        bool hasRevisionEvidence = !string.IsNullOrWhiteSpace(_currentSimulationRevision) &&
            SimulationPipeline.TryGetAcceptedResult(
                ApplicationData.Current.LocalFolder.Path,
                _currentSimulationRevision,
                out SimulationPipelineResult? result) &&
            result is not null &&
            SimulationPipeline.TryReadFitEvidence(result, out evidence) &&
            evidence is not null;
        bool hasBundledEvidence = !hasRevisionEvidence &&
            IsBundledProductionBaseline() &&
            _bundledSimulationFitEvidence is not null;
        if (hasBundledEvidence)
        {
            evidence = _bundledSimulationFitEvidence;
        }
        bool hasEvidence = hasRevisionEvidence || hasBundledEvidence;
        if (!hasEvidence || evidence is null)
        {
            FitEvidenceStatusText.Text = "Not simulated";
            FitEvidenceStatusText.Foreground = ResourceBrush("TextFillColorSecondaryBrush");
            PeakStrainLabelText.Text = "Peak material strain";
            PeakStrainText.Text = "No evidence";
            P95StrainText.Text = "No evidence";
            P999StrainText.Text = "No evidence";
            CollisionEvidenceText.Text = "No evidence";
            PeakStrainProgress.Value = 0;
            P95StrainProgress.Value = 0;
            P999StrainProgress.Value = 0;
            CollisionEvidenceProgress.Value = 0;
            return;
        }

        string solverLabel = evidence.SolverName.Contains("Style3D", StringComparison.OrdinalIgnoreCase)
            ? "Newton Style3D"
            : evidence.SolverName;
        FitEvidenceStatusText.Text = $"Accepted · {solverLabel} · {evidence.CompletedFrames} frames";
        FitEvidenceStatusText.Foreground = ResourceBrush("SystemFillColorSuccessBrush");
        if (!evidence.PeakStrainGateEnabled &&
            evidence.NinetyNinthPointNinetyNinthPercentileEdgeStrainRatio is double p9999 &&
            evidence.MaximumAllowedNinetyNinthPointNinetyNinthPercentileEdgeStrainRatio is double maxP9999)
        {
            PeakStrainLabelText.Text = "Tail strain (99.99th)";
            PeakStrainText.Text = $"{p9999:P1} / {maxP9999:P0} limit";
            PeakStrainProgress.Value = 100 * p9999 / maxP9999;
        }
        else
        {
            PeakStrainLabelText.Text = "Peak material strain";
            PeakStrainText.Text = $"{evidence.MaximumEdgeStrainRatio:P1} / {evidence.MaximumAllowedEdgeStrainRatio:P0} limit";
            PeakStrainProgress.Value = 100 * evidence.MaximumEdgeStrainRatio /
                evidence.MaximumAllowedEdgeStrainRatio;
        }
        P95StrainText.Text = $"{evidence.NinetyFifthPercentileEdgeStrainRatio:P1} / {evidence.MaximumAllowedNinetyFifthPercentileEdgeStrainRatio:P0} limit";
        P999StrainText.Text = evidence.NinetyNinthPointNinthPercentileEdgeStrainRatio is double p999 &&
            evidence.MaximumAllowedNinetyNinthPointNinthPercentileEdgeStrainRatio is double maxP999
            ? $"{p999:P1} / {maxP999:P0} limit"
            : "Legacy report";
        CollisionEvidenceText.Text = $"{evidence.BodyCollisions} body · {evidence.SelfCollisions} self";
        P95StrainProgress.Value = 100 * evidence.NinetyFifthPercentileEdgeStrainRatio /
            evidence.MaximumAllowedNinetyFifthPercentileEdgeStrainRatio;
        P999StrainProgress.Value = evidence.NinetyNinthPointNinthPercentileEdgeStrainRatio is double localized &&
            evidence.MaximumAllowedNinetyNinthPointNinthPercentileEdgeStrainRatio is double maxLocalized
            ? 100 * localized / maxLocalized
            : 0;
        CollisionEvidenceProgress.Value = evidence.BodyCollisions + evidence.SelfCollisions > 0 ? 100 : 0;
    }

    private void UpdateGarmentEaseReadout()
    {
        if (_garmentTemplateKey != AdaptiveShirtTemplate || _garmentDocument is null)
        {
            GarmentEaseResultText.Text = "Ease readout is available for the adaptive shirt.";
            GarmentEaseResultText.Foreground = ResourceBrush("TextFillColorSecondaryBrush");
            ShirtConstructionResultText.Text = "Construction controls are available for the adaptive shirt.";
            ShirtConstructionResultText.Foreground = ResourceBrush("TextFillColorSecondaryBrush");
            BustShapingResultText.Text = "Bust shaping is available for the adaptive shirt.";
            BustShapingResultText.Foreground = ResourceBrush("TextFillColorSecondaryBrush");
            return;
        }
        try
        {
            AdaptiveShirtSourceGirths girths = AdaptiveShirtPatternGrader.MeasureGeometryGirths(_garmentDocument);
            ShirtConstructionProfileDocument construction =
                _garmentDocument.ShirtConstructionProfile ??
                ShirtConstructionPatternDrafter.Measure(_garmentDocument);
            GarmentEaseResultText.Text =
                $"Measured garment: chest {girths.ChestGirthCm:0.0} cm · waist {girths.WaistGirthCm:0.0} cm · hem {girths.HipGirthCm:0.0} cm";
            ShirtConstructionResultText.Text =
                $"Neck {construction.NecklineWidthCm:0.0} × {construction.FrontNeckDepthCm:0.0} cm · shoulder {construction.ShoulderLengthCm:0.0}/{construction.ShoulderDropCm:0.0} cm · armscye {construction.ArmscyeDepthCm:0.0} cm depth, {construction.ArmscyeScoopCm:+0.0;-0.0;0.0} cm shape, {construction.UnderarmExtensionCm:0.00} cm junction extension";
            ShirtBustShapingProfileDocument bustShaping = CurrentShirtBustShapingProfile();
            BustShapingResultText.Text = PhysicalBustShapingDescription(bustShaping, " · ");
            GarmentEaseResultText.Foreground = ResourceBrush("SystemFillColorSuccessBrush");
            ShirtConstructionResultText.Foreground = ResourceBrush("SystemFillColorSuccessBrush");
            BustShapingResultText.Foreground = ResourceBrush("SystemFillColorSuccessBrush");
        }
        catch (InvalidOperationException)
        {
            GarmentEaseResultText.Text = "Drafted garment measurements are unavailable for this pattern.";
            GarmentEaseResultText.Foreground = ResourceBrush("TextFillColorSecondaryBrush");
            ShirtConstructionResultText.Text = "Construction measurements are unavailable for this pattern.";
            ShirtConstructionResultText.Foreground = ResourceBrush("TextFillColorSecondaryBrush");
            BustShapingResultText.Text = "Bust-shaping measurements are unavailable for this pattern.";
            BustShapingResultText.Foreground = ResourceBrush("TextFillColorSecondaryBrush");
        }
    }

    private async Task InitializeDrapeViewportAsync()
    {
        try
        {
            await DrapeWebView.EnsureCoreWebView2Async();
            DrapeWebView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            DrapeWebView.CoreWebView2.Settings.AreDevToolsEnabled = false;
            DrapeWebView.CoreWebView2.NavigationCompleted += OnDrapeNavigationCompleted;
            DrapeWebView.CoreWebView2.WebMessageReceived += OnDrapeWebMessageReceived;

            string assetsFolder = System.IO.Path.Combine(AppContext.BaseDirectory, "Assets");
            DrapeWebView.CoreWebView2.SetVirtualHostNameToFolderMapping(
                "patterna.local",
                assetsFolder,
                CoreWebView2HostResourceAccessKind.Allow);
            string viewportPath = System.IO.Path.Combine(assetsFolder, "avatar3d.html");
            long viewportVersion = File.GetLastWriteTimeUtc(viewportPath).Ticks;
            DrapeWebView.CoreWebView2.Navigate(
                $"https://patterna.local/avatar3d.html?v={viewportVersion}");
        }
        catch (Exception exception)
        {
            SimulationStatusText.Text = "3D viewport could not start";
            ShowStatus("3D preview unavailable", exception.Message, InfoBarSeverity.Error);
        }
    }

    private async void OnDrapeNavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        if (!e.IsSuccess)
        {
            SimulationStatusText.Text = "3D viewport failed to load";
            return;
        }

        _webReady = true;
        await UpdateDrapeViewportAsync();
    }

    private async Task UpdateDrapeViewportAsync()
    {
        string posture = PostureComboBox.SelectedIndex switch
        {
            0 => "forward",
            2 => "erect",
            _ => "balanced"
        };

        Dictionary<string, object?> avatar = new()
        {
            ["height"] = HeightSlider.Value,
            ["chest"] = ChestSlider.Value,
            ["waist"] = WaistSlider.Value,
            ["hip"] = HipSlider.Value,
            ["shoulder"] = ShoulderSlider.Value,
            ["torso"] = TorsoSlider.Value,
            ["posture"] = posture,
            ["template"] = (BodyTemplateComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "neutral",
            ["photos"] = _photoCount,
            ["showBra"] = ShowBraToggle.IsOn
        };

        foreach (MeasurementParameter measurement in MeasurementGroups.SelectMany(group => group.Measurements))
        {
            avatar[measurement.Key] = measurement.Value;
        }

        avatar["customMeasurements"] = CustomMeasurements.Select((measurement, index) => new
        {
            key = $"custom_{index + 1}",
            measurement.Name,
            measurement.Value,
            measurement.Unit
        }).ToArray();

        var fabric = new
        {
            key = _fabricKey,
            weight = FabricWeightSlider.Value,
            stretch = FabricStretchSlider.Value,
            bend = double.IsNaN(BendNumberBox.Value) ? 8 : BendNumberBox.Value,
            friction = double.IsNaN(FrictionNumberBox.Value) ? 0.4 : FrictionNumberBox.Value
        };

        _garmentDocument = BuildCurrentGarmentDocument();
        PatternaUnrealBridgeDocument bridgeDocument = BuildCurrentUnrealBridgeDocument(_garmentDocument, posture);
        await WriteUnrealBridgeDocumentAsync(bridgeDocument);
        _currentSimulationRevision = SimulationPipeline.ComputeRevision(bridgeDocument);
        SimulationPipelineResult? acceptedResult = null;
        bool hasRevisionResult = SimulationPipeline.TryGetAcceptedResult(
            ApplicationData.Current.LocalFolder.Path,
            _currentSimulationRevision,
            out acceptedResult);
        bool isBundledBaseline = IsBundledProductionBaseline();
        if (hasRevisionResult || isBundledBaseline)
        {
            _acceptedSimulationRevision = _currentSimulationRevision;
        }
        UpdateSimulationFreshness();
        UpdateFitIntelligence();

        if (!_webReady || DrapeWebView.CoreWebView2 is null)
        {
            return;
        }

        string garmentJson = JsonSerializer.Serialize(_garmentDocument, GarmentJsonOptions);
        string script = $"window.patterna.updateAvatar({JsonSerializer.Serialize(avatar)}); window.patterna.updateFabric({JsonSerializer.Serialize(fabric)}); window.patterna.updateGarment({garmentJson});";
        await ExecuteDrapeScriptAsync(script);
        if (acceptedResult is not null)
        {
            await DisplayAcceptedSimulationAsync(acceptedResult);
        }
        else if (isBundledBaseline && !string.Equals(_displayedSimulationRevision, "bundled", StringComparison.Ordinal))
        {
            if (await LoadViewportAssetsAsync(
                "bundled",
                "window.patterna.loadBundledProduction();"))
            {
                _displayedSimulationRevision = "bundled";
            }
        }
        else if (!isBundledBaseline && acceptedResult is null)
        {
            await ExecuteDrapeScriptAsync("window.patterna.clearAcceptedRevision();");
            _displayedSimulationRevision = null;
        }
    }

    private async Task DisplayAcceptedSimulationAsync(SimulationPipelineResult result)
    {
        if (!_webReady ||
            DrapeWebView.CoreWebView2 is null ||
            string.Equals(_displayedSimulationRevision, result.Revision, StringComparison.Ordinal))
        {
            return;
        }

        const string revisionHost = "accepted-revision.patterna.local";
        DrapeWebView.CoreWebView2.SetVirtualHostNameToFolderMapping(
            revisionHost,
            result.JobDirectory,
            CoreWebView2HostResourceAccessKind.Allow);
        string bodyUrl = $"https://{revisionHost}/{Uri.EscapeDataString(System.IO.Path.GetFileName(result.BodyPath))}";
        string garmentUrl = $"https://{revisionHost}/{Uri.EscapeDataString(System.IO.Path.GetFileName(result.RenderMeshPath))}";
        string displayAvatarDirectory = System.IO.Path.Combine(result.JobDirectory, "display-avatar");
        string? displayAvatarBaseUrl = File.Exists(System.IO.Path.Combine(displayAvatarDirectory, "manifest.json"))
            ? $"https://{revisionHost}/display-avatar/"
            : null;
        string solverLabel = result.SolverName.Contains("Style3D", StringComparison.OrdinalIgnoreCase)
            ? "Newton Style3D"
            : result.SolverName;
        string label = $"Accepted exact-body {solverLabel} equilibrium · revision {result.Revision[..12]} · {result.FabricThicknessMillimeters:0.###} mm {result.FabricName}";
        string script = $"window.patterna.loadAcceptedRevision({JsonSerializer.Serialize(bodyUrl)},{JsonSerializer.Serialize(garmentUrl)},{JsonSerializer.Serialize(label)},{JsonSerializer.Serialize(result.Revision)},{JsonSerializer.Serialize(displayAvatarBaseUrl)});";
        if (await LoadViewportAssetsAsync(result.Revision, script))
        {
            _displayedSimulationRevision = result.Revision;
        }
    }

    private PatternaUnrealBridgeDocument BuildCurrentUnrealBridgeDocument(
        GarmentDocument garment,
        string posture)
    {
        List<UnrealBridgeMeasurementDocument> measurements =
        [
            new("height", "Standing height", HeightSlider.Value, "cm", "manual-or-baseline"),
            new("chest", "Chest circumference", ChestSlider.Value, "cm", "manual-or-baseline"),
            new("waist", "Natural waist circumference", WaistSlider.Value, "cm", "manual-or-baseline"),
            new("hip", "Full hip circumference", HipSlider.Value, "cm", "manual-or-baseline"),
            new("shoulder", "Shoulder width", ShoulderSlider.Value, "cm", "manual-or-baseline"),
            new("torso", "Torso length", TorsoSlider.Value, "cm", "manual-or-baseline")
        ];

        measurements.AddRange(
            MeasurementGroups
                .SelectMany(group => group.Measurements)
                .Select(measurement => new UnrealBridgeMeasurementDocument(
                    measurement.Key,
                    measurement.Label,
                    measurement.Value,
                    measurement.Unit,
                    measurement.IsUserOverride ? "manual" : "estimated")));

        UnrealBridgeCustomMeasurementDocument[] customMeasurements = CustomMeasurements
            .Select((measurement, index) => new UnrealBridgeCustomMeasurementDocument(
                $"custom_{index + 1}",
                measurement.Name,
                measurement.Value,
                measurement.Unit))
            .ToArray();

        double leftOutseam = FindDetailedMeasurement("outseamL")?.Value ?? HeightSlider.Value * 0.617;
        double rightOutseam = FindDetailedMeasurement("outseamR")?.Value ?? HeightSlider.Value * 0.617;
        double waistHeight = (leftOutseam + rightOutseam) * 0.5;
        FabricPhysicsDocument fabric = garment.Fabric;
        double maximumPieceWidth = garment.Pieces.Max(piece =>
        {
            PatternPointDocument[] points = [piece.Start, .. piece.Boundary.Select(curve => curve.End)];
            return (points.Max(point => point.X) - points.Min(point => point.X)) * piece.ScaleX;
        });
        double maximumPieceHeight = garment.Pieces.Max(piece =>
        {
            PatternPointDocument[] points = [piece.Start, .. piece.Boundary.Select(curve => curve.End)];
            return (points.Max(point => point.Y) - points.Min(point => point.Y)) * piece.ScaleY;
        });

        UnrealFabricGenerationDocument unrealFabric = new(
            fabric.Id,
            fabric.Name,
            fabric.MassGramsPerSquareMeter,
            fabric.ThicknessMillimeters,
            fabric.WarpStretchPercent,
            fabric.WeftStretchPercent,
            fabric.BiasStretchPercent,
            fabric.BendResistance,
            fabric.ShearResistance,
            fabric.StaticFriction,
            fabric.DynamicFriction,
            fabric.Calibration);

        UnrealGarmentGenerationDocument unrealGeneration = new(
            _garmentTemplateKey == AdaptiveShirtTemplate ? "source-pattern-v1" : "flared-skirt-v1",
            garment.Id,
            WaistSlider.Value,
            HipSlider.Value,
            2.0,
            5.0,
            maximumPieceWidth,
            maximumPieceHeight,
            waistHeight,
            8.0,
            fabric.ThicknessMillimeters / 10.0,
            72,
            48,
            unrealFabric);

        UnrealBodyProfileDocument body = new(
            "centimeters",
            posture,
            (BodyTemplateComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "neutral",
            _photoCount,
            measurements,
            customMeasurements);

        UnrealPatternTopologySummaryDocument patternTopology = BuildPatternTopologySummary(garment);

        return new PatternaUnrealBridgeDocument(
            "patterna.unreal-bridge/1.0",
            DateTimeOffset.UtcNow,
            body,
            garment,
            unrealGeneration,
            patternTopology);
    }

    private static UnrealPatternTopologySummaryDocument BuildPatternTopologySummary(
        GarmentDocument garment)
    {
        try
        {
            PatternTopologyCompilation compilation = PatternTopologyCompiler.Compile(garment);
            UnrealPatternTopologyDiagnosticDocument[] diagnostics = compilation.Diagnostics
                .Select(diagnostic => new UnrealPatternTopologyDiagnosticDocument(
                    diagnostic.Severity.ToString().ToLowerInvariant(),
                    diagnostic.Code,
                    diagnostic.Message,
                    diagnostic.SourceId))
                .ToArray();

            return new UnrealPatternTopologySummaryDocument(
                compilation.SchemaVersion,
                true,
                compilation.Panels.Count,
                compilation.VertexCount,
                compilation.TriangleCount,
                compilation.Seams.Count,
                diagnostics.Count(diagnostic => diagnostic.Severity == "warning"),
                diagnostics);
        }
        catch (PatternTopologyException exception)
        {
            UnrealPatternTopologyDiagnosticDocument[] diagnostics = exception.Errors
                .Select(error => new UnrealPatternTopologyDiagnosticDocument(
                    "error",
                    "topology-invalid",
                    error))
                .ToArray();

            return new UnrealPatternTopologySummaryDocument(
                "patterna.topology/1.1",
                false,
                0,
                0,
                0,
                0,
                0,
                diagnostics);
        }
    }

    private async Task WriteUnrealBridgeDocumentAsync(PatternaUnrealBridgeDocument bridgeDocument)
    {
        await _unrealBridgeWriteLock.WaitAsync();
        try
        {
            string bridgeDirectory = System.IO.Path.Combine(ApplicationData.Current.LocalFolder.Path, "UnrealBridge");
            Directory.CreateDirectory(bridgeDirectory);
            string destinationPath = System.IO.Path.Combine(bridgeDirectory, "current.patterna-unreal.json");
            string temporaryPath = System.IO.Path.Combine(bridgeDirectory, "current.patterna-unreal.tmp");
            string json = JsonSerializer.Serialize(bridgeDocument, UnrealBridgeJsonOptions);

            await File.WriteAllTextAsync(temporaryPath, json, new UTF8Encoding(false));
            File.Move(temporaryPath, destinationPath, true);
            ApplicationData.Current.LocalSettings.Values["UnrealBridgePath"] = destinationPath;
        }
        catch (Exception exception)
        {
            System.Diagnostics.Debug.WriteLine($"Patternal Unreal bridge write failed: {exception.Message}");
        }
        finally
        {
            _unrealBridgeWriteLock.Release();
        }
    }

    private void UpdateSimulationFreshness()
    {
        bool isShirt = _garmentTemplateKey == AdaptiveShirtTemplate && _adaptiveShirtDocument is not null;
        bool isCurrent = isShirt &&
            !string.IsNullOrWhiteSpace(_currentSimulationRevision) &&
            string.Equals(_currentSimulationRevision, _acceptedSimulationRevision, StringComparison.Ordinal);

        HighFidelityPreviewImage.Visibility = isCurrent && !_webReady ? Visibility.Visible : Visibility.Collapsed;
        DrapeWebView.Visibility = isShirt && _webReady ? Visibility.Visible : Visibility.Collapsed;
        AcceptedShirtControls.Visibility = isShirt ? Visibility.Visible : Visibility.Collapsed;
        AcceptedEquilibriumCard.Visibility = isCurrent ? Visibility.Visible : Visibility.Collapsed;
        SimulationStatusBorder.Visibility = isCurrent ? Visibility.Visible : Visibility.Collapsed;
        UpdateAcceptedEquilibriumTopology();
        StaleSimulationNotice.Visibility = isShirt && !isCurrent ? Visibility.Visible : Visibility.Collapsed;
        UnacceptedGarmentNotice.Visibility = isShirt ? Visibility.Collapsed : Visibility.Visible;

        if (isCurrent)
        {
            bool isBundledFit = IsBundledProductionBaseline();
            AcceptedEquilibriumHeaderText.Text = isBundledFit
                ? "NEWTON STYLE3D EQUILIBRIUM"
                : "REVISION-SPECIFIC STYLE3D EQUILIBRIUM";
            AcceptedEquilibriumDetailText.Text = isBundledFit
                ? "High-resolution cotton cloth with exact seams, static equilibrium, and zero body or self intersections"
                : "The current pattern was accepted after Newton Style3D equilibrium, collision, seam, and strain-tail validation";
            SimulationStatusText.Text = isBundledFit
                ? $"Accepted Style3D cloth · revision {_currentSimulationRevision![..12]}"
                : $"Accepted same-source cloth · revision {_currentSimulationRevision![..12]}";
        }
        else if (isShirt)
        {
            string revision = string.IsNullOrWhiteSpace(_currentSimulationRevision)
                ? "pending"
                : _currentSimulationRevision[..12];
            string? baselineMismatch = GetBundledProductionBaselineMismatch();
            StaleSimulationDetailText.Text =
                string.IsNullOrWhiteSpace(baselineMismatch)
                    ? "This body and 2D pattern have no matching accepted cloth. The old result is hidden."
                    : $"No matching accepted cloth: {baselineMismatch}. The old result is hidden.";
            SimulationStatusText.Text = $"3D regeneration required · revision {revision}";
        }
    }

    private void UpdateAcceptedEquilibriumTopology()
    {
        GarmentDocument? garment = _garmentDocument ?? _adaptiveShirtDocument;
        AcceptedEquilibriumTopologyText.Text = garment is null
            ? "Exact measured collision body · topology unavailable"
            : $"Exact measured collision body · {garment.Panels.Count} pattern panels · {garment.Seams.Count} construction seams";
    }

    private bool IsBundledProductionBaseline() => GetBundledProductionBaselineMismatch() is null;

    private string? GetBundledProductionBaselineMismatch()
    {
        if (_bundledSimulationFitEvidence is null)
        {
            return "the new full-bust body and shirt do not yet have accepted simulation evidence";
        }
        if (_adaptiveShirtDocument is null)
        {
            return "the bundled shirt source is unavailable";
        }
        if (_garmentTemplateKey != AdaptiveShirtTemplate)
        {
            return "the selected garment is not the production shirt";
        }
        if (Math.Abs(HeightSlider.Value - DefaultHeight) >= 0.001 ||
            Math.Abs(ChestSlider.Value - DefaultChest) >= 0.001 ||
            Math.Abs(WaistSlider.Value - DefaultWaist) >= 0.001 ||
            Math.Abs(HipSlider.Value - DefaultHip) >= 0.001 ||
            Math.Abs(ShoulderSlider.Value - DefaultShoulder) >= 0.001 ||
            Math.Abs(TorsoSlider.Value - DefaultTorso) >= 0.001)
        {
            return "a key body dimension differs from the simulated body";
        }
        if (PostureComboBox.SelectedIndex != 1 ||
            BodyTemplateComboBox.SelectedIndex != DefaultBodyTemplateIndex ||
            _photoCount != 0)
        {
            return "the posture, morphology, or photo body source differs from the simulated body";
        }
        if (_fabricKey != "cotton" ||
            Math.Abs(FabricWeightSlider.Value - 180) >= 0.001 ||
            Math.Abs(FabricStretchSlider.Value - 35) >= 0.001 ||
            Math.Abs((double.IsNaN(BendNumberBox.Value) ? 8 : BendNumberBox.Value) - 8) >= 0.001 ||
            Math.Abs((double.IsNaN(FrictionNumberBox.Value) ? 0.4 : FrictionNumberBox.Value) - 0.4) >= 0.001)
        {
            return "the fabric physics differ from the fitted cotton jersey";
        }
        GarmentEaseProfileDocument sourceEase =
            AdaptiveShirtPatternGrader.MeasureSourceEase(_adaptiveShirtDocument);
        GarmentEaseProfileDocument currentEase = CurrentGarmentEaseProfile();
        if (Math.Abs(currentEase.ChestEaseCm - sourceEase.ChestEaseCm) >= 0.001 ||
            Math.Abs(currentEase.WaistEaseCm - sourceEase.WaistEaseCm) >= 0.001 ||
            Math.Abs(currentEase.HipEaseCm - sourceEase.HipEaseCm) >= 0.001 ||
            Math.Abs(currentEase.UpperArmEaseCm - sourceEase.UpperArmEaseCm) >= 0.001 ||
            Math.Abs(currentEase.ArmscyeEaseCm - sourceEase.ArmscyeEaseCm) >= 0.001)
        {
            return string.Create(
                CultureInfo.InvariantCulture,
                $"the finished garment ease ({currentEase.ChestEaseCm:0.###}, {currentEase.WaistEaseCm:0.###}, {currentEase.HipEaseCm:0.###}, {currentEase.UpperArmEaseCm:0.###}, {currentEase.ArmscyeEaseCm:0.###} cm) differs from the simulated pattern ({sourceEase.ChestEaseCm:0.###}, {sourceEase.WaistEaseCm:0.###}, {sourceEase.HipEaseCm:0.###}, {sourceEase.UpperArmEaseCm:0.###}, {sourceEase.ArmscyeEaseCm:0.###} cm)");
        }
        // A user confirming an unchanged default measurement alters provenance, not body geometry.
        if (MeasurementGroups.SelectMany(group => group.Measurements).Any(measurement =>
                Math.Abs(measurement.Value - measurement.DefaultValue) >= 0.001) ||
            CustomMeasurements.Count != 1 ||
            Math.Abs(CustomMeasurements[0].Value) >= 0.001)
        {
            return "a detailed or custom body measurement differs from the simulated body";
        }
        GarmentDocument canonicalGarment = BuildBundledProductionGarmentDocument();
        ShirtConstructionProfileDocument sourceConstruction =
            TryMeasureShirtConstructionProfile(canonicalGarment) ?? DefaultShirtConstructionProfile();
        ShirtConstructionProfileDocument currentConstruction = CurrentShirtConstructionProfile();
        if (!ShirtConstructionPatternDrafter.AreEquivalent(currentConstruction, sourceConstruction))
        {
            return "the neckline, shoulder, armscye, sleeve cap, width distribution, or balance differs from the simulated pattern";
        }
        GarmentDocument currentGarment = _garmentDocument ?? BuildCurrentGarmentDocument();
        bool hasCanonicalGarmentStructure = string.Equals(
            GarmentCodePatternExporter.ComputeStructuralSignature(currentGarment),
            GarmentCodePatternExporter.ComputeStructuralSignature(canonicalGarment),
            StringComparison.Ordinal);
        if (!hasCanonicalGarmentStructure)
        {
            return "the effective pattern geometry, seams, or closures differ from the production source";
        }
        return null;
    }

    private async Task<bool> LoadViewportAssetsAsync(string revision, string script)
    {
        if (string.Equals(_pendingViewportAssetRevision, revision, StringComparison.Ordinal))
        {
            return false;
        }

        _pendingViewportAssetLoad?.TrySetCanceled();
        TaskCompletionSource<ViewportAssetLoadResult> completion = new(
            TaskCreationOptions.RunContinuationsAsynchronously);
        _pendingViewportAssetRevision = revision;
        _pendingViewportAssetLoad = completion;
        try
        {
            if (!await ExecuteDrapeScriptAsync(script))
            {
                return false;
            }

            Task completed = await Task.WhenAny(completion.Task, Task.Delay(TimeSpan.FromSeconds(15)));
            if (completed != completion.Task)
            {
                SimulationStatusText.Text = "3D asset load timed out";
                return false;
            }

            ViewportAssetLoadResult result = await completion.Task;
            if (!result.Success)
            {
                SimulationStatusText.Text = "3D asset load failed";
                ShowStatus(
                    "Accepted 3D assets could not be displayed",
                    result.Error ?? "The embedded renderer rejected the revision assets.",
                    InfoBarSeverity.Error);
            }
            return result.Success;
        }
        catch (TaskCanceledException)
        {
            return false;
        }
        finally
        {
            if (ReferenceEquals(_pendingViewportAssetLoad, completion))
            {
                _pendingViewportAssetRevision = null;
                _pendingViewportAssetLoad = null;
            }
        }
    }

    private void OnDrapeWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        try
        {
            using JsonDocument message = JsonDocument.Parse(e.WebMessageAsJson);
            JsonElement root = message.RootElement;
            if (!root.TryGetProperty("type", out JsonElement type))
            {
                return;
            }

            if (string.Equals(type.GetString(), "bra-availability", StringComparison.Ordinal))
            {
                bool available = root.TryGetProperty("available", out JsonElement availableElement) &&
                    availableElement.ValueKind == JsonValueKind.True;
                SetBraDisplayAvailability(available);
                return;
            }

            if (!string.Equals(type.GetString(), "asset-load", StringComparison.Ordinal) ||
                !root.TryGetProperty("revision", out JsonElement revisionElement) ||
                !string.Equals(revisionElement.GetString(), _pendingViewportAssetRevision, StringComparison.Ordinal))
            {
                return;
            }

            bool success = root.TryGetProperty("success", out JsonElement successElement) &&
                successElement.ValueKind == JsonValueKind.True;
            string? error = root.TryGetProperty("error", out JsonElement errorElement) &&
                errorElement.ValueKind == JsonValueKind.String
                    ? errorElement.GetString()
                    : null;
            _pendingViewportAssetLoad?.TrySetResult(new ViewportAssetLoadResult(success, error));
        }
        catch (JsonException)
        {
            // Ignore unrelated or malformed renderer messages.
        }
    }

    private void SetBraDisplayAvailability(bool available)
    {
        ShowBraToggle.IsEnabled = available;
        BraAvailabilityText.Text = available
            ? "Display only. The supported bust shape and cloth collision body stay identical when this is off."
            : "No fitted bra asset matches this edited avatar. Run Simulate to generate the matching presentation; body and collision shape remain unchanged.";
        AutomationProperties.SetHelpText(
            ShowBraToggle,
            available
                ? "Shows or hides the fitted bra without changing the supported body or collision shape"
                : "Unavailable until Simulate generates a fitted presentation asset for the current avatar");
    }

    private async Task<bool> ExecuteDrapeScriptAsync(string script)
    {
        if (!_webReady || DrapeWebView.CoreWebView2 is null)
        {
            return false;
        }

        try
        {
            await DrapeWebView.CoreWebView2.ExecuteScriptAsync(script);
            return true;
        }
        catch
        {
            SimulationStatusText.Text = "3D preview is reconnecting";
            return false;
        }
    }

    private async void OnImportPhotosClicked(object sender, RoutedEventArgs e)
    {
        FileOpenPicker picker = new();
        picker.FileTypeFilter.Add(".jpg");
        picker.FileTypeFilter.Add(".jpeg");
        picker.FileTypeFilter.Add(".png");
        picker.SuggestedStartLocation = PickerLocationId.PicturesLibrary;
        picker.ViewMode = PickerViewMode.Thumbnail;

        nint windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(((App)Application.Current).MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);

        IReadOnlyList<StorageFile> files = await picker.PickMultipleFilesAsync();
        if (files.Count == 0)
        {
            return;
        }

        AvatarPhotoButton.IsEnabled = false;
        PhotoStatusText.Text = $"Calibrating {files.Count} local reference photo{(files.Count == 1 ? string.Empty : "s")}...";
        await Task.Delay(850);

        _photoCount = files.Count;
        AvatarPhotoButton.IsEnabled = true;
        PhotoStatusText.Text = $"{files.Count} local photos linked · avatar draft refreshed";
        WorkspaceTabs.SelectedIndex = 1;
        await UpdateDrapeViewportAsync();
        await ExecuteDrapeScriptAsync($"window.patterna.setPhotoCalibration({_photoCount});");
        ShowStatus("Avatar draft updated", "Reference photos were linked locally. Production AI reconstruction is not enabled in this prototype.", InfoBarSeverity.Informational);
    }

    private void OnAvatarProfileChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_pageReady)
        {
            return;
        }

        UpdateFitIntelligence();
        _ = UpdateDrapeViewportAsync();
    }

    private void OnFabricPresetChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_pageReady)
        {
            return;
        }

        ApplySelectedFabricPreset();
        UpdateFitIntelligence();
        _ = UpdateDrapeViewportAsync();
    }

    private void ApplySelectedFabricPreset()
    {
        if (FabricPresetComboBox.SelectedItem is not ComboBoxItem selected)
        {
            return;
        }

        _fabricKey = selected.Tag?.ToString() ?? "cotton";
        switch (_fabricKey)
        {
            case "silk":
                FabricWeightSlider.Value = 65;
                FabricStretchSlider.Value = 14;
                BendNumberBox.Value = 16;
                FrictionNumberBox.Value = 0.22;
                break;
            case "linen":
                FabricWeightSlider.Value = 190;
                FabricStretchSlider.Value = 5;
                BendNumberBox.Value = 62;
                FrictionNumberBox.Value = 0.56;
                break;
            case "wool":
                FabricWeightSlider.Value = 260;
                FabricStretchSlider.Value = 18;
                BendNumberBox.Value = 46;
                FrictionNumberBox.Value = 0.62;
                break;
            default:
                FabricWeightSlider.Value = 180;
                FabricStretchSlider.Value = 35;
                BendNumberBox.Value = 8;
                FrictionNumberBox.Value = 0.4;
                break;
        }

        UpdateFabricLabels();
    }

    private void OnFabricPhysicsChanged(object sender, RangeBaseValueChangedEventArgs e)
    {
        if (!_pageReady)
        {
            return;
        }

        UpdateFabricLabels();
        UpdateFitIntelligence();
        _ = UpdateDrapeViewportAsync();
    }

    private void OnGarmentEaseChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (!_pageReady)
        {
            return;
        }

        if (ReferenceEquals(sender, ArmscyeEaseNumberBox))
        {
            AlignConstructionControlsToBundledSource();
        }
        RenderPattern();
        UpdatePatternPointInspector();
        UpdateFitIntelligence();
        _ = UpdateDrapeViewportAsync();
    }

    private void OnShirtConstructionChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (!_pageReady || _updatingConstructionControls)
        {
            return;
        }

        _constructionProfileEdited = true;
        RenderPattern();
        UpdatePatternPointInspector();
        UpdateFitIntelligence();
        _ = UpdateDrapeViewportAsync();
    }

    private void OnBustShapingModeChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_pageReady || _updatingBustShapingControls)
        {
            return;
        }
        string mode = (BustShapingModeComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ??
            ShirtBustShapingModes.None;
        if (!string.Equals(mode, ShirtBustShapingModes.None, StringComparison.OrdinalIgnoreCase) &&
            LeftDartIntakeNumberBox.Value <= 0 &&
            RightDartIntakeNumberBox.Value <= 0)
        {
            SetBustShapingControls(EstimateCurrentBustShapingProfile() with { Mode = mode });
        }
        ApplyBustShapingControlChange("Bust shaping mode updated");
    }

    private void OnBustShapingValueChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (!_pageReady || _updatingBustShapingControls)
        {
            return;
        }
        ApplyBustShapingControlChange("Bust shaping updated");
    }

    private void OnEstimateBustShapingClicked(object sender, RoutedEventArgs e)
    {
        string selectedMode = (BustShapingModeComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ??
            ShirtBustShapingModes.SideDarts;
        if (string.Equals(selectedMode, ShirtBustShapingModes.None, StringComparison.OrdinalIgnoreCase))
        {
            selectedMode = ShirtBustShapingModes.SideDarts;
        }
        SetBustShapingControls(EstimateCurrentBustShapingProfile() with { Mode = selectedMode });
        if (_pageReady)
        {
            ApplyBustShapingControlChange("Bust shaping estimated");
        }
    }

    private void ApplyBustShapingControlChange(string title)
    {
        try
        {
            ShirtBustShapingProfileDocument profile = CurrentShirtBustShapingProfile();
            RenderPattern();
            UpdatePatternPointInspector();
            UpdateFitIntelligence();
            _ = UpdateDrapeViewportAsync();
            BustShapingResultText.Text = PhysicalBustShapingDescription(profile, ", ") +
                (string.Equals(profile.Mode, ShirtBustShapingModes.None, StringComparison.OrdinalIgnoreCase)
                    ? string.Empty
                    : $"; tips stop {profile.DartTipOffsetCm:0.0} cm from the measured bust points.");
            ShowStatus(
                title,
                !string.Equals(profile.Mode, ShirtBustShapingModes.None, StringComparison.OrdinalIgnoreCase)
                    ? "The editable pattern now carries measurement-driven physical intake and matched seam spans."
                    : "The unmodified source block is active.",
                InfoBarSeverity.Success);
        }
        catch (InvalidOperationException exception)
        {
            BustShapingResultText.Text = exception.Message;
            ShowStatus("Bust shaping needs correction", exception.Message, InfoBarSeverity.Warning);
        }
    }

    private static string PhysicalBustShapingDescription(
        ShirtBustShapingProfileDocument profile,
        string separator)
    {
        string construction = profile.Mode switch
        {
            ShirtBustShapingModes.SideDarts => "Physical side darts",
            ShirtBustShapingModes.ShoulderDarts => "Physical shoulder darts",
            ShirtBustShapingModes.DistributedDarts => "Distributed side and shoulder darts",
            _ => string.Empty
        };
        return construction.Length == 0
            ? "No bust darts are applied to the source block."
            : $"{construction}: left {profile.LeftDartIntakeCm:0.0} cm{separator}right {profile.RightDartIntakeCm:0.0} cm{separator}separation {profile.BustPointSeparationCm:0.0} cm";
    }

    private void OnAdvancedPhysicsChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_pageReady)
        {
            _ = UpdateDrapeViewportAsync();
        }
    }

    private void UpdateFabricLabels()
    {
        FabricWeightValueText.Text = $"{FabricWeightSlider.Value:0} g/m²";
        FabricStretchValueText.Text = $"{FabricStretchSlider.Value:0}%";
    }

    private async void OnRunSimulationClicked(object sender, RoutedEventArgs e)
    {
        WorkspaceTabs.SelectedIndex = 1;
        if (_garmentTemplateKey != AdaptiveShirtTemplate || _adaptiveShirtDocument is null)
        {
            UpdateSimulationFreshness();
            ShowStatus(
                "Current garment is not simulation-ready",
                "The wrap dress still fails its source continuity and strain gates, so Patternal will not generate a misleading 3D result.",
                InfoBarSeverity.Warning);
            return;
        }

        RunSimulationButton.IsEnabled = false;
        SimulateCommandButton.IsEnabled = false;
        SimulationProgressRing.IsActive = true;
        SimulationProgressRing.Visibility = Visibility.Visible;
        SimulationStatusBorder.Visibility = Visibility.Visible;
        SimulationStatusText.Text = "Preparing a revisioned same-source cloth job";
        _simulationCancellation?.Cancel();
        _simulationCancellation?.Dispose();
        _simulationCancellation = new CancellationTokenSource();

        try
        {
            await UpdateDrapeViewportAsync();
            _garmentDocument = BuildCurrentGarmentDocument();
            string posture = PostureComboBox.SelectedIndex switch
            {
                0 => "forward",
                2 => "erect",
                _ => "balanced"
            };
            PatternaUnrealBridgeDocument bridge = BuildCurrentUnrealBridgeDocument(_garmentDocument, posture);
            SimulationRuntime runtime = SimulationRuntimeLocator.Resolve(
                AppContext.BaseDirectory,
                System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Patterna"));
            string bridgePath = System.IO.Path.Combine(
                ApplicationData.Current.LocalFolder.Path,
                "UnrealBridge",
                "current.patterna-unreal.json");
            Progress<SimulationPipelineProgress> progress = new(update =>
            {
                SimulationStatusText.Text = update.Message;
            });
            SimulationPipelineResult result = await SimulationPipeline.RunAsync(
                runtime,
                ApplicationData.Current.LocalFolder.Path,
                bridge,
                bridgePath,
                progress,
                _simulationCancellation.Token);

            PatternaUnrealBridgeDocument latestBridge = BuildCurrentUnrealBridgeDocument(
                BuildCurrentGarmentDocument(),
                posture);
            _currentSimulationRevision = SimulationPipeline.ComputeRevision(latestBridge);
            if (!string.Equals(_currentSimulationRevision, result.Revision, StringComparison.Ordinal))
            {
                throw new SimulationPipelineException("The document changed while the simulation was running. The completed result was kept as an audit artifact but was not displayed.");
            }

            _acceptedSimulationRevision = result.Revision;
            UpdateSimulationFreshness();
            UpdateFitIntelligence();
            await DisplayAcceptedSimulationAsync(result);
            ShowStatus(
                "Current cloth revision accepted",
                "Patternal regenerated the exact measured body and welded cloth surface and loaded them into the interactive 3D viewport.",
                InfoBarSeverity.Success);
        }
        catch (OperationCanceledException)
        {
            SimulationStatusText.Text = "Simulation cancelled";
        }
        catch (Exception exception) when (exception is SimulationPipelineException or IOException or UnauthorizedAccessException or JsonException)
        {
            _acceptedSimulationRevision = null;
            UpdateSimulationFreshness();
            ShowStatus("3D regeneration failed", exception.Message, InfoBarSeverity.Error);
        }
        finally
        {
            SimulationProgressRing.IsActive = false;
            SimulationProgressRing.Visibility = Visibility.Collapsed;
            UpdateSimulationFreshness();
            RunSimulationButton.IsEnabled = true;
            SimulateCommandButton.IsEnabled = true;
        }
    }

    private async void OnNewPatternClicked(object sender, RoutedEventArgs e)
    {
        ContentDialog dialog = new()
        {
            Title = "Create a fresh pattern?",
            Content = "This resets the current measurements and material settings to the sample body.",
            PrimaryButtonText = "Create pattern",
            CloseButtonText = "Keep editing",
            DefaultButton = ContentDialogButton.Close,
            XamlRoot = XamlRoot
        };

        if (await dialog.ShowAsync() != ContentDialogResult.Primary)
        {
            return;
        }

        HeightSlider.Value = DefaultHeight;
        ChestSlider.Value = DefaultChest;
        WaistSlider.Value = DefaultWaist;
        HipSlider.Value = DefaultHip;
        ShoulderSlider.Value = DefaultShoulder;
        TorsoSlider.Value = DefaultTorso;
        PostureComboBox.SelectedIndex = 1;
        BodyTemplateComboBox.SelectedIndex = DefaultBodyTemplateIndex;
        LinkProportionsToggle.IsOn = true;
        ShowBraToggle.IsOn = true;
        foreach (MeasurementParameter measurement in MeasurementGroups.SelectMany(group => group.Measurements))
        {
            measurement.Reset();
        }
        CustomMeasurements.Clear();
        CustomMeasurements.Add(new CustomMeasurement("Custom landmark", 0, "cm"));
        ChestEaseNumberBox.Value = DefaultChestEase;
        WaistEaseNumberBox.Value = DefaultWaistEase;
        HipEaseNumberBox.Value = DefaultHipEase;
        UpperArmEaseNumberBox.Value = DefaultUpperArmEase;
        ArmscyeEaseNumberBox.Value = DefaultArmscyeEase;
        _constructionProfileRestored = false;
        _constructionProfileEdited = false;
        _bustShapingProfileRestored = false;
        if (_adaptiveShirtDocument is not null)
        {
            SetConstructionControls(MeasurementAwareConstructionProfile());
        }
        SetBustShapingControls(EstimateCurrentBustShapingProfile() with
        {
            Mode = ShirtBustShapingModes.SideDarts
        });
        EndCanvasDraft(false);
        _patternPointOffsets.Clear();
        _patternStructuralEdits.Clear();
        _seamSideBReverseOverrides.Clear();
        _closureStateOverrides.Clear();
        _patternUndoStack.Clear();
        _patternRedoStack.Clear();
        _selectedPatternPoint = null;
        _selectedAssemblyRelationship = null;
        UpdatePatternHistoryButtons();
        UpdatePatternPointInspector();
        UpdateAssemblyInspector();
        FabricPresetComboBox.SelectedIndex = 1;
        _photoCount = 0;
        PhotoStatusText.Text = "Manual measurements · no photos linked";
        _selectedPieceId = BuildBaseGarmentDocument().Pieces[0].Id;
        RefreshPatternWorkspaceMetadata();
        PatternPiecesList.SelectedIndex = 0;
        RenderPattern();
        await UpdateDrapeViewportAsync();
        ShowStatus("New pattern created", "The sample body and lightweight cotton jersey preset are ready.", InfoBarSeverity.Success);
    }

    private void OnSavePatternClicked(object sender, RoutedEventArgs e)
    {
        ApplicationDataContainer settings = ApplicationData.Current.LocalSettings;
        settings.Values["Height"] = HeightSlider.Value;
        settings.Values["Chest"] = ChestSlider.Value;
        settings.Values["Waist"] = WaistSlider.Value;
        settings.Values["Hip"] = HipSlider.Value;
        settings.Values["Shoulder"] = ShoulderSlider.Value;
        settings.Values["Torso"] = TorsoSlider.Value;
        settings.Values["Posture"] = PostureComboBox.SelectedIndex;
        settings.Values["BodyTemplate"] = BodyTemplateComboBox.SelectedIndex;
        settings.Values["LinkedProportions"] = LinkProportionsToggle.IsOn;
        settings.Values["ShowFittedBra"] = ShowBraToggle.IsOn;
        settings.Values["DetailedMeasurements"] = JsonSerializer.Serialize(
            MeasurementGroups.SelectMany(group => group.Measurements).ToDictionary(item => item.Key, item => item.Value));
        settings.Values["DetailedMeasurementOverrides"] = JsonSerializer.Serialize(
            MeasurementGroups.SelectMany(group => group.Measurements).ToDictionary(item => item.Key, item => item.IsUserOverride));
        settings.Values["CustomMeasurements"] = JsonSerializer.Serialize(
            CustomMeasurements.Select(item => new SavedCustomMeasurement(item.Name, item.Value, item.Unit)).ToArray());
        settings.Values["Fabric"] = FabricPresetComboBox.SelectedIndex;
        settings.Values["GarmentTemplate"] = _garmentTemplateKey;
        settings.Values["ChestEase"] = ChestEaseNumberBox.Value;
        settings.Values["WaistEase"] = WaistEaseNumberBox.Value;
        settings.Values["HipEase"] = HipEaseNumberBox.Value;
        settings.Values["UpperArmEase"] = UpperArmEaseNumberBox.Value;
        settings.Values["ArmscyeEase"] = ArmscyeEaseNumberBox.Value;
        ShirtConstructionProfileDocument construction = CurrentShirtConstructionProfile();
        settings.Values["ShirtConstructionProfile"] = JsonSerializer.Serialize(
            construction,
            GarmentJsonOptions);
        settings.Values["ShirtBustShapingProfile"] = JsonSerializer.Serialize(
            CurrentShirtBustShapingProfile(),
            GarmentJsonOptions);
        settings.Values["BustShapingDefaultVersion"] = BustShapingDefaultVersion;
        settings.Values["PatternPointOffsets"] = JsonSerializer.Serialize(_patternPointOffsets, GarmentJsonOptions);
        settings.Values["PatternStructuralEdits"] = JsonSerializer.Serialize(_patternStructuralEdits, GarmentJsonOptions);
        settings.Values["SeamSideBReverseOverrides"] = JsonSerializer.Serialize(_seamSideBReverseOverrides, GarmentJsonOptions);
        settings.Values["ClosureStateOverrides"] = JsonSerializer.Serialize(_closureStateOverrides, GarmentJsonOptions);
        _garmentDocument = BuildCurrentGarmentDocument();
        settings.Values["GarmentDocument"] = JsonSerializer.Serialize(_garmentDocument, GarmentJsonOptions);
        settings.Values["SavedAt"] = DateTimeOffset.Now.ToString("O", CultureInfo.InvariantCulture);
        ShowStatus("Snapshot saved", "Measurements, avatar display options, fabric physics, pattern curves, panel placements, seams, and closure states are stored locally.", InfoBarSeverity.Success);
    }

    private void RestoreSnapshot()
    {
        ApplicationDataContainer settings = ApplicationData.Current.LocalSettings;
        if (settings.Values["GarmentTemplate"] is string garmentTemplate &&
            garmentTemplate is AdaptiveShirtTemplate or WrapDressTemplate)
        {
            _garmentTemplateKey = garmentTemplate;
        }
        if (settings.Values["Height"] is double height)
        {
            HeightSlider.Value = height;
            ChestSlider.Value = ReadDouble(settings, "Chest", DefaultChest);
            WaistSlider.Value = ReadDouble(settings, "Waist", DefaultWaist);
            HipSlider.Value = ReadDouble(settings, "Hip", DefaultHip);
            ShoulderSlider.Value = ReadDouble(settings, "Shoulder", DefaultShoulder);
            TorsoSlider.Value = ReadDouble(settings, "Torso", DefaultTorso);
            PostureComboBox.SelectedIndex = ReadInt(settings, "Posture", 1);
            BodyTemplateComboBox.SelectedIndex = ReadInt(settings, "BodyTemplate", DefaultBodyTemplateIndex);
            LinkProportionsToggle.IsOn = settings.Values["LinkedProportions"] is not bool linked || linked;
            ShowBraToggle.IsOn = settings.Values["ShowFittedBra"] is not bool showFittedBra || showFittedBra;
            FabricPresetComboBox.SelectedIndex = ReadInt(settings, "Fabric", 1);
            ChestEaseNumberBox.Value = ReadDouble(settings, "ChestEase", DefaultChestEase);
            WaistEaseNumberBox.Value = ReadDouble(settings, "WaistEase", DefaultWaistEase);
            HipEaseNumberBox.Value = ReadDouble(settings, "HipEase", DefaultHipEase);
            UpperArmEaseNumberBox.Value = ReadDouble(settings, "UpperArmEase", DefaultUpperArmEase);
            ArmscyeEaseNumberBox.Value = ReadDouble(settings, "ArmscyeEase", DefaultArmscyeEase);
            if (settings.Values["ShirtConstructionProfile"] is string constructionJson)
            {
                try
                {
                    ShirtConstructionProfileDocument? construction =
                        JsonSerializer.Deserialize<ShirtConstructionProfileDocument>(
                            constructionJson,
                            GarmentJsonOptions);
                    if (construction is not null)
                    {
                        SetConstructionControls(construction);
                        _constructionProfileRestored = true;
                        _constructionProfileEdited = true;
                    }
                }
                catch (JsonException)
                {
                    // Keep source-block defaults when a saved construction profile is unreadable.
                }
            }
            if (settings.Values["ShirtBustShapingProfile"] is string bustShapingJson)
            {
                try
                {
                    ShirtBustShapingProfileDocument? bustShaping =
                        JsonSerializer.Deserialize<ShirtBustShapingProfileDocument>(
                            bustShapingJson,
                            GarmentJsonOptions);
                    if (bustShaping is not null)
                    {
                        int savedDefaultVersion = ReadInt(settings, "BustShapingDefaultVersion", 0);
                        bool isLegacyImplicitNoDartDefault =
                            savedDefaultVersion < BustShapingDefaultVersion &&
                            string.Equals(
                                bustShaping.Mode,
                                ShirtBustShapingModes.None,
                                StringComparison.OrdinalIgnoreCase) &&
                            NearlyEqual(bustShaping.LeftDartIntakeCm, 0) &&
                            NearlyEqual(bustShaping.RightDartIntakeCm, 0);
                        if (!isLegacyImplicitNoDartDefault)
                        {
                            SetBustShapingControls(bustShaping);
                            _bustShapingProfileRestored = true;
                        }
                    }
                }
                catch (JsonException)
                {
                    // Keep the current measurement-driven default when a saved profile is unreadable.
                }
            }

            if (settings.Values["DetailedMeasurements"] is string detailedJson)
            {
                try
                {
                    Dictionary<string, double>? savedValues = JsonSerializer.Deserialize<Dictionary<string, double>>(detailedJson);
                    Dictionary<string, bool>? savedOverrides = settings.Values["DetailedMeasurementOverrides"] is string overridesJson
                        ? JsonSerializer.Deserialize<Dictionary<string, bool>>(overridesJson)
                        : null;
                    if (savedValues is not null)
                    {
                        foreach ((string key, double value) in savedValues)
                        {
                            bool isUserOverride = savedOverrides?.GetValueOrDefault(key) ?? true;
                            RestoreDetailedValue(key, value, isUserOverride);
                        }
                    }
                }
                catch (JsonException)
                {
                    // Preserve defaults when a prior local snapshot is unreadable.
                }
            }

            if (settings.Values["CustomMeasurements"] is string customJson)
            {
                try
                {
                    SavedCustomMeasurement[]? savedCustom = JsonSerializer.Deserialize<SavedCustomMeasurement[]>(customJson);
                    if (savedCustom is { Length: > 0 })
                    {
                        CustomMeasurements.Clear();
                        foreach (SavedCustomMeasurement item in savedCustom)
                        {
                            CustomMeasurements.Add(new CustomMeasurement(item.Name, item.Value, item.Unit));
                        }
                    }
                }
                catch (JsonException)
                {
                    // Preserve the editable placeholder when a prior local snapshot is unreadable.
                }
            }
        }

        if (settings.Values["PatternPointOffsets"] is string offsetsJson)
        {
            try
            {
                Dictionary<string, PatternPointDocument>? savedOffsets =
                    JsonSerializer.Deserialize<Dictionary<string, PatternPointDocument>>(offsetsJson, GarmentJsonOptions);
                if (savedOffsets is not null)
                {
                    RestorePatternPointOffsets(savedOffsets);
                }
            }
            catch (JsonException)
            {
                // Preserve generated geometry when a prior local offset snapshot is unreadable.
            }
        }

        if (settings.Values["PatternStructuralEdits"] is string structuralEditsJson)
        {
            try
            {
                PatternStructuralEditCommand[]? savedStructuralEdits =
                    JsonSerializer.Deserialize<PatternStructuralEditCommand[]>(structuralEditsJson, GarmentJsonOptions);
                if (savedStructuralEdits is not null)
                {
                    _patternStructuralEdits.Clear();
                    _patternStructuralEdits.AddRange(savedStructuralEdits.Where(IsValidSavedStructuralEdit));
                }
            }
            catch (JsonException)
            {
                // Preserve generated topology when a prior structural-edit snapshot is unreadable.
            }
        }

        if (settings.Values["SeamSideBReverseOverrides"] is string seamOverridesJson)
        {
            try
            {
                Dictionary<string, bool>? savedSeamOverrides =
                    JsonSerializer.Deserialize<Dictionary<string, bool>>(seamOverridesJson, GarmentJsonOptions);
                if (savedSeamOverrides is not null)
                {
                    _seamSideBReverseOverrides.Clear();
                    foreach ((string key, bool value) in savedSeamOverrides)
                    {
                        _seamSideBReverseOverrides[key] = value;
                    }
                }
            }
            catch (JsonException)
            {
                // Preserve generated sewing directions when a prior snapshot is unreadable.
            }
        }

        if (settings.Values["ClosureStateOverrides"] is string closureOverridesJson)
        {
            try
            {
                Dictionary<string, string>? savedClosureOverrides =
                    JsonSerializer.Deserialize<Dictionary<string, string>>(closureOverridesJson, GarmentJsonOptions);
                if (savedClosureOverrides is not null)
                {
                    _closureStateOverrides.Clear();
                    foreach ((string key, string value) in savedClosureOverrides.Where(item =>
                        GarmentClosureStates.Supported.Contains(item.Value)))
                    {
                        _closureStateOverrides[key] = value;
                    }
                }
            }
            catch (JsonException)
            {
                // Preserve generated closure states when a prior snapshot is unreadable.
            }
        }

        UpdatePatternHistoryButtons();
    }

    private static bool IsValidSavedStructuralEdit(PatternStructuralEditCommand edit)
        => edit switch
        {
            PatternBoundarySplitCommand split =>
                !string.IsNullOrWhiteSpace(split.PieceId) &&
                !string.IsNullOrWhiteSpace(split.CurveId) &&
                double.IsFinite(split.Parameter) &&
                split.Parameter is > 0 and < 1,
            PatternNotchCommand notch =>
                !string.IsNullOrWhiteSpace(notch.PieceId) &&
                !string.IsNullOrWhiteSpace(notch.CurveId) &&
                double.IsFinite(notch.Parameter) &&
                notch.Parameter is > 0 and < 1 &&
                double.IsFinite(notch.DepthCm) &&
                notch.DepthCm > 0 &&
                double.IsFinite(notch.WidthCm) &&
                notch.WidthCm >= 0 &&
                notch.Count is >= 1 and <= 3,
            PatternPieceCreateCommand createPiece =>
                createPiece.Piece is not null &&
                createPiece.Panel is not null &&
                !string.IsNullOrWhiteSpace(createPiece.Piece.Id) &&
                !string.IsNullOrWhiteSpace(createPiece.Panel.Id) &&
                string.Equals(createPiece.Piece.Id, createPiece.Panel.PieceId, StringComparison.OrdinalIgnoreCase),
            PatternSeamCreateCommand createSeam =>
                createSeam.Seam is not null &&
                !string.IsNullOrWhiteSpace(createSeam.Seam.Id) &&
                createSeam.Seam.SideA.EdgeIds.Count > 0 &&
                createSeam.Seam.SideB.EdgeIds.Count > 0,
            PatternInternalPathCreateCommand createPath =>
                !string.IsNullOrWhiteSpace(createPath.PieceId) &&
                createPath.Path is not null &&
                !string.IsNullOrWhiteSpace(createPath.Path.Id) &&
                PatternInternalPathKinds.Supported.Contains(createPath.Path.Kind) &&
                createPath.Path.Segments.Count > 0,
            PatternDartCreateCommand createDart =>
                !string.IsNullOrWhiteSpace(createDart.PieceId) &&
                createDart.Dart is not null &&
                !string.IsNullOrWhiteSpace(createDart.Dart.Id) &&
                !string.IsNullOrWhiteSpace(createDart.Dart.FirstLegBoundaryCurveId) &&
                !string.IsNullOrWhiteSpace(createDart.Dart.SecondLegBoundaryCurveId),
            PatternPiecePropertiesCommand properties =>
                !string.IsNullOrWhiteSpace(properties.PieceId) &&
                !string.IsNullOrWhiteSpace(properties.Name) &&
                properties.CutQuantity is >= 1 and <= 20 &&
                double.IsFinite(properties.SeamAllowanceCm) &&
                properties.SeamAllowanceCm is >= 0 and <= 10 &&
                !(properties.CutOnFold && properties.Mirrored),
            PatternInternalPathUpdateCommand updatePath =>
                !string.IsNullOrWhiteSpace(updatePath.PieceId) &&
                !string.IsNullOrWhiteSpace(updatePath.PathId) &&
                updatePath.Path is not null &&
                !string.IsNullOrWhiteSpace(updatePath.Path.Id) &&
                updatePath.Path.Segments.Count > 0,
            PatternInternalPathDeleteCommand deletePath =>
                !string.IsNullOrWhiteSpace(deletePath.PieceId) &&
                !string.IsNullOrWhiteSpace(deletePath.PathId),
            PatternDartUpdateCommand updateDart =>
                !string.IsNullOrWhiteSpace(updateDart.PieceId) &&
                !string.IsNullOrWhiteSpace(updateDart.DartId) &&
                updateDart.Dart is not null &&
                !string.IsNullOrWhiteSpace(updateDart.Dart.Id),
            PatternDartDeleteCommand deleteDart =>
                !string.IsNullOrWhiteSpace(deleteDart.PieceId) &&
                !string.IsNullOrWhiteSpace(deleteDart.DartId),
            PatternBoundaryCurveKindCommand curveKind =>
                !string.IsNullOrWhiteSpace(curveKind.PieceId) &&
                !string.IsNullOrWhiteSpace(curveKind.CurveId) &&
                curveKind.Kind is "line" or "cubic",
            _ => false
        };

    private static double ReadDouble(ApplicationDataContainer settings, string key, double fallback)
        => settings.Values[key] is double value ? value : fallback;

    private static int ReadInt(ApplicationDataContainer settings, string key, int fallback)
        => settings.Values[key] is int value ? value : fallback;

    private async void OnExportClicked(object sender, RoutedEventArgs e)
    {
        FileSavePicker picker = new()
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            SuggestedFileName = _garmentTemplateKey == AdaptiveShirtTemplate
                ? "Patternal-adaptive-crew-neck"
                : "Patternal-wrap-dress"
        };
        picker.FileTypeChoices.Add("Scalable vector pattern", new List<string> { ".svg" });

        nint windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(((App)Application.Current).MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
        StorageFile? file = await picker.PickSaveFileAsync();
        if (file is null)
        {
            return;
        }

        await FileIO.WriteTextAsync(file, BuildSvgExport());
        ShowStatus("Pattern exported", $"Saved {file.Name} with measurement metadata.", InfoBarSeverity.Success);
    }

    private string BuildSvgExport()
    {
        _garmentDocument = BuildCurrentGarmentDocument();
        string chest = ChestSlider.Value.ToString("0.0", CultureInfo.InvariantCulture);
        string waist = WaistSlider.Value.ToString("0.0", CultureInfo.InvariantCulture);
        string hip = HipSlider.Value.ToString("0.0", CultureInfo.InvariantCulture);
        GarmentEaseProfileDocument? ease = _garmentDocument.EaseProfile;
        string easeMetadata = ease is null
            ? string.Empty
            : $"; chest ease {ease.ChestEaseCm.ToString("0.0", CultureInfo.InvariantCulture)} cm; waist ease {ease.WaistEaseCm.ToString("0.0", CultureInfo.InvariantCulture)} cm; hip ease {ease.HipEaseCm.ToString("0.0", CultureInfo.InvariantCulture)} cm; upper arm ease {ease.UpperArmEaseCm.ToString("0.0", CultureInfo.InvariantCulture)} cm; armscye ease {ease.ArmscyeEaseCm.ToString("0.0", CultureInfo.InvariantCulture)} cm";
        string metadata =
            $"Patternal {_garmentDocument.SchemaVersion}; chest {chest} cm; waist {waist} cm; hip {hip} cm" +
            $"{easeMetadata}; {_garmentDocument.Panels.Count} simulation panels; {_garmentDocument.Seams.Count} seams";
        return PatternSvgExporter.Export(
            _garmentDocument,
            metadata,
            new PatternSvgExportOptions(
                SeamAllowanceToggle.IsOn,
                GrainlinesToggle.IsOn));
    }

    private void OnStartCanvasPolygonDraftClicked(object sender, RoutedEventArgs e)
    {
        EndCanvasDraft(false);
        _canvasDraftTool = CanvasDraftTool.Polygon;
        _canvasDraftPoints.Clear();
        _canvasDraftPointer = null;
        CanvasDraftToolbar.Visibility = Visibility.Visible;
        DrawPolygonPieceButton.IsEnabled = false;
        UpdateCanvasDraftControls();
        DrawCanvasDraftPreview();
        ShowStatus(
            "Polygon drafting active",
            "Click directly on the 2D canvas to place corners. Shift bypasses the 0.1 cm snap. Finish closes the boundary.",
            InfoBarSeverity.Informational);
    }

    private void OnPatternCanvasPointerMoved(object sender, PointerRoutedEventArgs e)
    {
        if (_canvasDraftTool == CanvasDraftTool.None)
        {
            return;
        }
        _canvasDraftPointer = CanvasDraftPointFromPointer(e);
        DrawCanvasDraftPreview();
        e.Handled = true;
    }

    private void OnPatternCanvasPointerPressed(object sender, PointerRoutedEventArgs e)
    {
        if (_canvasDraftTool != CanvasDraftTool.Polygon)
        {
            return;
        }
        PatternPointDocument point = CanvasDraftPointFromPointer(e);
        if (_canvasDraftPoints.Count >= 3 && PatternPointDistance(point, _canvasDraftPoints[0]) <= 0.4)
        {
            FinishCanvasPolygonDraft();
            e.Handled = true;
            return;
        }
        if (_canvasDraftPoints.Count > 0 && PatternPointDistance(point, _canvasDraftPoints[^1]) < 0.05)
        {
            ShowStatus("Point already placed", "Move at least 0.05 cm before placing another polygon corner.", InfoBarSeverity.Warning);
            e.Handled = true;
            return;
        }
        _canvasDraftPoints.Add(point);
        _canvasDraftPointer = point;
        UpdateCanvasDraftControls();
        DrawCanvasDraftPreview();
        e.Handled = true;
    }

    private PatternPointDocument CanvasDraftPointFromPointer(PointerRoutedEventArgs e)
    {
        Point position = e.GetCurrentPoint(PatternCanvas).Position;
        PatternPointDocument point = new(
            Math.Clamp(position.X, 0, PatternCanvas.Width) / PatternPixelsPerCentimeter,
            Math.Clamp(position.Y, 0, PatternCanvas.Height) / PatternPixelsPerCentimeter);
        bool bypassSnap = e.KeyModifiers.HasFlag(Windows.System.VirtualKeyModifiers.Shift);
        return SnapPatternPoint(point, bypassSnap);
    }

    private void OnUndoCanvasDraftPointClicked(object sender, RoutedEventArgs e)
    {
        if (_canvasDraftTool == CanvasDraftTool.None || _canvasDraftPoints.Count == 0)
        {
            return;
        }
        _canvasDraftPoints.RemoveAt(_canvasDraftPoints.Count - 1);
        UpdateCanvasDraftControls();
        DrawCanvasDraftPreview();
    }

    private void OnFinishCanvasDraftClicked(object sender, RoutedEventArgs e)
        => FinishCanvasPolygonDraft();

    private void OnCancelCanvasDraftClicked(object sender, RoutedEventArgs e)
    {
        EndCanvasDraft(true);
        ShowStatus("Canvas drafting canceled", "No pattern geometry was changed.", InfoBarSeverity.Informational);
    }

    private void FinishCanvasPolygonDraft()
    {
        if (_canvasDraftTool != CanvasDraftTool.Polygon || _canvasDraftPoints.Count < 3)
        {
            return;
        }
        GarmentDocument current = BuildCurrentGarmentDocument();
        HashSet<string> pieceIds = current.Pieces.Select(piece => piece.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        HashSet<string> panelIds = current.Panels.Select(panel => panel.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        string pieceId = UniqueDocumentId(pieceIds, "canvas-polygon");
        string panelId = UniqueDocumentId(panelIds, $"{pieceId}-panel");
        PatternPieceDocument piece;
        try
        {
            piece = PatternDraftFactory.CreateCanvasPolygonPiece(
                pieceId,
                $"Canvas polygon {current.Pieces.Count + 1}",
                _canvasDraftPoints,
                PatternPixelsPerCentimeter,
                1,
                1,
                false,
                false);
        }
        catch (ArgumentException exception)
        {
            ShowStatus("Polygon cannot be finished", exception.Message, InfoBarSeverity.Warning);
            return;
        }
        ClothPanelDocument panel = PatternDraftFactory.CreatePanel(panelId, piece, current.Pieces.Count);
        PushPatternEditUndo();
        _patternStructuralEdits.Add(new PatternPieceCreateCommand(piece, panel));
        _selectedPieceId = piece.Id;
        _selectedPatternPoint = null;
        _pendingSewingEdge = null;
        EndCanvasDraft(false);
        RefreshPatternWorkspaceMetadata();
        RenderPattern();
        UpdatePatternPointInspector();
        UpdateAssemblyInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus(
            "Canvas polygon created",
            $"{piece.Name} contains {piece.Boundary.Count} snapped corners, stable edge identities, a cloth panel, a grainline, and a simulation placement.",
            InfoBarSeverity.Success);
    }

    private void UpdateCanvasDraftControls()
    {
        int count = _canvasDraftPoints.Count;
        UndoCanvasDraftPointButton.IsEnabled = count > 0;
        FinishCanvasDraftButton.IsEnabled = count >= 3;
        CanvasDraftStatusText.Text = count switch
        {
            0 => "Click the first polygon corner",
            1 => "1 corner placed · continue drawing",
            2 => "2 corners placed · add at least one more",
            _ => $"{count} corners placed · click the first point or Finish piece"
        };
    }

    private void DrawCanvasDraftPreview()
    {
        foreach (UIElement element in _canvasDraftPreviewElements)
        {
            PatternCanvas.Children.Remove(element);
        }
        _canvasDraftPreviewElements.Clear();
        if (_canvasDraftTool == CanvasDraftTool.None)
        {
            return;
        }
        PointCollection previewPoints = new();
        foreach (PatternPointDocument point in _canvasDraftPoints)
        {
            previewPoints.Add(CanvasDraftDisplayPoint(point));
        }
        if (_canvasDraftPointer is not null &&
            (_canvasDraftPoints.Count == 0 || PatternPointDistance(_canvasDraftPointer, _canvasDraftPoints[^1]) >= 0.001))
        {
            previewPoints.Add(CanvasDraftDisplayPoint(_canvasDraftPointer));
        }
        if (previewPoints.Count > 1)
        {
            Polyline preview = new()
            {
                Points = previewPoints,
                Stroke = ResourceBrush("AccentFillColorDefaultBrush"),
                StrokeThickness = 2.5,
                StrokeLineJoin = PenLineJoin.Round
            };
            PatternCanvas.Children.Add(preview);
            _canvasDraftPreviewElements.Add(preview);
        }
        if (_canvasDraftPoints.Count >= 3)
        {
            PatternPointDocument last = _canvasDraftPointer ?? _canvasDraftPoints[^1];
            Point firstPoint = CanvasDraftDisplayPoint(_canvasDraftPoints[0]);
            Point lastPoint = CanvasDraftDisplayPoint(last);
            Line closingPreview = new()
            {
                X1 = lastPoint.X,
                Y1 = lastPoint.Y,
                X2 = firstPoint.X,
                Y2 = firstPoint.Y,
                Stroke = ResourceBrush("AccentFillColorDefaultBrush"),
                StrokeThickness = 1.5,
                StrokeDashArray = new DoubleCollection { 4, 3 },
                Opacity = 0.75
            };
            PatternCanvas.Children.Add(closingPreview);
            _canvasDraftPreviewElements.Add(closingPreview);
        }
        foreach (PatternPointDocument point in _canvasDraftPoints)
        {
            Point display = CanvasDraftDisplayPoint(point);
            Ellipse marker = new()
            {
                Width = 10,
                Height = 10,
                Fill = ResourceBrush("AccentFillColorDefaultBrush"),
                Stroke = ResourceBrush("PatternCanvasBackgroundBrush"),
                StrokeThickness = 2
            };
            Canvas.SetLeft(marker, display.X - 5);
            Canvas.SetTop(marker, display.Y - 5);
            PatternCanvas.Children.Add(marker);
            _canvasDraftPreviewElements.Add(marker);
        }
    }

    private static Point CanvasDraftDisplayPoint(PatternPointDocument point)
        => new(point.X * PatternPixelsPerCentimeter, point.Y * PatternPixelsPerCentimeter);

    private void EndCanvasDraft(bool render)
    {
        foreach (UIElement element in _canvasDraftPreviewElements)
        {
            PatternCanvas.Children.Remove(element);
        }
        _canvasDraftPreviewElements.Clear();
        _canvasDraftPoints.Clear();
        _canvasDraftPointer = null;
        _canvasDraftTool = CanvasDraftTool.None;
        CanvasDraftToolbar.Visibility = Visibility.Collapsed;
        DrawPolygonPieceButton.IsEnabled = true;
        if (render)
        {
            RenderPattern();
        }
    }

    private void OnPatternPieceClicked(object sender, ItemClickEventArgs e)
    {
        if (e.ClickedItem is PatternPieceListItem item)
        {
            _selectedPieceId = item.Id;
            _selectedPatternPoint = null;
            RenderPattern();
            UpdatePatternPointInspector();
            string pieceName = BuildCurrentGarmentDocument().Pieces
                .FirstOrDefault(piece => string.Equals(piece.Id, item.Id, StringComparison.OrdinalIgnoreCase))?.Name
                ?? item.Id;
            ShowStatus("Pattern piece selected", $"{pieceName} is active in the drafting canvas.", InfoBarSeverity.Informational);
        }
    }

    private async void OnAddPatternPieceClicked(object sender, RoutedEventArgs e)
    {
        EndCanvasDraft(false);
        GarmentDocument current = BuildCurrentGarmentDocument();
        HashSet<string> pieceIds = current.Pieces.Select(piece => piece.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        HashSet<string> panelIds = current.Panels.Select(panel => panel.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        string pieceId = UniqueDocumentId(pieceIds, "drafted-piece");
        string panelId = UniqueDocumentId(panelIds, $"{pieceId}-panel");
        int position = current.Pieces.Count;

        TextBox nameBox = new()
        {
            Header = "Piece name",
            Text = $"Drafted piece {position + 1}"
        };
        ComboBox shapeBox = new()
        {
            Header = "Shape",
            HorizontalAlignment = HorizontalAlignment.Stretch,
            SelectedIndex = 0,
            Items =
            {
                new ComboBoxItem { Content = "Rectangle" },
                new ComboBoxItem { Content = "Ellipse" },
                new ComboBoxItem { Content = "Polygon" }
            }
        };
        NumberBox widthBox = new()
        {
            Header = "Width (cm)",
            Minimum = 0.5,
            Maximum = 300,
            SmallChange = 0.5,
            Value = 28,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact
        };
        NumberBox heightBox = new()
        {
            Header = "Height (cm)",
            Minimum = 0.5,
            Maximum = 300,
            SmallChange = 0.5,
            Value = 38,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact
        };
        NumberBox seamAllowanceBox = new()
        {
            Header = "Seam allowance (cm)",
            Minimum = 0,
            Maximum = 10,
            SmallChange = 0.1,
            Value = 1,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact
        };
        NumberBox cutQuantityBox = new()
        {
            Header = "Cut quantity",
            Minimum = 1,
            Maximum = 20,
            SmallChange = 1,
            Value = 1,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact
        };
        CheckBox mirroredBox = new()
        {
            Content = "Create mirrored cutting instruction"
        };
        CheckBox cutOnFoldBox = new()
        {
            Content = "Cut on fold"
        };
        TextBox polygonVerticesBox = new()
        {
            Header = "Polygon vertices (cm)",
            PlaceholderText = "0,0; 28,0; 28,38; 0,38",
            Text = "0,0; 28,0; 24,38; 4,38",
            AcceptsReturn = true,
            TextWrapping = TextWrapping.Wrap,
            Visibility = Visibility.Collapsed
        };
        AutomationProperties.SetName(nameBox, "New pattern piece name");
        AutomationProperties.SetName(shapeBox, "New pattern piece shape");
        AutomationProperties.SetName(widthBox, "New pattern piece width in centimeters");
        AutomationProperties.SetName(heightBox, "New pattern piece height in centimeters");
        AutomationProperties.SetName(seamAllowanceBox, "New pattern piece seam allowance in centimeters");
        AutomationProperties.SetName(cutQuantityBox, "New pattern piece cut quantity");
        AutomationProperties.SetName(mirroredBox, "Mirror new pattern piece");
        AutomationProperties.SetName(cutOnFoldBox, "Cut new pattern piece on fold");
        AutomationProperties.SetName(polygonVerticesBox, "New polygon vertices in local centimeters");
        Grid dimensions = new() { ColumnSpacing = 10 };
        dimensions.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        dimensions.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        dimensions.Children.Add(widthBox);
        dimensions.Children.Add(heightBox);
        Grid.SetColumn(heightBox, 1);
        Grid construction = new() { ColumnSpacing = 10 };
        construction.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        construction.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        construction.Children.Add(seamAllowanceBox);
        construction.Children.Add(cutQuantityBox);
        Grid.SetColumn(cutQuantityBox, 1);
        StackPanel form = new() { Spacing = 10, Width = 420 };
        form.Children.Add(nameBox);
        form.Children.Add(shapeBox);
        form.Children.Add(dimensions);
        form.Children.Add(polygonVerticesBox);
        form.Children.Add(construction);
        form.Children.Add(mirroredBox);
        form.Children.Add(cutOnFoldBox);
        shapeBox.SelectionChanged += (_, _) =>
        {
            bool polygonSelected = shapeBox.SelectedIndex == 2;
            dimensions.Visibility = polygonSelected ? Visibility.Collapsed : Visibility.Visible;
            polygonVerticesBox.Visibility = polygonSelected ? Visibility.Visible : Visibility.Collapsed;
        };
        ContentDialog dialog = new()
        {
            Title = "Draft a pattern piece",
            Content = form,
            PrimaryButtonText = "Create piece",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Primary,
            XamlRoot = XamlRoot
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary)
        {
            return;
        }

        double widthCm = widthBox.Value;
        double heightCm = heightBox.Value;
        PatternDraftShape shape = shapeBox.SelectedIndex switch
        {
            1 => PatternDraftShape.Ellipse,
            2 => PatternDraftShape.Polygon,
            _ => PatternDraftShape.Rectangle
        };
        double layoutLeft = 36 + position % 3 * 292;
        double layoutTop = 40 + position / 3 * 210;
        bool cutOnFold = cutOnFoldBox.IsChecked == true;
        string pieceName = string.IsNullOrWhiteSpace(nameBox.Text) ? $"Drafted piece {position + 1}" : nameBox.Text;
        PatternPieceDocument piece;
        if (shape == PatternDraftShape.Polygon)
        {
            if (!TryParsePolygonVertices(polygonVerticesBox.Text, out IReadOnlyList<PatternPointDocument> vertices, out string error))
            {
                ShowStatus("Polygon coordinates are invalid", error, InfoBarSeverity.Warning);
                return;
            }
            try
            {
                piece = PatternDraftFactory.CreatePolygonPiece(
                    pieceId,
                    pieceName,
                    vertices,
                    seamAllowanceBox.Value,
                    (int)Math.Round(cutQuantityBox.Value),
                    mirroredBox.IsChecked == true && !cutOnFold,
                    cutOnFold,
                    layoutLeft,
                    layoutTop);
            }
            catch (ArgumentException exception)
            {
                ShowStatus("Polygon cannot be created", exception.Message, InfoBarSeverity.Warning);
                return;
            }
            (double polygonMinX, double polygonMinY, double polygonMaxX, double polygonMaxY) = GetPatternPieceBounds(piece);
            widthCm = polygonMaxX - polygonMinX;
            heightCm = polygonMaxY - polygonMinY;
        }
        else
        {
            piece = PatternDraftFactory.CreatePiece(
                pieceId,
                pieceName,
                shape,
                widthCm,
                heightCm,
                seamAllowanceBox.Value,
                (int)Math.Round(cutQuantityBox.Value),
                mirroredBox.IsChecked == true && !cutOnFold,
                cutOnFold,
                layoutLeft,
                layoutTop,
                PatternPixelsPerCentimeter * 0.5);
        }
        ClothPanelDocument panel = PatternDraftFactory.CreatePanel(
            panelId,
            piece,
            position);
        PushPatternEditUndo();
        _patternStructuralEdits.Add(new PatternPieceCreateCommand(piece, panel));
        _selectedPieceId = pieceId;
        _selectedPatternPoint = null;
        _pendingSewingEdge = null;
        RefreshPatternWorkspaceMetadata();
        RenderPattern();
        UpdatePatternPointInspector();
        UpdateAssemblyInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus(
            "Editable pattern piece created",
            $"{piece.Name} is a {widthCm:0.##} by {heightCm:0.##} cm {shape.ToString().ToLowerInvariant()} with stable boundary IDs, construction settings, a grainline, a cloth panel, and a simulation placement. Use Edit points to shape and sew it.",
            InfoBarSeverity.Success);
    }

    private static bool TryParsePolygonVertices(
        string text,
        out IReadOnlyList<PatternPointDocument> vertices,
        out string error)
    {
        List<PatternPointDocument> parsed = [];
        string[] entries = text.Split([';', '\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        for (int index = 0; index < entries.Length; index++)
        {
            string[] coordinates = entries[index].Split([',', ' ', '\t'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            if (coordinates.Length != 2 ||
                !double.TryParse(coordinates[0], NumberStyles.Float, CultureInfo.InvariantCulture, out double x) ||
                !double.TryParse(coordinates[1], NumberStyles.Float, CultureInfo.InvariantCulture, out double y) ||
                !double.IsFinite(x) ||
                !double.IsFinite(y))
            {
                vertices = [];
                error = $"Vertex {index + 1} must use X,Y numeric coordinates, with vertices separated by semicolons or lines.";
                return false;
            }
            parsed.Add(new PatternPointDocument(x, y));
        }
        if (parsed.Count < 3)
        {
            vertices = [];
            error = "Enter at least three polygon vertices.";
            return false;
        }
        vertices = parsed;
        error = string.Empty;
        return true;
    }

    private async void OnAddInternalPathClicked(object sender, RoutedEventArgs e)
    {
        GarmentDocument current = BuildCurrentGarmentDocument();
        PatternPieceDocument? piece = ResolveSelectedPatternPiece(current);
        if (piece is null)
        {
            ShowStatus("Select a pattern piece", "Choose a pattern piece before adding internal construction geometry.", InfoBarSeverity.Warning);
            return;
        }

        (double minX, double minY, double maxX, double maxY) = GetPatternPieceBounds(piece);
        double width = Math.Max(1, maxX - minX);
        double centerY = (minY + maxY) * 0.5;
        ComboBox targetBox = new()
        {
            Header = "Create or edit",
            HorizontalAlignment = HorizontalAlignment.Stretch,
            SelectedIndex = 0
        };
        targetBox.Items.Add(new ComboBoxItem { Content = "New internal line" });
        foreach (PatternInternalPathDocument existingPath in piece.InternalPaths.Where(path =>
            path.Segments.Count == 1 &&
            string.Equals(path.Segments[0].Kind, "line", StringComparison.OrdinalIgnoreCase)))
        {
            targetBox.Items.Add(new ComboBoxItem
            {
                Content = $"Edit: {existingPath.Label ?? existingPath.Id}",
                Tag = existingPath.Id
            });
        }
        TextBox nameBox = new()
        {
            Header = "Line name",
            Text = $"Construction line {piece.InternalPaths.Count + 1}"
        };
        ComboBox kindBox = new()
        {
            Header = "Purpose",
            HorizontalAlignment = HorizontalAlignment.Stretch,
            SelectedIndex = 0,
            Items =
            {
                new ComboBoxItem { Content = "Construction", Tag = PatternInternalPathKinds.Construction },
                new ComboBoxItem { Content = "Stitch", Tag = PatternInternalPathKinds.Stitch },
                new ComboBoxItem { Content = "Fold", Tag = PatternInternalPathKinds.Fold },
                new ComboBoxItem { Content = "Cut", Tag = PatternInternalPathKinds.Cut },
                new ComboBoxItem { Content = "Pleat", Tag = PatternInternalPathKinds.Pleat }
            }
        };
        NumberBox startXBox = CreateCoordinateNumberBox("Start X (cm)", minX + width * 0.2);
        NumberBox startYBox = CreateCoordinateNumberBox("Start Y (cm)", centerY);
        NumberBox endXBox = CreateCoordinateNumberBox("End X (cm)", minX + width * 0.8);
        NumberBox endYBox = CreateCoordinateNumberBox("End Y (cm)", centerY);
        AutomationProperties.SetName(nameBox, "Internal line name");
        AutomationProperties.SetName(kindBox, "Internal line purpose");
        AutomationProperties.SetName(targetBox, "Select a new or existing straight internal line");
        Grid coordinates = CreateCoordinateGrid(startXBox, startYBox, endXBox, endYBox);
        StackPanel form = new() { Spacing = 10, Width = 420 };
        form.Children.Add(new TextBlock
        {
            Text = $"{piece.Name} local coordinates. Piece bounds: X {minX:0.##} to {maxX:0.##} cm, Y {minY:0.##} to {maxY:0.##} cm.",
            TextWrapping = TextWrapping.Wrap,
            Foreground = ResourceBrush("TextFillColorSecondaryBrush")
        });
        form.Children.Add(targetBox);
        form.Children.Add(nameBox);
        form.Children.Add(kindBox);
        form.Children.Add(coordinates);
        ContentDialog dialog = new()
        {
            Title = "Add an internal line",
            Content = form,
            PrimaryButtonText = "Add line",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Primary,
            XamlRoot = XamlRoot
        };
        void LoadTarget()
        {
            string? selectedPathId = (targetBox.SelectedItem as ComboBoxItem)?.Tag?.ToString();
            PatternInternalPathDocument? selectedPath = piece.InternalPaths.FirstOrDefault(path =>
                string.Equals(path.Id, selectedPathId, StringComparison.OrdinalIgnoreCase));
            bool editing = selectedPath is not null;
            dialog.Title = editing ? "Edit an internal line" : "Add an internal line";
            dialog.PrimaryButtonText = editing ? "Apply line" : "Add line";
            dialog.SecondaryButtonText = editing ? "Delete line" : string.Empty;
            if (selectedPath is null)
            {
                nameBox.Text = $"Construction line {piece.InternalPaths.Count + 1}";
                SelectComboBoxByTag(kindBox, PatternInternalPathKinds.Construction);
                startXBox.Value = minX + width * 0.2;
                startYBox.Value = centerY;
                endXBox.Value = minX + width * 0.8;
                endYBox.Value = centerY;
                return;
            }
            nameBox.Text = selectedPath.Label ?? selectedPath.Id;
            SelectComboBoxByTag(kindBox, selectedPath.Kind);
            startXBox.Value = selectedPath.Start.X;
            startYBox.Value = selectedPath.Start.Y;
            endXBox.Value = selectedPath.Segments[0].End.X;
            endYBox.Value = selectedPath.Segments[0].End.Y;
        }
        targetBox.SelectionChanged += (_, _) => LoadTarget();
        LoadTarget();
        ContentDialogResult result = await dialog.ShowAsync();
        if (result == ContentDialogResult.None)
        {
            return;
        }

        string? targetPathId = (targetBox.SelectedItem as ComboBoxItem)?.Tag?.ToString();
        if (result == ContentDialogResult.Secondary && targetPathId is not null)
        {
            PushPatternEditUndo();
            _patternStructuralEdits.Add(new PatternInternalPathDeleteCommand(piece.Id, targetPathId));
            RefreshPatternWorkspaceMetadata();
            RenderPattern();
            UpdatePatternPointInspector();
            _ = UpdateDrapeViewportAsync();
            ShowStatus("Internal line deleted", $"Removed {targetPathId} from {piece.Name}.", InfoBarSeverity.Success);
            return;
        }

        PatternPointDocument start = new(startXBox.Value, startYBox.Value);
        PatternPointDocument end = new(endXBox.Value, endYBox.Value);
        if (PatternPointDistance(start, end) < 0.001)
        {
            ShowStatus("Internal line needs length", "The start and end coordinates must be different.", InfoBarSeverity.Warning);
            return;
        }
        string kind = (kindBox.SelectedItem as ComboBoxItem)?.Tag?.ToString()
            ?? PatternInternalPathKinds.Construction;
        HashSet<string> pathIds = piece.InternalPaths.Select(path => path.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        string pathId = targetPathId ?? UniqueDocumentId(pathIds, "internal-line");
        PatternInternalPathDocument? targetPath = piece.InternalPaths.FirstOrDefault(path =>
            string.Equals(path.Id, targetPathId, StringComparison.OrdinalIgnoreCase));
        string segmentId = targetPath?.Segments[0].Id ?? $"{pathId}-segment-1";
        PatternInternalPathDocument path = new(
            pathId,
            kind,
            start,
            [new PatternCurveDocument(segmentId, "line", end)])
        {
            Label = string.IsNullOrWhiteSpace(nameBox.Text) ? null : nameBox.Text.Trim()
        };
        PushPatternEditUndo();
        _patternStructuralEdits.Add(targetPathId is null
            ? new PatternInternalPathCreateCommand(piece.Id, path)
            : new PatternInternalPathUpdateCommand(piece.Id, targetPathId, path));
        RefreshPatternWorkspaceMetadata();
        RenderPattern();
        UpdatePatternPointInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus(
            targetPathId is null ? "Internal line created" : "Internal line updated",
            $"{path.Label ?? path.Id} is stored as exact {kind} geometry on {piece.Name}.",
            InfoBarSeverity.Success);
    }

    private async void OnEditPatternPiecePropertiesClicked(object sender, RoutedEventArgs e)
    {
        GarmentDocument current = BuildCurrentGarmentDocument();
        PatternPieceDocument? piece = ResolveSelectedPatternPiece(current);
        if (piece is null)
        {
            ShowStatus("Select a pattern piece", "Choose a pattern piece before editing its construction settings.", InfoBarSeverity.Warning);
            return;
        }

        (double minX, double minY, double maxX, double maxY) = GetPatternPieceBounds(piece);
        PatternGrainlineDocument grainline = piece.Grainline ?? new PatternGrainlineDocument(
            new PatternPointDocument((minX + maxX) * 0.5, minY + (maxY - minY) * 0.2),
            new PatternPointDocument((minX + maxX) * 0.5, minY + (maxY - minY) * 0.8));
        TextBox nameBox = new() { Header = "Piece name", Text = piece.Name };
        NumberBox seamAllowanceBox = new()
        {
            Header = "Seam allowance (cm)",
            Minimum = 0,
            Maximum = 10,
            SmallChange = 0.1,
            Value = piece.SeamAllowanceCm,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact
        };
        NumberBox cutQuantityBox = new()
        {
            Header = "Cut quantity",
            Minimum = 1,
            Maximum = 20,
            SmallChange = 1,
            Value = piece.CutQuantity,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact
        };
        CheckBox mirroredBox = new() { Content = "Mirrored cutting instruction", IsChecked = piece.Mirrored };
        CheckBox cutOnFoldBox = new() { Content = "Cut on fold", IsChecked = piece.CutOnFold };
        CheckBox showGrainlineBox = new() { Content = "Include grainline", IsChecked = piece.Grainline is not null };
        CheckBox lockGrainlineBox = new() { Content = "Lock grainline", IsChecked = grainline.Locked };
        NumberBox grainStartXBox = CreateCoordinateNumberBox("Grain start X (cm)", grainline.Start.X);
        NumberBox grainStartYBox = CreateCoordinateNumberBox("Grain start Y (cm)", grainline.Start.Y);
        NumberBox grainEndXBox = CreateCoordinateNumberBox("Grain end X (cm)", grainline.End.X);
        NumberBox grainEndYBox = CreateCoordinateNumberBox("Grain end Y (cm)", grainline.End.Y);
        AutomationProperties.SetName(nameBox, "Pattern piece name");
        AutomationProperties.SetName(seamAllowanceBox, "Pattern piece seam allowance in centimeters");
        AutomationProperties.SetName(cutQuantityBox, "Pattern piece cut quantity");
        AutomationProperties.SetName(mirroredBox, "Mirror pattern piece cutting instruction");
        AutomationProperties.SetName(cutOnFoldBox, "Cut pattern piece on fold");
        AutomationProperties.SetName(showGrainlineBox, "Include pattern piece grainline");
        AutomationProperties.SetName(lockGrainlineBox, "Lock pattern piece grainline");
        Grid construction = CreateTwoColumnGrid(seamAllowanceBox, cutQuantityBox);
        Grid grainCoordinates = CreateCoordinateGrid(grainStartXBox, grainStartYBox, grainEndXBox, grainEndYBox);
        StackPanel form = new() { Spacing = 10, Width = 440 };
        form.Children.Add(nameBox);
        form.Children.Add(construction);
        form.Children.Add(mirroredBox);
        form.Children.Add(cutOnFoldBox);
        form.Children.Add(new Border
        {
            Height = 1,
            Margin = new Thickness(0, 4, 0, 4),
            Background = ResourceBrush("DividerStrokeColorDefaultBrush")
        });
        form.Children.Add(showGrainlineBox);
        form.Children.Add(grainCoordinates);
        form.Children.Add(lockGrainlineBox);
        ScrollViewer scrollViewer = new()
        {
            Content = form,
            MaxHeight = 560,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        };
        ContentDialog dialog = new()
        {
            Title = $"Piece settings: {piece.Name}",
            Content = scrollViewer,
            PrimaryButtonText = "Apply settings",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Primary,
            XamlRoot = XamlRoot
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary)
        {
            return;
        }

        PatternGrainlineDocument? editedGrainline = null;
        if (showGrainlineBox.IsChecked == true)
        {
            PatternPointDocument grainStart = new(grainStartXBox.Value, grainStartYBox.Value);
            PatternPointDocument grainEnd = new(grainEndXBox.Value, grainEndYBox.Value);
            if (PatternPointDistance(grainStart, grainEnd) < 0.001)
            {
                ShowStatus("Grainline needs length", "The grainline start and end coordinates must be different.", InfoBarSeverity.Warning);
                return;
            }
            editedGrainline = new PatternGrainlineDocument(
                grainStart,
                grainEnd,
                lockGrainlineBox.IsChecked == true);
        }
        bool cutOnFold = cutOnFoldBox.IsChecked == true;
        PatternPiecePropertiesCommand command = new(
            piece.Id,
            string.IsNullOrWhiteSpace(nameBox.Text) ? piece.Name : nameBox.Text.Trim(),
            (int)Math.Round(cutQuantityBox.Value),
            mirroredBox.IsChecked == true && !cutOnFold,
            cutOnFold,
            seamAllowanceBox.Value,
            editedGrainline);
        PushPatternEditUndo();
        _patternStructuralEdits.Add(command);
        RefreshPatternWorkspaceMetadata();
        RenderPattern();
        UpdatePatternPointInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus(
            "Piece settings updated",
            $"{command.Name} now uses a {command.SeamAllowanceCm:0.##} cm seam allowance and cut quantity {command.CutQuantity}.",
            InfoBarSeverity.Success);
    }

    private async void OnAddDartClicked(object sender, RoutedEventArgs e)
    {
        GarmentDocument current = BuildStructurallyEditedBaseDocument();
        PatternPieceDocument? piece = ResolveSelectedPatternPiece(current);
        if (piece is null || piece.Boundary.Count == 0)
        {
            ShowStatus("Select a pattern piece", "Choose a pattern piece with a boundary before adding a dart.", InfoBarSeverity.Warning);
            return;
        }

        (double minX, double minY, double maxX, double maxY) = GetPatternPieceBounds(piece);
        ComboBox targetBox = new()
        {
            Header = "Create or edit",
            HorizontalAlignment = HorizontalAlignment.Stretch,
            SelectedIndex = 0
        };
        targetBox.Items.Add(new ComboBoxItem { Content = "New dart" });
        foreach (PatternDartDocument existingDart in piece.Darts)
        {
            targetBox.Items.Add(new ComboBoxItem
            {
                Content = $"Edit: {existingDart.Name}",
                Tag = existingDart.Id
            });
        }
        TextBox nameBox = new()
        {
            Header = "Dart name",
            Text = $"Dart {piece.Darts.Count + 1}"
        };
        ComboBox firstLegCurveBox = CreateBoundaryCurveComboBox(piece, "First leg boundary", _selectedPatternPoint?.CurveId);
        ComboBox secondLegCurveBox = CreateBoundaryCurveComboBox(piece, "Second leg boundary", _selectedPatternPoint?.CurveId);
        NumberBox firstLegParameterBox = CreateParameterNumberBox("First position (%)", 40);
        NumberBox secondLegParameterBox = CreateParameterNumberBox("Second position (%)", 60);
        NumberBox apexXBox = CreateCoordinateNumberBox("Apex X (cm)", (minX + maxX) * 0.5);
        NumberBox apexYBox = CreateCoordinateNumberBox("Apex Y (cm)", minY + (maxY - minY) * 0.55);
        ComboBox constructionModeBox = new()
        {
            Header = "Construction",
            HorizontalAlignment = HorizontalAlignment.Stretch,
            SelectedIndex = 0,
            Items =
            {
                new ComboBoxItem
                {
                    Content = "Guide only",
                    Tag = PatternDartConstructionModes.Annotation
                },
                new ComboBoxItem
                {
                    Content = "Cut and sew free edge",
                    Tag = PatternDartConstructionModes.SewnFreeEdge
                },
                new ComboBoxItem
                {
                    Content = "Cut and sew existing seam",
                    Tag = PatternDartConstructionModes.SewnEdge
                }
            }
        };
        ComboBox foldDirectionBox = new()
        {
            Header = "Fold direction",
            HorizontalAlignment = HorizontalAlignment.Stretch,
            SelectedIndex = 0,
            Items =
            {
                new ComboBoxItem { Content = "Center", Tag = "center" },
                new ComboBoxItem { Content = "Left", Tag = "left" },
                new ComboBoxItem { Content = "Right", Tag = "right" }
            }
        };
        AutomationProperties.SetName(nameBox, "Dart name");
        AutomationProperties.SetName(constructionModeBox, "Dart construction mode");
        AutomationProperties.SetName(foldDirectionBox, "Dart fold direction");
        AutomationProperties.SetName(targetBox, "Select a new or existing dart");
        Grid legCurves = CreateTwoColumnGrid(firstLegCurveBox, secondLegCurveBox);
        Grid legPositions = CreateTwoColumnGrid(firstLegParameterBox, secondLegParameterBox);
        Grid apexCoordinates = CreateTwoColumnGrid(apexXBox, apexYBox);
        StackPanel form = new() { Spacing = 10, Width = 440 };
        form.Children.Add(new TextBlock
        {
            Text = "Guide darts annotate only. A free-edge dart cuts and closes an unsewn edge. An existing-seam dart also divides its matched seam into two physical spans, and requires the drafted intake to match the opposite edge after the mouth closes.",
            TextWrapping = TextWrapping.Wrap,
            Foreground = ResourceBrush("TextFillColorSecondaryBrush")
        });
        form.Children.Add(targetBox);
        form.Children.Add(nameBox);
        form.Children.Add(legCurves);
        form.Children.Add(legPositions);
        form.Children.Add(apexCoordinates);
        form.Children.Add(constructionModeBox);
        form.Children.Add(foldDirectionBox);
        ContentDialog dialog = new()
        {
            Title = "Add a dart",
            Content = form,
            PrimaryButtonText = "Add dart",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Primary,
            XamlRoot = XamlRoot
        };
        void LoadTarget()
        {
            string? selectedDartId = (targetBox.SelectedItem as ComboBoxItem)?.Tag?.ToString();
            PatternDartDocument? selectedDart = piece.Darts.FirstOrDefault(dart =>
                string.Equals(dart.Id, selectedDartId, StringComparison.OrdinalIgnoreCase));
            bool editing = selectedDart is not null;
            dialog.Title = editing ? "Edit a dart" : "Add a dart";
            dialog.PrimaryButtonText = editing ? "Apply dart" : "Add dart";
            dialog.SecondaryButtonText = editing ? "Delete dart" : string.Empty;
            if (selectedDart is null)
            {
                nameBox.Text = $"Dart {piece.Darts.Count + 1}";
                SelectComboBoxByTag(firstLegCurveBox, _selectedPatternPoint?.CurveId ?? piece.Boundary[0].Id);
                SelectComboBoxByTag(secondLegCurveBox, _selectedPatternPoint?.CurveId ?? piece.Boundary[0].Id);
                firstLegParameterBox.Value = 40;
                secondLegParameterBox.Value = 60;
                apexXBox.Value = (minX + maxX) * 0.5;
                apexYBox.Value = minY + (maxY - minY) * 0.55;
                SelectComboBoxByTag(constructionModeBox, PatternDartConstructionModes.Annotation);
                SelectComboBoxByTag(foldDirectionBox, "center");
                return;
            }
            nameBox.Text = selectedDart.Name;
            SelectComboBoxByTag(firstLegCurveBox, selectedDart.FirstLegBoundaryCurveId);
            SelectComboBoxByTag(secondLegCurveBox, selectedDart.SecondLegBoundaryCurveId);
            firstLegParameterBox.Value = selectedDart.FirstLegParameter * 100;
            secondLegParameterBox.Value = selectedDart.SecondLegParameter * 100;
            apexXBox.Value = selectedDart.Apex.X;
            apexYBox.Value = selectedDart.Apex.Y;
            SelectComboBoxByTag(constructionModeBox, selectedDart.ConstructionMode);
            SelectComboBoxByTag(foldDirectionBox, selectedDart.FoldDirection);
        }
        targetBox.SelectionChanged += (_, _) => LoadTarget();
        LoadTarget();
        ContentDialogResult result = await dialog.ShowAsync();
        if (result == ContentDialogResult.None)
        {
            return;
        }

        string? targetDartId = (targetBox.SelectedItem as ComboBoxItem)?.Tag?.ToString();
        if (result == ContentDialogResult.Secondary && targetDartId is not null)
        {
            PushPatternEditUndo();
            _patternStructuralEdits.Add(new PatternDartDeleteCommand(piece.Id, targetDartId));
            RefreshPatternWorkspaceMetadata();
            RenderPattern();
            UpdatePatternPointInspector();
            _ = UpdateDrapeViewportAsync();
            ShowStatus("Dart deleted", $"Removed {targetDartId} from {piece.Name}.", InfoBarSeverity.Success);
            return;
        }

        string firstCurveId = (firstLegCurveBox.SelectedItem as ComboBoxItem)?.Tag?.ToString()
            ?? piece.Boundary[0].Id;
        string secondCurveId = (secondLegCurveBox.SelectedItem as ComboBoxItem)?.Tag?.ToString()
            ?? piece.Boundary[0].Id;
        double firstParameter = firstLegParameterBox.Value / 100;
        double secondParameter = secondLegParameterBox.Value / 100;
        if (string.Equals(firstCurveId, secondCurveId, StringComparison.OrdinalIgnoreCase) &&
            Math.Abs(firstParameter - secondParameter) < 0.01)
        {
            ShowStatus("Dart legs overlap", "Choose distinct leg positions on the boundary.", InfoBarSeverity.Warning);
            return;
        }
        HashSet<string> dartIds = piece.Darts.Select(dart => dart.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        string dartId = targetDartId ?? UniqueDocumentId(dartIds, "dart");
        PatternDartDocument dart = new(
            dartId,
            string.IsNullOrWhiteSpace(nameBox.Text) ? dartId : nameBox.Text.Trim(),
            firstCurveId,
            firstParameter,
            secondCurveId,
            secondParameter,
            new PatternPointDocument(apexXBox.Value, apexYBox.Value),
            (foldDirectionBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "center")
        {
            ConstructionMode =
                (constructionModeBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ??
                PatternDartConstructionModes.Annotation
        };
        PatternStructuralEditCommand prospectiveCommand = targetDartId is null
            ? new PatternDartCreateCommand(piece.Id, dart)
            : new PatternDartUpdateCommand(piece.Id, targetDartId, dart);
        try
        {
            PatternPhysicalDartCompiler.Compile(
                PatternStructuralEditor.ApplyEdits(current, [prospectiveCommand]));
        }
        catch (InvalidOperationException exception)
        {
            ShowStatus("Dart construction is not sewable", exception.Message, InfoBarSeverity.Warning);
            return;
        }
        PushPatternEditUndo();
        _patternStructuralEdits.Add(prospectiveCommand);
        RefreshPatternWorkspaceMetadata();
        RenderPattern();
        UpdatePatternPointInspector();
        _ = UpdateDrapeViewportAsync();
        ShowStatus(
            targetDartId is null ? "Dart created" : "Dart updated",
            dart.ConstructionMode switch
            {
                PatternDartConstructionModes.SewnFreeEdge =>
                    $"{dart.Name} now cuts {firstCurveId} into two sewn dart legs.",
                PatternDartConstructionModes.SewnEdge =>
                    $"{dart.Name} now closes physically and divides the matched seam around its intake.",
                _ =>
                    $"{dart.Name} is anchored to {firstCurveId} and {secondCurveId} as a construction guide."
            },
            InfoBarSeverity.Success);
    }

    private PatternPieceDocument? ResolveSelectedPatternPiece(GarmentDocument document)
        => document.Pieces.FirstOrDefault(piece =>
            string.Equals(piece.Id, _selectedPieceId, StringComparison.OrdinalIgnoreCase))
            ?? document.Pieces.FirstOrDefault();

    private static ComboBox CreateBoundaryCurveComboBox(
        PatternPieceDocument piece,
        string header,
        string? preferredCurveId)
    {
        ComboBox comboBox = new()
        {
            Header = header,
            HorizontalAlignment = HorizontalAlignment.Stretch
        };
        int selectedIndex = 0;
        for (int index = 0; index < piece.Boundary.Count; index++)
        {
            PatternCurveDocument curve = piece.Boundary[index];
            comboBox.Items.Add(new ComboBoxItem
            {
                Content = string.IsNullOrWhiteSpace(curve.Label) ? curve.Id : $"{curve.Label} ({curve.Id})",
                Tag = curve.Id
            });
            if (string.Equals(curve.Id, preferredCurveId, StringComparison.OrdinalIgnoreCase))
            {
                selectedIndex = index;
            }
        }
        comboBox.SelectedIndex = selectedIndex;
        AutomationProperties.SetName(comboBox, header);
        return comboBox;
    }

    private static void SelectComboBoxByTag(ComboBox comboBox, string value)
    {
        for (int index = 0; index < comboBox.Items.Count; index++)
        {
            if (comboBox.Items[index] is ComboBoxItem item &&
                string.Equals(item.Tag?.ToString(), value, StringComparison.OrdinalIgnoreCase))
            {
                comboBox.SelectedIndex = index;
                return;
            }
        }
    }

    private static NumberBox CreateCoordinateNumberBox(string header, double value)
    {
        NumberBox box = new()
        {
            Header = header,
            Minimum = -1000,
            Maximum = 1000,
            SmallChange = 0.1,
            Value = Math.Round(value, 2),
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact
        };
        AutomationProperties.SetName(box, header);
        return box;
    }

    private static NumberBox CreateParameterNumberBox(string header, double value)
    {
        NumberBox box = new()
        {
            Header = header,
            Minimum = 1,
            Maximum = 99,
            SmallChange = 1,
            Value = value,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact
        };
        AutomationProperties.SetName(box, header);
        return box;
    }

    private static Grid CreateCoordinateGrid(
        FrameworkElement startX,
        FrameworkElement startY,
        FrameworkElement endX,
        FrameworkElement endY)
    {
        Grid grid = new() { ColumnSpacing = 10, RowSpacing = 10 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        grid.Children.Add(startX);
        grid.Children.Add(startY);
        grid.Children.Add(endX);
        grid.Children.Add(endY);
        Grid.SetColumn(startY, 1);
        Grid.SetRow(endX, 1);
        Grid.SetRow(endY, 1);
        Grid.SetColumn(endY, 1);
        return grid;
    }

    private static Grid CreateTwoColumnGrid(FrameworkElement first, FrameworkElement second)
    {
        Grid grid = new() { ColumnSpacing = 10 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.Children.Add(first);
        grid.Children.Add(second);
        Grid.SetColumn(second, 1);
        return grid;
    }

    private static (double MinX, double MinY, double MaxX, double MaxY) GetPatternPieceBounds(
        PatternPieceDocument piece)
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
        return (
            points.Min(point => point.X),
            points.Min(point => point.Y),
            points.Max(point => point.X),
            points.Max(point => point.Y));
    }

    private static double PatternPointDistance(PatternPointDocument first, PatternPointDocument second)
    {
        double deltaX = second.X - first.X;
        double deltaY = second.Y - first.Y;
        return Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
    }

    private static string UniqueDocumentId(IReadOnlySet<string> existingIds, string desired)
    {
        if (!existingIds.Contains(desired))
        {
            return desired;
        }
        for (int suffix = 2; suffix < int.MaxValue; suffix++)
        {
            string candidate = $"{desired}-{suffix}";
            if (!existingIds.Contains(candidate))
            {
                return candidate;
            }
        }
        throw new InvalidOperationException($"Could not create a unique identifier from {desired}.");
    }

    private async void OnGarmentTemplateChanged(object sender, SelectionChangedEventArgs e)
    {
        if (GarmentTemplateComboBox.SelectedItem is not ComboBoxItem { Tag: string templateKey } ||
            templateKey is not AdaptiveShirtTemplate and not WrapDressTemplate)
        {
            return;
        }

        if (templateKey == AdaptiveShirtTemplate && _pageReady && _adaptiveShirtDocument is null)
        {
            GarmentTemplateComboBox.SelectedIndex = 1;
            ShowStatus(
                "Adaptive shirt unavailable",
                "The accepted GarmentCode source could not be loaded, so Patternal kept the wrap-dress document active.",
                InfoBarSeverity.Error);
            return;
        }

        _garmentTemplateKey = templateKey;
        if (!_pageReady)
        {
            return;
        }

        EndCanvasDraft(false);
        _patternPointOffsets.Clear();
        _patternStructuralEdits.Clear();
        _seamSideBReverseOverrides.Clear();
        _closureStateOverrides.Clear();
        _patternUndoStack.Clear();
        _patternRedoStack.Clear();
        _selectedPatternPoint = null;
        _selectedAssemblyRelationship = null;
        _selectedPieceId = BuildBaseGarmentDocument().Pieces[0].Id;
        UpdatePatternHistoryButtons();
        RefreshPatternWorkspaceMetadata();
        RenderPattern();
        UpdatePatternPointInspector();
        UpdateAssemblyInspector();
        await UpdateDrapeViewportAsync();
        ShowStatus(
            "Garment document changed",
            templateKey == AdaptiveShirtTemplate
                ? "The 2D workspace now uses the editable shirt source paired with the body-aware production fit."
                : "The wrap dress remains editable, but 3D is blocked until its bodice continuity and strain pass validation.",
            templateKey == AdaptiveShirtTemplate ? InfoBarSeverity.Success : InfoBarSeverity.Warning);
    }

    private void OnPatternDisplayOptionChanged(object sender, RoutedEventArgs e) => RenderPattern();

    private void OnFitPatternClicked(object sender, RoutedEventArgs e)
    {
        PatternViewbox.Stretch = Stretch.Uniform;
        CanvasScaleText.Text = "Fit · 12.5 mm grid";
        ShowStatus("Pattern fitted", "All pieces are visible at the current window size.", InfoBarSeverity.Informational);
    }

    private void OnTogglePiecesClicked(object sender, RoutedEventArgs e)
    {
        bool isVisible = PiecesToggleButton.IsChecked == true;
        PiecesPanel.Visibility = isVisible ? Visibility.Visible : Visibility.Collapsed;
        PiecesColumn.Width = isVisible ? new GridLength(244) : new GridLength(0);
    }

    private void OnToggleInspectorClicked(object sender, RoutedEventArgs e)
    {
        bool isVisible = InspectorToggleButton.IsChecked == true;
        InspectorPanel.Visibility = isVisible ? Visibility.Visible : Visibility.Collapsed;
        InspectorColumn.Width = isVisible ? new GridLength(420) : new GridLength(0);
    }

    private void OnWorkspaceTabsSizeChanged(object sender, SizeChangedEventArgs e)
        => UpdateDrapeSurfaceHeight();

    private void OnPageRootSizeChanged(object sender, SizeChangedEventArgs e)
        => UpdateDrapeSurfaceHeight();

    private void UpdateDrapeSurfaceHeight()
    {
        if (DrapeSurfaceGrid is not null && PageRoot.ActualHeight > 0)
        {
            DrapeSurfaceGrid.Height = Math.Max(320, PageRoot.ActualHeight - EditorCommandBar.ActualHeight - 70);
        }
    }

    private async void OnDrapeCameraViewClicked(object sender, RoutedEventArgs e)
    {
        if (sender is not Button button ||
            button.Tag is null ||
            Convert.ToString(button.Tag, System.Globalization.CultureInfo.InvariantCulture) is not string viewName ||
            string.IsNullOrWhiteSpace(viewName))
        {
            return;
        }

        await ExecuteDrapeScriptAsync(
            $"window.patterna.setCameraView({JsonSerializer.Serialize(viewName)});");
    }

    private async void OnResetDrapeCameraClicked(object sender, RoutedEventArgs e)
        => await ExecuteDrapeScriptAsync("window.patterna.resetCamera();");

    private void ShowStatus(string title, string message, InfoBarSeverity severity)
    {
        WorkspaceInfoBar.IsOpen = false;
        WorkspaceInfoBar.Title = title;
        WorkspaceInfoBar.Message = message;
        WorkspaceInfoBar.Severity = severity;
        WorkspaceInfoBar.IsOpen = true;
    }
}

internal enum CanvasDraftTool
{
    None,
    Polygon
}

internal enum PatternPointRole
{
    Start,
    End,
    Control1,
    Control2
}

internal sealed record PatternPointHandle(
    string PieceId,
    string? CurveId,
    PatternPointRole Role,
    string DisplayName);

internal sealed record PatternEdgeHandle(string PieceId, string CurveId);

internal enum AssemblyRelationshipKind
{
    Seam,
    Closure
}

internal sealed record AssemblyRelationshipHandle(
    string Id,
    AssemblyRelationshipKind Kind,
    string DisplayName);

internal sealed record PatternEditSnapshot(
    IReadOnlyDictionary<string, PatternPointDocument> PatternPointOffsets,
    IReadOnlyList<PatternStructuralEditCommand> StructuralEdits,
    IReadOnlyDictionary<string, bool> SeamSideBReverseOverrides,
    IReadOnlyDictionary<string, string> ClosureStateOverrides);

internal sealed record ViewportAssetLoadResult(bool Success, string? Error);

public sealed class PatternPieceListItem
{
    public PatternPieceListItem(string id, string name, string detail, Brush swatch)
    {
        Id = id;
        Name = name;
        Detail = detail;
        Swatch = swatch;
    }

    public string Id { get; set; }

    public string Name { get; set; }

    public string Detail { get; set; }

    public Brush Swatch { get; set; }
}

internal sealed record SavedCustomMeasurement(string Name, double Value, string Unit);

public sealed class MeasurementGroup
{
    public MeasurementGroup(
        string title,
        string description,
        IEnumerable<MeasurementParameter> measurements,
        bool isExpanded = false)
    {
        Title = title;
        Description = description;
        Measurements = new ObservableCollection<MeasurementParameter>(measurements);
        IsExpanded = isExpanded;
    }

    public string Title { get; }
    public string Description { get; }
    public ObservableCollection<MeasurementParameter> Measurements { get; }
    public bool IsExpanded { get; set; }
}

public sealed class MeasurementParameter : INotifyPropertyChanged
{
    private double _value;
    private bool _isUserOverride;

    public MeasurementParameter(
        string key,
        string label,
        double value,
        double minimum,
        double maximum,
        double increment,
        string unit)
    {
        Key = key;
        Label = label;
        DefaultValue = value;
        _value = value;
        Minimum = minimum;
        Maximum = maximum;
        Increment = increment;
        Unit = unit;
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public string Key { get; }
    public string Label { get; }
    public string Unit { get; }
    public string DisplayLabel => $"{Label} ({Unit})";
    public string AutomationName => $"{Label} in {Unit}";
    public double DefaultValue { get; }
    public double Minimum { get; }
    public double Maximum { get; }
    public double Increment { get; }
    public bool IsUserOverride => _isUserOverride;

    public double Value
    {
        get => _value;
        set
        {
            SetValue(value);
        }
    }

    public void MarkUserEntered()
    {
        if (_isUserOverride)
        {
            return;
        }

        _isUserOverride = true;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(IsUserOverride)));
    }

    public void SetEstimatedValue(double value)
    {
        if (!_isUserOverride)
        {
            SetValue(value);
        }
    }

    public void Restore(double value, bool isUserOverride)
    {
        SetValue(value);
        _isUserOverride = isUserOverride;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(IsUserOverride)));
    }

    public void Reset()
    {
        _isUserOverride = false;
        SetValue(DefaultValue);
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(IsUserOverride)));
    }

    private void SetValue(double value)
    {
        double normalized = Math.Round(Math.Clamp(value, Minimum, Maximum), 2);
        if (Math.Abs(_value - normalized) < 0.001)
        {
            return;
        }

        _value = normalized;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Value)));
    }
}

public sealed class CustomMeasurement : INotifyPropertyChanged
{
    private string _name;
    private double _value;

    public CustomMeasurement(string name, double value, string unit)
    {
        _name = name;
        _value = value;
        Unit = unit;
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public string Name
    {
        get => _name;
        set
        {
            if (_name == value)
            {
                return;
            }

            _name = value;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Name)));
        }
    }

    public double Value
    {
        get => _value;
        set
        {
            if (Math.Abs(_value - value) < 0.001)
            {
                return;
            }

            _value = Math.Round(value, 2);
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Value)));
        }
    }

    public string Unit { get; }
}
