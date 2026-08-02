#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "PatternaAvatarPreviewActor.generated.h"

class UCameraComponent;
class UChaosClothAssetBase;
class UChaosClothComponent;
class UChildActorComponent;
class UPhysicsAsset;
class URectLightComponent;
class USceneComponent;
class USkeletalMeshComponent;
class USkyLightComponent;
class UStaticMeshComponent;

UCLASS()
class PATTERNAUNREAL_API APatternaAvatarPreviewActor final : public AActor
{
    GENERATED_BODY()

public:
    APatternaAvatarPreviewActor();

    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void OnConstruction(const FTransform& Transform) override;

    void SetViewAngle(float AngleDegrees);

private:
    void ConfigureClothSimulation();
    UPhysicsAsset* BuildGarmentCollisionPhysicsAsset(USkeletalMeshComponent* BodyPose);
    USkeletalMeshComponent* FindBodyPoseComponent() const;
    void UpdateAcceptanceViewCapture(float DeltaSeconds);
    void UpdateCameraTransform();

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Scene")
    TObjectPtr<USceneComponent> SceneRoot;

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Scene")
    TObjectPtr<USceneComponent> AvatarRoot;

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Avatar")
    TObjectPtr<UChildActorComponent> MetaHuman;

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Garment")
    TObjectPtr<UChaosClothComponent> Garment;

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Scene")
    TObjectPtr<UStaticMeshComponent> Floor;

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Scene")
    TObjectPtr<UCameraComponent> Camera;

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Lighting")
    TObjectPtr<URectLightComponent> FillLight;

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Lighting")
    TObjectPtr<URectLightComponent> RimLight;

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Lighting")
    TObjectPtr<USkyLightComponent> SkyLight;

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Assets")
    TObjectPtr<UChaosClothAssetBase> GarmentAsset;

    UPROPERTY(VisibleAnywhere, Category = "Patterna|Assets")
    TObjectPtr<UPhysicsAsset> BodyPhysicsAsset;

    UPROPERTY(Transient)
    TObjectPtr<UPhysicsAsset> GarmentCollisionPhysicsAsset;

    UPROPERTY(EditAnywhere, Category = "Patterna|Camera")
    bool bAutoOrbit = false;

    UPROPERTY(EditAnywhere, Category = "Patterna|Camera", meta = (ClampMin = "0.0", ClampMax = "30.0"))
    float OrbitDegreesPerSecond = 6.0f;

    UPROPERTY(EditAnywhere, Category = "Patterna|Camera", meta = (ClampMin = "200.0", ClampMax = "800.0"))
    float CameraDistance = 580.0f;

    UPROPERTY(EditAnywhere, Category = "Patterna|Camera")
    FVector CameraFocus = FVector(0.0f, 0.0f, 96.0f);

    float OrbitAngleDegrees = 0.0f;
    bool bCaptureAcceptanceViews = false;
    bool bFullDressPreview = false;
    bool bFittedDressPreview = false;
    bool bShirtPreview = false;
    float AcceptanceCaptureElapsedSeconds = 0.0f;
    int32 AcceptanceCaptureSimulationFrames = 0;
    int32 AcceptanceCaptureViewIndex = 0;
};
