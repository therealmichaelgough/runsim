#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "RunsimTerrain.generated.h"

class UProceduralMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;

/**
 * The visible ground: a chunked procedural heightfield built from
 * RunsimTerrainMath's analytic h(x, y), in a minimalist flat-shaded style.
 *
 * An 11 x 11 ring buffer of 96 m chunks (a ~1.06 km square window) is kept
 * anchored around the runner; each chunk is one UProceduralMeshComponent
 * whose triangles are partitioned into a small palette of colour bands
 * (meadow / grass / dry grass / rock / ridge) drawn as separate mesh
 * sections tinted by shared dynamic material instances -- no assets, no
 * textures, no vertex-colour material needed.  Faces are flat-shaded
 * (vertices duplicated per triangle) for the low-poly look.
 *
 * Chunks rebuild against a budget per update, nearest first, so crossing a
 * chunk boundary or changing hilliness never stalls a frame; an endless run
 * allocates nothing after the pools are built.
 */
UCLASS()
class RUNSIMVIEWER_API ARunsimTerrain : public AActor
{
	GENERATED_BODY()

public:
	ARunsimTerrain();

	virtual void BeginPlay() override;

	/** Relief scale in [0, 1]; marks every chunk dirty when it changes. */
	void SetHilliness(float InHilliness);
	float GetHilliness() const { return Hilliness; }

	/** Re-anchor the chunk window around a point (metres), rebuilding up to
	 *  MaxChunkBuildsPerUpdate stale chunks, nearest first. */
	void UpdateAround(float CentreXM, float CentreYM);

	int32 GetNumChunks() const { return Chunks.Num(); }
	int32 GetNumCleanChunks() const;

protected:
	void BuildPools();
	void BuildChunk(int32 Slot, FIntPoint Coord);

	UPROPERTY()
	TObjectPtr<USceneComponent> Root;

	UPROPERTY()
	TArray<TObjectPtr<UProceduralMeshComponent>> Chunks;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> BaseMaterial;

	UPROPERTY()
	TArray<TObjectPtr<UMaterialInstanceDynamic>> BandMaterials;

	/** World chunk coordinate each pool slot currently displays. */
	TArray<FIntPoint> ChunkCoord;
	/** TerrainVersion each slot was built at (hilliness invalidation). */
	TArray<int32> ChunkBuiltVersion;

	int32 TerrainVersion = 0;
	float Hilliness = 0.45f;
	bool bBuilt = false;

	/** 11 x 11 chunks of 96 m -> a 1056 m square active window (>= 1 km^2). */
	static constexpr int32 GridSide = 11;
	static constexpr float ChunkSizeM = 96.0f;
	/** 24 x 24 quads per chunk -> 4 m facets, 1152 flat-shaded triangles. */
	static constexpr int32 QuadsPerChunk = 24;
	/** Rebuild budget per UpdateAround call (one call per pawn tick). */
	static constexpr int32 MaxChunkBuildsPerUpdate = 4;
	/** meadow, grass, dry grass, rock, ridge. */
	static constexpr int32 NumBands = 5;
};
