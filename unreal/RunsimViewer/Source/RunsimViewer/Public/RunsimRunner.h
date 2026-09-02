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
 *
 * The runner moves in 2D across the heightfield: steering input drives a
 * rate-limited yaw, the grade fed to the gait blend is the terrain's
 * directional derivative along the heading, and the body is tilted to the
 * local tangent plane (pitch along the heading, bank across it).  Steering
 * is an approximation -- the solutions are straight-line gaits being
 * re-aimed, there are no curve-specific dynamics (noted on the HUD/README).
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
	void SetSteerInput(float InSteer);      // [-1, 1], + steers right
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
	FVector2D GetPositionM() const { return FVector2D(PosXM, PosYM); }
	float GetHeadingDeg() const { return HeadingDeg; }
	float GetDistanceM() const { return DistanceM; }
	float GetHilliness() const { return Hilliness; }
	float GetGrade() const { return CurrentGrade; }
	/** True when the terrain is steeper than the solved gait-grade range
	 *  (the pose is clamped there; the body still tilts). */
	bool IsGaitGradeClamped() const { return bGaitGradeClamped; }
	float GetStrideTimeS() const { return CachedPose.StrideTimeS; }
	float GetStrideLenM() const { return CachedPose.StrideLenM; }
	float GetWalkWeight() const { return CachedPose.WalkWeight; }
	bool HasCot() const { return CachedPose.bHasCot; }
	float GetCot() const { return CachedPose.Cot; }
	bool HasGrf() const { return CachedPose.bHasGrf; }
	float GetGrfBw() const { return CachedPose.GrfBw; }
	bool HasMetRate() const { return CachedPose.bHasMet; }
	float GetMetRateWkg() const { return CachedPose.MetRateWkg; }
	bool HasContact() const { return CachedPose.bHasContact; }
	float GetContactTimeS() const { return CachedPose.ContactTimeS; }
	float GetFlightFrac() const { return CachedPose.FlightFrac; }
	bool HasArmData() const;
	/** Point on the terrain under the runner, in world cm. */
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

	/** Simulation state (metres, seconds, m/s, degrees). */
	float PosXM = 0.0f;
	float PosYM = 0.0f;
	float HeadingDeg = 0.0f;
	float YawRateDegS = 0.0f;
	float SteerInput = 0.0f;
	float DistanceM = 0.0f;      // odometer along the path
	float Phase = 0.0f;
	float SpeedMps = 3.0f;
	float TargetSpeedMps = 3.0f;
	float Hilliness = 0.45f;
	int32 PlaybackIndex = INDEX_NONE;  // INDEX_NONE = blended 2D mode
	float CurrentGrade = 0.0f;
	bool bGaitGradeClamped = false;
	bool bPaused = false;

	FRunsimPose CachedPose;

	/** Matches the web viewer's speed follower: speed += (target-speed)*dt*k */
	static constexpr float SpeedFollowRate = 1.6f;
	/** Steering: full input commands 60 deg/s, followed at 4/s -- fast
	 *  enough to feel direct, slow enough to read as a runner leaning into
	 *  a turn rather than a vehicle snapping. */
	static constexpr float MaxYawRateDegS = 60.0f;
	static constexpr float SteerFollowRate = 4.0f;
	/** The engine basic shapes are 100 uu across in every axis. */
	static constexpr float BasicShapeSize = 100.0f;
};
