#include "Modules/ModuleManager.h"

#include "AssetToolsModule.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AutomatedAssetImportData.h"
#include "ChaosClothAsset/ClothAsset.h"
#include "ChaosClothAsset/ClothCollectionGroup.h"
#include "ChaosClothAsset/ClothGeometryTools.h"
#include "ChaosClothAsset/CollectionClothFacade.h"
#include "ChaosClothAsset/CollectionClothFabricFacade.h"
#include "ChaosClothAsset/CollectionClothSelectionFacade.h"
#include "ChaosClothAsset/SimulationMaxDistanceConfigNode.h"
#include "ChaosClothAsset/SimulationSelfCollisionSpheresConfigNode.h"
#include "ChaosClothAsset/SimulationSolverConfigNode.h"
#include "ChaosOutfitAsset/Outfit.h"
#include "ChaosOutfitAsset/OutfitAsset.h"
#include "ChaosOutfitAsset/SizedOutfitSource.h"
#include "Containers/Ticker.h"
#include "Dataflow/DataflowBlueprintLibrary.h"
#include "Dataflow/DataflowGraph.h"
#include "Dataflow/DataflowNode.h"
#include "Dataflow/DataflowObject.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/Texture2D.h"
#include "EditorReimportHandler.h"
#include "FileHelpers.h"
#include "Factories/MaterialFactoryNew.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMisc.h"
#include "Internationalization/Regex.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpressionConstant.h"
#include "Materials/MaterialExpressionConstant3Vector.h"
#include "Materials/MaterialExpressionMultiply.h"
#include "Materials/MaterialExpressionTextureCoordinate.h"
#include "Materials/MaterialExpressionTextureSample.h"
#include "Materials/MaterialExpressionVertexColor.h"
#include "Misc/FileHelper.h"
#include "Misc/App.h"
#include "Misc/Paths.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PointWeightMap.h"
#include "StructUtils/PropertyBag.h"
#include "Utils/ClothingMeshUtils.h"
#include "UObject/UnrealType.h"

DEFINE_LOG_CATEGORY_STATIC(LogPatternaUnrealEditor, Log, All);

namespace PatternaUnrealEditor
{
    constexpr const TCHAR* ClothAssetPath =
        TEXT("/Game/MetaHumans/PatternaFlaredSkirt/ClothAssets/PatternaFlaredSkirt.PatternaFlaredSkirt");
    constexpr const TCHAR* RebuiltClothAssetPath =
        TEXT("/Game/PatternaMeasuredGarments/V2/PatternaFlaredSkirt/ClothAssets/PatternaFlaredSkirt.PatternaFlaredSkirt");
    constexpr const TCHAR* RebuiltClothDestination =
        TEXT("/Game/PatternaMeasuredGarments/V2");
    constexpr const TCHAR* FullDressClothAssetPath =
        TEXT("/Game/PatternaMeasuredGarments/V3/PatternaWrapDress/ClothAssets/PatternaWrapDress.PatternaWrapDress");
    constexpr const TCHAR* FullDressClothDestination =
        TEXT("/Game/PatternaMeasuredGarments/V3");
    constexpr const TCHAR* FittedDressClothAssetPath =
        TEXT("/Game/PatternaMeasuredGarments/V4/PatternaDefaultFemalePencilDress/ClothAssets/PatternaFittedPencilDress.PatternaFittedPencilDress");
    constexpr const TCHAR* FittedDressClothDestination =
        TEXT("/Game/PatternaMeasuredGarments/V4");
    constexpr const TCHAR* ShirtClothAssetPath =
        TEXT("/Game/PatternaMeasuredGarments/V6/PatternaFemaleShirt/ClothAssets/PatternaFemaleShirt.PatternaFemaleShirt");
    constexpr const TCHAR* ShirtClothDestination =
        TEXT("/Game/PatternaMeasuredGarments/V6");
    constexpr const TCHAR* ResizableOutfitAssetPath =
        TEXT("/Game/Outfits/PatternaWrapDress/PatternaWrapDress/PatternaWrapDress_ResizableV8.PatternaWrapDress_ResizableV8");
    constexpr const TCHAR* ResizableOutfitPackagePath =
        TEXT("/Game/Outfits/PatternaWrapDress/PatternaWrapDress/PatternaWrapDress_ResizableV8");
    constexpr const TCHAR* BodyMeshPath =
        TEXT("/Game/PatternaMeasuredV2/MH_Patterna_Female_Default/Body/SKM_MH_Patterna_Female_Default_BodyMesh.SKM_MH_Patterna_Female_Default_BodyMesh");
    constexpr const TCHAR* FaceMeshPath =
        TEXT("/Game/PatternaMeasuredV2/MH_Patterna_Female_Default/Face/SKM_MH_Patterna_Female_Default_FaceMesh.SKM_MH_Patterna_Female_Default_FaceMesh");
    constexpr const TCHAR* BodyPhysicsPath =
        TEXT("/Game/PatternaMeasuredV2/MH_Patterna_Female_Default/Body/PHYS_MH_Patterna_Female_Default.PHYS_MH_Patterna_Female_Default");

    FString GetClothSourcePath()
    {
        return FPaths::ConvertRelativePathToFull(
            FPaths::Combine(
                FPaths::ProjectDir(),
                TEXT("SourceAssets/PatternaFlaredSkirtMeasured/PatternaFlaredSkirt.usda")));
    }

    FString GetGarmentManifestPath()
    {
        return FPaths::ConvertRelativePathToFull(
            FPaths::Combine(
                FPaths::ProjectDir(),
                TEXT("SourceAssets/PatternaFlaredSkirtMeasured/PatternaFlaredSkirt.garment.json")));
    }

    FString GetFullDressSourcePath()
    {
        return FPaths::ConvertRelativePathToFull(
            FPaths::Combine(
                FPaths::ProjectDir(),
                TEXT("SourceAssets/PatternaWrapDressV1/PatternaWrapDress.usda")));
    }

    FString GetFullDressManifestPath()
    {
        return FPaths::ConvertRelativePathToFull(
            FPaths::Combine(
                FPaths::ProjectDir(),
                TEXT("SourceAssets/PatternaWrapDressV1/PatternaWrapDress.garment.json")));
    }

    FString GetFittedDressSourcePath()
    {
        return FPaths::ConvertRelativePathToFull(
            FPaths::Combine(
                FPaths::ProjectDir(),
                TEXT("SourceAssets/GarmentCode/PatternaDefaultFemalePencilDress.usda")));
    }

    FString GetFittedDressManifestPath()
    {
        return FPaths::ConvertRelativePathToFull(
            FPaths::Combine(
                FPaths::ProjectDir(),
                TEXT("SourceAssets/GarmentCode/PatternaDefaultFemalePencilDress.manifest.json")));
    }

    FString GetShirtSourcePath()
    {
        return FPaths::ConvertRelativePathToFull(
            FPaths::Combine(
                FPaths::ProjectDir(),
                TEXT("SourceAssets/GarmentCode/PatternaFemaleShirt.usda")));
    }

    FString GetShirtManifestPath()
    {
        return FPaths::ConvertRelativePathToFull(
            FPaths::Combine(
                FPaths::ProjectDir(),
                TEXT("SourceAssets/GarmentCode/PatternaFemaleShirt.manifest.json")));
    }

    struct FPatternaBendingSettings
    {
        float Warp = 0.0f;
        float Weft = 0.0f;
        float Bias = 0.0f;
    };

    struct FPatternaSimulationCounts
    {
        int32 PanelCount = 0;
        int32 VertexCount = 0;
        int32 TriangleCount = 0;
        int32 SeamCount = 0;
        int32 StitchCount = 0;
        int32 RenderVertexCount = 0;
        int32 RenderTriangleCount = 0;
    };

    bool TryReadManifestNumber(const FString& ManifestJson, const TCHAR* const FieldName, float& OutValue)
    {
        const FRegexPattern Pattern(
            FString::Printf(TEXT("\\\"%s\\\"\\s*:\\s*([0-9eE+.-]+)"), FieldName));
        FRegexMatcher Matcher(Pattern, ManifestJson);
        if (!Matcher.FindNext())
        {
            return false;
        }

        OutValue = FCString::Atof(*Matcher.GetCaptureGroup(1));
        return FMath::IsFinite(OutValue) && OutValue >= 0.0f;
    }

    bool TryReadManifestInteger(const FString& ManifestJson, const TCHAR* const FieldName, int32& OutValue)
    {
        const FRegexPattern Pattern(
            FString::Printf(TEXT("\\\"%s\\\"\\s*:\\s*([0-9]+)"), FieldName));
        FRegexMatcher Matcher(Pattern, ManifestJson);
        if (!Matcher.FindNext())
        {
            return false;
        }

        OutValue = FCString::Atoi(*Matcher.GetCaptureGroup(1));
        return OutValue > 0;
    }

    bool LoadSimulationCounts(
        const FString& ManifestPath,
        FPatternaSimulationCounts& OutCounts)
    {
        FString ManifestJson;
        if (!FFileHelper::LoadFileToString(ManifestJson, *ManifestPath))
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna could not read the garment manifest at %s."),
                *ManifestPath);
            return false;
        }

        const FRegexPattern SimulationPattern(TEXT("\\\"simulation\\\"\\s*:\\s*\\{([^}]*)\\}"));
        FRegexMatcher SimulationMatcher(SimulationPattern, ManifestJson);
        if (!SimulationMatcher.FindNext())
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna garment manifest is missing its simulation object: %s."),
                *ManifestPath);
            return false;
        }

        const FString SimulationJson = SimulationMatcher.GetCaptureGroup(1);
        const FRegexPattern RenderPattern(TEXT("\\\"render\\\"\\s*:\\s*\\{([^}]*)\\}"));
        FRegexMatcher RenderMatcher(RenderPattern, ManifestJson);
        if (!RenderMatcher.FindNext())
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna garment manifest is missing its render object: %s."),
                *ManifestPath);
            return false;
        }

        const FString RenderJson = RenderMatcher.GetCaptureGroup(1);
        const bool bValid =
            TryReadManifestInteger(SimulationJson, TEXT("panelCount"), OutCounts.PanelCount) &&
            TryReadManifestInteger(SimulationJson, TEXT("vertexCount"), OutCounts.VertexCount) &&
            TryReadManifestInteger(SimulationJson, TEXT("triangleCount"), OutCounts.TriangleCount) &&
            TryReadManifestInteger(SimulationJson, TEXT("seamCount"), OutCounts.SeamCount) &&
            TryReadManifestInteger(SimulationJson, TEXT("stitchCount"), OutCounts.StitchCount) &&
            TryReadManifestInteger(RenderJson, TEXT("vertexCount"), OutCounts.RenderVertexCount) &&
            TryReadManifestInteger(RenderJson, TEXT("triangleCount"), OutCounts.RenderTriangleCount);
        if (!bValid)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna garment manifest has invalid simulation, seam, stitch, or render counts: %s."),
                *ManifestPath);
            return false;
        }

        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna loaded garment counts from the manifest. Panels: %d, vertices: %d, triangles: %d, seams: %d, stitches: %d, render vertices: %d, render triangles: %d."),
            OutCounts.PanelCount,
            OutCounts.VertexCount,
            OutCounts.TriangleCount,
            OutCounts.SeamCount,
            OutCounts.StitchCount,
            OutCounts.RenderVertexCount,
            OutCounts.RenderTriangleCount);
        return true;
    }

    bool LoadBendingSettings(
        const FString& ManifestPath,
        FPatternaBendingSettings& OutSettings)
    {
        FString ManifestJson;
        if (!FFileHelper::LoadFileToString(ManifestJson, *ManifestPath))
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna could not read the garment manifest at %s."),
                *ManifestPath);
            return false;
        }

        const bool bValid =
            TryReadManifestNumber(ManifestJson, TEXT("bendWarp"), OutSettings.Warp) &&
            TryReadManifestNumber(ManifestJson, TEXT("bendWeft"), OutSettings.Weft) &&
            TryReadManifestNumber(ManifestJson, TEXT("bendBias"), OutSettings.Bias);
        if (!bValid)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna garment manifest is missing valid bendWarp, bendWeft, or bendBias values."));
            return false;
        }

        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna loaded explicit bending settings from the garment manifest. Warp: %.4f, weft: %.4f, bias: %.4f."),
            OutSettings.Warp,
            OutSettings.Weft,
            OutSettings.Bias);
        return true;
    }

    bool ApplyGarmentMaxDistanceMap(
        UChaosClothAsset* const ClothAsset,
        const bool bUseShoulderSupport,
        const bool bHoldHighestBand,
        const bool bUseFullyDynamicGarment,
        const float MaxDistanceHighCm)
    {
        using namespace UE::Chaos::ClothAsset;

        if (!ClothAsset)
        {
            return false;
        }

        constexpr float HeldBandDepthCm = 0.75f;
        constexpr float TransitionDepthCm = 4.5f;
        constexpr float ShoulderHeldDepthCm = 1.25f;
        constexpr float ShoulderSupportDepthCm = 25.0f;
        constexpr float ShoulderRestMaxDistanceCm = 0.25f;
        const FName MaxDistanceMapName(TEXT("MaxDistance"));
        const FName KinematicSelectionName(TEXT("KinematicVertices3D"));

        const TArray<TSharedRef<const FManagedArrayCollection>>& SourceCollections =
            static_cast<const UChaosClothAsset*>(ClothAsset)->GetClothCollections();
        TArray<TSharedRef<const FManagedArrayCollection>> UpdatedCollections;
        UpdatedCollections.Reserve(SourceCollections.Num());

        int32 TotalVertices = 0;
        int32 HeldVertices = 0;
        int32 StabilizedVertices = 0;
        int32 FullyDynamicVertices = 0;
        bool bAllLodsValid = SourceCollections.Num() > 0;

        for (int32 LodIndex = 0; LodIndex < SourceCollections.Num(); ++LodIndex)
        {
            TSharedRef<FManagedArrayCollection> UpdatedCollection =
                MakeShared<FManagedArrayCollection>(*SourceCollections[LodIndex]);
            FCollectionClothFacade ClothFacade(UpdatedCollection);
            const TConstArrayView<FVector3f> Positions = ClothFacade.GetSimPosition3D();
            if (!ClothFacade.IsValid() || Positions.IsEmpty())
            {
                bAllLodsValid = false;
                UpdatedCollections.Emplace(MoveTemp(UpdatedCollection));
                continue;
            }

            float TopZ = -TNumericLimits<float>::Max();
            for (const FVector3f& Position : Positions)
            {
                TopZ = FMath::Max(TopZ, Position.Z);
            }

            ClothFacade.AddWeightMap(MaxDistanceMapName);
            TArrayView<float> MaxDistanceWeights = ClothFacade.GetWeightMap(MaxDistanceMapName);
            if (MaxDistanceWeights.Num() != Positions.Num())
            {
                bAllLodsValid = false;
                UpdatedCollections.Emplace(MoveTemp(UpdatedCollection));
                continue;
            }

            int32 LodHeldVertices = 0;
            int32 LodStabilizedVertices = 0;
            int32 LodFullyDynamicVertices = 0;
            for (int32 VertexIndex = 0; VertexIndex < Positions.Num(); ++VertexIndex)
            {
                const float DepthBelowTopCm = TopZ - Positions[VertexIndex].Z;
                float Weight = 1.0f;
                if (bUseShoulderSupport && DepthBelowTopCm <= ShoulderSupportDepthCm)
                {
                    if (DepthBelowTopCm <= ShoulderHeldDepthCm)
                    {
                        Weight = 0.0f;
                    }
                    else
                    {
                        const float NormalizedDepth = FMath::Clamp(
                            (DepthBelowTopCm - ShoulderHeldDepthCm) /
                                (ShoulderSupportDepthCm - ShoulderHeldDepthCm),
                            0.0f,
                            1.0f);
                        const float RefinementBlend = FMath::Pow(NormalizedDepth, 5.0f);
                        const float MaximumDistanceCm = FMath::Lerp(
                            ShoulderRestMaxDistanceCm,
                            MaxDistanceHighCm,
                            RefinementBlend);
                        Weight = MaximumDistanceCm / MaxDistanceHighCm;
                    }
                }
                else if (bHoldHighestBand && DepthBelowTopCm <= TransitionDepthCm)
                {
                    Weight = 0.0f;
                    if (DepthBelowTopCm > HeldBandDepthCm)
                    {
                        const float LinearWeight = FMath::Clamp(
                            (DepthBelowTopCm - HeldBandDepthCm) /
                                (TransitionDepthCm - HeldBandDepthCm),
                            0.0f,
                            1.0f);
                        Weight = LinearWeight * LinearWeight * (3.0f - (2.0f * LinearWeight));
                    }
                }
                else if (bUseFullyDynamicGarment)
                {
                    Weight = 1.0f;
                }

                MaxDistanceWeights[VertexIndex] = Weight;
                LodHeldVertices += FMath::IsNearlyZero(Weight) ? 1 : 0;
                LodStabilizedVertices += Weight < 0.999f && !FMath::IsNearlyZero(Weight) ? 1 : 0;
                LodFullyDynamicVertices += Weight >= 0.999f ? 1 : 0;
            }

            FCollectionClothSelectionFacade SelectionFacade(UpdatedCollection);
            SelectionFacade.DefineSchema();
            TSet<int32> KinematicVertices = FClothGeometryTools::GenerateKinematicVertices3D(
                UpdatedCollection,
                MaxDistanceMapName,
                FVector2f(0.0f, MaxDistanceHighCm),
                NAME_None);
            SelectionFacade.FindOrAddSelectionSet(
                KinematicSelectionName,
                ClothCollectionGroup::SimVertices3D) = MoveTemp(KinematicVertices);

            TotalVertices += Positions.Num();
            HeldVertices += LodHeldVertices;
            StabilizedVertices += LodStabilizedVertices;
            FullyDynamicVertices += LodFullyDynamicVertices;
            bAllLodsValid = bAllLodsValid && LodFullyDynamicVertices > 0 &&
                (!bUseShoulderSupport ||
                    (LodHeldVertices > 0 && LodStabilizedVertices > 0)) &&
                (!bHoldHighestBand || LodHeldVertices > 0) &&
                (!bUseFullyDynamicGarment ||
                    (LodHeldVertices == 0 && LodStabilizedVertices == 0));

            UE_LOG(
                LogPatternaUnrealEditor,
                Display,
                TEXT("Patterna garment max-distance LOD %d: %d vertices, %d held at 0 cm, %d locally stabilized, %d fully dynamic, top Z %.2f cm, mode %s."),
                LodIndex,
                Positions.Num(),
                LodHeldVertices,
                LodStabilizedVertices,
                LodFullyDynamicVertices,
                TopZ,
                bUseFullyDynamicGarment
                    ? TEXT("fully dynamic sewing")
                    : bUseShoulderSupport
                        ? TEXT("anchored prefit refinement")
                        : bHoldHighestBand ? TEXT("held upper band") : TEXT("unrestricted"));

            UpdatedCollections.Emplace(MoveTemp(UpdatedCollection));
        }

        if (!bAllLodsValid)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna garment max-distance validation failed. LODs: %d, vertices: %d, held: %d, fully dynamic: %d."),
                SourceCollections.Num(),
                TotalVertices,
                HeldVertices,
                FullyDynamicVertices);
            return false;
        }

        ClothAsset->Build(UpdatedCollections);
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna garment max-distance map built into cloth asset. LODs: %d, vertices: %d, held: %d, locally stabilized: %d, fully dynamic: %d, mode %s."),
            UpdatedCollections.Num(),
            TotalVertices,
            HeldVertices,
            StabilizedVertices,
            FullyDynamicVertices,
            bUseFullyDynamicGarment
                ? TEXT("fully dynamic sewing")
                : bUseShoulderSupport
                    ? TEXT("anchored prefit refinement")
                    : bHoldHighestBand ? TEXT("held upper band") : TEXT("unrestricted"));
        return true;
    }

    bool BuildRenderDeformerBindings(
        UE::Chaos::ClothAsset::FCollectionClothFacade& ClothFacade,
        int32& OutNumInfluences)
    {
        using namespace UE::Chaos::ClothAsset;

        OutNumInfluences = 0;
        if (!ClothFacade.IsValid() ||
            ClothFacade.GetNumSimVertices3D() == 0 ||
            ClothFacade.GetNumSimFaces() == 0 ||
            ClothFacade.GetNumRenderVertices() == 0 ||
            ClothFacade.GetNumRenderFaces() == 0)
        {
            return false;
        }

        if (!ClothFacade.IsValid(EClothCollectionExtendedSchemas::RenderDeformer))
        {
            ClothFacade.DefineSchema(EClothCollectionExtendedSchemas::RenderDeformer);
        }

        const TConstArrayView<FVector3f> SimPositions = ClothFacade.GetSimPosition3D();
        const TConstArrayView<FIntVector3> SimIndices = ClothFacade.GetSimIndices3D();
        const TConstArrayView<FVector3f> RenderPositions = ClothFacade.GetRenderPosition();
        const TConstArrayView<FVector3f> RenderNormals = ClothFacade.GetRenderNormal();
        const TConstArrayView<FIntVector3> RenderIndices = ClothFacade.GetRenderIndices();
        if (RenderPositions.Num() != RenderNormals.Num() ||
            SimPositions.Num() > static_cast<int32>(TNumericLimits<uint16>::Max()) + 1)
        {
            return false;
        }

        TArray<uint32> ScalarSimIndices;
        ScalarSimIndices.Reserve(SimIndices.Num() * 3);
        for (const FIntVector3& Triangle : SimIndices)
        {
            ScalarSimIndices.Add(Triangle.X);
            ScalarSimIndices.Add(Triangle.Y);
            ScalarSimIndices.Add(Triangle.Z);
        }

        TArray<uint32> ScalarRenderIndices;
        ScalarRenderIndices.Reserve(RenderIndices.Num() * 3);
        for (const FIntVector3& Triangle : RenderIndices)
        {
            ScalarRenderIndices.Add(Triangle.X);
            ScalarRenderIndices.Add(Triangle.Y);
            ScalarRenderIndices.Add(Triangle.Z);
        }

        const ClothingMeshUtils::ClothMeshDesc SimMesh(
            SimPositions,
            ScalarSimIndices);
        const ClothingMeshUtils::ClothMeshDesc RenderMesh(
            RenderPositions,
            RenderNormals,
            TConstArrayView<FVector3f>(),
            ScalarRenderIndices);
        FPointWeightMap PointWeights(SimPositions.Num(), 1.0f);
        TArray<FMeshToMeshVertData> Mapping;
        TArray<ClothingMeshUtils::FMeshToMeshFilterSet> FilterSets;
        ClothingMeshUtils::GenerateMeshToMeshVertData(
            Mapping,
            RenderMesh,
            SimMesh,
            &PointWeights,
            false,
            false,
            5.0f,
            FilterSets);

        if (RenderPositions.IsEmpty() || Mapping.Num() % RenderPositions.Num() != 0)
        {
            return false;
        }
        OutNumInfluences = Mapping.Num() / RenderPositions.Num();
        if (OutNumInfluences != 1)
        {
            return false;
        }

        TArrayView<TArray<FVector4f>> PositionBarycentric =
            ClothFacade.GetRenderDeformerPositionBaryCoordsAndDist();
        TArrayView<TArray<FVector4f>> NormalBarycentric =
            ClothFacade.GetRenderDeformerNormalBaryCoordsAndDist();
        TArrayView<TArray<FVector4f>> TangentBarycentric =
            ClothFacade.GetRenderDeformerTangentBaryCoordsAndDist();
        TArrayView<TArray<FIntVector3>> SimulationTriangleIndices =
            ClothFacade.GetRenderDeformerSimIndices3D();
        TArrayView<TArray<float>> InfluenceWeights =
            ClothFacade.GetRenderDeformerWeight();
        TArrayView<float> SkinningBlend = ClothFacade.GetRenderDeformerSkinningBlend();
        if (PositionBarycentric.Num() != RenderPositions.Num() ||
            NormalBarycentric.Num() != RenderPositions.Num() ||
            TangentBarycentric.Num() != RenderPositions.Num() ||
            SimulationTriangleIndices.Num() != RenderPositions.Num() ||
            InfluenceWeights.Num() != RenderPositions.Num() ||
            SkinningBlend.Num() != RenderPositions.Num())
        {
            return false;
        }

        for (int32 RenderVertexIndex = 0; RenderVertexIndex < RenderPositions.Num(); ++RenderVertexIndex)
        {
            const FMeshToMeshVertData& Binding = Mapping[RenderVertexIndex];
            PositionBarycentric[RenderVertexIndex] = { Binding.PositionBaryCoordsAndDist };
            NormalBarycentric[RenderVertexIndex] = { Binding.NormalBaryCoordsAndDist };
            TangentBarycentric[RenderVertexIndex] = { Binding.TangentBaryCoordsAndDist };
            SimulationTriangleIndices[RenderVertexIndex] =
            {
                FIntVector3(
                    Binding.SourceMeshVertIndices[0],
                    Binding.SourceMeshVertIndices[1],
                    Binding.SourceMeshVertIndices[2])
            };
            InfluenceWeights[RenderVertexIndex] = { Binding.Weight };
            SkinningBlend[RenderVertexIndex] = 1.0f;
        }

        for (int32 RenderPatternIndex = 0;
             RenderPatternIndex < ClothFacade.GetNumRenderPatterns();
             ++RenderPatternIndex)
        {
            ClothFacade.GetRenderPattern(RenderPatternIndex)
                .SetRenderDeformerNumInfluences(OutNumInfluences);
        }
        return true;
    }

    bool PreserveDetailedRenderMeshOrBuildFromSimulation(
        UChaosClothAsset* const ClothAsset,
        const TArray<TSharedRef<const FManagedArrayCollection>>& PreRegenerationCollections,
        const bool bForceSimulationRenderMesh)
    {
        using namespace UE::Chaos::ClothAsset;

        if (!ClothAsset)
        {
            return false;
        }

        constexpr const TCHAR* ProjectMaterialPath =
            TEXT("/Game/Patterna/Materials/M_PatternaFabricTwoSided.M_PatternaFabricTwoSided");
        const FSoftObjectPath ProjectMaterialSoftPath(ProjectMaterialPath);
        const TArray<TSharedRef<const FManagedArrayCollection>>& SourceCollections =
            static_cast<const UChaosClothAsset*>(ClothAsset)->GetClothCollections();
        TArray<TSharedRef<const FManagedArrayCollection>> UpdatedCollections;
        UpdatedCollections.Reserve(SourceCollections.Num());

        bool bAllLodsValid = !SourceCollections.IsEmpty();
        int32 TotalRenderPatterns = 0;
        int32 TotalRenderVertices = 0;
        int32 TotalRenderFaces = 0;
        int32 DetailedLodsPreserved = 0;
        int32 SimulationFallbackLodsBuilt = 0;

        for (int32 LodIndex = 0; LodIndex < SourceCollections.Num(); ++LodIndex)
        {
            TSharedRef<FManagedArrayCollection> UpdatedCollection =
                MakeShared<FManagedArrayCollection>(*SourceCollections[LodIndex]);
            FCollectionClothFacade ClothFacade(UpdatedCollection);
            if (!ClothFacade.IsValid() ||
                ClothFacade.GetNumSimPatterns() == 0 ||
                ClothFacade.GetNumSimVertices2D() == 0 ||
                ClothFacade.GetNumSimFaces() == 0)
            {
                bAllLodsValid = false;
                UpdatedCollections.Emplace(MoveTemp(UpdatedCollection));
                continue;
            }

            const int32 SimPatterns = ClothFacade.GetNumSimPatterns();
            const int32 SimVertices = ClothFacade.GetNumSimVertices2D();
            const int32 SimFaces = ClothFacade.GetNumSimFaces();
            const int32 CurrentRenderPatterns = ClothFacade.GetNumRenderPatterns();
            const int32 CurrentRenderVertices = ClothFacade.GetNumRenderVertices();
            const int32 CurrentRenderFaces = ClothFacade.GetNumRenderFaces();
            const bool bCurrentRenderMeshValid =
                CurrentRenderPatterns > 0 &&
                CurrentRenderVertices >= SimVertices &&
                CurrentRenderFaces >= SimFaces;
            const bool bCurrentRenderMeshDetailed =
                bCurrentRenderMeshValid &&
                (CurrentRenderVertices > SimVertices || CurrentRenderFaces > SimFaces);

            const bool bHasPreRegenerationCollection =
                PreRegenerationCollections.IsValidIndex(LodIndex);
            TOptional<FCollectionClothConstFacade> PreRegenerationFacade;
            if (bHasPreRegenerationCollection)
            {
                PreRegenerationFacade.Emplace(PreRegenerationCollections[LodIndex]);
            }

            const bool bPreRegenerationRenderMeshValid =
                PreRegenerationFacade.IsSet() &&
                PreRegenerationFacade->IsValid() &&
                PreRegenerationFacade->GetNumRenderPatterns() > 0 &&
                PreRegenerationFacade->GetNumRenderVertices() >= SimVertices &&
                PreRegenerationFacade->GetNumRenderFaces() >= SimFaces;
            const bool bDetailedPreRegenerationRenderMesh =
                bPreRegenerationRenderMeshValid &&
                (PreRegenerationFacade->GetNumRenderVertices() > SimVertices ||
                 PreRegenerationFacade->GetNumRenderFaces() > SimFaces);
            bool bRestoredPreRegenerationRenderMesh = false;

            if (bForceSimulationRenderMesh)
            {
                FClothGeometryTools::DeleteRenderMesh(UpdatedCollection);
                constexpr bool bGenerateSingleRenderPattern = true;
                FClothGeometryTools::CopySimMeshToRenderMesh(
                    UpdatedCollection,
                    ProjectMaterialSoftPath,
                    bGenerateSingleRenderPattern);
                ++SimulationFallbackLodsBuilt;
            }
            else if (bPreRegenerationRenderMeshValid &&
                (!bCurrentRenderMeshValid ||
                 (bDetailedPreRegenerationRenderMesh && !bCurrentRenderMeshDetailed)))
            {
                FClothGeometryTools::DeleteRenderMesh(UpdatedCollection);
                for (int32 PatternIndex = 0;
                     PatternIndex < PreRegenerationFacade->GetNumRenderPatterns();
                     ++PatternIndex)
                {
                    ClothFacade.AddGetRenderPattern().Initialize(
                        PreRegenerationFacade->GetRenderPattern(PatternIndex),
                        0);
                }
                bRestoredPreRegenerationRenderMesh = true;
                DetailedLodsPreserved += bDetailedPreRegenerationRenderMesh ? 1 : 0;
            }
            else if (!bCurrentRenderMeshValid)
            {
                FClothGeometryTools::DeleteRenderMesh(UpdatedCollection);
                constexpr bool bGenerateSingleRenderPattern = false;
                FClothGeometryTools::CopySimMeshToRenderMesh(
                    UpdatedCollection,
                    ProjectMaterialSoftPath,
                bGenerateSingleRenderPattern);
                ++SimulationFallbackLodsBuilt;
            }

            FClothGeometryTools::RecalculateRenderMeshNormals(UpdatedCollection);
            int32 RenderDeformerInfluences = 0;
            const bool bRenderDeformerBuilt = BuildRenderDeformerBindings(
                ClothFacade,
                RenderDeformerInfluences);

            const int32 RenderPatterns = ClothFacade.GetNumRenderPatterns();
            const int32 RenderVertices = ClothFacade.GetNumRenderVertices();
            const int32 RenderFaces = ClothFacade.GetNumRenderFaces();
            const bool bLodValid =
                RenderPatterns > 0 &&
                (bForceSimulationRenderMesh ? RenderVertices > 0 : RenderVertices >= SimVertices) &&
                RenderFaces >= SimFaces &&
                bRenderDeformerBuilt &&
                RenderDeformerInfluences > 0;
            bAllLodsValid = bAllLodsValid && bLodValid;
            TotalRenderPatterns += RenderPatterns;
            TotalRenderVertices += RenderVertices;
            TotalRenderFaces += RenderFaces;

            UE_LOG(
                LogPatternaUnrealEditor,
                Display,
                TEXT("Patterna render mesh LOD %d: %d patterns, %d vertices, %d faces, pre-regeneration detail available %s, pre-regeneration mesh restored %s, simulation fallback %s, render-deformer bindings built %s with %d influences, valid %s."),
                LodIndex,
                RenderPatterns,
                RenderVertices,
                RenderFaces,
                bDetailedPreRegenerationRenderMesh ? TEXT("yes") : TEXT("no"),
                bRestoredPreRegenerationRenderMesh ? TEXT("yes") : TEXT("no"),
                (!bRestoredPreRegenerationRenderMesh && !bCurrentRenderMeshValid) ? TEXT("yes") : TEXT("no"),
                bRenderDeformerBuilt ? TEXT("yes") : TEXT("no"),
                RenderDeformerInfluences,
                bLodValid ? TEXT("yes") : TEXT("no"));

            UpdatedCollections.Emplace(MoveTemp(UpdatedCollection));
        }

        if (!bAllLodsValid)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna could not preserve or rebuild a valid render mesh for every cloth LOD."));
            return false;
        }

        ClothAsset->Build(UpdatedCollections);
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna prepared cloth render meshes. LODs: %d, detailed LODs preserved: %d, simulation fallbacks built: %d, render patterns: %d, vertices: %d, faces: %d."),
            UpdatedCollections.Num(),
            DetailedLodsPreserved,
            SimulationFallbackLodsBuilt,
            TotalRenderPatterns,
            TotalRenderVertices,
            TotalRenderFaces);
        return true;
    }

    bool ConfigureFabricCollisionThickness(UChaosClothAsset* const ClothAsset)
    {
        using namespace UE::Chaos::ClothAsset;

        if (!ClothAsset)
        {
            return false;
        }

        // The previous 2 cm shell was nearly sixty times thicker than the
        // current 0.34 mm fabric and visibly pushed the skirt into a rigid,
        // tented silhouette. The 0.8 mm envelope remains wider than the
        // physical textile while avoiding a visibly inflated shell.
        constexpr float CollisionThicknessCm = 0.08f;
        const TArray<TSharedRef<const FManagedArrayCollection>>& SourceCollections =
            static_cast<const UChaosClothAsset*>(ClothAsset)->GetClothCollections();
        TArray<TSharedRef<const FManagedArrayCollection>> UpdatedCollections;
        UpdatedCollections.Reserve(SourceCollections.Num());

        bool bAllLodsValid = !SourceCollections.IsEmpty();
        int32 TotalFabrics = 0;
        for (int32 LodIndex = 0; LodIndex < SourceCollections.Num(); ++LodIndex)
        {
            TSharedRef<FManagedArrayCollection> UpdatedCollection =
                MakeShared<FManagedArrayCollection>(*SourceCollections[LodIndex]);
            FCollectionClothFacade ClothFacade(UpdatedCollection);
            const int32 NumFabrics = ClothFacade.GetNumFabrics();
            if (!ClothFacade.IsValid() || NumFabrics == 0)
            {
                bAllLodsValid = false;
                UpdatedCollections.Emplace(MoveTemp(UpdatedCollection));
                continue;
            }

            for (int32 FabricIndex = 0; FabricIndex < NumFabrics; ++FabricIndex)
            {
                FCollectionClothFabricFacade Fabric = ClothFacade.GetFabric(FabricIndex);
                const auto BendingStiffness = Fabric.GetBendingStiffness();
                const float BucklingRatio = Fabric.GetBucklingRatio();
                const auto BucklingStiffness = Fabric.GetBucklingStiffness();
                const auto StretchStiffness = Fabric.GetStretchStiffness();
                const float PreviousCollisionThickness = Fabric.GetCollisionThickness();
                Fabric.Initialize(
                    BendingStiffness,
                    BucklingRatio,
                    BucklingStiffness,
                    StretchStiffness,
                    Fabric.GetDensity(),
                    Fabric.GetFriction(),
                    Fabric.GetDamping(),
                    Fabric.GetPressure(),
                    Fabric.GetLayer(),
                    CollisionThicknessCm);
                ++TotalFabrics;

                UE_LOG(
                    LogPatternaUnrealEditor,
                    Display,
                    TEXT("Patterna cloth LOD %d fabric %d collision thickness: %.2f cm to %.2f cm."),
                    LodIndex,
                    FabricIndex,
                    PreviousCollisionThickness,
                    CollisionThicknessCm);
            }

            UpdatedCollections.Emplace(MoveTemp(UpdatedCollection));
        }

        if (!bAllLodsValid || TotalFabrics == 0)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna could not configure collision thickness for every cloth LOD."));
            return false;
        }

        ClothAsset->Build(UpdatedCollections);
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna configured %.2f cm fabric collision thickness on %d fabrics across %d LODs."),
            CollisionThicknessCm,
            TotalFabrics,
            UpdatedCollections.Num());
        return true;
    }

    bool ConfigureTwoSidedGarmentMaterials(
        UChaosClothAsset* const ClothAsset,
        TArray<UPackage*>& OutMaterialPackages)
    {
        using namespace UE::Chaos::ClothAsset;

        if (!ClothAsset)
        {
            return false;
        }

        constexpr const TCHAR* SourceMaterialPath =
            TEXT("/ChaosClothAsset/Materials/USDImportMaterial.USDImportMaterial");
        constexpr const TCHAR* ProjectMaterialPath =
            TEXT("/Game/Patterna/Materials/M_PatternaFabricTwoSided.M_PatternaFabricTwoSided");

        UMaterial* const SourceMaterial = LoadObject<UMaterial>(nullptr, SourceMaterialPath);
        UMaterial* ProjectMaterial = LoadObject<UMaterial>(nullptr, ProjectMaterialPath);
        if (!SourceMaterial)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna could not load the source USD cloth material."));
            return false;
        }

        if (!ProjectMaterial)
        {
            UMaterialFactoryNew* const MaterialFactory = NewObject<UMaterialFactoryNew>();
            ProjectMaterial = Cast<UMaterial>(
                FAssetToolsModule::GetModule().Get().CreateAsset(
                    TEXT("M_PatternaFabricTwoSided"),
                    TEXT("/Game/Patterna/Materials"),
                    UMaterial::StaticClass(),
                    MaterialFactory));
        }

        if (!ProjectMaterial)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna could not create its project-local fabric material."));
            return false;
        }

        const FLinearColor FabricBaseColor(0.045f, 0.006f, 0.016f);
        constexpr const TCHAR* FabricNormalTexturePath =
            TEXT("/Game/Patterna/Materials/T_PatternaCottonPoplinNormal.T_PatternaCottonPoplinNormal");
        UTexture2D* FabricNormalTexture = LoadObject<UTexture2D>(
            nullptr,
            FabricNormalTexturePath);
        if (!FabricNormalTexture)
        {
            UPackage* const TexturePackage = CreatePackage(
                TEXT("/Game/Patterna/Materials/T_PatternaCottonPoplinNormal"));
            FabricNormalTexture = NewObject<UTexture2D>(
                TexturePackage,
                TEXT("T_PatternaCottonPoplinNormal"),
                RF_Public | RF_Standalone);
        }
        if (!FabricNormalTexture)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna could not create its cotton poplin normal texture."));
            return false;
        }

        constexpr int32 TextureSize = 128;
        constexpr float ThreadsPerTile = 8.0f;
        TArray<FColor> NormalPixels;
        NormalPixels.SetNumUninitialized(TextureSize * TextureSize);
        const auto SampleWeaveHeight = [=](const float U, const float V)
        {
            const float WarpPhase = 2.0f * PI * ThreadsPerTile * U;
            const float WeftPhase = 2.0f * PI * ThreadsPerTile * V;
            return
                0.55f * FMath::Sin(WarpPhase) +
                0.42f * FMath::Sin(WeftPhase) +
                0.18f * FMath::Sin(WarpPhase) * FMath::Sin(WeftPhase);
        };
        constexpr float GradientScale = 0.38f;
        for (int32 Y = 0; Y < TextureSize; ++Y)
        {
            for (int32 X = 0; X < TextureSize; ++X)
            {
                const float U = (X + 0.5f) / TextureSize;
                const float V = (Y + 0.5f) / TextureSize;
                const float TexelStep = 1.0f / TextureSize;
                const float GradientX =
                    (SampleWeaveHeight(U + TexelStep, V) - SampleWeaveHeight(U - TexelStep, V)) *
                    GradientScale;
                const float GradientY =
                    (SampleWeaveHeight(U, V + TexelStep) - SampleWeaveHeight(U, V - TexelStep)) *
                    GradientScale;
                const FVector3f Normal = FVector3f(-GradientX, -GradientY, 1.0f).GetSafeNormal();
                NormalPixels[(Y * TextureSize) + X] = FColor(
                    FMath::Clamp(FMath::RoundToInt((Normal.X * 0.5f + 0.5f) * 255.0f), 0, 255),
                    FMath::Clamp(FMath::RoundToInt((Normal.Y * 0.5f + 0.5f) * 255.0f), 0, 255),
                    FMath::Clamp(FMath::RoundToInt((Normal.Z * 0.5f + 0.5f) * 255.0f), 0, 255),
                    255);
            }
        }
        FabricNormalTexture->Modify();
        FabricNormalTexture->PreEditChange(nullptr);
        FabricNormalTexture->Source.Init(
            TextureSize,
            TextureSize,
            1,
            1,
            TSF_BGRA8,
            reinterpret_cast<const uint8*>(NormalPixels.GetData()));
        FabricNormalTexture->CompressionSettings = TC_Normalmap;
        FabricNormalTexture->CompressionNoAlpha = true;
        FabricNormalTexture->SRGB = false;
        FabricNormalTexture->MipGenSettings = TMGS_SimpleAverage;
        FabricNormalTexture->LODGroup = TEXTUREGROUP_WorldNormalMap;
        FabricNormalTexture->AddressX = TA_Wrap;
        FabricNormalTexture->AddressY = TA_Wrap;
        FabricNormalTexture->PostEditChange();
        FabricNormalTexture->MarkPackageDirty();
        OutMaterialPackages.AddUnique(FabricNormalTexture->GetPackage());

        constexpr const TCHAR* FabricColorTexturePath =
            TEXT("/Game/Patterna/Materials/T_PatternaCottonPoplinColor.T_PatternaCottonPoplinColor");
        UTexture2D* FabricColorTexture = LoadObject<UTexture2D>(
            nullptr,
            FabricColorTexturePath);
        if (!FabricColorTexture)
        {
            UPackage* const TexturePackage = CreatePackage(
                TEXT("/Game/Patterna/Materials/T_PatternaCottonPoplinColor"));
            FabricColorTexture = NewObject<UTexture2D>(
                TexturePackage,
                TEXT("T_PatternaCottonPoplinColor"),
                RF_Public | RF_Standalone);
        }
        if (!FabricColorTexture)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna could not create its cotton poplin color texture."));
            return false;
        }

        TArray<FColor> ColorPixels;
        ColorPixels.SetNumUninitialized(TextureSize * TextureSize);
        for (int32 Y = 0; Y < TextureSize; ++Y)
        {
            for (int32 X = 0; X < TextureSize; ++X)
            {
                const float U = (X + 0.5f) / TextureSize;
                const float V = (Y + 0.5f) / TextureSize;
                const float WarpPhase = 2.0f * PI * ThreadsPerTile * U;
                const float WeftPhase = 2.0f * PI * ThreadsPerTile * V;
                const float YarnVariation =
                    0.10f * FMath::Sin(WarpPhase) +
                    0.065f * FMath::Sin(WeftPhase) +
                    0.035f * FMath::Sin(WarpPhase + WeftPhase) +
                    0.02f * FMath::Sin((3.0f * WarpPhase) - (2.0f * WeftPhase));
                FLinearColor YarnColor = FabricBaseColor * (1.0f + YarnVariation);
                YarnColor.A = 1.0f;
                ColorPixels[(Y * TextureSize) + X] = YarnColor.ToFColorSRGB();
            }
        }
        FabricColorTexture->Modify();
        FabricColorTexture->PreEditChange(nullptr);
        FabricColorTexture->Source.Init(
            TextureSize,
            TextureSize,
            1,
            1,
            TSF_BGRA8,
            reinterpret_cast<const uint8*>(ColorPixels.GetData()));
        FabricColorTexture->CompressionSettings = TC_Default;
        FabricColorTexture->CompressionNoAlpha = true;
        FabricColorTexture->SRGB = true;
        FabricColorTexture->MipGenSettings = TMGS_SimpleAverage;
        FabricColorTexture->LODGroup = TEXTUREGROUP_World;
        FabricColorTexture->AddressX = TA_Wrap;
        FabricColorTexture->AddressY = TA_Wrap;
        FabricColorTexture->PostEditChange();
        FabricColorTexture->MarkPackageDirty();
        OutMaterialPackages.AddUnique(FabricColorTexture->GetPackage());

        bool bProjectMaterialChanged = false;
        ProjectMaterial->Modify();
        UMaterialEditorOnlyData* const EditorData = ProjectMaterial->GetEditorOnlyData();

        UMaterialExpressionMultiply* FabricColorMultiply =
            Cast<UMaterialExpressionMultiply>(EditorData->BaseColor.Expression);
        UMaterialExpressionTextureSample* FabricColorSample = FabricColorMultiply
            ? Cast<UMaterialExpressionTextureSample>(FabricColorMultiply->A.Expression)
            : Cast<UMaterialExpressionTextureSample>(EditorData->BaseColor.Expression);
        if (!FabricColorMultiply)
        {
            FabricColorMultiply = NewObject<UMaterialExpressionMultiply>(ProjectMaterial);
            ProjectMaterial->GetExpressionCollection().AddExpression(FabricColorMultiply);
            if (FabricColorSample)
            {
                FabricColorMultiply->A.Connect(0, FabricColorSample);
            }
            EditorData->BaseColor.Connect(0, FabricColorMultiply);
            bProjectMaterialChanged = true;
        }
        if (!FabricColorSample)
        {
            FabricColorSample = NewObject<UMaterialExpressionTextureSample>(ProjectMaterial);
            ProjectMaterial->GetExpressionCollection().AddExpression(FabricColorSample);
            FabricColorMultiply->A.Connect(0, FabricColorSample);
            bProjectMaterialChanged = true;
        }
        UMaterialExpressionVertexColor* FabricVertexColor =
            Cast<UMaterialExpressionVertexColor>(FabricColorMultiply->B.Expression);
        if (!FabricVertexColor)
        {
            FabricVertexColor = NewObject<UMaterialExpressionVertexColor>(ProjectMaterial);
            ProjectMaterial->GetExpressionCollection().AddExpression(FabricVertexColor);
            FabricColorMultiply->B.Connect(0, FabricVertexColor);
            bProjectMaterialChanged = true;
        }
        UMaterialExpressionTextureCoordinate* FabricColorCoordinates =
            Cast<UMaterialExpressionTextureCoordinate>(FabricColorSample->Coordinates.Expression);
        if (!FabricColorCoordinates)
        {
            FabricColorCoordinates = NewObject<UMaterialExpressionTextureCoordinate>(ProjectMaterial);
            ProjectMaterial->GetExpressionCollection().AddExpression(FabricColorCoordinates);
            FabricColorSample->Coordinates.Connect(0, FabricColorCoordinates);
            bProjectMaterialChanged = true;
        }
        FabricColorSample->Texture = FabricColorTexture;
        FabricColorSample->SamplerType = SAMPLERTYPE_Color;
        FabricColorSample->ConstCoordinate = 0;
        FabricColorCoordinates->CoordinateIndex = 0;
        FabricColorCoordinates->UTiling = 96.0f;
        FabricColorCoordinates->VTiling = 64.0f;
        bProjectMaterialChanged = true;

        UMaterialExpressionConstant* Roughness =
            Cast<UMaterialExpressionConstant>(EditorData->Roughness.Expression);
        if (!Roughness)
        {
            Roughness = NewObject<UMaterialExpressionConstant>(ProjectMaterial);
            ProjectMaterial->GetExpressionCollection().AddExpression(Roughness);
            EditorData->Roughness.Connect(0, Roughness);
            bProjectMaterialChanged = true;
        }
        if (!FMath::IsNearlyEqual(Roughness->R, 0.78f))
        {
            Roughness->R = 0.78f;
            bProjectMaterialChanged = true;
        }

        UMaterialExpressionConstant* Specular =
            Cast<UMaterialExpressionConstant>(EditorData->Specular.Expression);
        if (!Specular)
        {
            Specular = NewObject<UMaterialExpressionConstant>(ProjectMaterial);
            ProjectMaterial->GetExpressionCollection().AddExpression(Specular);
            EditorData->Specular.Connect(0, Specular);
            bProjectMaterialChanged = true;
        }

        UMaterialExpressionTextureSample* FabricNormalSample =
            Cast<UMaterialExpressionTextureSample>(EditorData->Normal.Expression);
        if (!FabricNormalSample)
        {
            FabricNormalSample = NewObject<UMaterialExpressionTextureSample>(ProjectMaterial);
            ProjectMaterial->GetExpressionCollection().AddExpression(FabricNormalSample);
            EditorData->Normal.Connect(0, FabricNormalSample);
            bProjectMaterialChanged = true;
        }
        UMaterialExpressionTextureCoordinate* FabricCoordinates =
            Cast<UMaterialExpressionTextureCoordinate>(FabricNormalSample->Coordinates.Expression);
        if (!FabricCoordinates)
        {
            FabricCoordinates = NewObject<UMaterialExpressionTextureCoordinate>(ProjectMaterial);
            ProjectMaterial->GetExpressionCollection().AddExpression(FabricCoordinates);
            FabricNormalSample->Coordinates.Connect(0, FabricCoordinates);
            bProjectMaterialChanged = true;
        }
        FabricNormalSample->Texture = FabricNormalTexture;
        FabricNormalSample->SamplerType = SAMPLERTYPE_Normal;
        FabricNormalSample->ConstCoordinate = 0;
        FabricCoordinates->CoordinateIndex = 0;
        FabricCoordinates->UTiling = 96.0f;
        FabricCoordinates->VTiling = 64.0f;
        bProjectMaterialChanged = true;
        if (!FMath::IsNearlyEqual(Specular->R, 0.16f))
        {
            Specular->R = 0.16f;
            bProjectMaterialChanged = true;
        }

        UMaterialExpressionConstant3Vector* SubsurfaceColor =
            Cast<UMaterialExpressionConstant3Vector>(EditorData->SubsurfaceColor.Expression);
        if (!SubsurfaceColor)
        {
            SubsurfaceColor = NewObject<UMaterialExpressionConstant3Vector>(ProjectMaterial);
            ProjectMaterial->GetExpressionCollection().AddExpression(SubsurfaceColor);
            EditorData->SubsurfaceColor.Connect(0, SubsurfaceColor);
            bProjectMaterialChanged = true;
        }
        const FLinearColor FabricSubsurfaceColor(0.12f, 0.012f, 0.035f);
        if (!SubsurfaceColor->Constant.Equals(FabricSubsurfaceColor, 0.0001f))
        {
            SubsurfaceColor->Constant = FabricSubsurfaceColor;
            bProjectMaterialChanged = true;
        }

        UMaterialExpressionConstant3Vector* EmissiveColor =
            Cast<UMaterialExpressionConstant3Vector>(EditorData->EmissiveColor.Expression);
        if (!EmissiveColor)
        {
            EmissiveColor = NewObject<UMaterialExpressionConstant3Vector>(ProjectMaterial);
            ProjectMaterial->GetExpressionCollection().AddExpression(EmissiveColor);
            EditorData->EmissiveColor.Connect(0, EmissiveColor);
            bProjectMaterialChanged = true;
        }
        const FLinearColor FabricAmbientLift(0.005f, 0.0005f, 0.0015f);
        if (!EmissiveColor->Constant.Equals(FabricAmbientLift, 0.0001f))
        {
            EmissiveColor->Constant = FabricAmbientLift;
            bProjectMaterialChanged = true;
        }

        if (!ProjectMaterial->TwoSided)
        {
            ProjectMaterial->TwoSided = true;
            bProjectMaterialChanged = true;
        }
        if (ProjectMaterial->GetShadingModels().GetFirstShadingModel() != MSM_Cloth)
        {
            ProjectMaterial->SetShadingModel(MSM_Cloth);
            bProjectMaterialChanged = true;
        }
        if (ProjectMaterial->BlendMode != BLEND_Opaque)
        {
            ProjectMaterial->BlendMode = BLEND_Opaque;
            bProjectMaterialChanged = true;
        }

        if (bProjectMaterialChanged)
        {
            ProjectMaterial->PostEditChange();
            ProjectMaterial->MarkPackageDirty();
            UE_LOG(
                LogPatternaUnrealEditor,
                Display,
                TEXT("Patterna configured its project-local fabric with two-sided cloth shading, cotton-poplin weave normals, soft subsurface wrap, calibrated roughness, and a low ambient lift."));
        }

        if (SourceMaterial->TwoSided)
        {
            SourceMaterial->Modify();
            SourceMaterial->TwoSided = false;
            SourceMaterial->PostEditChange();
            SourceMaterial->MarkPackageDirty();
            OutMaterialPackages.AddUnique(SourceMaterial->GetPackage());
            UE_LOG(
                LogPatternaUnrealEditor,
                Display,
                TEXT("Patterna restored the shared engine USD cloth material to one-sided rendering."));
        }

        const FSoftObjectPath ProjectMaterialSoftPath(ProjectMaterial);
        const TArray<TSharedRef<const FManagedArrayCollection>>& SourceCollections =
            static_cast<const UChaosClothAsset*>(ClothAsset)->GetClothCollections();
        TArray<TSharedRef<const FManagedArrayCollection>> UpdatedCollections;
        UpdatedCollections.Reserve(SourceCollections.Num());
        int32 MaterialSlotsUpdated = 0;
        bool bAllLodsValid = !SourceCollections.IsEmpty();

        for (const TSharedRef<const FManagedArrayCollection>& SourceCollection : SourceCollections)
        {
            TSharedRef<FManagedArrayCollection> UpdatedCollection =
                MakeShared<FManagedArrayCollection>(*SourceCollection);
            FCollectionClothFacade ClothFacade(UpdatedCollection);
            TArrayView<FSoftObjectPath> MaterialPaths =
                ClothFacade.GetRenderMaterialSoftObjectPathName();
            if (MaterialPaths.IsEmpty())
            {
                bAllLodsValid = false;
            }
            for (FSoftObjectPath& MaterialPath : MaterialPaths)
            {
                MaterialPath = ProjectMaterialSoftPath;
                ++MaterialSlotsUpdated;
            }
            UpdatedCollections.Emplace(MoveTemp(UpdatedCollection));
        }

        if (!bAllLodsValid || MaterialSlotsUpdated == 0)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna could not assign its project-local fabric material to every cloth LOD."));
            return false;
        }

        ClothAsset->Build(UpdatedCollections);
        OutMaterialPackages.AddUnique(ProjectMaterial->GetPackage());
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna assigned project-local two-sided material %s to %d cloth material slots."),
            *ProjectMaterial->GetPathName(),
            MaterialSlotsUpdated);
        return true;
    }

    bool RepairClothBindingsAtPath(
        const TCHAR* InClothAssetPath,
        const FString& ManifestPath)
    {
        FModuleManager::Get().LoadModuleChecked<IModuleInterface>(TEXT("ChaosClothAssetDataflowNodes"));

        FPatternaBendingSettings BendingSettings;
        if (!LoadBendingSettings(ManifestPath, BendingSettings))
        {
            return false;
        }

        const bool bIsFittedDress = FString(InClothAssetPath).Contains(
            TEXT(".PatternaFittedPencilDress"),
            ESearchCase::IgnoreCase);
        const bool bIsShirt = FString(InClothAssetPath).Contains(
            TEXT(".PatternaFemaleShirt"),
            ESearchCase::IgnoreCase);
        const float MaxDistanceHighCm = bIsShirt ? 5.0f : 100.0f;

        UChaosClothAsset* const ClothAsset = LoadObject<UChaosClothAsset>(nullptr, InClothAssetPath);
        USkeletalMesh* const BodyMesh = LoadObject<USkeletalMesh>(nullptr, BodyMeshPath);
        UPhysicsAsset* const BodyPhysics = LoadObject<UPhysicsAsset>(nullptr, BodyPhysicsPath);

        if (!ClothAsset || !BodyMesh || !BodyPhysics)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna cloth repair could not load all assets. Cloth: %s, body: %s, physics: %s."),
                ClothAsset ? TEXT("loaded") : TEXT("missing"),
                BodyMesh ? TEXT("loaded") : TEXT("missing"),
                BodyPhysics ? TEXT("loaded") : TEXT("missing"));
            return false;
        }

        UDataflow* const Dataflow = ClothAsset->GetDataflowInstance().GetDataflowAsset();
        const TSharedPtr<UE::Dataflow::FGraph> Graph = Dataflow ? Dataflow->GetDataflow() : nullptr;
        if (!Dataflow || !Graph)
        {
            UE_LOG(LogPatternaUnrealEditor, Error, TEXT("Patterna cloth repair found no embedded Dataflow graph."));
            return false;
        }

        Dataflow->Modify();
        ClothAsset->Modify();

        const TArray<TSharedRef<const FManagedArrayCollection>>& LoadedCollections =
            static_cast<const UChaosClothAsset*>(ClothAsset)->GetClothCollections();
        TArray<TSharedRef<const FManagedArrayCollection>> PreRegenerationCollections;
        PreRegenerationCollections.Reserve(LoadedCollections.Num());
        for (const TSharedRef<const FManagedArrayCollection>& LoadedCollection : LoadedCollections)
        {
            PreRegenerationCollections.Emplace(
                MakeShared<FManagedArrayCollection>(*LoadedCollection));
        }

        FInstancedPropertyBag& DataflowVariables =
            ClothAsset->GetDataflowInstance().GetVariables();
        const UPropertyBag* const DataflowVariableStruct =
            DataflowVariables.GetPropertyBagStruct();
        bool bCapturedImportedCollection = false;
        const TConstArrayView<FPropertyBagPropertyDesc> VariableDescriptions =
            DataflowVariableStruct
                ? DataflowVariableStruct->GetPropertyDescs()
                : TConstArrayView<FPropertyBagPropertyDesc>();
        for (const FPropertyBagPropertyDesc& VariableDescription : VariableDescriptions)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Display,
                TEXT("Patterna inspecting Dataflow variable %s with value type %d."),
                *VariableDescription.Name.ToString(),
                static_cast<int32>(VariableDescription.ValueType));
            TValueOrError<FStructView, EPropertyBagResult> CollectionResult =
                DataflowVariables.GetValueStruct(
                    VariableDescription.Name,
                    FManagedArrayCollection::StaticStruct());
            const FStructView* const CollectionView = CollectionResult.TryGetValue();
            if (!CollectionView)
            {
                continue;
            }

            const FManagedArrayCollection& ImportedCollection =
                CollectionView->Get<FManagedArrayCollection>();
            const TSharedRef<FManagedArrayCollection> ImportedCollectionCopy =
                MakeShared<FManagedArrayCollection>(ImportedCollection);
            UE::Chaos::ClothAsset::FCollectionClothFacade ImportedClothFacade(
                ImportedCollectionCopy);
            UE_LOG(
                LogPatternaUnrealEditor,
                Display,
                TEXT("Patterna Dataflow collection variable %s contains %d simulation patterns, %d simulation vertices, %d simulation faces, %d render patterns, %d render vertices, %d render faces."),
                *VariableDescription.Name.ToString(),
                ImportedClothFacade.GetNumSimPatterns(),
                ImportedClothFacade.GetNumSimVertices2D(),
                ImportedClothFacade.GetNumSimFaces(),
                ImportedClothFacade.GetNumRenderPatterns(),
                ImportedClothFacade.GetNumRenderVertices(),
                ImportedClothFacade.GetNumRenderFaces());
            if (ImportedClothFacade.IsValid() &&
                ImportedClothFacade.GetNumSimPatterns() > 0 &&
                ImportedClothFacade.GetNumRenderPatterns() > 0)
            {
                UE::Chaos::ClothAsset::FClothGeometryTools::BindMeshToRootBone(
                    ImportedCollectionCopy,
                    false,
                    true);
                UE::Chaos::ClothAsset::FClothGeometryTools::RecalculateRenderMeshNormals(
                    ImportedCollectionCopy);
                int32 ImportedRenderDeformerInfluences = 0;
                const bool bImportedRenderDeformerBuilt = BuildRenderDeformerBindings(
                    ImportedClothFacade,
                    ImportedRenderDeformerInfluences);
                if (!bImportedRenderDeformerBuilt || ImportedRenderDeformerInfluences <= 0)
                {
                    UE_LOG(
                        LogPatternaUnrealEditor,
                        Error,
                        TEXT("Patterna could not build render-deformer bindings in Dataflow collection variable %s before regeneration."),
                        *VariableDescription.Name.ToString());
                    return false;
                }

                const TSharedRef<FManagedArrayCollection> RegenerationInputCollectionCopy =
                    MakeShared<FManagedArrayCollection>(*ImportedCollectionCopy);
                UE::Chaos::ClothAsset::FCollectionClothFacade RegenerationInputFacade(
                    RegenerationInputCollectionCopy);
                UE::Chaos::ClothAsset::FClothGeometryTools::DeleteRenderMesh(
                    RegenerationInputCollectionCopy);
                constexpr bool bGenerateSingleRegenerationRenderPattern = false;
                UE::Chaos::ClothAsset::FClothGeometryTools::CopySimMeshToRenderMesh(
                    RegenerationInputCollectionCopy,
                    FSoftObjectPath(TEXT("/Game/Patterna/Materials/M_PatternaFabricTwoSided.M_PatternaFabricTwoSided")),
                    bGenerateSingleRegenerationRenderPattern);
                UE::Chaos::ClothAsset::FClothGeometryTools::BindMeshToRootBone(
                    RegenerationInputCollectionCopy,
                    false,
                    true);
                UE::Chaos::ClothAsset::FClothGeometryTools::RecalculateRenderMeshNormals(
                    RegenerationInputCollectionCopy);
                int32 RegenerationRenderDeformerInfluences = 0;
                const bool bRegenerationRenderDeformerBuilt = BuildRenderDeformerBindings(
                    RegenerationInputFacade,
                    RegenerationRenderDeformerInfluences);
                if (!bRegenerationRenderDeformerBuilt ||
                    RegenerationRenderDeformerInfluences <= 0)
                {
                    UE_LOG(
                        LogPatternaUnrealEditor,
                        Error,
                        TEXT("Patterna could not build the safe simulation render proxy for Dataflow collection variable %s."),
                        *VariableDescription.Name.ToString());
                    return false;
                }

                const EPropertyBagResult SetImportedCollectionResult =
                    DataflowVariables.SetValueStruct(
                        VariableDescription.Name,
                        *RegenerationInputCollectionCopy);
                if (SetImportedCollectionResult != EPropertyBagResult::Success)
                {
                    UE_LOG(
                        LogPatternaUnrealEditor,
                        Error,
                        TEXT("Patterna could not write the bound render collection back to Dataflow variable %s before regeneration. Result: %d."),
                        *VariableDescription.Name.ToString(),
                        static_cast<int32>(SetImportedCollectionResult));
                    return false;
                }

                if (PreRegenerationCollections.IsEmpty())
                {
                    PreRegenerationCollections.Emplace(ImportedCollectionCopy);
                }
                else
                {
                    PreRegenerationCollections[0] = ImportedCollectionCopy;
                }

                UE_LOG(
                    LogPatternaUnrealEditor,
                    Display,
                    TEXT("Patterna captured Dataflow collection variable %s before regeneration: %d simulation patterns, %d simulation vertices, %d simulation faces, %d render patterns, %d render vertices, %d render faces."),
                    *VariableDescription.Name.ToString(),
                    ImportedClothFacade.GetNumSimPatterns(),
                    ImportedClothFacade.GetNumSimVertices2D(),
                    ImportedClothFacade.GetNumSimFaces(),
                    ImportedClothFacade.GetNumRenderPatterns(),
                    ImportedClothFacade.GetNumRenderVertices(),
                    ImportedClothFacade.GetNumRenderFaces());
                UE_LOG(
                    LogPatternaUnrealEditor,
                    Display,
                    TEXT("Patterna retained %d render-deformer influence per detailed render vertex and wrote a safe %d-vertex simulation render proxy with %d influence into Dataflow collection variable %s before cloth regeneration."),
                    ImportedRenderDeformerInfluences,
                    RegenerationInputFacade.GetNumRenderVertices(),
                    RegenerationRenderDeformerInfluences,
                    *VariableDescription.Name.ToString());
                bCapturedImportedCollection = true;
                break;
            }
        }

        if (!bCapturedImportedCollection)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Warning,
                TEXT("Patterna found no Dataflow variable containing both simulation and render cloth geometry before regeneration. Variables inspected: %d."),
                VariableDescriptions.Num());
        }

        int32 NodesInspected = 0;
        int32 SkinWeightNodesFound = 0;
        int32 PhysicsNodesFound = 0;
        int32 StretchConfigNodesFound = 0;
        int32 BendingConfigNodesFound = 0;
        int32 MaxDistanceConfigNodesFound = 0;
        int32 SolverConfigNodesFound = 0;
        int32 SelfCollisionSphereNodesFound = 0;
        int32 RestLengthSettingsUpdated = 0;
        int32 FlatBendingSettingsUpdated = 0;
        int32 ConstraintModelSettingsUpdated = 0;
        int32 FabricValueSettingsUpdated = 0;
        int32 ObjectBindingsUpdated = 0;

        for (const TSharedPtr<FDataflowNode>& Node : Graph->GetNodes())
        {
            if (!Node)
            {
                continue;
            }

            ++NodesInspected;
            bool bNodeChanged = false;
            const UScriptStruct* const NodeStruct = Node->TypedScriptStruct();
            const FString StructName = NodeStruct ? NodeStruct->GetName() : FString(TEXT("Unknown"));

            const auto SetEnumValue = [NodeStruct, &Node](
                const FName PropertyName,
                const FString& ValueName) -> bool
            {
                if (!NodeStruct)
                {
                    return false;
                }

                FEnumProperty* const EnumProperty =
                    FindFProperty<FEnumProperty>(NodeStruct, PropertyName);
                if (!EnumProperty)
                {
                    return false;
                }

                const int64 DesiredValue = EnumProperty->GetEnum()->GetValueByNameString(ValueName);
                if (DesiredValue == INDEX_NONE)
                {
                    return false;
                }

                void* const ValuePtr = EnumProperty->ContainerPtrToValuePtr<void>(Node.Get());
                if (EnumProperty->GetUnderlyingProperty()->GetSignedIntPropertyValue(ValuePtr) == DesiredValue)
                {
                    return false;
                }

                EnumProperty->GetUnderlyingProperty()->SetIntPropertyValue(ValuePtr, DesiredValue);
                return true;
            };

            const auto EnableImportedFabricBounds = [NodeStruct, &Node](const FName PropertyName) -> bool
            {
                if (!NodeStruct)
                {
                    return false;
                }

                FStructProperty* const WeightedProperty =
                    FindFProperty<FStructProperty>(NodeStruct, PropertyName);
                if (!WeightedProperty)
                {
                    return false;
                }

                FBoolProperty* const ImportProperty =
                    FindFProperty<FBoolProperty>(WeightedProperty->Struct, TEXT("bImportFabricBounds"));
                if (!ImportProperty)
                {
                    return false;
                }

                void* const WeightedValuePtr =
                    WeightedProperty->ContainerPtrToValuePtr<void>(Node.Get());
                void* const ImportValuePtr =
                    ImportProperty->ContainerPtrToValuePtr<void>(WeightedValuePtr);
                if (ImportProperty->GetPropertyValue(ImportValuePtr))
                {
                    return false;
                }

                ImportProperty->SetPropertyValue(ImportValuePtr, true);
                return true;
            };

            const auto SetExplicitWeightedValue = [NodeStruct, &Node](
                const FName PropertyName,
                const float DesiredValue) -> bool
            {
                if (!NodeStruct)
                {
                    return false;
                }

                FStructProperty* const WeightedProperty =
                    FindFProperty<FStructProperty>(NodeStruct, PropertyName);
                if (!WeightedProperty)
                {
                    return false;
                }

                void* const WeightedValuePtr =
                    WeightedProperty->ContainerPtrToValuePtr<void>(Node.Get());
                bool bChanged = false;
                for (const FName BoundName : { FName(TEXT("Low")), FName(TEXT("High")) })
                {
                    if (FFloatProperty* const BoundProperty =
                        FindFProperty<FFloatProperty>(WeightedProperty->Struct, BoundName))
                    {
                        void* const BoundValuePtr =
                            BoundProperty->ContainerPtrToValuePtr<void>(WeightedValuePtr);
                        if (!FMath::IsNearlyEqual(
                            BoundProperty->GetPropertyValue(BoundValuePtr),
                            DesiredValue))
                        {
                            BoundProperty->SetPropertyValue(BoundValuePtr, DesiredValue);
                            bChanged = true;
                        }
                    }
                }

                for (const FName FlagName :
                    { FName(TEXT("bImportFabricBounds")), FName(TEXT("bBuildFabricMaps")) })
                {
                    if (FBoolProperty* const FlagProperty =
                        FindFProperty<FBoolProperty>(WeightedProperty->Struct, FlagName))
                    {
                        void* const FlagValuePtr =
                            FlagProperty->ContainerPtrToValuePtr<void>(WeightedValuePtr);
                        if (FlagProperty->GetPropertyValue(FlagValuePtr))
                        {
                            FlagProperty->SetPropertyValue(FlagValuePtr, false);
                            bChanged = true;
                        }
                    }
                }

                return bChanged;
            };

            UE_LOG(
                LogPatternaUnrealEditor,
                Verbose,
                TEXT("Patterna Dataflow node %s uses struct %s."),
                *Node->GetName().ToString(),
                *StructName);

            if (NodeStruct)
            {
                if (StructName.Contains(TEXT("SimulationStretchConfig")) &&
                    !StructName.Contains(TEXT("Override")))
                {
                    ++StretchConfigNodesFound;
                    const bool bChangedConstraintModel =
                        SetEnumValue(TEXT("SolverType"), TEXT("XPBD")) |
                        SetEnumValue(TEXT("DistributionType"), TEXT("Anisotropic"));
                    const bool bChangedFabricImports =
                        EnableImportedFabricBounds(TEXT("StretchStiffnessWarp")) |
                        EnableImportedFabricBounds(TEXT("StretchStiffnessWeft")) |
                        EnableImportedFabricBounds(TEXT("StretchStiffnessBias")) |
                        EnableImportedFabricBounds(TEXT("StretchAnisoDamping"));
                    if (bChangedConstraintModel || bChangedFabricImports)
                    {
                        bNodeChanged = true;
                        ConstraintModelSettingsUpdated += bChangedConstraintModel ? 1 : 0;
                        FabricValueSettingsUpdated += bChangedFabricImports ? 1 : 0;
                        UE_LOG(
                            LogPatternaUnrealEditor,
                            Display,
                            TEXT("Patterna configured %s for anisotropic XPBD stretch using imported fabric values."),
                            *Node->GetName().ToString());
                    }

                    if (FBoolProperty* const Use3dRestLengthsProperty =
                        FindFProperty<FBoolProperty>(NodeStruct, TEXT("bStretchUse3dRestLengths")))
                    {
                        void* const ValuePtr =
                            Use3dRestLengthsProperty->ContainerPtrToValuePtr<void>(Node.Get());
                        if (Use3dRestLengthsProperty->GetPropertyValue(ValuePtr))
                        {
                            Use3dRestLengthsProperty->SetPropertyValue(ValuePtr, false);
                            bNodeChanged = true;
                            ++RestLengthSettingsUpdated;
                            UE_LOG(
                                LogPatternaUnrealEditor,
                                Display,
                                TEXT("Patterna changed %s to use 2D pattern-space stretch rest lengths."),
                                *Node->GetName().ToString());
                        }
                    }
                }

                if (StructName.Contains(TEXT("SimulationBendingConfig")) &&
                    !StructName.Contains(TEXT("Override")))
                {
                    ++BendingConfigNodesFound;
                    bool bChangedBendingRestState = false;
                    const bool bChangedConstraintModel =
                        SetEnumValue(TEXT("SolverType"), TEXT("XPBD")) |
                        SetEnumValue(TEXT("DistributionType"), TEXT("Anisotropic"));
                    const bool bChangedFabricImports =
                        SetExplicitWeightedValue(TEXT("BendingStiffnessWarp"), BendingSettings.Warp) |
                        SetExplicitWeightedValue(TEXT("BendingStiffnessWeft"), BendingSettings.Weft) |
                        SetExplicitWeightedValue(TEXT("BendingStiffnessBias"), BendingSettings.Bias) |
                        EnableImportedFabricBounds(TEXT("BendingAnisoDamping")) |
                        EnableImportedFabricBounds(TEXT("AnisoBucklingRatio")) |
                        EnableImportedFabricBounds(TEXT("BucklingStiffnessWarp")) |
                        EnableImportedFabricBounds(TEXT("BucklingStiffnessWeft")) |
                        EnableImportedFabricBounds(TEXT("BucklingStiffnessBias"));
                    if (bChangedConstraintModel || bChangedFabricImports)
                    {
                        bNodeChanged = true;
                        ConstraintModelSettingsUpdated += bChangedConstraintModel ? 1 : 0;
                        FabricValueSettingsUpdated += bChangedFabricImports ? 1 : 0;
                        UE_LOG(
                            LogPatternaUnrealEditor,
                            Display,
                            TEXT("Patterna configured %s for anisotropic XPBD bending using explicit manifest values."),
                            *Node->GetName().ToString());
                    }

                    if (FEnumProperty* const RestAngleTypeProperty =
                        FindFProperty<FEnumProperty>(NodeStruct, TEXT("RestAngleType")))
                    {
                        void* const ValuePtr =
                            RestAngleTypeProperty->ContainerPtrToValuePtr<void>(Node.Get());
                        const int64 FlatnessRatioValue =
                            RestAngleTypeProperty->GetEnum()->GetValueByNameString(TEXT("FlatnessRatio"));
                        if (FlatnessRatioValue != INDEX_NONE &&
                            RestAngleTypeProperty->GetUnderlyingProperty()->GetSignedIntPropertyValue(ValuePtr) !=
                                FlatnessRatioValue)
                        {
                            RestAngleTypeProperty->GetUnderlyingProperty()->SetIntPropertyValue(
                                ValuePtr,
                                FlatnessRatioValue);
                            bChangedBendingRestState = true;
                        }
                    }

                    if (FStructProperty* const FlatnessRatioProperty =
                        FindFProperty<FStructProperty>(NodeStruct, TEXT("FlatnessRatio")))
                    {
                        void* const WeightedValuePtr =
                            FlatnessRatioProperty->ContainerPtrToValuePtr<void>(Node.Get());
                        for (const FName BoundName : { FName(TEXT("Low")), FName(TEXT("High")) })
                        {
                            if (FFloatProperty* const BoundProperty =
                                FindFProperty<FFloatProperty>(FlatnessRatioProperty->Struct, BoundName))
                            {
                                void* const BoundValuePtr =
                                    BoundProperty->ContainerPtrToValuePtr<void>(WeightedValuePtr);
                                if (!FMath::IsNearlyEqual(BoundProperty->GetPropertyValue(BoundValuePtr), 1.0f))
                                {
                                    BoundProperty->SetPropertyValue(BoundValuePtr, 1.0f);
                                    bChangedBendingRestState = true;
                                }
                            }
                        }
                    }

                    if (bChangedBendingRestState)
                    {
                        bNodeChanged = true;
                        ++FlatBendingSettingsUpdated;
                        UE_LOG(
                            LogPatternaUnrealEditor,
                            Display,
                            TEXT("Patterna changed %s to use completely flat fabric bending rest angles."),
                            *Node->GetName().ToString());
                    }
                }

                if (StructName.Contains(TEXT("SimulationMaxDistanceConfig")))
                {
                    ++MaxDistanceConfigNodesFound;
                    FChaosClothAssetSimulationMaxDistanceConfigNode* const MaxDistanceNode =
                        static_cast<FChaosClothAssetSimulationMaxDistanceConfigNode*>(Node.Get());
                    bool bChangedMaxDistance = false;

                    if (!FMath::IsNearlyZero(MaxDistanceNode->MaxDistance.Low))
                    {
                        MaxDistanceNode->MaxDistance.Low = 0.0f;
                        bChangedMaxDistance = true;
                    }
                    if (!FMath::IsNearlyEqual(MaxDistanceNode->MaxDistance.High, MaxDistanceHighCm))
                    {
                        MaxDistanceNode->MaxDistance.High = MaxDistanceHighCm;
                        bChangedMaxDistance = true;
                    }
                    if (MaxDistanceNode->MaxDistance.WeightMap != TEXT("MaxDistance"))
                    {
                        MaxDistanceNode->MaxDistance.WeightMap = TEXT("MaxDistance");
                        bChangedMaxDistance = true;
                    }
                    if (MaxDistanceNode->MaxDistance.bImportFabricBounds)
                    {
                        MaxDistanceNode->MaxDistance.bImportFabricBounds = false;
                        bChangedMaxDistance = true;
                    }
                    if (MaxDistanceNode->MaxDistance.bBuildFabricMaps)
                    {
                        MaxDistanceNode->MaxDistance.bBuildFabricMaps = false;
                        bChangedMaxDistance = true;
                    }
                    if (!MaxDistanceNode->InKinematic.StringValue.IsEmpty())
                    {
                        MaxDistanceNode->InKinematic.StringValue.Empty();
                        bChangedMaxDistance = true;
                    }

                    if (bChangedMaxDistance)
                    {
                        bNodeChanged = true;
                        UE_LOG(
                            LogPatternaUnrealEditor,
                            Display,
                            TEXT("Patterna configured %s with a normalized MaxDistance map, 0 to %.2f cm bounds, and no extra kinematic selection."),
                            *Node->GetName().ToString(),
                            MaxDistanceHighCm);
                    }
                }

                if (StructName.Contains(TEXT("SimulationSolverConfig")))
                {
                    ++SolverConfigNodesFound;
                    FChaosClothAssetSimulationSolverConfigNode* const SolverNode =
                        static_cast<FChaosClothAssetSimulationSolverConfigNode*>(Node.Get());
                    bool bChangedSolver = false;

                    if (SolverNode->NumIterations != 8)
                    {
                        SolverNode->NumIterations = 8;
                        bChangedSolver = true;
                    }
                    if (SolverNode->MaxNumIterations != 12)
                    {
                        SolverNode->MaxNumIterations = 12;
                        bChangedSolver = true;
                    }
                    if (SolverNode->NumSubstepsImported.ImportedValue != 4 ||
                        SolverNode->NumSubstepsImported.bUseImportedValue)
                    {
                        SolverNode->NumSubstepsImported.ImportedValue = 4;
                        SolverNode->NumSubstepsImported.bUseImportedValue = false;
                        bChangedSolver = true;
                    }
                    if (SolverNode->bEnableDynamicSubstepping)
                    {
                        SolverNode->bEnableDynamicSubstepping = false;
                        bChangedSolver = true;
                    }
                    if (SolverNode->bEnableNumSelfCollisionSubsteps ||
                        SolverNode->NumSelfCollisionSubsteps != 4)
                    {
                        SolverNode->bEnableNumSelfCollisionSubsteps = false;
                        SolverNode->NumSelfCollisionSubsteps = 4;
                        bChangedSolver = true;
                    }

                    if (bChangedSolver)
                    {
                        bNodeChanged = true;
                        UE_LOG(
                            LogPatternaUnrealEditor,
                            Display,
                            TEXT("Patterna configured %s for 8 iterations, up to 12 low-frame-rate iterations, and 4 collision substeps."),
                            *Node->GetName().ToString());
                    }
                }

                if (StructName.Contains(TEXT("SimulationSelfCollisionSpheresConfig")))
                {
                    ++SelfCollisionSphereNodesFound;
                    FChaosClothAssetSimulationSelfCollisionSpheresConfigNode* const SelfCollisionNode =
                        static_cast<FChaosClothAssetSimulationSelfCollisionSpheresConfigNode*>(Node.Get());
                    bool bChangedSelfCollision = false;

                    if (!FMath::IsNearlyEqual(SelfCollisionNode->SelfCollisionSphereRadius, 0.12f))
                    {
                        SelfCollisionNode->SelfCollisionSphereRadius = 0.12f;
                        bChangedSelfCollision = true;
                    }
                    if (!FMath::IsNearlyEqual(SelfCollisionNode->SelfCollisionSphereStiffness, 1.0f))
                    {
                        SelfCollisionNode->SelfCollisionSphereStiffness = 1.0f;
                        bChangedSelfCollision = true;
                    }
                    if (!FMath::IsNearlyEqual(SelfCollisionNode->SelfCollisionSphereRadiusCullMultiplier, 1.5f))
                    {
                        SelfCollisionNode->SelfCollisionSphereRadiusCullMultiplier = 1.5f;
                        bChangedSelfCollision = true;
                    }

                    if (bChangedSelfCollision)
                    {
                        bNodeChanged = true;
                        UE_LOG(
                            LogPatternaUnrealEditor,
                            Display,
                            TEXT("Patterna configured %s with 0.12 cm self-collision spheres and full spring stiffness."),
                            *Node->GetName().ToString());
                    }
                }

                if (FObjectPropertyBase* const SkeletalMeshProperty =
                    FindFProperty<FObjectPropertyBase>(NodeStruct, TEXT("SkeletalMesh")))
                {
                    void* const ValuePtr = SkeletalMeshProperty->ContainerPtrToValuePtr<void>(Node.Get());
                    UObject* const CurrentValue = SkeletalMeshProperty->GetObjectPropertyValue(ValuePtr);
                    const FString CurrentPath = CurrentValue ? CurrentValue->GetPathName() : FString();
                    const bool bIsSkinWeightNode = StructName.Contains(TEXT("TransferSkinWeights"));
                    const bool bIsObsoletePatternaBody =
                        CurrentPath.Contains(TEXT("MH_Patterna_Female_Default_FullBody"));

                    if (bIsSkinWeightNode)
                    {
                        ++SkinWeightNodesFound;
                    }

                    if ((bIsSkinWeightNode || bIsObsoletePatternaBody) && CurrentValue != BodyMesh)
                    {
                        UE_LOG(
                            LogPatternaUnrealEditor,
                            Display,
                            TEXT("Patterna replacing skeletal source on %s from %s to %s."),
                            *Node->GetName().ToString(),
                            CurrentValue ? *CurrentPath : TEXT("None"),
                            *BodyMesh->GetPathName());
                        SkeletalMeshProperty->SetObjectPropertyValue(ValuePtr, BodyMesh);
                        bNodeChanged = true;
                        ++ObjectBindingsUpdated;
                    }
                }

                if (FObjectPropertyBase* const PhysicsProperty =
                    FindFProperty<FObjectPropertyBase>(NodeStruct, TEXT("PhysicsAsset")))
                {
                    void* const ValuePtr = PhysicsProperty->ContainerPtrToValuePtr<void>(Node.Get());
                    UObject* const CurrentValue = PhysicsProperty->GetObjectPropertyValue(ValuePtr);
                    const FString CurrentPath = CurrentValue ? CurrentValue->GetPathName() : FString();
                    const bool bIsPhysicsNode = StructName.Contains(TEXT("SetPhysicsAsset"));
                    const bool bIsObsoletePatternaPhysics =
                        CurrentPath.Contains(TEXT("MH_Patterna_Female_Default_FullBody_Physics"));

                    if (bIsPhysicsNode)
                    {
                        ++PhysicsNodesFound;
                    }

                    if ((bIsPhysicsNode || bIsObsoletePatternaPhysics) && CurrentValue != BodyPhysics)
                    {
                        UE_LOG(
                            LogPatternaUnrealEditor,
                            Display,
                            TEXT("Patterna replacing physics source on %s from %s to %s."),
                            *Node->GetName().ToString(),
                            CurrentValue ? *CurrentPath : TEXT("None"),
                            *BodyPhysics->GetPathName());
                        PhysicsProperty->SetObjectPropertyValue(ValuePtr, BodyPhysics);
                        bNodeChanged = true;
                        ++ObjectBindingsUpdated;
                    }
                }
            }

            if (bNodeChanged)
            {
                Node->Invalidate();
                Dataflow->RefreshEdNodeByGuid(Node->GetGuid());
            }
        }

        const TArray<TSharedPtr<FDataflowNode>> TerminalNodes =
            Graph->GetFilteredNodes(FDataflowTerminalNode::StaticType());
        for (const TSharedPtr<FDataflowNode>& TerminalNode : TerminalNodes)
        {
            if (TerminalNode)
            {
                UE_LOG(
                    LogPatternaUnrealEditor,
                    Display,
                    TEXT("Patterna found Dataflow terminal %s using struct %s."),
                    *TerminalNode->GetName().ToString(),
                    TerminalNode->TypedScriptStruct()
                        ? *TerminalNode->TypedScriptStruct()->GetName()
                        : TEXT("Unknown"));
            }
        }

        const bool bHasRequiredNodes =
            SkinWeightNodesFound > 0 &&
            PhysicsNodesFound > 0 &&
            StretchConfigNodesFound > 0 &&
            BendingConfigNodesFound > 0 &&
            MaxDistanceConfigNodesFound == 1 &&
            SolverConfigNodesFound > 0 &&
            SelfCollisionSphereNodesFound > 0;
        const bool bHasTerminal = TerminalNodes.Num() > 0;
        if (!bHasRequiredNodes || !bHasTerminal)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna cloth repair stopped without saving because the loaded Dataflow is incomplete. Nodes: %d, skin-weight nodes: %d, physics nodes: %d, stretch nodes: %d, bending nodes: %d, max-distance nodes: %d, solver nodes: %d, self-collision sphere nodes: %d, terminals: %d."),
                NodesInspected,
                SkinWeightNodesFound,
                PhysicsNodesFound,
                StretchConfigNodesFound,
                BendingConfigNodesFound,
                MaxDistanceConfigNodesFound,
                SolverConfigNodesFound,
                SelfCollisionSphereNodesFound,
                TerminalNodes.Num());
            return false;
        }

        const bool bRegenerated =
            UDataflowBlueprintLibrary::RegenerateAssetFromDataflow(ClothAsset, true);
        if (!bRegenerated)
        {
            UE_LOG(LogPatternaUnrealEditor, Error, TEXT("Patterna cloth repair failed to regenerate the cloth asset."));
            return false;
        }

        const bool bUsesShoulderSupport = bIsFittedDress || bIsShirt;
        const bool bRenderMeshPrepared =
            PreserveDetailedRenderMeshOrBuildFromSimulation(
                ClothAsset,
                PreRegenerationCollections,
                false);
        const bool bFabricCollisionConfigured =
            ConfigureFabricCollisionThickness(ClothAsset);
        const bool bIsFullDress =
            FCString::Stricmp(InClothAssetPath, FullDressClothAssetPath) == 0 ||
            bIsFittedDress;
        const bool bSupportMapBuilt = ApplyGarmentMaxDistanceMap(
            ClothAsset,
            bUsesShoulderSupport,
            !bIsFullDress && !bIsShirt,
            bIsFullDress && !bIsFittedDress,
            MaxDistanceHighCm);
        if (!bFabricCollisionConfigured || !bSupportMapBuilt)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna cloth repair stopped without saving because collision thickness or the garment support map could not be built."));
            return false;
        }

        TArray<UPackage*> PackagesToSave;
        const bool bMaterialsConfigured =
            ConfigureTwoSidedGarmentMaterials(ClothAsset, PackagesToSave);
        if (!bMaterialsConfigured)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna cloth repair stopped without saving because its fabric material could not be configured as two-sided."));
            return false;
        }

        ClothAsset->MarkPackageDirty();
        Dataflow->MarkPackageDirty();
        PackagesToSave.AddUnique(ClothAsset->GetPackage());
        const bool bSaved = UEditorLoadingAndSavingUtils::SavePackages(PackagesToSave, false);
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna cloth repair completed. Nodes inspected: %d, skin-weight nodes: %d, physics nodes: %d, stretch nodes: %d, bending nodes: %d, max-distance nodes: %d, solver nodes: %d, self-collision sphere nodes: %d, 2D rest settings updated: %d, flat bend settings updated: %d, XPBD constraint settings updated: %d, fabric value settings updated: %d, bindings updated: %d, terminals: %d, regenerated: %s, render mesh prepared: %s, fabric collision: %s, support map: %s, two-sided materials: %s, saved: %s."),
            NodesInspected,
            SkinWeightNodesFound,
            PhysicsNodesFound,
            StretchConfigNodesFound,
            BendingConfigNodesFound,
            MaxDistanceConfigNodesFound,
            SolverConfigNodesFound,
            SelfCollisionSphereNodesFound,
            RestLengthSettingsUpdated,
            FlatBendingSettingsUpdated,
            ConstraintModelSettingsUpdated,
            FabricValueSettingsUpdated,
            ObjectBindingsUpdated,
            TerminalNodes.Num(),
            bRegenerated ? TEXT("yes") : TEXT("no"),
            bRenderMeshPrepared ? TEXT("yes") : TEXT("no"),
            bFabricCollisionConfigured ? TEXT("yes") : TEXT("no"),
            bSupportMapBuilt ? TEXT("yes") : TEXT("no"),
            bMaterialsConfigured ? TEXT("yes") : TEXT("no"),
            bSaved ? TEXT("yes") : TEXT("no"));
        return bRegenerated && bRenderMeshPrepared && bFabricCollisionConfigured &&
            bSupportMapBuilt && bMaterialsConfigured && bSaved &&
            SkinWeightNodesFound > 0 &&
            PhysicsNodesFound > 0 &&
            StretchConfigNodesFound > 0 &&
            BendingConfigNodesFound > 0 &&
            MaxDistanceConfigNodesFound == 1 &&
            SolverConfigNodesFound > 0 &&
            SelfCollisionSphereNodesFound > 0;
    }

    bool RepairClothBindings()
    {
        return RepairClothBindingsAtPath(ClothAssetPath, GetGarmentManifestPath());
    }

    bool RepairRebuiltClothBindings()
    {
        return RepairClothBindingsAtPath(RebuiltClothAssetPath, GetGarmentManifestPath());
    }

    bool RepairFullDressClothBindings()
    {
        return RepairClothBindingsAtPath(FullDressClothAssetPath, GetFullDressManifestPath());
    }

    bool RepairFittedDressClothBindings()
    {
        return RepairClothBindingsAtPath(FittedDressClothAssetPath, GetFittedDressManifestPath());
    }

    bool RepairShirtClothBindings()
    {
        return RepairClothBindingsAtPath(ShirtClothAssetPath, GetShirtManifestPath());
    }

    void ScheduleUnattendedExit()
    {
        if (!FApp::IsUnattended())
        {
            return;
        }
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                FPlatformMisc::RequestExit(false);
                return false;
            }),
            5.0f);
    }

    bool ValidateClothAssetAtPath(
        const TCHAR* const InClothAssetPath,
        const int32 ExpectedSimPatterns,
        const int32 ExpectedSimVertices,
        const int32 ExpectedSimFaces,
        const int32 ExpectedSeams,
        const int32 ExpectedSeamStitches,
        const int32 ExpectedRenderVertices,
        const int32 ExpectedRenderFaces,
        const bool bRequireDetailedRenderMesh,
        const TCHAR* const ValidationReportFileName,
        const TCHAR* const GarmentLabel)
    {
        using namespace UE::Chaos::ClothAsset;

        const UChaosClothAsset* const ClothAsset =
            LoadObject<UChaosClothAsset>(nullptr, InClothAssetPath);
        if (!ClothAsset)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna %s validation could not load %s."),
                GarmentLabel,
                InClothAssetPath);
            return false;
        }

        const TArray<TSharedRef<const FManagedArrayCollection>>& Collections =
            ClothAsset->GetClothCollections();
        bool bAccepted = Collections.Num() >= 1;
        FString LodsJson;
        for (int32 LodIndex = 0; LodIndex < Collections.Num(); ++LodIndex)
        {
            const FCollectionClothConstFacade ClothFacade(Collections[LodIndex]);
            const int32 SimPatterns = ClothFacade.GetNumSimPatterns();
            const int32 SimVertices2D = ClothFacade.GetNumSimVertices2D();
            const int32 SimVertices3D = ClothFacade.GetNumSimVertices3D();
            const int32 SimFaces = ClothFacade.GetNumSimFaces();
            const int32 RenderPatterns = ClothFacade.GetNumRenderPatterns();
            const int32 RenderVertices = ClothFacade.GetNumRenderVertices();
            const int32 RenderFaces = ClothFacade.GetNumRenderFaces();
            const int32 Seams = ClothFacade.GetNumSeams();
            int32 SeamStitches = 0;
            bool bSeamTopologyValid = Seams == ExpectedSeams;
            const TConstArrayView<TArray<int32>> SeamStitchLookup = ClothFacade.GetSeamStitchLookup();
            for (int32 SeamIndex = 0; SeamIndex < Seams; ++SeamIndex)
            {
                const FCollectionClothSeamConstFacade Seam = ClothFacade.GetSeam(SeamIndex);
                const TConstArrayView<FIntVector2> StitchEnds = Seam.GetSeamStitch2DEndIndices();
                const TConstArrayView<int32> StitchVertices3D = Seam.GetSeamStitch3DIndex();
                const int32 StitchOffset = Seam.GetSeamStitchesOffset();
                SeamStitches += Seam.GetNumSeamStitches();
                bSeamTopologyValid = bSeamTopologyValid &&
                    StitchEnds.Num() == StitchVertices3D.Num() &&
                    StitchEnds.Num() == Seam.GetNumSeamStitches();
                for (int32 StitchIndex = 0; StitchIndex < StitchEnds.Num(); ++StitchIndex)
                {
                    const FIntVector2 Endpoints = StitchEnds[StitchIndex];
                    const int32 Vertex3D = StitchVertices3D[StitchIndex];
                    const int32 GlobalStitchIndex = StitchOffset + StitchIndex;
                    bSeamTopologyValid = bSeamTopologyValid &&
                        Endpoints.X >= 0 && Endpoints.X < SimVertices2D &&
                        Endpoints.Y >= 0 && Endpoints.Y < SimVertices2D &&
                        Endpoints.X != Endpoints.Y &&
                        Vertex3D >= 0 && Vertex3D < SimVertices3D &&
                        SeamStitchLookup.IsValidIndex(Vertex3D) &&
                        SeamStitchLookup[Vertex3D].Contains(GlobalStitchIndex);
                }
            }
            bSeamTopologyValid = bSeamTopologyValid &&
                (LodIndex == 0 ? SeamStitches == ExpectedSeamStitches : SeamStitches > 0);

            int32 MinimumRenderDeformerInfluences = MAX_int32;
            for (int32 RenderPatternIndex = 0; RenderPatternIndex < RenderPatterns; ++RenderPatternIndex)
            {
                MinimumRenderDeformerInfluences = FMath::Min(
                    MinimumRenderDeformerInfluences,
                    ClothFacade.GetRenderPattern(RenderPatternIndex).GetRenderDeformerNumInfluences());
            }
            if (RenderPatterns == 0)
            {
                MinimumRenderDeformerInfluences = 0;
            }
            UE_LOG(
                LogPatternaUnrealEditor,
                Display,
                TEXT("Patterna %s saved LOD %d: %d simulation patterns, %d 2D simulation vertices, %d 3D simulation vertices, %d simulation faces, %d seams, %d seam stitches, seam topology %s, %d render patterns, %d render vertices, %d render faces, minimum render-deformer influences %d."),
                GarmentLabel,
                LodIndex,
                SimPatterns,
                SimVertices2D,
                SimVertices3D,
                SimFaces,
                Seams,
                SeamStitches,
                bSeamTopologyValid ? TEXT("valid") : TEXT("invalid"),
                RenderPatterns,
                RenderVertices,
                RenderFaces,
                MinimumRenderDeformerInfluences);
            if (LodIndex == 0)
            {
                bAccepted = bAccepted && ClothFacade.IsValid() &&
                    SimPatterns == ExpectedSimPatterns &&
                    SimVertices2D == ExpectedSimVertices &&
                    SimFaces == ExpectedSimFaces &&
                    bSeamTopologyValid &&
                    RenderPatterns >= 1 &&
                    RenderVertices >= (bRequireDetailedRenderMesh ? ExpectedRenderVertices : ExpectedSimVertices) &&
                    RenderFaces >= (bRequireDetailedRenderMesh ? ExpectedRenderFaces : ExpectedSimFaces) &&
                    (!bRequireDetailedRenderMesh || MinimumRenderDeformerInfluences > 0);
            }
            if (!LodsJson.IsEmpty())
            {
                LodsJson += TEXT(",\n");
            }
            LodsJson += FString::Printf(
                TEXT("    {\"lod\":%d,\"simPatterns\":%d,\"simVertices2D\":%d,\"simVertices3D\":%d,\"simFaces\":%d,\"seams\":%d,\"seamStitches\":%d,\"seamTopologyValid\":%s,\"renderPatterns\":%d,\"renderVertices\":%d,\"renderFaces\":%d,\"minimumRenderDeformerInfluences\":%d}"),
                LodIndex,
                SimPatterns,
                SimVertices2D,
                SimVertices3D,
                SimFaces,
                Seams,
                SeamStitches,
                bSeamTopologyValid ? TEXT("true") : TEXT("false"),
                RenderPatterns,
                RenderVertices,
                RenderFaces,
                MinimumRenderDeformerInfluences);
        }

        const FString ValidationJson = FString::Printf(
            TEXT("{\n  \"schemaVersion\": \"patterna.unreal-cloth-validation/2.0\",\n  \"assetPath\": \"%s\",\n  \"accepted\": %s,\n  \"lods\": [\n%s\n  ]\n}\n"),
            InClothAssetPath,
            bAccepted ? TEXT("true") : TEXT("false"),
            *LodsJson);
        const FString ValidationPath = FPaths::ConvertRelativePathToFull(
            FPaths::Combine(
                FPaths::ProjectSavedDir(),
                ValidationReportFileName));
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(ValidationPath), true);
        const bool bWritten = FFileHelper::SaveStringToFile(ValidationJson, *ValidationPath);
        if (bAccepted && bWritten)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Display,
                TEXT("Patterna %s saved-asset validation passed. Report: %s."),
                GarmentLabel,
                *ValidationPath);
        }
        else
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna %s saved-asset validation failed. Report: %s."),
                GarmentLabel,
                *ValidationPath);
        }
        return bAccepted && bWritten;
    }

    bool ValidateFullDressClothAsset()
    {
        FPatternaSimulationCounts Counts;
        if (!LoadSimulationCounts(GetFullDressManifestPath(), Counts))
        {
            return false;
        }

        return ValidateClothAssetAtPath(
            FullDressClothAssetPath,
            Counts.PanelCount,
            Counts.VertexCount,
            Counts.TriangleCount,
            Counts.SeamCount,
            Counts.StitchCount,
            Counts.RenderVertexCount,
            Counts.RenderTriangleCount,
            false,
            TEXT("Patterna/FullDressUnrealValidation.json"),
            TEXT("full dress"));
    }

    bool ValidateFittedDressClothAsset()
    {
        FPatternaSimulationCounts Counts;
        if (!LoadSimulationCounts(GetFittedDressManifestPath(), Counts))
        {
            return false;
        }

        return ValidateClothAssetAtPath(
            FittedDressClothAssetPath,
            Counts.PanelCount,
            Counts.VertexCount,
            Counts.TriangleCount,
            Counts.SeamCount,
            Counts.StitchCount,
            Counts.RenderVertexCount,
            Counts.RenderTriangleCount,
            true,
            TEXT("Patterna/FittedDressUnrealValidation.json"),
            TEXT("fitted dress"));
    }

    bool ValidateShirtClothAsset()
    {
        FPatternaSimulationCounts Counts;
        if (!LoadSimulationCounts(GetShirtManifestPath(), Counts))
        {
            return false;
        }

        return ValidateClothAssetAtPath(
            ShirtClothAssetPath,
            Counts.PanelCount,
            Counts.VertexCount,
            Counts.TriangleCount,
            Counts.SeamCount,
            Counts.StitchCount,
            Counts.RenderVertexCount,
            Counts.RenderTriangleCount,
            true,
            TEXT("Patterna/ShirtUnrealValidation.json"),
            TEXT("shirt"));
    }

    void ScheduleFullDressClothValidation()
    {
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                ValidateFullDressClothAsset();
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void ScheduleFullDressClothRepair()
    {
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna scheduled the isolated full-dress repair after editor startup."));
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                UE_LOG(
                    LogPatternaUnrealEditor,
                    Display,
                    TEXT("Patterna is starting the deferred full-dress repair."));
                RepairFullDressClothBindings();
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void ScheduleFittedDressClothRepair()
    {
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna scheduled the isolated fitted-dress repair after editor startup."));
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                RepairFittedDressClothBindings();
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void ScheduleShirtClothRepair()
    {
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna scheduled the isolated shirt repair after editor startup."));
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                RepairShirtClothBindings();
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void ScheduleFittedDressClothValidation()
    {
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                ValidateFittedDressClothAsset();
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void ScheduleShirtClothValidation()
    {
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                ValidateShirtClothAsset();
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void ReimportAndRepairClothBindingsAtPath(
        const TCHAR* const InClothAssetPath,
        const FString& SourcePath,
        const FString& ManifestPath)
    {
        FModuleManager::Get().LoadModuleChecked<IModuleInterface>(TEXT("ChaosClothAssetDataflowNodes"));

        UChaosClothAsset* const ClothAsset = LoadObject<UChaosClothAsset>(nullptr, InClothAssetPath);
        if (!ClothAsset)
        {
            UE_LOG(LogPatternaUnrealEditor, Error, TEXT("Patterna cloth reimport could not load the cloth asset."));
            return;
        }

        if (!FPaths::FileExists(SourcePath))
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna cloth reimport source is missing: %s."),
                *SourcePath);
            return;
        }

        const bool bReimported = FReimportManager::Instance()->Reimport(
            ClothAsset,
            false,
            false,
            SourcePath,
            nullptr,
            INDEX_NONE,
            true,
            true,
            false);
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna cloth source reimport completed: %s."),
            bReimported ? TEXT("yes") : TEXT("no"));

        if (bReimported)
        {
            RepairClothBindingsAtPath(InClothAssetPath, ManifestPath);
        }
    }

    void ReimportAndRepairClothBindings()
    {
        ReimportAndRepairClothBindingsAtPath(
            ClothAssetPath,
            GetClothSourcePath(),
            GetGarmentManifestPath());
    }

    void ReimportAndRepairRebuiltClothBindings()
    {
        ReimportAndRepairClothBindingsAtPath(
            RebuiltClothAssetPath,
            GetClothSourcePath(),
            GetGarmentManifestPath());
    }

    void ScheduleFullDressReimportAndRepair()
    {
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna scheduled the isolated full-dress reimport after editor startup."));
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                UE_LOG(
                    LogPatternaUnrealEditor,
                    Display,
                    TEXT("Patterna is starting the deferred full-dress reimport."));
                ReimportAndRepairClothBindingsAtPath(
                    FullDressClothAssetPath,
                    GetFullDressSourcePath(),
                    GetFullDressManifestPath());
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void ScheduleFittedDressReimportAndRepair()
    {
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna scheduled the isolated fitted-dress reimport after editor startup."));
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                ReimportAndRepairClothBindingsAtPath(
                    FittedDressClothAssetPath,
                    GetFittedDressSourcePath(),
                    GetFittedDressManifestPath());
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void ScheduleShirtReimportAndRepair()
    {
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna scheduled the isolated shirt reimport after editor startup."));
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                ReimportAndRepairClothBindingsAtPath(
                    ShirtClothAssetPath,
                    GetShirtSourcePath(),
                    GetShirtManifestPath());
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void BuildResizableFullDressOutfit()
    {
        UChaosClothAsset* const ClothAsset =
            LoadObject<UChaosClothAsset>(nullptr, FullDressClothAssetPath);
        USkeletalMesh* const BodyMesh = LoadObject<USkeletalMesh>(nullptr, BodyMeshPath);
        USkeletalMesh* const FaceMesh = LoadObject<USkeletalMesh>(nullptr, FaceMeshPath);
        if (!ClothAsset || !BodyMesh || !FaceMesh)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna cannot build the resizable outfit. Cloth: %s, body: %s, face: %s."),
                ClothAsset ? TEXT("loaded") : TEXT("missing"),
                BodyMesh ? TEXT("loaded") : TEXT("missing"),
                FaceMesh ? TEXT("loaded") : TEXT("missing"));
            ScheduleUnattendedExit();
            return;
        }

        UChaosOutfitAsset* OutfitAsset =
            LoadObject<UChaosOutfitAsset>(nullptr, ResizableOutfitAssetPath);
        bool bCreatedAsset = false;
        if (!OutfitAsset)
        {
            UPackage* const Package = CreatePackage(ResizableOutfitPackagePath);
            OutfitAsset = NewObject<UChaosOutfitAsset>(
                Package,
                TEXT("PatternaWrapDress_ResizableV8"),
                RF_Public | RF_Standalone | RF_Transactional);
            bCreatedAsset = true;
        }

        UChaosOutfit* const Outfit = NewObject<UChaosOutfit>(
            OutfitAsset,
            TEXT("PatternaWrapDress_SourceOutfit"),
            RF_Transactional);
        FChaosSizedOutfitSource Source;
        Source.SourceAsset = ClothAsset;
        Source.SizeName = TEXT("PatternaFemaleDefault");
        Source.SourceBodyParts = { BodyMesh, FaceMesh };
        Source.NumResizingInterpolationPoints = 2000;
        Outfit->Add(Source);
        OutfitAsset->Build(Outfit);
        OutfitAsset->MarkPackageDirty();

        if (bCreatedAsset)
        {
            FAssetRegistryModule::AssetCreated(OutfitAsset);
        }
        const bool bSaved = UEditorLoadingAndSavingUtils::SavePackages(
            { OutfitAsset->GetOutermost() },
            false);
        if (bSaved)
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Display,
                TEXT("Patterna resizable outfit build completed. Pieces: %d, source body parts: 2, interpolation points: 2000, saved: yes, asset: %s."),
                Outfit->GetPieces().Num(),
                ResizableOutfitAssetPath);
        }
        else
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna resizable outfit build failed to save asset %s."),
                ResizableOutfitAssetPath);
        }
        ScheduleUnattendedExit();
    }

    void ImportFreshAndRepairClothBindingsAtPath(
        const FString& SourcePath,
        const TCHAR* const DestinationPath,
        const TCHAR* const ExpectedClothAssetPath,
        const FString& ManifestPath)
    {
        if (!FPaths::FileExists(SourcePath))
        {
            UE_LOG(
                LogPatternaUnrealEditor,
                Error,
                TEXT("Patterna fresh cloth import source is missing: %s."),
                *SourcePath);
            return;
        }

        IAssetTools& AssetTools = FAssetToolsModule::GetModule().Get();
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna starting automated cloth import from %s to %s."),
            *SourcePath,
            DestinationPath);
        UAutomatedAssetImportData* const ImportData = NewObject<UAutomatedAssetImportData>();
        ImportData->GroupName = TEXT("Patterna verified cloth import");
        ImportData->Filenames = { SourcePath };
        ImportData->DestinationPath = DestinationPath;
        ImportData->bReplaceExisting = false;
        ImportData->bSkipReadOnly = true;
        const TArray<UObject*> ImportedAssets = AssetTools.ImportAssetsAutomated(ImportData);
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna automated cloth import returned %d objects."),
            ImportedAssets.Num());

        UChaosClothAsset* ImportedClothAsset = nullptr;
        for (UObject* const ImportedAsset : ImportedAssets)
        {
            if (UChaosClothAsset* const Candidate = Cast<UChaosClothAsset>(ImportedAsset))
            {
                ImportedClothAsset = Candidate;
                break;
            }
        }

        if (!ImportedClothAsset)
        {
            ImportedClothAsset = LoadObject<UChaosClothAsset>(nullptr, ExpectedClothAssetPath);
        }

        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna fresh cloth import completed. Imported objects: %d, cloth asset: %s."),
            ImportedAssets.Num(),
            ImportedClothAsset ? *ImportedClothAsset->GetPathName() : TEXT("None"));

        if (!ImportedClothAsset)
        {
            UE_LOG(LogPatternaUnrealEditor, Error, TEXT("Patterna fresh cloth import produced no cloth asset."));
            return;
        }

        RepairClothBindingsAtPath(*ImportedClothAsset->GetPathName(), ManifestPath);
    }

    void ImportFreshAndRepairClothBindings()
    {
        ImportFreshAndRepairClothBindingsAtPath(
            GetClothSourcePath(),
            RebuiltClothDestination,
            RebuiltClothAssetPath,
            GetGarmentManifestPath());
    }

    void ImportFullDressAndRepairClothBindings()
    {
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna scheduled the isolated full-dress import after editor startup."));
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                UE_LOG(
                    LogPatternaUnrealEditor,
                    Display,
                    TEXT("Patterna is starting the deferred full-dress import."));
                ImportFreshAndRepairClothBindingsAtPath(
                    GetFullDressSourcePath(),
                    FullDressClothDestination,
                    FullDressClothAssetPath,
                    GetFullDressManifestPath());
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void ImportFittedDressAndRepairClothBindings()
    {
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna scheduled the isolated fitted-dress import after editor startup."));
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                ImportFreshAndRepairClothBindingsAtPath(
                    GetFittedDressSourcePath(),
                    FittedDressClothDestination,
                    FittedDressClothAssetPath,
                    GetFittedDressManifestPath());
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    void ImportShirtAndRepairClothBindings()
    {
        UE_LOG(
            LogPatternaUnrealEditor,
            Display,
            TEXT("Patterna scheduled the isolated shirt import after editor startup."));
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float)
            {
                ImportFreshAndRepairClothBindingsAtPath(
                    GetShirtSourcePath(),
                    ShirtClothDestination,
                    ShirtClothAssetPath,
                    GetShirtManifestPath());
                ScheduleUnattendedExit();
                return false;
            }),
            3.0f);
    }

    FAutoConsoleCommand RepairClothBindingsCommand(
        TEXT("Patterna.RepairClothBindings"),
        TEXT("Bind the Patterna garment Dataflow to the assembled female MetaHuman body and physics asset, evaluate it, and save it."),
        FConsoleCommandDelegate::CreateLambda([] { RepairClothBindings(); }));

    FAutoConsoleCommand RepairRebuiltClothBindingsCommand(
        TEXT("Patterna.RepairRebuiltClothBindings"),
        TEXT("Rebuild the fresh Patterna garment with female MetaHuman bindings and a validated waistband constraint."),
        FConsoleCommandDelegate::CreateLambda([] { RepairRebuiltClothBindings(); }));

    FAutoConsoleCommand RepairFullDressClothBindingsCommand(
        TEXT("Patterna.RepairFullDressClothBindings"),
        TEXT("Rebuild the isolated full Patterna wrap dress with female MetaHuman body and physics bindings."),
        FConsoleCommandDelegate::CreateStatic(&ScheduleFullDressClothRepair));

    FAutoConsoleCommand RepairFittedDressClothBindingsCommand(
        TEXT("Patterna.RepairFittedDressClothBindings"),
        TEXT("Rebuild the isolated fitted dress with female MetaHuman body and physics bindings."),
        FConsoleCommandDelegate::CreateStatic(&ScheduleFittedDressClothRepair));

    FAutoConsoleCommand RepairShirtClothBindingsCommand(
        TEXT("Patterna.RepairShirtClothBindings"),
        TEXT("Rebuild the isolated shirt with female MetaHuman body and physics bindings."),
        FConsoleCommandDelegate::CreateStatic(&ScheduleShirtClothRepair));

    FAutoConsoleCommand ValidateFullDressClothAssetCommand(
        TEXT("Patterna.ValidateFullDressClothAsset"),
        TEXT("Validate the isolated saved full-dress Chaos Cloth collections and write a machine-readable report."),
        FConsoleCommandDelegate::CreateStatic(&ScheduleFullDressClothValidation));

    FAutoConsoleCommand ValidateFittedDressClothAssetCommand(
        TEXT("Patterna.ValidateFittedDressClothAsset"),
        TEXT("Validate the isolated fitted-dress Chaos Cloth collections and write a machine-readable report."),
        FConsoleCommandDelegate::CreateStatic(&ScheduleFittedDressClothValidation));

    FAutoConsoleCommand ValidateShirtClothAssetCommand(
        TEXT("Patterna.ValidateShirtClothAsset"),
        TEXT("Validate the isolated saved shirt Chaos Cloth collections and write a machine-readable report."),
        FConsoleCommandDelegate::CreateStatic(&ScheduleShirtClothValidation));

    FAutoConsoleCommand ReimportAndRepairClothBindingsCommand(
        TEXT("Patterna.ReimportAndRepairClothBindings"),
        TEXT("Reimport the generated Patterna USDA garment, bind it to the assembled female MetaHuman, evaluate it, and save it."),
        FConsoleCommandDelegate::CreateStatic(&ReimportAndRepairClothBindings));

    FAutoConsoleCommand ReimportAndRepairRebuiltClothBindingsCommand(
        TEXT("Patterna.ReimportAndRepairRebuiltClothBindings"),
        TEXT("Reimport the generated Patterna USDA into the fresh cloth asset, then rebuild its avatar bindings and waistband constraint."),
        FConsoleCommandDelegate::CreateStatic(&ReimportAndRepairRebuiltClothBindings));

    FAutoConsoleCommand ReimportAndRepairFullDressClothBindingsCommand(
        TEXT("Patterna.ReimportAndRepairFullDressClothBindings"),
        TEXT("Reimport the isolated full wrap dress source, rebuild its female MetaHuman bindings, and save it."),
        FConsoleCommandDelegate::CreateStatic(&ScheduleFullDressReimportAndRepair));

    FAutoConsoleCommand ReimportAndRepairFittedDressClothBindingsCommand(
        TEXT("Patterna.ReimportAndRepairFittedDressClothBindings"),
        TEXT("Reimport the fitted dress source, rebuild its female MetaHuman bindings, and save it."),
        FConsoleCommandDelegate::CreateStatic(&ScheduleFittedDressReimportAndRepair));

    FAutoConsoleCommand ReimportAndRepairShirtClothBindingsCommand(
        TEXT("Patterna.ReimportAndRepairShirtClothBindings"),
        TEXT("Reimport the shirt source, rebuild its female MetaHuman bindings, and save it."),
        FConsoleCommandDelegate::CreateStatic(&ScheduleShirtReimportAndRepair));

    FAutoConsoleCommand BuildResizableFullDressOutfitCommand(
        TEXT("Patterna.BuildResizableFullDressOutfit"),
        TEXT("Build a Chaos Outfit Asset with a measured female MetaHuman source size from the verified full dress cloth asset."),
        FConsoleCommandDelegate::CreateStatic(&BuildResizableFullDressOutfit));

    FAutoConsoleCommand ImportFreshAndRepairClothBindingsCommand(
        TEXT("Patterna.ImportFreshAndRepairClothBindings"),
        TEXT("Import the generated Patterna USDA garment into a fresh cloth asset, bind it to the assembled female MetaHuman, evaluate it, and save it."),
        FConsoleCommandDelegate::CreateStatic(&ImportFreshAndRepairClothBindings));

    FAutoConsoleCommand ImportFullDressAndRepairClothBindingsCommand(
        TEXT("Patterna.ImportFullDressAndRepairClothBindings"),
        TEXT("Import the verified full wrap dress into an isolated cloth asset, bind it to the assembled female MetaHuman, evaluate it, and save it."),
        FConsoleCommandDelegate::CreateStatic(&ImportFullDressAndRepairClothBindings));

    FAutoConsoleCommand ImportFittedDressAndRepairClothBindingsCommand(
        TEXT("Patterna.ImportFittedDressAndRepairClothBindings"),
        TEXT("Import the body-specific fitted dress into an isolated cloth asset, bind it to the female MetaHuman, evaluate it, and save it."),
        FConsoleCommandDelegate::CreateStatic(&ImportFittedDressAndRepairClothBindings));

    FAutoConsoleCommand ImportShirtAndRepairClothBindingsCommand(
        TEXT("Patterna.ImportShirtAndRepairClothBindings"),
        TEXT("Import the verified shirt into an isolated cloth asset, bind it to the female MetaHuman, evaluate it, and save it."),
        FConsoleCommandDelegate::CreateStatic(&ImportShirtAndRepairClothBindings));
}

class FPatternaUnrealEditorModule final : public IModuleInterface
{
};

IMPLEMENT_MODULE(FPatternaUnrealEditorModule, PatternaUnrealEditor)
