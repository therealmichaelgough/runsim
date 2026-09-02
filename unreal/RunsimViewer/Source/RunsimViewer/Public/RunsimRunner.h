#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "RunsimGaitData.h"

#include "RunsimRunner.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInterface;

/**
 * The runner: one capsule primitive per simulated body segment, posed every
 * tick from the blended Moco solutions.
 *
 * Nothing here is simulated in-engine.  Phase advances with the blended
 * stride time and the world position advances with the blended stride
 * length / stride time -- the "no foot skate" rule from the web viewer: the
 * body travels at the speed the baked stride actually produces, not at the
 * speed the user asked for.
 */
UCLASS()
class RUNSIMVIEWER_API ARunsimRunner : public AActor
{
	GENERATED_BODY()

public:
	ARunsimRunner();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Controls, driven by ARunsimPawn. */
	void SetTargetSpeed(float MetresPerSecond);
	void SetHilliness(float InHilliness);
	void SetPaused(bool bInPaused);

	/** Cycle: blended 2D gaits -> each 3D solution wholesale -> back. */
	void CyclePlaybackGait();
	bool IsPlayback3D() const { return PlaybackIndex != INDEX_NONE; }
	FString GetPlaybackLabel() const;
	void TogglePaused() { SetPaused(!bPaused); }
	bool IsPaused() const { return bPaused; }

	/** Telemetry, read by the camera and the HUD. */
	float GetSpeedMps() const { return SpeedMps; }
	float GetTargetSpeedMps() const { return TargetSpeedMps; }
	float GetDistanceM() const { return DistanceM; }
	float GetHilliness() const { return Hilliness; }
	float GetGrade() const { return CurrentGrade; }
	float GetStrideTimeS() const { return CachedPose.StrideTimeS; }
	float GetStrideLenM() const { return CachedPose.StrideLenM; }
	float GetWalkWeight() const { return CachedPose.WalkWeight; }
	bool HasCot() const { return CachedPose.bHasCot; }
	float GetCot() const { return CachedPose.Cot; }
	bool HasArmData() const;
	/** Point on the terrain centre line under the runner, in world cm. */
	FVector GetGroundLocation() const;

	const URunsimGaitData* GetGaitData() const { return GaitData; }

protected:
	void BuildSegmentComponents();
	void PoseSegments();

	UPROPERTY()
	TObjectPtr<USceneComponent> Root;

	UPROPERTY()
	TObjectPtr<URunsimGaitData> GaitData;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> SegmentComponents;

	UPROPERTY()
	TObjectPtr<UStaticMesh> CylinderMesh;

	UPROPERTY()
	TObjectPtr<UStaticMesh> SphereMesh;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> BaseMaterial;

	/** Simulation state (metres, seconds, m/s). */
	float DistanceM = 0.0f;
	float Phase = 0.0f;
	float SpeedMps = 3.0f;
	float TargetSpeedMps = 3.0f;
	float Hilliness = 0.45f;
	int32 PlaybackIndex = INDEX_NONE;  // INDEX_NONE = blended 2D mode
	float CurrentGrade = 0.0f;
	bool bPaused = false;

	FRunsimPose CachedPose;

	/** Matches the web viewer's speed follower: speed += (target-speed)*dt*k */
	static constexpr float SpeedFollowRate = 1.6f;
	/** The engine basic shapes are 100 uu across in every axis. */
	static constexpr float BasicShapeSize = 100.0f;
};
