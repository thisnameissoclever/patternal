using UnrealBuildTool;

public class PatternaUnrealEditorTarget : TargetRules
{
    public PatternaUnrealEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.AddRange(new[] { "PatternaUnreal", "PatternaUnrealEditor" });
    }
}
