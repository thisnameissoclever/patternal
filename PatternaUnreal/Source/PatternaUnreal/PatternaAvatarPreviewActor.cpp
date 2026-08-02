#include "PatternaAvatarPreviewActor.h"

#include "Animation/MorphTarget.h"
#include "Camera/CameraComponent.h"
#include "ChaosClothAsset/ClothAsset.h"
#include "ChaosClothAsset/ClothComponent.h"
#include "ChaosClothAsset/CollectionClothFacade.h"
#include "ChaosClothAsset/ClothSimulationProxy.h"
#include "Components/ChildActorComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Dom/JsonObject.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMisc.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"
#include "PhysicsEngine/SphereElem.h"
#include "RawIndexBuffer.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkinWeightVertexBuffer.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "SkeletalRenderPublic.h"
#include "UObject/ConstructorHelpers.h"
#include "UnrealClient.h"

namespace
{
    void ApplyCleanBodyBaseColor(USkeletalMeshComponent* const BodyPose)
    {
        if (!BodyPose || BodyPose->GetNumMaterials() == 0)
        {
            UE_LOG(LogTemp, Warning, TEXT("Patterna clean body texture could not be applied because the body has no material slot."));
            return;
        }

        UTexture2D* const CleanBodyTexture = LoadObject<UTexture2D>(
            nullptr,
            TEXT("/Game/PatternaMeasuredGarments/V3/PatternaWrapDress/AvatarMaterials/T_Body_BC_Clean.T_Body_BC_Clean"));
        if (!CleanBodyTexture)
        {
            UE_LOG(LogTemp, Warning, TEXT("Patterna clean body base-color texture is unavailable; using the source MetaHuman material."));
            return;
        }

        UMaterialInstanceDynamic* const BodyMaterial = BodyPose->CreateDynamicMaterialInstance(0);
        if (!BodyMaterial)
        {
            UE_LOG(LogTemp, Warning, TEXT("Patterna body material override could not be created."));
            return;
        }

        BodyMaterial->SetTextureParameterValue(TEXT("Basecolor Baked"), CleanBodyTexture);
        UE_LOG(
            LogTemp,
            Display,
            TEXT("Patterna body preview uses isolated clean base color %s on material slot 0."),
            *CleanBodyTexture->GetPathName());
    }

    void SetPatternaViewAngle(const TArray<FString>& Arguments, UWorld* const World)
    {
        if (!World || Arguments.IsEmpty())
        {
            UE_LOG(LogTemp, Warning, TEXT("Usage: Patterna.ViewAngle <degrees>"));
            return;
        }

        float AngleDegrees = 0.0f;
        if (!LexTryParseString(AngleDegrees, *Arguments[0]))
        {
            UE_LOG(LogTemp, Warning, TEXT("Patterna.ViewAngle requires a numeric angle."));
            return;
        }

        for (TActorIterator<APatternaAvatarPreviewActor> ActorIterator(World); ActorIterator; ++ActorIterator)
        {
            ActorIterator->SetViewAngle(AngleDegrees);
        }
    }

    FAutoConsoleCommandWithWorldAndArgs PatternaViewAngleCommand(
        TEXT("Patterna.ViewAngle"),
        TEXT("Set the Patterna fit-preview camera angle in degrees: 90 front, 0 side, 270 back."),
        FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&SetPatternaViewAngle));

    float GetPercentile(const TArray<float>& SortedValues, const float Percentile)
    {
        check(!SortedValues.IsEmpty());

        const float Position = FMath::Clamp(Percentile, 0.0f, 1.0f) * (SortedValues.Num() - 1);
        const int32 LowerIndex = FMath::FloorToInt(Position);
        const int32 UpperIndex = FMath::CeilToInt(Position);
        const float Alpha = Position - LowerIndex;
        return FMath::Lerp(SortedValues[LowerIndex], SortedValues[UpperIndex], Alpha);
    }

    bool IsTorsoSurfaceBone(const FName BoneName)
    {
        const FString Name = BoneName.ToString();
        return Name.Equals(TEXT("pelvis"), ESearchCase::IgnoreCase) ||
            Name.StartsWith(TEXT("spine_"), ESearchCase::IgnoreCase) ||
            Name.StartsWith(TEXT("clavicle_"), ESearchCase::IgnoreCase) ||
            Name.StartsWith(TEXT("neck_"), ESearchCase::IgnoreCase) ||
            Name.Contains(TEXT("breast"), ESearchCase::IgnoreCase);
    }

    TArray<bool> BuildTorsoSurfaceVertexMask(
        USkeletalMeshComponent* const BodyPose,
        const int32 VertexCount)
    {
        TArray<bool> TorsoVertexMask;
        TorsoVertexMask.Init(false, VertexCount);

        const USkeletalMesh* const BodyMesh = BodyPose
            ? BodyPose->GetSkeletalMeshAsset()
            : nullptr;
        const FSkeletalMeshRenderData* const RenderData = BodyMesh
            ? BodyMesh->GetResourceForRendering()
            : nullptr;
        const FSkinWeightVertexBuffer* const SkinWeightBuffer = BodyPose
            ? BodyPose->GetSkinWeightBuffer(0)
            : nullptr;
        if (!BodyMesh || !RenderData || RenderData->LODRenderData.IsEmpty() || !SkinWeightBuffer)
        {
            UE_LOG(LogTemp, Error, TEXT("Patterna could not read skin weights for torso-only body sampling."));
            return TorsoVertexMask;
        }

        const FReferenceSkeleton& ReferenceSkeleton = BodyMesh->GetRefSkeleton();
        TArray<bool> TorsoBoneMask;
        TorsoBoneMask.Init(false, ReferenceSkeleton.GetNum());
        for (int32 BoneIndex = 0; BoneIndex < ReferenceSkeleton.GetNum(); ++BoneIndex)
        {
            TorsoBoneMask[BoneIndex] = IsTorsoSurfaceBone(ReferenceSkeleton.GetBoneName(BoneIndex));
        }

        constexpr float MinimumTorsoInfluence = 0.35f;
        const uint32 MaximumBoneInfluences = SkinWeightBuffer->GetMaxBoneInfluences();
        const FSkeletalMeshLODRenderData& LodData = RenderData->LODRenderData[0];
        int32 AcceptedVertexCount = 0;
        for (const FSkelMeshRenderSection& Section : LodData.RenderSections)
        {
            for (uint32 LocalVertexIndex = 0; LocalVertexIndex < Section.NumVertices; ++LocalVertexIndex)
            {
                const uint32 VertexIndex = Section.GetVertexBufferIndex() + LocalVertexIndex;
                if (!TorsoVertexMask.IsValidIndex(VertexIndex))
                {
                    continue;
                }

                uint32 TorsoWeight = 0;
                uint32 TotalWeight = 0;
                for (uint32 InfluenceIndex = 0; InfluenceIndex < MaximumBoneInfluences; ++InfluenceIndex)
                {
                    const uint16 Weight = SkinWeightBuffer->GetBoneWeight(VertexIndex, InfluenceIndex);
                    if (Weight == 0)
                    {
                        continue;
                    }

                    TotalWeight += Weight;
                    const uint32 BoneMapIndex = SkinWeightBuffer->GetBoneIndex(VertexIndex, InfluenceIndex);
                    if (!Section.BoneMap.IsValidIndex(BoneMapIndex))
                    {
                        continue;
                    }

                    const int32 MeshBoneIndex = Section.BoneMap[BoneMapIndex];
                    if (TorsoBoneMask.IsValidIndex(MeshBoneIndex) && TorsoBoneMask[MeshBoneIndex])
                    {
                        TorsoWeight += Weight;
                    }
                }

                const bool IsTorsoVertex = TotalWeight > 0 &&
                    static_cast<float>(TorsoWeight) / static_cast<float>(TotalWeight) >= MinimumTorsoInfluence;
                TorsoVertexMask[VertexIndex] = IsTorsoVertex;
                AcceptedVertexCount += IsTorsoVertex ? 1 : 0;
            }
        }

        UE_LOG(
            LogTemp,
            Display,
            TEXT("Patterna torso surface filter retained %d of %d LOD 0 vertices using a %.0f percent torso-bone influence threshold."),
            AcceptedVertexCount,
            VertexCount,
            MinimumTorsoInfluence * 100.0f);
        return TorsoVertexMask;
    }

    TArray<FVector2D> GetOuterBodySurfacePoints(
        const TArray<FVector2D>& CrossSectionSamples,
        const float CenterX,
        const float CenterY,
        const float MinimumX,
        const float MaximumX,
        const float MinimumY,
        const float MaximumY,
        const int32 SectorCount,
        const float OutlierAllowanceCm)
    {
        TArray<float> MaximumRadiusSquaredBySector;
        MaximumRadiusSquaredBySector.Init(-1.0f, SectorCount);
        TArray<FVector2D> SurfacePointBySector;
        SurfacePointBySector.Init(FVector2D::ZeroVector, SectorCount);

        for (const FVector2D& CrossSectionSample : CrossSectionSamples)
        {
            if (CrossSectionSample.X < MinimumX - OutlierAllowanceCm ||
                CrossSectionSample.X > MaximumX + OutlierAllowanceCm ||
                CrossSectionSample.Y < MinimumY - OutlierAllowanceCm ||
                CrossSectionSample.Y > MaximumY + OutlierAllowanceCm)
            {
                continue;
            }

            const float OffsetX = CrossSectionSample.X - CenterX;
            const float OffsetY = CrossSectionSample.Y - CenterY;
            const float RadiusSquared = FMath::Square(OffsetX) + FMath::Square(OffsetY);
            float NormalizedAngle = FMath::Atan2(OffsetY, OffsetX) + PI;
            NormalizedAngle /= 2.0f * PI;
            const int32 SectorIndex = FMath::Clamp(
                FMath::FloorToInt(NormalizedAngle * SectorCount),
                0,
                SectorCount - 1);
            if (RadiusSquared > MaximumRadiusSquaredBySector[SectorIndex])
            {
                MaximumRadiusSquaredBySector[SectorIndex] = RadiusSquared;
                SurfacePointBySector[SectorIndex] = CrossSectionSample;
            }
        }

        TArray<FVector2D> SurfacePoints;
        SurfacePoints.Reserve(SectorCount);
        for (int32 SectorIndex = 0; SectorIndex < SectorCount; ++SectorIndex)
        {
            if (MaximumRadiusSquaredBySector[SectorIndex] > SMALL_NUMBER)
            {
                SurfacePoints.Add(SurfacePointBySector[SectorIndex]);
            }
        }
        return SurfacePoints;
    }

    void LogBodyCrossSections(USkeletalMeshComponent* const BodyPose)
    {
        if (!BodyPose)
        {
            return;
        }

        TArray<FFinalSkinVertex> SkinnedVertices;
        BodyPose->GetCPUSkinnedVertices(SkinnedVertices, 0);
        if (SkinnedVertices.IsEmpty())
        {
            UE_LOG(LogTemp, Error, TEXT("Patterna could not sample the live avatar body mesh."));
            return;
        }

        const USkeletalMesh* const BodyMesh = BodyPose->GetSkeletalMeshAsset();
        const FSkeletalMeshRenderData* const RenderData = BodyMesh
            ? BodyMesh->GetResourceForRendering()
            : nullptr;
        if (!RenderData || RenderData->LODRenderData.IsEmpty())
        {
            UE_LOG(LogTemp, Error, TEXT("Patterna could not read LOD 0 triangles for body-plane sampling."));
            return;
        }

        const FSkeletalMeshLODRenderData& LodData = RenderData->LODRenderData[0];
        const FRawStaticIndexBuffer16or32Interface* const IndexBuffer =
            LodData.MultiSizeIndexContainer.GetIndexBuffer();
        if (!IndexBuffer || IndexBuffer->Num() < 3)
        {
            UE_LOG(LogTemp, Error, TEXT("Patterna body LOD 0 has no CPU-readable triangle indices."));
            return;
        }

        const TArray<bool> TorsoSurfaceVertexMask = BuildTorsoSurfaceVertexMask(
            BodyPose,
            SkinnedVertices.Num());
        const TArray<TObjectPtr<UMorphTarget>>& MorphTargets = BodyMesh->GetMorphTargets();
        UE_LOG(
            LogTemp,
            Display,
            TEXT("Patterna live avatar body mesh %s exposes %d morph targets."),
            *BodyMesh->GetPathName(),
            MorphTargets.Num());
        for (const UMorphTarget* const MorphTarget : MorphTargets)
        {
            UE_LOG(
                LogTemp,
                Display,
                TEXT("Patterna live avatar morph target: %s."),
                MorphTarget ? *MorphTarget->GetName() : TEXT("<null>"));
        }

        constexpr float TorsoHalfWidthLimitCm = 25.0f;
        constexpr float TorsoHalfDepthLimitCm = 30.0f;
        constexpr float LowerPercentile = 0.05f;
        constexpr float UpperPercentile = 0.95f;
        constexpr float LowestSampleHeightCm = 95.0f;
        constexpr float HighestSampleHeightCm = 151.0f;
        constexpr float SampleHeightStepCm = 2.0f;

        TArray<TSharedPtr<FJsonValue>> JsonSections;
        for (
            float SampleHeightCm = LowestSampleHeightCm;
            SampleHeightCm <= HighestSampleHeightCm;
            SampleHeightCm += SampleHeightStepCm)
        {
            TArray<float> WidthSamples;
            TArray<float> DepthSamples;
            TArray<FVector2D> CrossSectionSamples;
            for (const FSkelMeshRenderSection& Section : LodData.RenderSections)
            {
                for (uint32 TriangleIndex = 0; TriangleIndex < Section.NumTriangles; ++TriangleIndex)
                {
                    const uint32 FirstIndex = Section.BaseIndex + TriangleIndex * 3;
                    const uint32 VertexIndices[] = {
                        IndexBuffer->Get(FirstIndex),
                        IndexBuffer->Get(FirstIndex + 1),
                        IndexBuffer->Get(FirstIndex + 2)
                    };
                    if (!SkinnedVertices.IsValidIndex(VertexIndices[0]) ||
                        !SkinnedVertices.IsValidIndex(VertexIndices[1]) ||
                        !SkinnedVertices.IsValidIndex(VertexIndices[2]))
                    {
                        continue;
                    }

                    if (SampleHeightCm >= 109.0f)
                    {
                        int32 TorsoVertexCount = 0;
                        for (const uint32 VertexIndex : VertexIndices)
                        {
                            TorsoVertexCount += TorsoSurfaceVertexMask.IsValidIndex(VertexIndex) &&
                                TorsoSurfaceVertexMask[VertexIndex]
                                ? 1
                                : 0;
                        }
                        if (TorsoVertexCount < 2)
                        {
                            continue;
                        }
                    }

                    const FVector3f Positions[] = {
                        SkinnedVertices[VertexIndices[0]].Position,
                        SkinnedVertices[VertexIndices[1]].Position,
                        SkinnedVertices[VertexIndices[2]].Position
                    };
                    constexpr int32 EdgeVertices[][2] = { { 0, 1 }, { 1, 2 }, { 2, 0 } };
                    for (const int32* const Edge : EdgeVertices)
                    {
                        const FVector3f& Start = Positions[Edge[0]];
                        const FVector3f& End = Positions[Edge[1]];
                        const float StartOffset = Start.Z - SampleHeightCm;
                        const float EndOffset = End.Z - SampleHeightCm;
                        if ((StartOffset < 0.0f && EndOffset < 0.0f) ||
                            (StartOffset > 0.0f && EndOffset > 0.0f) ||
                            FMath::IsNearlyEqual(Start.Z, End.Z, KINDA_SMALL_NUMBER))
                        {
                            continue;
                        }

                        const float Alpha = FMath::Clamp(
                            (SampleHeightCm - Start.Z) / (End.Z - Start.Z),
                            0.0f,
                            1.0f);
                        const FVector3f Intersection = FMath::Lerp(Start, End, Alpha);
                        if (FMath::Abs(Intersection.X) > TorsoHalfWidthLimitCm ||
                            FMath::Abs(Intersection.Y) > TorsoHalfDepthLimitCm)
                        {
                            continue;
                        }

                        WidthSamples.Add(Intersection.X);
                        DepthSamples.Add(Intersection.Y);
                        CrossSectionSamples.Add(FVector2D(Intersection.X, Intersection.Y));
                    }
                }
            }

            if (WidthSamples.Num() < 20)
            {
                UE_LOG(
                    LogTemp,
                    Warning,
                    TEXT("Patterna robust live body cross-section Z %.1f cm had only %d torso samples."),
                    SampleHeightCm,
                    WidthSamples.Num());
                continue;
            }

            WidthSamples.Sort();
            DepthSamples.Sort();
            const float MinimumX = GetPercentile(WidthSamples, LowerPercentile);
            const float MaximumX = GetPercentile(WidthSamples, UpperPercentile);
            const float MinimumY = GetPercentile(DepthSamples, LowerPercentile);
            const float MaximumY = GetPercentile(DepthSamples, UpperPercentile);
            const float WidthCm = MaximumX - MinimumX;
            const float DepthCm = MaximumY - MinimumY;
            const float WidthCenterCm = (MaximumX + MinimumX) * 0.5f;
            const float DepthCenterCm = (MaximumY + MinimumY) * 0.5f;
            const float DepthRadiusCm = DepthCm * 0.5f;
            const float WidthRadiusCm = WidthCm * 0.5f;
            const float RadiusSum = DepthRadiusCm + WidthRadiusCm;
            const float H = RadiusSum > SMALL_NUMBER
                ? FMath::Square((WidthRadiusCm - DepthRadiusCm) / RadiusSum)
                : 0.0f;
            const float ApproximateCircumferenceCm = PI * RadiusSum *
                (1.0f + ((3.0f * H) / (10.0f + FMath::Sqrt(4.0f - (3.0f * H)))));
            const TArray<FVector2D> SurfacePoints = GetOuterBodySurfacePoints(
                CrossSectionSamples,
                WidthCenterCm,
                DepthCenterCm,
                MinimumX,
                MaximumX,
                MinimumY,
                MaximumY,
                64,
                1.5f);

            UE_LOG(
                LogTemp,
                Display,
                TEXT("Patterna robust live body cross-section Z %.1f cm: %d vertices, X %.2f to %.2f cm, Y %.2f to %.2f cm, width %.2f cm, depth %.2f cm, center X %.2f Y %.2f cm, ellipse circumference %.2f cm, depth-to-width %.3f."),
                SampleHeightCm,
                WidthSamples.Num(),
                MinimumX,
                MaximumX,
                MinimumY,
                MaximumY,
                WidthCm,
                DepthCm,
                WidthCenterCm,
                DepthCenterCm,
                ApproximateCircumferenceCm,
                WidthCm > SMALL_NUMBER ? DepthCm / WidthCm : 0.0f);

            TSharedRef<FJsonObject> JsonSection = MakeShared<FJsonObject>();
            JsonSection->SetNumberField(TEXT("heightCm"), SampleHeightCm);
            JsonSection->SetNumberField(TEXT("widthCm"), WidthCm);
            JsonSection->SetNumberField(TEXT("depthCm"), DepthCm);
            JsonSection->SetNumberField(TEXT("centerXCm"), WidthCenterCm);
            JsonSection->SetNumberField(TEXT("centerYCm"), DepthCenterCm);
            JsonSection->SetNumberField(TEXT("ellipseCircumferenceCm"), ApproximateCircumferenceCm);
            JsonSection->SetNumberField(TEXT("sampleCount"), WidthSamples.Num());
            JsonSection->SetNumberField(TEXT("surfacePointCount"), SurfacePoints.Num());
            TArray<TSharedPtr<FJsonValue>> JsonSurfacePoints;
            JsonSurfacePoints.Reserve(SurfacePoints.Num());
            for (const FVector2D& SurfacePoint : SurfacePoints)
            {
                const float OffsetX = SurfacePoint.X - WidthCenterCm;
                const float OffsetY = SurfacePoint.Y - DepthCenterCm;
                TSharedRef<FJsonObject> JsonSurfacePoint = MakeShared<FJsonObject>();
                JsonSurfacePoint->SetNumberField(TEXT("angleRadians"), FMath::Atan2(OffsetY, OffsetX));
                JsonSurfacePoint->SetNumberField(TEXT("radiusCm"), FMath::Sqrt(FMath::Square(OffsetX) + FMath::Square(OffsetY)));
                JsonSurfacePoint->SetNumberField(TEXT("xCm"), SurfacePoint.X);
                JsonSurfacePoint->SetNumberField(TEXT("yCm"), SurfacePoint.Y);
                JsonSurfacePoints.Add(MakeShared<FJsonValueObject>(JsonSurfacePoint));
            }
            JsonSection->SetArrayField(TEXT("surfacePoints"), JsonSurfacePoints);
            JsonSections.Add(MakeShared<FJsonValueObject>(JsonSection));
        }

        if (JsonSections.IsEmpty())
        {
            return;
        }

        TSharedRef<FJsonObject> RootObject = MakeShared<FJsonObject>();
        RootObject->SetStringField(TEXT("schemaVersion"), TEXT("patterna.live-body-profile/1.0"));
        RootObject->SetStringField(TEXT("bodyAssetPath"), BodyMesh->GetPathName());
        RootObject->SetNumberField(TEXT("sampleHalfBandCm"), 0.0f);
        RootObject->SetNumberField(TEXT("lowestSampleHeightCm"), LowestSampleHeightCm);
        RootObject->SetNumberField(TEXT("highestSampleHeightCm"), HighestSampleHeightCm);
        RootObject->SetNumberField(TEXT("sampleHeightStepCm"), SampleHeightStepCm);
        RootObject->SetNumberField(TEXT("lowerPercentile"), LowerPercentile);
        RootObject->SetNumberField(TEXT("upperPercentile"), UpperPercentile);
        RootObject->SetStringField(
            TEXT("surfaceSampling"),
            TEXT("torso-skin-weight-filtered-triangle-plane-intersection-above-109cm"));
        RootObject->SetArrayField(TEXT("sections"), JsonSections);

        FString SerializedProfile;
        const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&SerializedProfile);
        if (!FJsonSerializer::Serialize(RootObject, Writer))
        {
            UE_LOG(LogTemp, Error, TEXT("Patterna could not serialize the live body profile."));
            return;
        }

        const FString ProfileDirectory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Patterna"));
        IFileManager::Get().MakeDirectory(*ProfileDirectory, true);
        const FString ProfilePath = FPaths::Combine(ProfileDirectory, TEXT("LiveBodyProfile.json"));
        if (!FFileHelper::SaveStringToFile(SerializedProfile, *ProfilePath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
        {
            UE_LOG(LogTemp, Error, TEXT("Patterna could not save the live body profile to %s."), *ProfilePath);
            return;
        }

        UE_LOG(LogTemp, Display, TEXT("Patterna saved the live body profile to %s."), *ProfilePath);
    }

    bool ExportLiveBodyMesh(USkeletalMeshComponent* const BodyPose)
    {
        const USkeletalMesh* const BodyMesh = BodyPose
            ? BodyPose->GetSkeletalMeshAsset()
            : nullptr;
        const FSkeletalMeshRenderData* const RenderData = BodyMesh
            ? BodyMesh->GetResourceForRendering()
            : nullptr;
        if (!BodyPose || !BodyMesh || !RenderData || RenderData->LODRenderData.IsEmpty())
        {
            UE_LOG(LogTemp, Error, TEXT("Patterna could not export the live avatar surface because its render data is unavailable."));
            return false;
        }

        const int32 ExportLodIndex = FMath::Min(1, RenderData->LODRenderData.Num() - 1);
        TArray<FFinalSkinVertex> SkinnedVertices;
        BodyPose->GetCPUSkinnedVertices(SkinnedVertices, ExportLodIndex);
        const FSkeletalMeshLODRenderData& LodData = RenderData->LODRenderData[ExportLodIndex];
        const FRawStaticIndexBuffer16or32Interface* const IndexBuffer =
            LodData.MultiSizeIndexContainer.GetIndexBuffer();
        if (SkinnedVertices.IsEmpty() || !IndexBuffer || IndexBuffer->Num() < 3)
        {
            UE_LOG(LogTemp, Error, TEXT("Patterna could not export the live avatar surface because LOD %d has no CPU-readable geometry."), ExportLodIndex);
            return false;
        }

        int32 TriangleCount = 0;
        for (const FSkelMeshRenderSection& Section : LodData.RenderSections)
        {
            TriangleCount += Section.NumTriangles;
        }

        FString ObjText;
        ObjText.Reserve(SkinnedVertices.Num() * 72 + TriangleCount * 36);
        ObjText.Append(TEXT("# Patterna exact live MetaHuman body surface\n"));
        ObjText.Appendf(TEXT("# source %s\n"), *BodyMesh->GetPathName());
        ObjText.Appendf(TEXT("# lod %d vertices %d triangles %d\n"), ExportLodIndex, SkinnedVertices.Num(), TriangleCount);
        ObjText.Append(TEXT("# coordinates: GarmentCode meters, X width, Y height, Z depth\n"));
        for (const FFinalSkinVertex& Vertex : SkinnedVertices)
        {
            const FVector3f PositionCm = Vertex.Position;
            ObjText.Appendf(
                TEXT("v %.9f %.9f %.9f\n"),
                PositionCm.X / 100.0f,
                PositionCm.Z / 100.0f,
                PositionCm.Y / 100.0f);
        }

        for (const FSkelMeshRenderSection& Section : LodData.RenderSections)
        {
            for (uint32 TriangleIndex = 0; TriangleIndex < Section.NumTriangles; ++TriangleIndex)
            {
                const uint32 FirstIndex = Section.BaseIndex + TriangleIndex * 3;
                const uint32 VertexIndex0 = IndexBuffer->Get(FirstIndex) + 1;
                const uint32 VertexIndex1 = IndexBuffer->Get(FirstIndex + 1) + 1;
                const uint32 VertexIndex2 = IndexBuffer->Get(FirstIndex + 2) + 1;
                ObjText.Appendf(
                    TEXT("f %u %u %u\n"),
                    VertexIndex0,
                    VertexIndex1,
                    VertexIndex2);
            }
        }

        const FString OutputDirectory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Patterna"));
        IFileManager::Get().MakeDirectory(*OutputDirectory, true);
        const FString OutputPath = FPaths::Combine(OutputDirectory, TEXT("LiveBodyMesh.obj"));
        if (!FFileHelper::SaveStringToFile(
            ObjText,
            *OutputPath,
            FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
        {
            UE_LOG(LogTemp, Error, TEXT("Patterna could not save the exact live body mesh to %s."), *OutputPath);
            return false;
        }

        UE_LOG(
            LogTemp,
            Display,
            TEXT("Patterna exported exact live body LOD %d to %s with %d vertices and %d triangles."),
            ExportLodIndex,
            *OutputPath,
            SkinnedVertices.Num(),
            TriangleCount);
        return true;
    }

    void LogBodyMaterialsAndCollision(
        const USkeletalMeshComponent* const BodyPose,
        const UPhysicsAsset* const PhysicsAsset)
    {
        const USkeletalMesh* const BodyMesh = BodyPose ? BodyPose->GetSkeletalMeshAsset() : nullptr;
        if (BodyMesh)
        {
            const TArray<FSkeletalMaterial>& Materials = BodyMesh->GetMaterials();
            for (int32 MaterialIndex = 0; MaterialIndex < Materials.Num(); ++MaterialIndex)
            {
                const FSkeletalMaterial& Material = Materials[MaterialIndex];
                UE_LOG(
                    LogTemp,
                    Display,
                    TEXT("Patterna body material %d: slot %s, interface %s."),
                    MaterialIndex,
                    *Material.MaterialSlotName.ToString(),
                    Material.MaterialInterface ? *Material.MaterialInterface->GetPathName() : TEXT("<none>"));
            }
        }

        if (!PhysicsAsset)
        {
            return;
        }

        for (const USkeletalBodySetup* const BodySetup : PhysicsAsset->SkeletalBodySetups)
        {
            if (!BodySetup)
            {
                continue;
            }

            const FKAggregateGeom& Geometry = BodySetup->AggGeom;
            UE_LOG(
                LogTemp,
                Display,
                TEXT("Patterna collision body %s: %d spheres, %d boxes, %d capsules, %d convexes."),
                *BodySetup->BoneName.ToString(),
                Geometry.SphereElems.Num(),
                Geometry.BoxElems.Num(),
                Geometry.SphylElems.Num(),
                Geometry.ConvexElems.Num());

            for (int32 BoxIndex = 0; BoxIndex < Geometry.BoxElems.Num(); ++BoxIndex)
            {
                const FKBoxElem& Box = Geometry.BoxElems[BoxIndex];
                UE_LOG(
                    LogTemp,
                    Display,
                    TEXT("Patterna collision box %s[%d]: center %s, rotation %s, dimensions %.2f x %.2f x %.2f cm."),
                    *BodySetup->BoneName.ToString(),
                    BoxIndex,
                    *Box.Center.ToCompactString(),
                    *Box.Rotation.ToCompactString(),
                    Box.X,
                    Box.Y,
                    Box.Z);
            }

            for (int32 CapsuleIndex = 0; CapsuleIndex < Geometry.SphylElems.Num(); ++CapsuleIndex)
            {
                const FKSphylElem& Capsule = Geometry.SphylElems[CapsuleIndex];
                UE_LOG(
                    LogTemp,
                    Display,
                    TEXT("Patterna collision capsule %s[%d]: center %s, rotation %s, radius %.2f cm, length %.2f cm."),
                    *BodySetup->BoneName.ToString(),
                    CapsuleIndex,
                    *Capsule.Center.ToCompactString(),
                    *Capsule.Rotation.ToCompactString(),
                    Capsule.Radius,
                    Capsule.Length);
            }
        }
    }
}

APatternaAvatarPreviewActor::APatternaAvatarPreviewActor()
{
    PrimaryActorTick.bCanEverTick = true;

    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    SetRootComponent(SceneRoot);

    AvatarRoot = CreateDefaultSubobject<USceneComponent>(TEXT("AvatarRoot"));
    AvatarRoot->SetupAttachment(SceneRoot);

    MetaHuman = CreateDefaultSubobject<UChildActorComponent>(TEXT("MetaHuman"));
    MetaHuman->SetupAttachment(AvatarRoot);

    Garment = CreateDefaultSubobject<UChaosClothComponent>(TEXT("Garment"));
    Garment->SetupAttachment(AvatarRoot);
    Garment->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Garment->SetGenerateOverlapEvents(false);
    Garment->SetCollideWithEnvironment(true);

    Floor = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Floor"));
    Floor->SetupAttachment(SceneRoot);
    Floor->SetRelativeLocation(FVector(0.0f, 0.0f, -1.0f));
    Floor->SetRelativeScale3D(FVector(6.0f, 6.0f, 1.0f));
    Floor->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    Floor->SetGenerateOverlapEvents(false);

    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
    Camera->SetupAttachment(SceneRoot);
    Camera->SetFieldOfView(34.0f);
    Camera->bAutoActivate = true;

    FillLight = CreateDefaultSubobject<URectLightComponent>(TEXT("FillLight"));
    FillLight->SetupAttachment(SceneRoot);
    FillLight->SetRelativeLocation(FVector(180.0f, -180.0f, 190.0f));
    FillLight->SetRelativeRotation(FRotator(-25.0f, 135.0f, 0.0f));
    FillLight->SetIntensity(5000.0f);
    FillLight->SetSourceWidth(220.0f);
    FillLight->SetSourceHeight(220.0f);

    RimLight = CreateDefaultSubobject<URectLightComponent>(TEXT("RimLight"));
    RimLight->SetupAttachment(SceneRoot);
    RimLight->SetRelativeLocation(FVector(-190.0f, 170.0f, 165.0f));
    RimLight->SetRelativeRotation(FRotator(-20.0f, -45.0f, 0.0f));
    RimLight->SetIntensity(3600.0f);
    RimLight->SetSourceWidth(200.0f);
    RimLight->SetSourceHeight(200.0f);

    SkyLight = CreateDefaultSubobject<USkyLightComponent>(TEXT("SkyLight"));
    SkyLight->SetupAttachment(SceneRoot);
    SkyLight->SetIntensity(1.1f);
    SkyLight->SetRealTimeCaptureEnabled(true);

    static ConstructorHelpers::FClassFinder<AActor> MetaHumanBlueprintFinder(
        TEXT("/Game/PatternaMeasuredV2/MH_Patterna_Female_Default/BP_MH_Patterna_Female_Default")
    );
    if (MetaHumanBlueprintFinder.Succeeded())
    {
        MetaHuman->SetChildActorClass(MetaHumanBlueprintFinder.Class);
    }

    static ConstructorHelpers::FObjectFinder<UPhysicsAsset> PhysicsAssetFinder(
        TEXT("/Game/PatternaMeasuredV2/MH_Patterna_Female_Default/Body/PHYS_MH_Patterna_Female_Default.PHYS_MH_Patterna_Female_Default")
    );
    if (PhysicsAssetFinder.Succeeded())
    {
        BodyPhysicsAsset = PhysicsAssetFinder.Object;
    }

    static ConstructorHelpers::FObjectFinder<UStaticMesh> FloorMeshFinder(
        TEXT("/Engine/BasicShapes/Plane.Plane")
    );
    if (FloorMeshFinder.Succeeded())
    {
        Floor->SetStaticMesh(FloorMeshFinder.Object);
    }

    UpdateCameraTransform();
}

void APatternaAvatarPreviewActor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    UpdateCameraTransform();
}

void APatternaAvatarPreviewActor::BeginPlay()
{
    Super::BeginPlay();

    SetViewAngle(90.0f);
    bCaptureAcceptanceViews = FParse::Param(
        FCommandLine::Get(),
        TEXT("PatternaCaptureViews"));
    bFittedDressPreview = FParse::Param(
        FCommandLine::Get(),
        TEXT("PatternaFittedDressPreview"));
    bShirtPreview = FParse::Param(
        FCommandLine::Get(),
        TEXT("PatternaShirtPreview"));
    bFullDressPreview = bFittedDressPreview || bShirtPreview || FParse::Param(
        FCommandLine::Get(),
        TEXT("PatternaFullDressPreview"));
    const bool bRawFullDressPreview = FParse::Param(
        FCommandLine::Get(),
        TEXT("PatternaRawFullDressPreview"));

    const TCHAR* GarmentPath = bShirtPreview
        ? TEXT("/Game/PatternaMeasuredGarments/V6/PatternaFemaleShirt/ClothAssets/PatternaFemaleShirt.PatternaFemaleShirt")
        : bFittedDressPreview
        ? TEXT("/Game/PatternaMeasuredGarments/V4/PatternaDefaultFemalePencilDress/ClothAssets/PatternaFittedPencilDress.PatternaFittedPencilDress")
        : bFullDressPreview
        ? bRawFullDressPreview
            ? TEXT("/Game/PatternaMeasuredGarments/V3/PatternaWrapDress/ClothAssets/PatternaWrapDress.PatternaWrapDress")
            : TEXT("/Game/Outfits/PatternaWrapDress/PatternaWrapDress/PatternaWrapDress_ResizableV8.PatternaWrapDress_ResizableV8")
        : TEXT("/Game/PatternaMeasuredGarments/V2/PatternaFlaredSkirt/ClothAssets/PatternaFlaredSkirt.PatternaFlaredSkirt");

    GarmentAsset = LoadObject<UChaosClothAssetBase>(
        nullptr,
        GarmentPath
    );
    UE_LOG(
        LogTemp,
        Display,
        TEXT("Patterna preview garment selected: %s."),
        GarmentAsset ? *GarmentAsset->GetPathName() : TEXT("missing"));
    ConfigureClothSimulation();
}

void APatternaAvatarPreviewActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);

    if (bAutoOrbit)
    {
        OrbitAngleDegrees = FMath::Fmod(
            OrbitAngleDegrees + OrbitDegreesPerSecond * DeltaSeconds,
            360.0f
        );
        UpdateCameraTransform();
    }

    if (bCaptureAcceptanceViews)
    {
        UpdateAcceptanceViewCapture(DeltaSeconds);
    }
}

void APatternaAvatarPreviewActor::SetViewAngle(const float AngleDegrees)
{
    bAutoOrbit = false;
    OrbitAngleDegrees = FMath::Fmod(AngleDegrees, 360.0f);
    if (OrbitAngleDegrees < 0.0f)
    {
        OrbitAngleDegrees += 360.0f;
    }
    UpdateCameraTransform();
    UE_LOG(LogTemp, Display, TEXT("Patterna camera view angle set to %.1f degrees."), OrbitAngleDegrees);
}

void APatternaAvatarPreviewActor::UpdateAcceptanceViewCapture(const float DeltaSeconds)
{
    struct FAcceptanceView
    {
        float AngleDegrees;
        const TCHAR* Name;
        float DistanceCm;
        float FocusHeightCm;
    };

    static constexpr FAcceptanceView AcceptanceViews[] = {
        { 90.0f, TEXT("front"), 580.0f, 96.0f },
        { 0.0f, TEXT("right-side"), 580.0f, 96.0f },
        { 270.0f, TEXT("rear"), 580.0f, 96.0f },
        { 180.0f, TEXT("left-side"), 580.0f, 96.0f },
        { 45.0f, TEXT("front-oblique"), 580.0f, 96.0f },
        { 315.0f, TEXT("rear-oblique"), 580.0f, 96.0f },
        { 45.0f, TEXT("fabric-detail"), 100.0f, 120.0f }
    };
    const int32 InitialSettleFrames = bFullDressPreview ? 600 : 180;
    constexpr int32 FramesBetweenViews = 30;

    AcceptanceCaptureElapsedSeconds += DeltaSeconds;
    ++AcceptanceCaptureSimulationFrames;
    const int32 RequiredSimulationFrames =
        InitialSettleFrames + (AcceptanceCaptureViewIndex * FramesBetweenViews);
    if (AcceptanceCaptureSimulationFrames < RequiredSimulationFrames)
    {
        return;
    }

    if (AcceptanceCaptureViewIndex >= UE_ARRAY_COUNT(AcceptanceViews))
    {
        bCaptureAcceptanceViews = false;
        UE_LOG(LogTemp, Display, TEXT("Patterna acceptance view capture completed."));
        if (FParse::Param(FCommandLine::Get(), TEXT("PatternaExitAfterCapture")))
        {
            FPlatformMisc::RequestExit(false);
        }
        return;
    }

    const FAcceptanceView& View = AcceptanceViews[AcceptanceCaptureViewIndex];
    CameraDistance = View.DistanceCm;
    CameraFocus.Z = View.FocusHeightCm;
    SetViewAngle(View.AngleDegrees);

    const TCHAR* CaptureFolder = bShirtPreview
        ? TEXT("ShirtAcceptanceViews")
        : bFittedDressPreview
        ? TEXT("FittedDressAcceptanceViews")
        : bFullDressPreview
            ? TEXT("FullDressAcceptanceViews")
            : TEXT("AcceptanceViews");
    const FString CaptureDirectory = FPaths::Combine(
        FPaths::ProjectSavedDir(),
        TEXT("Patterna"),
        CaptureFolder);
    IFileManager::Get().MakeDirectory(*CaptureDirectory, true);
    const FString CapturePath = FPaths::Combine(
        CaptureDirectory,
        bShirtPreview
            ? FString::Printf(
                TEXT("PatternaShirt-%02d-%s.png"),
                AcceptanceCaptureViewIndex + 1,
                View.Name)
            : bFittedDressPreview
            ? FString::Printf(
                TEXT("PatternaFittedDress-%02d-%s.png"),
                AcceptanceCaptureViewIndex + 1,
                View.Name)
            : bFullDressPreview
            ? FString::Printf(
                TEXT("PatternaFullDress-%02d-%s.png"),
                AcceptanceCaptureViewIndex + 1,
                View.Name)
            : FString::Printf(
                TEXT("Patterna-%02d-%s.png"),
                AcceptanceCaptureViewIndex + 1,
                View.Name));
    FScreenshotRequest::RequestScreenshot(
        CapturePath,
        false,
        false,
        false,
        FIntRect(),
        true);
    UE_LOG(
        LogTemp,
        Display,
        TEXT("Patterna requested %s acceptance screenshot at %.1f degrees: %s"),
        View.Name,
        View.AngleDegrees,
        *CapturePath);
    if (AcceptanceCaptureViewIndex == 0)
    {
        const UE::Chaos::ClothAsset::FClothSimulationProxy* const SimulationProxy =
            Garment->GetClothSimulationProxy();
        UE_LOG(
            LogTemp,
            Display,
            TEXT("Patterna settled acceptance state: %d simulation frames, %.2f elapsed wall seconds, solver iterations %d, substeps %d."),
            AcceptanceCaptureSimulationFrames,
            AcceptanceCaptureElapsedSeconds,
            SimulationProxy ? SimulationProxy->GetNumIterations() : 0,
            SimulationProxy ? SimulationProxy->GetNumSubsteps() : 0);
    }
    ++AcceptanceCaptureViewIndex;
}

UPhysicsAsset* APatternaAvatarPreviewActor::BuildGarmentCollisionPhysicsAsset(
    USkeletalMeshComponent* const BodyPose)
{
    if (!BodyPose || !BodyPhysicsAsset)
    {
        return nullptr;
    }

    TArray<FFinalSkinVertex> SkinnedVertices;
    BodyPose->GetCPUSkinnedVertices(SkinnedVertices, 0);
    if (SkinnedVertices.IsEmpty())
    {
        UE_LOG(LogTemp, Error, TEXT("Patterna could not build measured garment collision because the live body mesh had no CPU vertices."));
        return nullptr;
    }

    UPhysicsAsset* const CollisionAsset = DuplicateObject<UPhysicsAsset>(BodyPhysicsAsset, this);
    if (!CollisionAsset)
    {
        UE_LOG(LogTemp, Error, TEXT("Patterna could not duplicate the avatar physics asset for garment collision."));
        return nullptr;
    }

    USkeletalBodySetup* PelvisSetup = nullptr;
    for (USkeletalBodySetup* const BodySetup : CollisionAsset->SkeletalBodySetups)
    {
        if (!BodySetup)
        {
            continue;
        }

        if (BodySetup->BoneName == TEXT("pelvis"))
        {
            PelvisSetup = BodySetup;
        }

        const bool bMeasuredDressTorsoBody = bFullDressPreview &&
            BodySetup->BoneName.ToString().StartsWith(TEXT("spine_"));
        if (BodySetup->BoneName == TEXT("pelvis") ||
            BodySetup->BoneName == TEXT("spine_02") ||
            bMeasuredDressTorsoBody)
        {
            BodySetup->AggGeom.SphereElems.Reset();
            BodySetup->AggGeom.BoxElems.Reset();
            BodySetup->AggGeom.SphylElems.Reset();
            BodySetup->AggGeom.ConvexElems.Reset();
        }
    }

    if (!PelvisSetup)
    {
        UE_LOG(LogTemp, Error, TEXT("Patterna could not find the pelvis collision body in the duplicated physics asset."));
        return nullptr;
    }

    const int32 PelvisBoneIndex = BodyPose->GetBoneIndex(TEXT("pelvis"));
    if (PelvisBoneIndex == INDEX_NONE)
    {
        UE_LOG(LogTemp, Error, TEXT("Patterna could not find the pelvis bone on the live avatar."));
        return nullptr;
    }

    const FTransform PelvisComponentTransform = BodyPose->GetBoneTransform(
        PelvisBoneIndex,
        FTransform::Identity);

    constexpr float SampleHalfBandCm = 0.75f;
    constexpr float TorsoHalfWidthLimitCm = 25.0f;
    constexpr float TorsoHalfDepthLimitCm = 30.0f;
    constexpr float LowerPercentile = 0.05f;
    constexpr float UpperPercentile = 0.95f;
    constexpr float SphereRadiusCm = 3.0f;
    constexpr float SurfaceAllowanceCm = 0.2f;
    constexpr float SurfaceOutlierAllowanceCm = 1.5f;
    constexpr int32 RingSphereCount = 32;

    TArray<float> SampleHeightsCm;
    const float HighestMeasuredSectionCm = bFullDressPreview ? 135.0f : 107.0f;
    for (float HeightCm = 95.0f; HeightCm <= HighestMeasuredSectionCm; HeightCm += 2.0f)
    {
        SampleHeightsCm.Add(HeightCm);
    }

    int32 GeneratedSphereCount = 0;
    int32 GeneratedSectionCount = 0;
    int32 GeneratedShoulderSphereCount = 0;
    float UpperReferenceCenterX = 0.0f;
    float UpperReferenceCenterY = 0.0f;
    float UpperReferenceHalfWidth = 0.0f;
    float UpperReferenceHalfDepth = 0.0f;
    bool bHasUpperReference = false;

    const auto AddCollisionRing = [
        &PelvisComponentTransform,
        &PelvisSetup,
        &GeneratedSphereCount](
            const TArray<FVector2D>& SurfacePoints,
            const float CenterX,
            const float CenterY,
            const float HeightCm)
    {
        for (const FVector2D& SurfacePoint : SurfacePoints)
        {
            const FVector2D OutwardDirection = FVector2D(
                SurfacePoint.X - CenterX,
                SurfacePoint.Y - CenterY).GetSafeNormal();
            const FVector ComponentCenter(
                SurfacePoint.X - OutwardDirection.X * (SphereRadiusCm - SurfaceAllowanceCm),
                SurfacePoint.Y - OutwardDirection.Y * (SphereRadiusCm - SurfaceAllowanceCm),
                HeightCm);

            FKSphereElem Sphere;
            Sphere.Center = PelvisComponentTransform.InverseTransformPosition(ComponentCenter);
            Sphere.Radius = SphereRadiusCm;
            PelvisSetup->AggGeom.SphereElems.Add(Sphere);
            ++GeneratedSphereCount;
        }
    };

    for (const float SampleHeightCm : SampleHeightsCm)
    {
        TArray<float> WidthSamples;
        TArray<float> DepthSamples;
        TArray<FVector2D> CrossSectionSamples;
        for (const FFinalSkinVertex& Vertex : SkinnedVertices)
        {
            const FVector3f Position = Vertex.Position;
            if (FMath::Abs(Position.Z - SampleHeightCm) > SampleHalfBandCm ||
                FMath::Abs(Position.X) > TorsoHalfWidthLimitCm ||
                FMath::Abs(Position.Y) > TorsoHalfDepthLimitCm)
            {
                continue;
            }

            WidthSamples.Add(Position.X);
            DepthSamples.Add(Position.Y);
            CrossSectionSamples.Add(FVector2D(Position.X, Position.Y));
        }

        if (WidthSamples.Num() < 20)
        {
            UE_LOG(
                LogTemp,
                Warning,
                TEXT("Patterna skipped garment collision cross-section Z %.1f cm because it had only %d samples."),
                SampleHeightCm,
                WidthSamples.Num());
            continue;
        }

        WidthSamples.Sort();
        DepthSamples.Sort();
        const float MinimumX = GetPercentile(WidthSamples, LowerPercentile);
        const float MaximumX = GetPercentile(WidthSamples, UpperPercentile);
        const float MinimumY = GetPercentile(DepthSamples, LowerPercentile);
        const float MaximumY = GetPercentile(DepthSamples, UpperPercentile);
        const float CenterX = (MinimumX + MaximumX) * 0.5f;
        const float CenterY = (MinimumY + MaximumY) * 0.5f;
        if (bFullDressPreview && SampleHeightCm >= 135.0f)
        {
            UpperReferenceCenterX = CenterX;
            UpperReferenceCenterY = CenterY;
            UpperReferenceHalfWidth = (MaximumX - MinimumX) * 0.5f;
            UpperReferenceHalfDepth = (MaximumY - MinimumY) * 0.5f;
            bHasUpperReference = true;
        }
        const TArray<FVector2D> SurfacePoints = GetOuterBodySurfacePoints(
            CrossSectionSamples,
            CenterX,
            CenterY,
            MinimumX,
            MaximumX,
            MinimumY,
            MaximumY,
            RingSphereCount,
            SurfaceOutlierAllowanceCm);

        AddCollisionRing(SurfacePoints, CenterX, CenterY, SampleHeightCm);

        if (SurfacePoints.Num() < RingSphereCount / 2)
        {
            UE_LOG(
                LogTemp,
                Warning,
                TEXT("Patterna garment collision cross-section Z %.1f cm covered only %d of %d angular sectors."),
                SampleHeightCm,
                SurfacePoints.Num(),
                RingSphereCount);
        }

        ++GeneratedSectionCount;
    }

    if (bFullDressPreview && bHasUpperReference)
    {
        constexpr float ShoulderCollisionHeightCm = 139.0f;
        constexpr float ShoulderHalfWidthCm = 20.25f;
        constexpr float ShoulderHalfDepthCm = 9.5f;
        constexpr float ShoulderCenterYCm = -2.5f;
        for (float HeightCm = 137.0f; HeightCm <= ShoulderCollisionHeightCm; HeightCm += 2.0f)
        {
            const float Blend = (HeightCm - 135.0f) / (149.0f - 135.0f);
            const float CenterX = FMath::Lerp(UpperReferenceCenterX, 0.0f, Blend);
            const float CenterY = FMath::Lerp(UpperReferenceCenterY, ShoulderCenterYCm, Blend);
            const float HalfWidth = FMath::Lerp(UpperReferenceHalfWidth, ShoulderHalfWidthCm, Blend);
            const float HalfDepth = FMath::Lerp(UpperReferenceHalfDepth, ShoulderHalfDepthCm, Blend);
            TArray<FVector2D> SurfacePoints;
            SurfacePoints.Reserve(RingSphereCount);
            for (int32 Index = 0; Index < RingSphereCount; ++Index)
            {
                const float Angle = 2.0f * UE_PI * Index / RingSphereCount;
                SurfacePoints.Add(FVector2D(
                    CenterX + HalfWidth * FMath::Cos(Angle),
                    CenterY + HalfDepth * FMath::Sin(Angle)));
            }
            AddCollisionRing(SurfacePoints, CenterX, CenterY, HeightCm);
            ++GeneratedSectionCount;
        }
    }

    if (bFullDressPreview)
    {
        constexpr float ShoulderMinimumHeightCm = 138.5f;
        constexpr float ShoulderMaximumHeightCm = 151.5f;
        constexpr float ShoulderMinimumLateralCm = 4.25f;
        constexpr float ShoulderMaximumLateralCm = 24.0f;
        constexpr float ShoulderMaximumDepthCm = 19.0f;
        constexpr float ShoulderMinimumUpNormal = 0.30f;
        constexpr float ShoulderSphereRadiusCm = 1.75f;
        constexpr float ShoulderSurfaceAllowanceCm = 0.12f;
        constexpr float ShoulderVoxelSizeCm = 2.25f;
        TSet<FIntVector> OccupiedShoulderVoxels;
        for (const FFinalSkinVertex& Vertex : SkinnedVertices)
        {
            const FVector3f Position = Vertex.Position;
            const FVector3f Normal = Vertex.TangentZ.ToFVector3f().GetSafeNormal();
            const float LateralDistanceCm = FMath::Abs(Position.X);
            if (Position.Z < ShoulderMinimumHeightCm ||
                Position.Z > ShoulderMaximumHeightCm ||
                LateralDistanceCm < ShoulderMinimumLateralCm ||
                LateralDistanceCm > ShoulderMaximumLateralCm ||
                FMath::Abs(Position.Y) > ShoulderMaximumDepthCm ||
                Normal.Z < ShoulderMinimumUpNormal)
            {
                continue;
            }

            const FIntVector Voxel(
                FMath::FloorToInt(Position.X / ShoulderVoxelSizeCm),
                FMath::FloorToInt(Position.Y / ShoulderVoxelSizeCm),
                FMath::FloorToInt(Position.Z / ShoulderVoxelSizeCm));
            if (OccupiedShoulderVoxels.Contains(Voxel))
            {
                continue;
            }
            OccupiedShoulderVoxels.Add(Voxel);

            const FVector ComponentCenter = FVector(
                Position - Normal *
                    (ShoulderSphereRadiusCm - ShoulderSurfaceAllowanceCm));
            FKSphereElem Sphere;
            Sphere.Center = PelvisComponentTransform.InverseTransformPosition(ComponentCenter);
            Sphere.Radius = ShoulderSphereRadiusCm;
            PelvisSetup->AggGeom.SphereElems.Add(Sphere);
            ++GeneratedSphereCount;
            ++GeneratedShoulderSphereCount;
        }

        if (GeneratedShoulderSphereCount == 0)
        {
            UE_LOG(
                LogTemp,
                Error,
                TEXT("Patterna measured garment collision did not generate a shoulder contact surface."));
            return nullptr;
        }
    }

    if (GeneratedSphereCount == 0)
    {
        UE_LOG(LogTemp, Error, TEXT("Patterna measured garment collision did not generate any body primitives."));
        return nullptr;
    }

    UE_LOG(
        LogTemp,
        Display,
        TEXT("Patterna built measured garment collision from %d live body cross-sections using %d spheres, including %d measured shoulder contact spheres."),
        GeneratedSectionCount,
        GeneratedSphereCount,
        GeneratedShoulderSphereCount);
    return CollisionAsset;
}

void APatternaAvatarPreviewActor::ConfigureClothSimulation()
{
    USkeletalMeshComponent* BodyPose = FindBodyPoseComponent();
    if (!BodyPose || !Garment || !GarmentAsset || !BodyPhysicsAsset)
    {
        UE_LOG(
            LogTemp,
            Error,
            TEXT("Patterna assembled MetaHuman or garment assets are incomplete; cloth simulation cannot start.")
        );
        return;
    }

    BodyPose->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    BodyPose->SetGenerateOverlapEvents(false);
    BodyPose->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    ApplyCleanBodyBaseColor(BodyPose);
    LogBodyMaterialsAndCollision(BodyPose, BodyPhysicsAsset);
    LogBodyCrossSections(BodyPose);
    if (FParse::Param(FCommandLine::Get(), TEXT("PatternaExportLiveBodyMesh")))
    {
        ExportLiveBodyMesh(BodyPose);
    }
    GarmentCollisionPhysicsAsset = BuildGarmentCollisionPhysicsAsset(BodyPose);
    if (GarmentCollisionPhysicsAsset)
    {
        LogBodyMaterialsAndCollision(BodyPose, GarmentCollisionPhysicsAsset);
    }

    Garment->AttachToComponent(
        BodyPose,
        FAttachmentTransformRules::SnapToTargetNotIncludingScale
    );
    Garment->SetAsset(GarmentAsset);
    Garment->SetLeaderPoseComponent(BodyPose, true, false);
    Garment->SetBindToLeaderComponent(false);
    // The asset is loaded after this component's OnRegister call. SetAsset only
    // refreshes rendering, so rebuild the runtime properties and simulation
    // proxy explicitly or the component remains a static dressing-pose mesh.
    Garment->SetAsset(GarmentAsset);
    Garment->ResetConfigProperties();
    Garment->RecreateClothSimulationProxy();
    Garment->ResetCollisionSources();
    // The source MetaHuman asset uses large circular torso capsules. The
    // runtime duplicate replaces them with a live, measurement-derived shell
    // while retaining the original limb collision primitives.
    Garment->AddCollisionSource(
        BodyPose,
        GarmentCollisionPhysicsAsset ? GarmentCollisionPhysicsAsset : BodyPhysicsAsset,
        false);
    const bool bDisableSimulationForInspection = FParse::Param(
        FCommandLine::Get(),
        TEXT("PatternaDisableSimulation"));
    const bool bEnableExperimentalChaosRefinement = FParse::Param(
        FCommandLine::Get(),
        TEXT("PatternaEnableChaosRefinement"));
    const bool bUseSolvedWarpEquilibrium =
        bShirtPreview && !bEnableExperimentalChaosRefinement;
    Garment->SetEnableSimulation(
        !bDisableSimulationForInspection && !bUseSolvedWarpEquilibrium);
    Garment->ForceNextUpdateTeleportAndReset();

    if (bUseSolvedWarpEquilibrium)
    {
        UE_LOG(
            LogTemp,
            Display,
            TEXT("Patterna shirt preview is rendering the accepted Warp equilibrium. Pass -PatternaEnableChaosRefinement to run the experimental Chaos refinement path."));
    }

    for (int32 ModelIndex = 0; ModelIndex < GarmentAsset->GetNumClothSimulationModels(); ++ModelIndex)
    {
        const TArray<TSharedRef<const FManagedArrayCollection>>& ClothCollections =
            GarmentAsset->GetCollections(ModelIndex);
        for (int32 CollectionIndex = 0; CollectionIndex < ClothCollections.Num(); ++CollectionIndex)
        {
            const UE::Chaos::ClothAsset::FCollectionClothConstFacade ClothFacade(
                ClothCollections[CollectionIndex]
            );

            int32 TotalSeamStitches = 0;
            for (int32 SeamIndex = 0; SeamIndex < ClothFacade.GetNumSeams(); ++SeamIndex)
            {
                TotalSeamStitches += ClothFacade.GetSeam(SeamIndex).GetNumSeamStitches();
            }

            UE_LOG(
                LogTemp,
                Display,
                TEXT("Patterna cloth model %d LOD %d: %d sim patterns, %d sim vertices, %d render patterns, %d seams, %d seam stitches, skeleton %s, physics %s."),
                ModelIndex,
                CollectionIndex,
                ClothFacade.GetNumSimPatterns(),
                ClothFacade.GetNumSimVertices3D(),
                ClothFacade.GetNumRenderPatterns(),
                ClothFacade.GetNumSeams(),
                TotalSeamStitches,
                *ClothFacade.GetSkeletalMeshSoftObjectPathName().ToString(),
                *ClothFacade.GetPhysicsAssetSoftObjectPathName().ToString()
            );
        }
    }

    UE_LOG(
        LogTemp,
        Display,
        TEXT("Patterna cloth runtime state: registered %s, simulation enabled %s."),
        Garment->IsRegistered() ? TEXT("yes") : TEXT("no"),
        Garment->IsSimulationEnabled() ? TEXT("yes") : TEXT("no")
    );

    const UE::Chaos::ClothAsset::FClothSimulationProxy* const SimulationProxy =
        Garment->GetClothSimulationProxy();
    UE_LOG(
        LogTemp,
        Display,
        TEXT("Patterna cloth proxy state: proxy %s, cloths %d, dynamic particles %d, kinematic particles %d, iterations %d, substeps %d."),
        SimulationProxy ? TEXT("yes") : TEXT("no"),
        SimulationProxy ? SimulationProxy->GetNumCloths() : 0,
        SimulationProxy ? SimulationProxy->GetNumDynamicParticles() : 0,
        SimulationProxy ? SimulationProxy->GetNumKinematicParticles() : 0,
        SimulationProxy ? SimulationProxy->GetNumIterations() : 0,
        SimulationProxy ? SimulationProxy->GetNumSubsteps() : 0
    );
}

USkeletalMeshComponent* APatternaAvatarPreviewActor::FindBodyPoseComponent() const
{
    const AActor* MetaHumanActor = MetaHuman ? MetaHuman->GetChildActor() : nullptr;
    if (!MetaHumanActor)
    {
        return nullptr;
    }

    TInlineComponentArray<USkeletalMeshComponent*> SkeletalMeshes;
    MetaHumanActor->GetComponents(SkeletalMeshes);

    for (const USkeletalMeshComponent* const SkeletalMesh : SkeletalMeshes)
    {
        UE_LOG(
            LogTemp,
            Display,
            TEXT("Patterna MetaHuman component %s uses mesh %s and is visible %s."),
            SkeletalMesh ? *SkeletalMesh->GetName() : TEXT("<null>"),
            SkeletalMesh && SkeletalMesh->GetSkeletalMeshAsset()
                ? *SkeletalMesh->GetSkeletalMeshAsset()->GetPathName()
                : TEXT("<none>"),
            SkeletalMesh && SkeletalMesh->IsVisible() ? TEXT("yes") : TEXT("no"));
    }

    for (USkeletalMeshComponent* SkeletalMesh : SkeletalMeshes)
    {
        if (SkeletalMesh && SkeletalMesh->GetName().Equals(TEXT("Body"), ESearchCase::IgnoreCase))
        {
            return SkeletalMesh;
        }
    }

    for (USkeletalMeshComponent* SkeletalMesh : SkeletalMeshes)
    {
        const FString AssetName = SkeletalMesh && SkeletalMesh->GetSkeletalMeshAsset()
            ? SkeletalMesh->GetSkeletalMeshAsset()->GetName()
            : FString();
        if (AssetName.Contains(TEXT("BodyMesh"), ESearchCase::IgnoreCase))
        {
            return SkeletalMesh;
        }
    }

    return nullptr;
}

void APatternaAvatarPreviewActor::UpdateCameraTransform()
{
    if (!Camera)
    {
        return;
    }

    const float OrbitRadians = FMath::DegreesToRadians(OrbitAngleDegrees);
    const FVector CameraLocation(
        FMath::Cos(OrbitRadians) * CameraDistance,
        FMath::Sin(OrbitRadians) * CameraDistance,
        CameraFocus.Z + 8.0f
    );

    Camera->SetRelativeLocation(CameraLocation);
    Camera->SetRelativeRotation((CameraFocus - CameraLocation).Rotation());
}
