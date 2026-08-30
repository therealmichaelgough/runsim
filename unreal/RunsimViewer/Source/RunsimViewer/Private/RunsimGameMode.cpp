#include "RunsimGameMode.h"

#include "RunsimHUD.h"
#include "RunsimPawn.h"
#include "RunsimRunner.h"
#include "RunsimTerrain.h"
#include "RunsimViewer.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/LightComponent.h"
#include "Engine/DirectionalLight.h"
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

	// Key light, low and from ahead-right so the slope reads in shading.
	// (No sky light: a cubemap is an asset, so a dim fill light stands in.)
	struct FLightSpec
	{
		FRotator Rotation;
		float Intensity;
		FLinearColor Color;
		bool bCastShadows;
	};
	const FLightSpec Specs[] = {
		{ FRotator(-38.0f, 145.0f, 0.0f), 7.0f, FLinearColor(1.0f, 0.96f, 0.88f, 1.0f), true },
		{ FRotator(-20.0f, -35.0f, 0.0f), 2.2f, FLinearColor(0.55f, 0.68f, 0.90f, 1.0f), false },
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
		}
		Light->SetActorRotation(Spec.Rotation);
	}

	UE_LOG(LogRunsim, Log, TEXT("spawned runsim scene (terrain, runner, lights)"));
}
