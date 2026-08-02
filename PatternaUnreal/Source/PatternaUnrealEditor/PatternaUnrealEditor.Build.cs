using UnrealBuildTool;

public class PatternaUnrealEditor : ModuleRules
{
    public PatternaUnrealEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        SetupModulePhysicsSupport(Target);

        PrivateDependencyModuleNames.AddRange(
            new[]
            {
                "Core",
                "CoreUObject",
                "Engine",
                "UnrealEd",
                "AssetTools",
                "AssetRegistry",
                "DataflowCore",
                "DataflowEngine",
                "Chaos",
                "ChaosClothAsset",
                "ChaosClothAssetEngine",
                "ChaosClothAssetDataflowNodes",
                "ClothingSystemRuntimeCommon",
                "ChaosOutfitAssetEngine",
                "MetaHumanCharacter",
                "MetaHumanCharacterEditor",
                "MetaHumanCoreTechLib"
            }
        );
    }
}
