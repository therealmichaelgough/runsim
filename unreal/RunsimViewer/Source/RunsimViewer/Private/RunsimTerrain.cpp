#include "RunsimTerrain.h"

#include "RunsimTerrainMath.h"
#include "RunsimViewer.h"

#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "ProceduralMeshComponent.h"
#include "UObject/ConstructorHelpers.h"

/** The palette: muted, minimalist trail-running country. */
static const FLinearColor& RunsimBandColor(int32 Band)
{
	static const FLinearColor Colors[5] = {
		FLinearColor(0.30f, 0.40f, 0.20f, 1.0f),  // 0 meadow (valley floor)
		FLinearColor(0.22f, 0.33f, 0.18f, 1.0f),  // 1 grass
		FLinearColor(0.42f, 0.40f, 0.22f, 1.0f),  // 2 dry grass (high slopes)
		FLinearColor(0.31f, 0.28f, 0.26f, 1.0f),  // 3 rock (steep)
		FLinearColor(0.52f, 0.50f, 0.45f, 1.0f),  // 4 ridge (pale crest)
	};
	return Colors[FMath::Clamp(Band, 0, 4)];
}

/** Band from *relief* height/slope (i.e. hilliness-normalised), so the
 *  landscape keeps its identity as the H/F keys scale the relief. */
static int32 RunsimBandFor(float ReliefH, float ReliefSlope)
{
	if (ReliefSlope > 0.32f)
	{
		return 3;                       // rock: steep whatever the height
	}
	if (ReliefH > 13.0f)
	{
		return 4;                       // pale crest band
	}
	if (ReliefH > 4.5f)
	{
		return 2;                       // dry grass
	}
	if (ReliefH > -3.0f)
	{
		return 1;                       // grass
	}
	return 0;                           // meadow / valley floor
}

ARunsimTerrain::ARunsimTerrain()
{
	PrimaryActorTick.bCanEverTick = false;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Movable);
	RootComponent = Root;

	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MaterialFinder(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	BaseMaterial = MaterialFinder.Succeeded() ? MaterialFinder.Object : nullptr;
}

void ARunsimTerrain::BeginPlay()
{
	Super::BeginPlay();
	BuildPools();
	// First anchor builds the whole window unbudgeted: one-time startup cost
	// (121 chunks x ~1.2k triangles), then steady state costs <= the budget.
	UpdateAround(0.0f, 0.0f);
	UE_LOG(LogRunsim, Log,
		TEXT("terrain: %d chunks of %.0f m (%d clean), %.0f m window, hilliness %.2f"),
		Chunks.Num(), ChunkSizeM, GetNumCleanChunks(),
		GridSide * ChunkSizeM, Hilliness);
}

int32 ARunsimTerrain::GetNumCleanChunks() const
{
	int32 Count = 0;
	for (int32 i = 0; i < ChunkBuiltVersion.Num(); ++i)
	{
		if (ChunkBuiltVersion[i] == TerrainVersion && ChunkCoord[i].X != MIN_int32)
		{
			++Count;
		}
	}
	return Count;
}

void ARunsimTerrain::BuildPools()
{
	if (bBuilt)
	{
		return;
	}
	bBuilt = true;

	BandMaterials.Reset(NumBands);
	for (int32 Band = 0; Band < NumBands; ++Band)
	{
		UMaterialInstanceDynamic* Mid = BaseMaterial
			? UMaterialInstanceDynamic::Create(BaseMaterial, this)
			: nullptr;
		if (Mid)
		{
			// BasicShapeMaterial exposes "Color"; setting a missing parameter
			// is a no-op, so this degrades to grey rather than failing.
			Mid->SetVectorParameterValue(TEXT("Color"), RunsimBandColor(Band));
			Mid->SetVectorParameterValue(TEXT("BaseColor"), RunsimBandColor(Band));
		}
		BandMaterials.Add(Mid);
	}

	const int32 NumChunks = GridSide * GridSide;
	Chunks.Reserve(NumChunks);
	ChunkCoord.Init(FIntPoint(MIN_int32, MIN_int32), NumChunks);
	ChunkBuiltVersion.Init(-1, NumChunks);
	for (int32 i = 0; i < NumChunks; ++i)
	{
		UProceduralMeshComponent* Comp = NewObject<UProceduralMeshComponent>(
			this, UProceduralMeshComponent::StaticClass(),
			*FString::Printf(TEXT("Chunk_%03d"), i));
		Comp->SetupAttachment(Root);
		Comp->SetMobility(EComponentMobility::Movable);
		Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Comp->SetCastShadow(false);
		Comp->bUseAsyncCooking = false;   // no collision is ever cooked
		Comp->RegisterComponent();
		Chunks.Add(Comp);
	}
}

void ARunsimTerrain::SetHilliness(float InHilliness)
{
	const float Clamped = FMath::Clamp(InHilliness, 0.0f, 1.0f);
	if (FMath::IsNearlyEqual(Clamped, Hilliness, 1.0e-4f))
	{
		return;
	}
	Hilliness = Clamped;
	// Invalidate every chunk; UpdateAround rebuilds them nearest-first
	// against the per-tick budget, so the change sweeps outward smoothly.
	++TerrainVersion;
}

void ARunsimTerrain::UpdateAround(float CentreXM, float CentreYM)
{
	if (!bBuilt)
	{
		BuildPools();
	}

	const int32 FirstX = FMath::FloorToInt(CentreXM / ChunkSizeM) - GridSide / 2;
	const int32 FirstY = FMath::FloorToInt(CentreYM / ChunkSizeM) - GridSide / 2;

	// Collect stale slots (wrong coord for the window, or built at an old
	// hilliness), nearest to the centre first.
	struct FStale
	{
		int32 Slot;
		FIntPoint Coord;
		float DistSq;
	};
	TArray<FStale, TInlineAllocator<64>> Stale;

	const bool bFirstAnchor = ChunkBuiltVersion.Num() > 0
		&& ChunkCoord[0].X == MIN_int32;

	for (int32 CY = FirstY; CY < FirstY + GridSide; ++CY)
	{
		for (int32 CX = FirstX; CX < FirstX + GridSide; ++CX)
		{
			const int32 RX = ((CX % GridSide) + GridSide) % GridSide;
			const int32 RY = ((CY % GridSide) + GridSide) % GridSide;
			const int32 Slot = RY * GridSide + RX;
			if (ChunkCoord[Slot] == FIntPoint(CX, CY)
				&& ChunkBuiltVersion[Slot] == TerrainVersion)
			{
				continue;
			}
			const float MidX = (CX + 0.5f) * ChunkSizeM - CentreXM;
			const float MidY = (CY + 0.5f) * ChunkSizeM - CentreYM;
			Stale.Add({ Slot, FIntPoint(CX, CY), MidX * MidX + MidY * MidY });
		}
	}
	if (Stale.Num() == 0)
	{
		return;
	}
	Stale.Sort([](const FStale& A, const FStale& B)
	{
		return A.DistSq < B.DistSq;
	});

	const int32 Budget = bFirstAnchor ? Stale.Num() : MaxChunkBuildsPerUpdate;
	for (int32 i = 0; i < Stale.Num() && i < Budget; ++i)
	{
		BuildChunk(Stale[i].Slot, Stale[i].Coord);
	}
}

void ARunsimTerrain::BuildChunk(int32 Slot, FIntPoint Coord)
{
	UProceduralMeshComponent* Comp = Chunks[Slot].Get();
	if (Comp == nullptr)
	{
		return;
	}
	ChunkCoord[Slot] = Coord;
	ChunkBuiltVersion[Slot] = TerrainVersion;

	const float OriginXM = Coord.X * ChunkSizeM;
	const float OriginYM = Coord.Y * ChunkSizeM;
	const float StepM = ChunkSizeM / QuadsPerChunk;
	const int32 N = QuadsPerChunk + 1;

	// Sample the shared height function once per grid point (world cm).
	TArray<FVector> Grid;
	Grid.SetNumUninitialized(N * N);
	for (int32 GY = 0; GY < N; ++GY)
	{
		for (int32 GX = 0; GX < N; ++GX)
		{
			Grid[GY * N + GX] = RunsimTerrain::GroundLocation(
				OriginXM + GX * StepM, OriginYM + GY * StepM, Hilliness);
		}
	}

	// Partition the triangles into colour bands; flat shading duplicates the
	// three corner vertices per triangle so each face keeps its own normal.
	TArray<FVector> Vertices[NumBands];
	TArray<int32> Triangles[NumBands];
	TArray<FVector> Normals[NumBands];
	const float InvHill = 1.0f / FMath::Max(Hilliness, 0.05f);

	auto EmitTriangle = [&](const FVector& A, const FVector& B, const FVector& C)
	{
		// Left-handed world: CounterClockwise(A,B,C) seen from +Z is
		// front-facing when the normal ((B-A)x(C-A)) points up.
		FVector FaceNormal = FVector::CrossProduct(B - A, C - A);
		if (FaceNormal.Z < 0.0f)
		{
			FaceNormal = -FaceNormal;
		}
		const float LenXY = FMath::Sqrt(
			FaceNormal.X * FaceNormal.X + FaceNormal.Y * FaceNormal.Y);
		const float ReliefSlope = FaceNormal.Z > 1.0e-6f
			? (LenXY / FaceNormal.Z) * InvHill : 10.0f;
		const float ReliefH = ((A.Z + B.Z + C.Z) / 3.0f)
			/ RunsimTerrain::UnitsPerMetre * InvHill;
		const int32 Band = RunsimBandFor(ReliefH, ReliefSlope);
		FaceNormal.Normalize();

		TArray<FVector>& V = Vertices[Band];
		TArray<int32>& T = Triangles[Band];
		TArray<FVector>& Nm = Normals[Band];
		const int32 Base = V.Num();
		V.Add(A); V.Add(B); V.Add(C);
		Nm.Add(FaceNormal); Nm.Add(FaceNormal); Nm.Add(FaceNormal);
		T.Add(Base); T.Add(Base + 1); T.Add(Base + 2);
	};

	for (int32 GY = 0; GY < QuadsPerChunk; ++GY)
	{
		for (int32 GX = 0; GX < QuadsPerChunk; ++GX)
		{
			const FVector& P00 = Grid[GY * N + GX];
			const FVector& P10 = Grid[GY * N + GX + 1];
			const FVector& P01 = Grid[(GY + 1) * N + GX];
			const FVector& P11 = Grid[(GY + 1) * N + GX + 1];
			// Alternate the quad diagonal so facet ridges do not stripe.
			if ((GX + GY) % 2 == 0)
			{
				EmitTriangle(P00, P01, P10);
				EmitTriangle(P10, P01, P11);
			}
			else
			{
				EmitTriangle(P00, P01, P11);
				EmitTriangle(P00, P11, P10);
			}
		}
	}

	Comp->ClearAllMeshSections();
	const TArray<FVector2D> NoUVs;
	const TArray<FLinearColor> NoColors;
	const TArray<FProcMeshTangent> NoTangents;
	for (int32 Band = 0; Band < NumBands; ++Band)
	{
		if (Vertices[Band].Num() == 0)
		{
			continue;
		}
		Comp->CreateMeshSection_LinearColor(Band, Vertices[Band],
			Triangles[Band], Normals[Band], NoUVs, NoColors, NoTangents,
			/*bCreateCollision=*/false);
		if (BandMaterials.IsValidIndex(Band) && BandMaterials[Band])
		{
			Comp->SetMaterial(Band, BandMaterials[Band]);
		}
	}
}
