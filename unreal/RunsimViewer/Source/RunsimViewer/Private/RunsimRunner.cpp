#include "RunsimRunner.h"

#include "RunsimTerrainMath.h"
#include "RunsimViewer.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

ARunsimRunner::ARunsimRunner()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Movable);
	RootComponent = Root;

	// Engine basic shapes only -- this project ships no content of its own.
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderFinder(
		TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereFinder(
		TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MaterialFinder(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	CylinderMesh = CylinderFinder.Succeeded() ? CylinderFinder.Object : nullptr;
	SphereMesh = SphereFinder.Succeeded() ? SphereFinder.Object : nullptr;
	BaseMaterial = MaterialFinder.Succeeded() ? MaterialFinder.Object : nullptr;
}

void ARunsimRunner::BeginPlay()
{
	Super::BeginPlay();

	GaitData = NewObject<URunsimGaitData>(this, TEXT("RunsimGaitData"));
	const FString Path = URunsimGaitData::DefaultDataPath();
	if (!GaitData->LoadFromFile(Path))
	{
		UE_LOG(LogRunsim, Error,
			TEXT("no gait data (%s); regenerate with scripts/export_ue_gaits.py -- %s"),
			*Path, *GaitData->GetLoadError());
		return;
	}

	TargetSpeedMps = FMath::Clamp(3.0f, GaitData->GetMinSpeed(), GaitData->GetMaxSpeed());
	SpeedMps = TargetSpeedMps;
	BuildSegmentComponents();
	// Pose once immediately so the very first rendered frame is already the
	// baked stance pose (milestone M1's static check).
	Tick(0.0f);
}

void ARunsimRunner::BuildSegmentComponents()
{
	const TArray<FRunsimSegment>& Segments = GaitData->GetSegments();
	SegmentComponents.Reset();
	SegmentComponents.Reserve(Segments.Num());

	for (int32 i = 0; i < Segments.Num(); ++i)
	{
		const FRunsimSegment& Seg = Segments[i];
		UStaticMesh* Mesh = Seg.bSphere ? SphereMesh.Get() : CylinderMesh.Get();

		UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(
			this, UStaticMeshComponent::StaticClass(),
			*FString::Printf(TEXT("Segment_%s"), *Seg.Name.ToString()));
		Comp->SetupAttachment(Root);
		Comp->SetMobility(EComponentMobility::Movable);
		Comp->SetStaticMesh(Mesh);
		Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Comp->SetCastShadow(true);
		Comp->RegisterComponent();

		if (BaseMaterial)
		{
			// BasicShapeMaterial may not expose a "Color" parameter; setting a
			// missing parameter is a no-op, so this degrades to plain grey.
			if (UMaterialInstanceDynamic* Mid =
				Comp->CreateDynamicMaterialInstance(0, BaseMaterial))
			{
				Mid->SetVectorParameterValue(TEXT("Color"), Seg.Color);
				Mid->SetVectorParameterValue(TEXT("BaseColor"), Seg.Color);
			}
		}

		// Segments whose body no loaded gait provides (the arm segments, until
		// a 3D solution is exported) simply stay hidden.
		const bool bHasBody = GaitData->GetSegmentBodyIndex(i) != INDEX_NONE;
		Comp->SetVisibility(bHasBody);
		if (!bHasBody)
		{
			UE_LOG(LogRunsim, Log,
				TEXT("segment '%s' hidden: no gait provides body '%s'"),
				*Seg.Name.ToString(), *Seg.BodyName.ToString());
		}

		SegmentComponents.Add(Comp);
	}
}

void ARunsimRunner::SetTargetSpeed(float MetresPerSecond)
{
	if (GaitData && GaitData->IsLoaded())
	{
		TargetSpeedMps = FMath::Clamp(MetresPerSecond,
			GaitData->GetMinSpeed(), GaitData->GetMaxSpeed());
	}
	else
	{
		TargetSpeedMps = MetresPerSecond;
	}
}

void ARunsimRunner::SetHilliness(float InHilliness)
{
	Hilliness = FMath::Clamp(InHilliness, 0.0f, 1.0f);
}

void ARunsimRunner::SetPaused(bool bInPaused)
{
	bPaused = bInPaused;
}

bool ARunsimRunner::HasArmData() const
{
	return GaitData != nullptr && GaitData->HasArmData();
}

void ARunsimRunner::CyclePlaybackGait()
{
	if (GaitData == nullptr || !GaitData->IsLoaded())
	{
		return;
	}
	const TArray<int32>& ThreeD = GaitData->Get3DGaits();
	if (ThreeD.Num() == 0)
	{
		return;
	}
	// INDEX_NONE -> ThreeD[0] -> ThreeD[1] -> ... -> INDEX_NONE
	const int32 Pos = ThreeD.IndexOfByKey(PlaybackIndex);
	if (PlaybackIndex == INDEX_NONE)
	{
		PlaybackIndex = ThreeD[0];
	}
	else if (Pos == INDEX_NONE || Pos + 1 >= ThreeD.Num())
	{
		PlaybackIndex = INDEX_NONE;
	}
	else
	{
		PlaybackIndex = ThreeD[Pos + 1];
	}
	UE_LOG(LogRunsim, Log, TEXT("gait source: %s"),
		PlaybackIndex == INDEX_NONE ? TEXT("blended 2D")
		: *GaitData->GetGaitLabel(PlaybackIndex));
}

FString ARunsimRunner::GetPlaybackLabel() const
{
	return (GaitData && PlaybackIndex != INDEX_NONE)
		? GaitData->GetGaitLabel(PlaybackIndex) : FString();
}

FVector ARunsimRunner::GetGroundLocation() const
{
	return RunsimTerrain::GroundLocation(DistanceM, Hilliness);
}

void ARunsimRunner::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (GaitData == nullptr || !GaitData->IsLoaded())
	{
		return;
	}

	if (!bPaused && DeltaSeconds > 0.0f)
	{
		// Clamp long hitches exactly as the web viewer does.
		const float Dt = FMath::Min(0.05f, DeltaSeconds);
		SpeedMps += (TargetSpeedMps - SpeedMps) * FMath::Min(1.0f, Dt * SpeedFollowRate);

		const float Grade = RunsimTerrain::GradeAt(DistanceM, Hilliness);
		FRunsimPose Step;
		const bool bPosed = (PlaybackIndex != INDEX_NONE)
			? GaitData->GetGaitPose(PlaybackIndex, Phase, Step)
			: GaitData->GetBlendedPose(SpeedMps, Grade, Phase, Step);
		if (bPosed)
		{
			// No foot skate: advance at the speed the baked stride produces,
			// projected onto the slope, not at the requested speed.
			const float EffectiveSpeed = Step.StrideLenM / Step.StrideTimeS;
			Phase = FMath::Frac(Phase + Dt / Step.StrideTimeS);
			DistanceM += EffectiveSpeed * FMath::Cos(FMath::Atan(Grade)) * Dt;
		}
	}

	CurrentGrade = RunsimTerrain::GradeAt(DistanceM, Hilliness);
	if (!GaitData->GetBlendedPose(SpeedMps, CurrentGrade, Phase, CachedPose))
	{
		return;
	}

	// Whole-runner placement: sit on the terrain, pitched by the local slope.
	// The simulation's ground plane (z = 0 in the baked pose) is then tangent
	// to the terrain at the runner's foot point.
	const FTransform RunnerTransform(
		FRotator(RunsimTerrain::PitchDegrees(DistanceM, Hilliness), 0.0f, 0.0f),
		RunsimTerrain::GroundLocation(DistanceM, Hilliness));
	SetActorTransform(RunnerTransform);

	PoseSegments();
}

void ARunsimRunner::PoseSegments()
{
	const TArray<FRunsimSegment>& Segments = GaitData->GetSegments();
	for (int32 i = 0; i < SegmentComponents.Num() && i < Segments.Num(); ++i)
	{
		UStaticMeshComponent* Comp = SegmentComponents[i].Get();
		if (Comp == nullptr)
		{
			continue;
		}
		const int32 BodyIndex = GaitData->GetSegmentBodyIndex(i);
		const bool bValid = BodyIndex != INDEX_NONE
			&& CachedPose.bBodyValid.IsValidIndex(BodyIndex)
			&& CachedPose.bBodyValid[BodyIndex];
		if (!bValid)
		{
			if (Comp->IsVisible())
			{
				Comp->SetVisibility(false);
			}
			continue;
		}
		if (!Comp->IsVisible())
		{
			Comp->SetVisibility(true);
		}

		const FRunsimSegment& Seg = Segments[i];
		// The engine cylinder/sphere are BasicShapeSize across in every axis,
		// with the cylinder's axis along +Z; LocalRotation takes +Z onto the
		// segment axis in the body frame.
		const FVector Scale(
			2.0f * Seg.RadiusCm / BasicShapeSize,
			2.0f * Seg.RadiusCm / BasicShapeSize,
			Seg.LengthCm / BasicShapeSize);

		const FTransform SegmentLocal(Seg.LocalRotation, Seg.LocalOffset, Scale);
		const FTransform BodyLocal(
			CachedPose.BodyRotation[BodyIndex],
			CachedPose.BodyPosition[BodyIndex]);

		// C = A * B applies A then B: the segment sits in the body's frame,
		// and the body's frame is relative to the actor (which carries the
		// terrain placement).
		Comp->SetRelativeTransform(SegmentLocal * BodyLocal);
	}
}
