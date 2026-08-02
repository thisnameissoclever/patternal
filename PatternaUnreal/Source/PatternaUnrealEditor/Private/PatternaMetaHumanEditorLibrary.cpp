#include "PatternaMetaHumanEditorLibrary.h"

#include "MetaHumanCharacter.h"
#include "MetaHumanCharacterBodyIdentity.h"
#include "MetaHumanCharacterEditorSubsystem.h"
#include "MetaHumanRigEvaluatedState.h"

namespace
{
    float GetPercentile(const TArray<float>& SortedValues, const float Percentile)
    {
        const float Position = FMath::Clamp(Percentile, 0.0f, 1.0f) * (SortedValues.Num() - 1);
        const int32 LowerIndex = FMath::FloorToInt(Position);
        const int32 UpperIndex = FMath::CeilToInt(Position);
        return FMath::Lerp(
            SortedValues[LowerIndex],
            SortedValues[UpperIndex],
            Position - LowerIndex);
    }
}

bool UPatternaMetaHumanEditorLibrary::GetBodyStateDiagnostics(
    UMetaHumanCharacter* const Character,
    float& GlobalDeltaScale,
    int32& LodZeroVertexCount,
    FVector& Minimum,
    FVector& Maximum)
{
    UMetaHumanCharacterEditorSubsystem* const Subsystem = UMetaHumanCharacterEditorSubsystem::Get();
    if (!Character || !Subsystem || !Subsystem->IsObjectAddedForEditing(Character))
    {
        return false;
    }

    const TSharedRef<const FMetaHumanCharacterBodyIdentity::FState> BodyState = Subsystem->GetBodyState(Character);
    const TArray<int32> VerticesPerLod = BodyState->GetNumVerticesPerLOD();
    if (VerticesPerLod.IsEmpty() || VerticesPerLod[0] <= 0)
    {
        return false;
    }

    const FMetaHumanRigEvaluatedState EvaluatedState = BodyState->GetVerticesAndVertexNormals();
    LodZeroVertexCount = FMath::Min(VerticesPerLod[0], EvaluatedState.Vertices.Num());
    if (LodZeroVertexCount <= 0)
    {
        return false;
    }

    FBox Bounds(ForceInit);
    for (int32 VertexIndex = 0; VertexIndex < LodZeroVertexCount; ++VertexIndex)
    {
        Bounds += FVector(EvaluatedState.Vertices[VertexIndex]);
    }

    GlobalDeltaScale = BodyState->GetGlobalDeltaScale();
    Minimum = Bounds.Min;
    Maximum = Bounds.Max;
    return Bounds.IsValid != 0;
}

bool UPatternaMetaHumanEditorLibrary::SetBodyGlobalDeltaScale(
    UMetaHumanCharacter* const Character,
    const float GlobalDeltaScale)
{
    UMetaHumanCharacterEditorSubsystem* const Subsystem = UMetaHumanCharacterEditorSubsystem::Get();
    if (!Character ||
        !Subsystem ||
        !Subsystem->IsObjectAddedForEditing(Character) ||
        !FMath::IsFinite(GlobalDeltaScale) ||
        GlobalDeltaScale < 0.0f ||
        GlobalDeltaScale > 2.0f)
    {
        return false;
    }

    Subsystem->SetBodyGlobalDeltaScale(Character, GlobalDeltaScale);
    return true;
}

bool UPatternaMetaHumanEditorLibrary::GetEvaluatedBodyCrossSections(
    UMetaHumanCharacter* const Character,
    const TArray<float>& HeightsCm,
    TArray<FVector4>& Sections)
{
    UMetaHumanCharacterEditorSubsystem* const Subsystem = UMetaHumanCharacterEditorSubsystem::Get();
    if (!Character || !Subsystem || !Subsystem->IsObjectAddedForEditing(Character))
    {
        return false;
    }

    const TSharedRef<const FMetaHumanCharacterBodyIdentity::FState> BodyState = Subsystem->GetBodyState(Character);
    const TArray<int32> VerticesPerLod = BodyState->GetNumVerticesPerLOD();
    if (VerticesPerLod.IsEmpty() || VerticesPerLod[0] <= 0)
    {
        return false;
    }

    const FMetaHumanRigEvaluatedState EvaluatedState = BodyState->GetVerticesAndVertexNormals();
    const int32 LodZeroVertexCount = FMath::Min(VerticesPerLod[0], EvaluatedState.Vertices.Num());
    Sections.Reset(HeightsCm.Num());
    for (const float HeightCm : HeightsCm)
    {
        TArray<float> WidthSamples;
        TArray<float> DepthSamples;
        for (int32 VertexIndex = 0; VertexIndex < LodZeroVertexCount; ++VertexIndex)
        {
            const FVector3f Position = EvaluatedState.Vertices[VertexIndex];
            if (FMath::Abs(Position.Y - HeightCm) > 0.75f ||
                FMath::Abs(Position.X) > 25.0f ||
                FMath::Abs(Position.Z) > 30.0f)
            {
                continue;
            }

            WidthSamples.Add(Position.X);
            DepthSamples.Add(Position.Z);
        }

        if (WidthSamples.Num() < 20)
        {
            Sections.Add(FVector4(HeightCm, 0.0f, 0.0f, 0.0f));
            continue;
        }

        WidthSamples.Sort();
        DepthSamples.Sort();
        const float WidthCm = GetPercentile(WidthSamples, 0.95f) - GetPercentile(WidthSamples, 0.05f);
        const float DepthCm = GetPercentile(DepthSamples, 0.95f) - GetPercentile(DepthSamples, 0.05f);
        const float WidthRadiusCm = WidthCm * 0.5f;
        const float DepthRadiusCm = DepthCm * 0.5f;
        const float RadiusSum = WidthRadiusCm + DepthRadiusCm;
        const float H = RadiusSum > SMALL_NUMBER
            ? FMath::Square((WidthRadiusCm - DepthRadiusCm) / RadiusSum)
            : 0.0f;
        const float CircumferenceCm = PI * RadiusSum *
            (1.0f + ((3.0f * H) / (10.0f + FMath::Sqrt(4.0f - (3.0f * H)))));
        Sections.Add(FVector4(HeightCm, WidthCm, DepthCm, CircumferenceCm));
    }

    return true;
}

int32 UPatternaMetaHumanEditorLibrary::GetBodyRigState(UMetaHumanCharacter* const Character)
{
    if (!Character)
    {
        return -1;
    }

    int32 State = Character->HasBodyDNA() ? 1 : 0;
    State |= Character->bFixedBodyType ? 2 : 0;
    return State;
}
