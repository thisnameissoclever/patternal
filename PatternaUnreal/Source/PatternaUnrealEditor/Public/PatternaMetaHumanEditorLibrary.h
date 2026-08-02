#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"

#include "PatternaMetaHumanEditorLibrary.generated.h"

class UMetaHumanCharacter;

UCLASS()
class PATTERNAUNREALEDITOR_API UPatternaMetaHumanEditorLibrary final : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category = "Patterna|MetaHuman")
    static bool GetBodyStateDiagnostics(
        UMetaHumanCharacter* Character,
        float& GlobalDeltaScale,
        int32& LodZeroVertexCount,
        FVector& Minimum,
        FVector& Maximum);

    UFUNCTION(BlueprintCallable, Category = "Patterna|MetaHuman")
    static bool SetBodyGlobalDeltaScale(UMetaHumanCharacter* Character, float GlobalDeltaScale);

    UFUNCTION(BlueprintCallable, Category = "Patterna|MetaHuman")
    static bool GetEvaluatedBodyCrossSections(
        UMetaHumanCharacter* Character,
        const TArray<float>& HeightsCm,
        TArray<FVector4>& Sections);

    UFUNCTION(BlueprintPure, Category = "Patterna|MetaHuman")
    static int32 GetBodyRigState(UMetaHumanCharacter* Character);
};
