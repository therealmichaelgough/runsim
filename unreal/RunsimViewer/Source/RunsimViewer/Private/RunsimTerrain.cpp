#include "RunsimTerrain.h"

#include "RunsimTerrainMath.h"
#include "RunsimViewer.h"

#include "Components/SplineMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

ARunsimTerrain::ARunsimTerrain()
{
	PrimaryActorTick.bCanEverTick = false;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Movable);
	RootComponent = Root;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeFinder(
		TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MaterialFinder(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	CubeMesh = CubeFinder.Succeeded() ? CubeFinder.Object : nullptr;
	BaseMaterial = MaterialFinder.Succeeded() ? MaterialFinder.Object : nullptr;
}

void ARunsimTerrain::BeginPlay()
{
	Super::BeginPlay();
	BuildComponents();
	UpdateAround(0.0f);
}

void ARunsimTerrain::BuildComponents()
{
	if (bBuilt)
	{
		return;
	}
	bBuilt = true;

	RibbonSegments.Reserve(NumRibbonSegments);
	SegmentWorldIndex.Init(MIN_int32, NumRibbonSegments);
	for (int32 i = 0; i < NumRibbonSegments; ++i)
	{
		USplineMeshComponent* Comp = NewObject<USplineMeshComponent>(
			this, USplineMeshComponent::StaticClass(),
			*FString::Printf(TEXT("Ribbon_%03d"), i));
		Comp->SetupAttachment(Root);
		Comp->SetMobility(EComponentMobility::Movable);
		Comp->SetStaticMesh(CubeMesh);
		Comp->SetForwardAxis(ESplineMeshAxis::X, false);
		Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Comp->SetCastShadow(false);
		Comp->RegisterComponent();

		if (BaseMaterial)
		{
			if (UMaterialInstanceDynamic* Mid =
				Comp->CreateDynamicMaterialInstance(0, BaseMaterial))
			{
				// Alternating shade so the ground reads as moving even when
				// BasicShapeMaterial ignores the parameter's name.
				const FLinearColor Shade = (i % 2 == 0)
					? FLinearColor(0.11f, 0.19f, 0.29f, 1.0f)
					: FLinearColor(0.09f, 0.16f, 0.25f, 1.0f);
				Mid->SetVectorParameterValue(TEXT("Color"), Shade);
				Mid->SetVectorParameterValue(TEXT("BaseColor"), Shade);
			}
		}
		RibbonSegments.Add(Comp);
	}

	DistanceMarkers.Reserve(NumMarkers);
	MarkerWorldIndex.Init(MIN_int32, NumMarkers);
	for (int32 i = 0; i < NumMarkers; ++i)
	{
		UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(
			this, UStaticMeshComponent::StaticClass(),
			*FString::Printf(TEXT("Marker_%02d"), i));
		Comp->SetupAttachment(Root);
		Comp->SetMobility(EComponentMobility::Movable);
		Comp->SetStaticMesh(CubeMesh);
		Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Comp->SetCastShadow(false);
		Comp->RegisterComponent();

		if (BaseMaterial)
		{
			if (UMaterialInstanceDynamic* Mid =
				Comp->CreateDynamicMaterialInstance(0, BaseMaterial))
			{
				const FLinearColor Marker(0.39f, 0.85f, 0.78f, 1.0f);
				Mid->SetVectorParameterValue(TEXT("Color"), Marker);
				Mid->SetVectorParameterValue(TEXT("BaseColor"), Marker);
			}
		}
		DistanceMarkers.Add(Comp);
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
	// Force every slot to rebuild on the next update.
	for (int32& Index : SegmentWorldIndex)
	{
		Index = MIN_int32;
	}
	for (int32& Index : MarkerWorldIndex)
	{
		Index = MIN_int32;
	}
}

void ARunsimTerrain::UpdateAround(float CentreMetres)
{
	if (!bBuilt)
	{
		BuildComponents();
	}

	const int32 FirstSegment = FMath::FloorToInt(
		(CentreMetres - BehindM) / SegmentLengthM);
	for (int32 Slot = 0; Slot < RibbonSegments.Num(); ++Slot)
	{
		const int32 WorldIndex = FirstSegment + Slot;
		// The ring buffer keeps a slot's contents whenever the window has not
		// moved past it, so a steady run refreshes at most one segment a tick.
		const int32 RingSlot = ((WorldIndex % NumRibbonSegments) + NumRibbonSegments)
			% NumRibbonSegments;
		if (SegmentWorldIndex[RingSlot] != WorldIndex)
		{
			RefreshSegment(RingSlot, WorldIndex);
		}
	}

	const int32 FirstMarker = FMath::FloorToInt(
		(CentreMetres - BehindM) / MarkerSpacingM);
	for (int32 Slot = 0; Slot < DistanceMarkers.Num(); ++Slot)
	{
		const int32 WorldIndex = FirstMarker + Slot;
		const int32 RingSlot = ((WorldIndex % NumMarkers) + NumMarkers) % NumMarkers;
		if (MarkerWorldIndex[RingSlot] != WorldIndex)
		{
			RefreshMarker(RingSlot, WorldIndex);
		}
	}
}

void ARunsimTerrain::RefreshSegment(int32 Slot, int32 WorldIndex)
{
	USplineMeshComponent* Comp = RibbonSegments[Slot].Get();
	if (Comp == nullptr)
	{
		return;
	}
	SegmentWorldIndex[Slot] = WorldIndex;

	const float X0 = WorldIndex * SegmentLengthM;
	const float X1 = X0 + SegmentLengthM;
	const float SpanCm = SegmentLengthM * RunsimTerrain::UnitsPerMetre;

	// Drop the ribbon by half its thickness so its top surface is the ground
	// plane the runner is standing on.
	const float Sink = 0.5f * TrackThicknessCm;
	const FVector Start(X0 * RunsimTerrain::UnitsPerMetre, 0.0f,
		RunsimTerrain::HeightM(X0, Hilliness) * RunsimTerrain::UnitsPerMetre - Sink);
	const FVector End(X1 * RunsimTerrain::UnitsPerMetre, 0.0f,
		RunsimTerrain::HeightM(X1, Hilliness) * RunsimTerrain::UnitsPerMetre - Sink);
	const FVector StartTangent(SpanCm, 0.0f,
		RunsimTerrain::GradeAt(X0, Hilliness) * SpanCm);
	const FVector EndTangent(SpanCm, 0.0f,
		RunsimTerrain::GradeAt(X1, Hilliness) * SpanCm);

	Comp->SetStartAndEnd(Start, StartTangent, End, EndTangent, false);
	const FVector2D CrossSection(TrackWidthCm / BasicShapeSize,
		TrackThicknessCm / BasicShapeSize);
	Comp->SetStartScale(CrossSection, false);
	Comp->SetEndScale(CrossSection, true);
}

void ARunsimTerrain::RefreshMarker(int32 Slot, int32 WorldIndex)
{
	UStaticMeshComponent* Comp = DistanceMarkers[Slot].Get();
	if (Comp == nullptr)
	{
		return;
	}
	MarkerWorldIndex[Slot] = WorldIndex;

	const float X = WorldIndex * MarkerSpacingM;
	const float PostHeightCm = 40.0f;
	const FVector Location(
		X * RunsimTerrain::UnitsPerMetre,
		-(TrackWidthCm * 0.5f + 40.0f),
		RunsimTerrain::HeightM(X, Hilliness) * RunsimTerrain::UnitsPerMetre
			+ PostHeightCm * 0.5f);
	Comp->SetRelativeLocation(Location);
	Comp->SetRelativeRotation(FRotator(
		RunsimTerrain::PitchDegrees(X, Hilliness), 0.0f, 0.0f));
	Comp->SetRelativeScale3D(FVector(
		8.0f / BasicShapeSize, 8.0f / BasicShapeSize, PostHeightCm / BasicShapeSize));
}
