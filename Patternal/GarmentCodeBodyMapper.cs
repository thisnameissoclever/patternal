using System.Text.Json;

namespace Patterna;

public sealed record GarmentCodeBodyMappingResult(
    IReadOnlyDictionary<string, double> Body,
    IReadOnlyDictionary<string, IReadOnlyList<string>> Sources,
    IReadOnlyList<string> FallbackParameters)
{
    public string ToJson(bool indented = true)
        => JsonSerializer.Serialize(
            new Dictionary<string, object> { ["body"] = Body },
            new JsonSerializerOptions { WriteIndented = indented });

    public string ToAvatarJson(UnrealBodyProfileDocument profile, bool indented = true)
    {
        ArgumentNullException.ThrowIfNull(profile);
        Dictionary<string, double> detailedMeasurements = profile.Measurements
            .Where(measurement => double.IsFinite(measurement.Value))
            .GroupBy(measurement => measurement.Key, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(group => group.Key, group => group.Last().Value, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, string> measurementOrigins = profile.Measurements
            .Where(measurement => double.IsFinite(measurement.Value))
            .GroupBy(measurement => measurement.Key, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                group => group.Key,
                group => group.Last().Origin,
                StringComparer.OrdinalIgnoreCase);
        foreach (UnrealBridgeCustomMeasurementDocument custom in profile.CustomMeasurements
                     .Where(measurement => double.IsFinite(measurement.Value)))
        {
            detailedMeasurements[custom.Key] = custom.Value;
            measurementOrigins[custom.Key] = "manual-custom";
        }

        return JsonSerializer.Serialize(
            new Dictionary<string, object>
            {
                ["body"] = Body,
                ["measurements"] = detailedMeasurements,
                ["measurementOrigins"] = measurementOrigins,
                ["measurementSources"] = Sources,
                ["fallbackParameters"] = FallbackParameters
            },
            new JsonSerializerOptions { WriteIndented = indented });
    }
}

public static class GarmentCodeBodyMapper
{
    public static GarmentCodeBodyMappingResult Map(UnrealBodyProfileDocument profile)
    {
        ArgumentNullException.ThrowIfNull(profile);
        if (!profile.Units.Equals("centimeters", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                $"GarmentCode body mapping requires centimeters, not {profile.Units}.");
        }

        Dictionary<string, double> measurements = profile.Measurements
            .Where(measurement => double.IsFinite(measurement.Value))
            .GroupBy(measurement => measurement.Key, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(group => group.Key, group => group.Last().Value, StringComparer.OrdinalIgnoreCase);
        foreach (UnrealBridgeCustomMeasurementDocument custom in profile.CustomMeasurements
                     .Where(measurement =>
                         measurement.Unit.Equals("cm", StringComparison.OrdinalIgnoreCase) &&
                         double.IsFinite(measurement.Value)))
        {
            measurements[custom.Key] = custom.Value;
        }

        Dictionary<string, IReadOnlyList<string>> sources = new(StringComparer.Ordinal);
        HashSet<string> fallbacks = new(StringComparer.Ordinal);
        double Read(string key, double fallback)
        {
            if (measurements.TryGetValue(key, out double value))
            {
                return value;
            }
            fallbacks.Add(key);
            return fallback;
        }
        double Average(string left, string right, double fallback)
            => (Read(left, fallback) + Read(right, fallback)) * 0.5;
        void Source(string target, params string[] keys)
            => sources[target] = keys;

        double height = Read("height", 167.0);
        double bust = Read("chest", 92.0);
        double waist = Read("waist", 71.0);
        double hips = Read("hip", 99.0);
        double shoulderWidth = Read("shoulder", 39.0);
        double backHipArc = Read("backHipArc", hips * 0.519);
        double acrossBack = Read("acrossBack", shoulderWidth * 0.936);
        double bustHeight = Average("bustHeightL", "bustHeightR", height * 0.154);
        double armholeDepth = Average("armholeDepthL", "armholeDepthR", bust * 0.225);
        double armscyeCircumference = Average("armscyeCircL", "armscyeCircR", bust * 0.457);
        double shoulderSlope = Average("shoulderSlopeL", "shoulderSlopeR", 11.75);
        double waistHipLength = Average("waistHipLengthL", "waistHipLengthR", height * 0.122);

        Dictionary<string, double> body = new(StringComparer.Ordinal)
        {
            ["height"] = height,
            ["head_l"] = Read("headHeight", height * 0.139),
            ["bust"] = bust,
            ["underbust"] = Read("underBust", bust * 0.867),
            ["waist"] = waist,
            ["hips"] = hips,
            ["back_width"] = bust * 0.474 * (acrossBack / Math.Max(shoulderWidth * 0.936, 0.1)),
            ["waist_back_width"] = waist * backHipArc / Math.Max(hips, 0.1),
            ["hip_back_width"] = backHipArc,
            ["bust_points"] = Read("bustSeparation", bust * 0.202),
            ["bum_points"] = Read("pelvicWidth", hips * 0.295) * 0.605,
            ["shoulder_w"] = shoulderWidth,
            ["shoulder_incl"] = shoulderSlope,
            ["waist_over_bust_line"] = Read("frontWaistLength", height * 0.260),
            ["waist_line"] = Read("backWaistLength", height * 0.250),
            ["bust_line"] = bustHeight,
            ["vert_bust_line"] = Math.Max(8.0, bustHeight - Read("bustProjectionL", bust * 0.052)),
            ["armscye_depth"] = Math.Max(8.0, armscyeCircumference * 0.301),
            ["neck_w"] = Read("neckBaseCirc", bust * 0.428) * 0.451,
            ["arm_length"] = Average("armLengthL", "armLengthR", height * 0.343),
            ["arm_pose_angle"] = 45.0 + Average("shoulderRollL", "shoulderRollR", 0.75),
            ["wrist"] = Average("wristCircL", "wristCircR", bust * 0.172),
            ["hips_line"] = waistHipLength,
            ["hip_inclination"] = Read("pelvicTilt", 8.0),
            ["leg_circ"] = Average("thighUpperCircL", "thighUpperCircR", hips * 0.580),
            ["crotch_hip_diff"] = Math.Max(2.0, Read("bodyRise", height * 0.160) - waistHipLength)
        };

        Source("height", "height");
        Source("head_l", "headHeight");
        Source("bust", "chest");
        Source("underbust", "underBust");
        Source("waist", "waist");
        Source("hips", "hip");
        Source("back_width", "chest", "acrossBack", "shoulder");
        Source("waist_back_width", "waist", "backHipArc", "hip");
        Source("hip_back_width", "backHipArc");
        Source("bust_points", "bustSeparation");
        Source("bum_points", "pelvicWidth");
        Source("shoulder_w", "shoulder");
        Source("shoulder_incl", "shoulderSlopeL", "shoulderSlopeR");
        Source("waist_over_bust_line", "frontWaistLength");
        Source("waist_line", "backWaistLength");
        Source("bust_line", "bustHeightL", "bustHeightR");
        Source("vert_bust_line", "bustHeightL", "bustHeightR", "bustProjectionL");
        Source("armscye_depth", "armscyeCircL", "armscyeCircR", "armholeDepthL", "armholeDepthR");
        Source("neck_w", "neckBaseCirc");
        Source("arm_length", "armLengthL", "armLengthR");
        Source("arm_pose_angle", "shoulderRollL", "shoulderRollR");
        Source("wrist", "wristCircL", "wristCircR");
        Source("hips_line", "waistHipLengthL", "waistHipLengthR");
        Source("hip_inclination", "pelvicTilt");
        Source("leg_circ", "thighUpperCircL", "thighUpperCircR");
        Source("crotch_hip_diff", "bodyRise", "waistHipLengthL", "waistHipLengthR");

        HashSet<string> signedAngleParameters = new(StringComparer.Ordinal)
        {
            "shoulder_incl",
            "arm_pose_angle",
            "hip_inclination"
        };
        foreach ((string key, double value) in body)
        {
            if (!double.IsFinite(value) || (!signedAngleParameters.Contains(key) && value <= 0))
            {
                throw new InvalidOperationException(
                    $"Mapped GarmentCode parameter {key} is outside its finite physical domain: {value}.");
            }
        }

        return new GarmentCodeBodyMappingResult(
            body,
            sources,
            fallbacks.Order(StringComparer.Ordinal).ToArray());
    }
}
