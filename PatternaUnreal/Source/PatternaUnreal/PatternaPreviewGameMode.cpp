#include "PatternaPreviewGameMode.h"

#include "PatternaAvatarPreviewActor.h"

#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"

APatternaPreviewGameMode::APatternaPreviewGameMode()
{
    DefaultPawnClass = nullptr;
    bStartPlayersAsSpectators = true;
}

void APatternaPreviewGameMode::BeginPlay()
{
    Super::BeginPlay();

    UWorld* World = GetWorld();
    if (!World)
    {
        UE_LOG(LogTemp, Error, TEXT("Patterna preview world is unavailable."));
        return;
    }

    PreviewActor = World->SpawnActor<APatternaAvatarPreviewActor>(
        APatternaAvatarPreviewActor::StaticClass(),
        FVector::ZeroVector,
        FRotator::ZeroRotator
    );

    if (!PreviewActor)
    {
        UE_LOG(LogTemp, Error, TEXT("Patterna preview actor could not be spawned."));
        return;
    }

    if (APlayerController* PlayerController = UGameplayStatics::GetPlayerController(this, 0))
    {
        PlayerController->SetViewTarget(PreviewActor);
    }
}
