#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"

#include "RunsimPawn.generated.h"

class UCameraComponent;
class USpringArmComponent;
class ARunsimRunner;
class ARunsimTerrain;

/**
 * The chase camera and the whole of the user interface.
 *
 * Spring arm with lag and a velocity-scaled look-ahead, defaulting to a 3/4
 * view; holding the right mouse button orbits.  Input uses the legacy axis /
 * action mappings from Config/DefaultInput.ini -- Enhanced Input would need
 * .uasset mapping contexts, and this project is deliberately text-only.
 */
UCLASS()
class RUNSIMVIEWER_API ARunsimPawn : public APawn
{
	GENERATED_BODY()

public:
	ARunsimPawn();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

	ARunsimRunner* GetRunner() const { return Runner; }
	float GetHilliness() const { return Hilliness; }
	bool IsPaused() const { return bPaused; }
	bool IsOrbiting() const { return bOrbiting; }

protected:
	/** 3/4 view: behind and to the side, looking slightly down. */
	static constexpr float DefaultYaw = 35.0f;
	static constexpr float DefaultPitch = -12.0f;
	static constexpr float DefaultArmLength = 700.0f;

	static constexpr float SpeedChangeRate = 1.2f;   // m/s per second held
	static constexpr float HillsChangeRate = 0.35f;  // hilliness per second
	static constexpr float OrbitSensitivity = 2.2f;  // deg per mouse unit
	static constexpr float ZoomStepCm = 90.0f;
	static constexpr float MinArmLength = 250.0f;
	static constexpr float MaxArmLength = 2000.0f;
	/** Look-ahead: 0.55 m of camera lead per m/s, as in the web viewer. */
	static constexpr float LookAheadPerMps = 55.0f;
	static constexpr float EyeHeightCm = 105.0f;

	void ResolveWorldActors();

	void InputSpeed(float Value);
	void InputHills(float Value);
	void InputTurn(float Value);
	void InputLookUp(float Value);
	void InputZoom(float Value);
	void OnOrbitPressed();
	void OnOrbitReleased();
	void OnTogglePause();
	void OnResetView();

	UPROPERTY()
	TObjectPtr<USceneComponent> Root;

	UPROPERTY()
	TObjectPtr<USpringArmComponent> SpringArm;

	UPROPERTY()
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY()
	TObjectPtr<ARunsimRunner> Runner;

	UPROPERTY()
	TObjectPtr<ARunsimTerrain> Terrain;

	float TargetSpeedMps = 3.0f;
	float Hilliness = 0.45f;
	bool bPaused = false;
	bool bOrbiting = false;

	float OrbitYaw = DefaultYaw;
	float OrbitPitch = DefaultPitch;
	float ArmLength = DefaultArmLength;
};
