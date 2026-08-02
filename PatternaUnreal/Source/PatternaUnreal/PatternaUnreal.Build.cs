using UnrealBuildTool;

public class PatternaUnreal : ModuleRules
{
    public PatternaUnreal(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(
            new[]
            {
                "Core",
                "CoreUObject",
                "Engine",
                "Json"
            }
        );

        PrivateDependencyModuleNames.AddRange(
            new[]
            {
                "ChaosClothAsset",
                "ChaosClothAssetEngine"
            }
        );
    }
}
