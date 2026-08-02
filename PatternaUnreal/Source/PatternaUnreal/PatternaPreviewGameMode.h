#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "PatternaPreviewGameMode.generated.h"

class APatternaAvatarPreviewActor;

UCLASS()
class PATTERNAUNREAL_API APatternaPreviewGameMode final : public AGameModeBase
{
    GENERATED_BODY()

public:
    APatternaPreviewGameMode();

    virtual void BeginPlay() override;

private:
    UPROPERTY(Transient)
    TObjectPtr<APatternaAvatarPreviewActor> PreviewActor;
};
