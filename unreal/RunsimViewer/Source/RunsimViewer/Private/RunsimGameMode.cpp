#include "RunsimGameMode.h"

#include "RunsimHUD.h"
#include "RunsimPawn.h"
#include "RunsimRunner.h"
#include "RunsimTerrain.h"
#include "RunsimViewer.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/LightComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/SkyLight.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerStart.h"

ARunsimGameMode::ARunsimGameMode()
{
	DefaultPawnClass = ARunsimPawn::StaticClass();
	HUDClass = ARunsimHUD::StaticClass();
	PlayerControllerClass = APlayerController::StaticClass();
}

void ARunsimGameMode::StartPlay()
{
	SpawnSceneIfNeeded();
	Super::StartPlay();
}

void ARunsimGameMode::SpawnSceneIfNeeded()
{
	UWorld* World = GetWorld();
	if (World == nullptr)
	{
		return;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride =
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	bool bHasTerrain = false;
	for (TActorIterator<ARunsimTerrain> It(World); It; ++It)
	{
		bHasTerrain = true;
		break;
	}
	if (!bHasTerrain)
	{
		World->SpawnActor<ARunsimTerrain>(ARunsimTerrain::StaticClass(),
			FTransform::Identity, Params);
	}

	bool bHasRunner = false;
	for (TActorIterator<ARunsimRunner> It(World); It; ++It)
	{
		bHasRunner = true;
		break;
	}
	if (!bHasRunner)
	{
		World->SpawnActor<ARunsimRunner>(ARunsimRunner::StaticClass(),
			FTransform::Identity, Params);
	}

	// An empty engine map has no PlayerStart, and AGameModeBase refuses to
	// spawn the default pawn without one. Provide it here so no level asset
	// (a .uasset) is ever needed.
	bool bHasPlayerStart = false;
	for (TActorIterator<APlayerStart> It(World); It; ++It)
	{
		bHasPlayerStart = true;
		break;
	}
	if (!bHasPlayerStart)
	{
		World->SpawnActor<APlayerStart>(APlayerStart::StaticClass(),
			FTransform(FRotator::ZeroRotator, FVector(0.0f, 0.0f, 200.0f)), Params);
	}

	SpawnLighting();
}

void ARunsimGameMode::SpawnLighting()
{
	UWorld* World = GetWorld();
	if (World == nullptr)
	{
		return;
	}

	// Only light an otherwise empty level. /Engine/Maps/Entry has no lights,
	// and a level the user built themselves probably does.
	for (TActorIterator<ADirectionalLight> It(World); It; ++It)
	{
		return;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride =
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	// Key light (the sun): low afternoon angle so slopes read in shading.
	// A dim cool fill keeps shadowed slopes from going black.
	struct FLightSpec
	{
		FRotator Rotation;
		float Intensity;
		FLinearColor Color;
		bool bCastShadows;
		bool bSun;
	};
	const FLightSpec Specs[] = {
		{ FRotator(-32.0f, 145.0f, 0.0f), 8.0f, FLinearColor(1.0f, 0.95f, 0.85f, 1.0f), true, true },
		{ FRotator(-20.0f, -35.0f, 0.0f), 1.2f, FLinearColor(0.55f, 0.68f, 0.90f, 1.0f), false, false },
	};

	for (const FLightSpec& Spec : Specs)
	{
		ADirectionalLight* Light = World->SpawnActor<ADirectionalLight>(
			ADirectionalLight::StaticClass(),
			FTransform(Spec.Rotation, FVector(0.0f, 0.0f, 2000.0f)), Params);
		if (Light == nullptr)
		{
			continue;
		}
		if (USceneComponent* LightRoot = Light->GetRootComponent())
		{
			LightRoot->SetMobility(EComponentMobility::Movable);
		}
		if (ULightComponent* LightComp = Light->GetLightComponent())
		{
			LightComp->SetIntensity(Spec.Intensity);
			LightComp->SetLightColor(Spec.Color);
			LightComp->SetCastShadows(Spec.bCastShadows);
			if (Spec.bSun)
			{
				if (UDirectionalLightComponent* Sun =
					Cast<UDirectionalLightComponent>(LightComp))
				{
					// Drives the procedural sky below.
					Sun->SetAtmosphereSunLight(true);
				}
			}
		}
		Light->SetActorRotation(Spec.Rotation);
	}

	// A procedural sky: USkyAtmosphereComponent is fully analytic (no
	// cubemap), and a real-time-capture sky light turns it into ambient
	// bounce -- both spawnable engine classes, so the text-only constraint
	// holds.  Height fog folds the far terrain into the horizon haze,
	// keeping the ~1 km chunk window and the draw distance consistent.
	World->SpawnActor<ASkyAtmosphere>(ASkyAtmosphere::StaticClass(),
		FTransform::Identity, Params);

	if (ASkyLight* Sky = World->SpawnActor<ASkyLight>(ASkyLight::StaticClass(),
		FTransform::Identity, Params))
	{
		if (USceneComponent* SkyRoot = Sky->GetRootComponent())
		{
			SkyRoot->SetMobility(EComponentMobility::Movable);
		}
		if (USkyLightComponent* SkyComp = Sky->GetLightComponent())
		{
			SkyComp->SetMobility(EComponentMobility::Movable);
			SkyComp->SetRealTimeCaptureEnabled(true);
			SkyComp->SetIntensity(1.0f);
		}
	}

	if (AExponentialHeightFog* Fog = World->SpawnActor<AExponentialHeightFog>(
		AExponentialHeightFog::StaticClass(),
		FTransform(FRotator::ZeroRotator, FVector(0.0f, 0.0f, 0.0f)), Params))
	{
		if (UExponentialHeightFogComponent* FogComp = Fog->GetComponent())
		{
			FogComp->SetFogDensity(0.04f);
			FogComp->SetFogHeightFalloff(0.05f);
			FogComp->SetStartDistance(4000.0f);       // 40 m clear foreground
			FogComp->SetFogInscatteringColor(
				FLinearColor(0.58f, 0.66f, 0.80f, 1.0f));
		}
	}

	UE_LOG(LogRunsim, Log,
		TEXT("spawned runsim scene (terrain, runner, lights, sky, fog)"));
}
