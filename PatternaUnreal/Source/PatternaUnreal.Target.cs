using UnrealBuildTool;

public class PatternaUnrealTarget : TargetRules
{
    public PatternaUnrealTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("PatternaUnreal");
    }
}
