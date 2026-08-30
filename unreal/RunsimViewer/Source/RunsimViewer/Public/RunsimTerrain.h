#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "RunsimTerrain.generated.h"

class USplineMeshComponent;
class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInterface;

/**
 * The visible ground: a spline-mesh ribbon built from RunsimTerrainMath's
 * sum-of-sines height function, plus distance posts every 5 m so motion is
 * legible.
 *
 * The ribbon is a fixed-size ring buffer of segments that is re-anchored
 * around the runner, so an endless run costs a constant number of components
 * and no allocation after BeginPlay.  Grade comes from the analytic
 * derivative -- there are no line traces and nothing to keep in sync.
 */
UCLASS()
class RUNSIMVIEWER_API ARunsimTerrain : public AActor
{
	GENERATED_BODY()

public:
	ARunsimTerrain();

	virtual void BeginPlay() override;

	/** Rebuilds when the shape changes; cheap no-op when it does not. */
	void SetHilliness(float InHilliness);
	float GetHilliness() const { return Hilliness; }

	/** Re-anchor the ribbon around a point on the track, in metres. */
	void UpdateAround(float CentreMetres);

protected:
	void BuildComponents();
	void RefreshSegment(int32 Slot, int32 WorldIndex);
	void RefreshMarker(int32 Slot, int32 WorldIndex);

	UPROPERTY()
	TObjectPtr<USceneComponent> Root;

	UPROPERTY()
	TArray<TObjectPtr<USplineMeshComponent>> RibbonSegments;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> DistanceMarkers;

	UPROPERTY()
	TObjectPtr<UStaticMesh> CubeMesh;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> BaseMaterial;

	TArray<int32> SegmentWorldIndex;
	TArray<int32> MarkerWorldIndex;

	float Hilliness = 0.45f;
	bool bBuilt = false;

	/** 200 m of ribbon in 1 m pieces, 60 m of it behind the runner. */
	static constexpr int32 NumRibbonSegments = 200;
	static constexpr float SegmentLengthM = 1.0f;
	static constexpr float BehindM = 60.0f;
	static constexpr float TrackWidthCm = 300.0f;
	static constexpr float TrackThicknessCm = 24.0f;

	/** One post every 5 m, covering the same 200 m window. */
	static constexpr int32 NumMarkers = 40;
	static constexpr float MarkerSpacingM = 5.0f;

	static constexpr float BasicShapeSize = 100.0f;
};
