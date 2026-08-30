#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"

#include "RunsimGameMode.generated.h"

/**
 * Wires the scene together in C++ so the project needs no level asset: on
 * StartPlay it spawns the runner, the terrain and two directional lights if
 * the level does not already contain them.  Set as GlobalDefaultGameMode in
 * Config/DefaultEngine.ini, so pressing Play in any empty level works.
 */
UCLASS()
class RUNSIMVIEWER_API ARunsimGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ARunsimGameMode();

	virtual void StartPlay() override;

private:
	void SpawnSceneIfNeeded();
	void SpawnLighting();
};
