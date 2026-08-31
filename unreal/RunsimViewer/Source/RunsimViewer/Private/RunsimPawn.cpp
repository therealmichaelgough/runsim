#include "RunsimPawn.h"

#include "RunsimRunner.h"
#include "RunsimTerrain.h"
#include "RunsimTerrainMath.h"
#include "RunsimViewer.h"

#include "Camera/CameraComponent.h"
#include "Components/InputComponent.h"
#include "EngineUtils.h"
#include "GameFramework/SpringArmComponent.h"

ARunsimPawn::ARunsimPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	// The camera reads the runner's pose after it has been updated.
	PrimaryActorTick.TickGroup = TG_PostPhysics;

	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Movable);
	RootComponent = Root;

	SpringArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("SpringArm"));
	SpringArm->SetupAttachment(Root);
	SpringArm->TargetArmLength = DefaultArmLength;
	SpringArm->bUsePawnControlRotation = false;
	SpringArm->bInheritPitch = false;
	SpringArm->bInheritYaw = false;
	SpringArm->bInheritRoll = false;
	SpringArm->bDoCollisionTest = false;
	SpringArm->bEnableCameraLag = true;
	SpringArm->CameraLagSpeed = 3.0f;          // plan section 5
	SpringArm->bEnableCameraRotationLag = true;
	SpringArm->CameraRotationLagSpeed = 8.0f;
	SpringArm->SetRelativeRotation(FRotator(DefaultPitch, DefaultYaw, 0.0f));

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(SpringArm, USpringArmComponent::SocketName);
	Camera->bUsePawnControlRotation = false;
	Camera->SetFieldOfView(75.0f);
}

void ARunsimPawn::BeginPlay()
{
	Super::BeginPlay();
	ResolveWorldActors();
}

void ARunsimPawn::ResolveWorldActors()
{
	UWorld* World = GetWorld();
	if (World == nullptr)
	{
		return;
	}
	if (Runner == nullptr)
	{
		for (TActorIterator<ARunsimRunner> It(World); It; ++It)
		{
			Runner = *It;
			// Tick after the runner so the camera never trails by a frame.
			AddTickPrerequisiteActor(Runner);
			break;
		}
	}
	if (Terrain == nullptr)
	{
		for (TActorIterator<ARunsimTerrain> It(World); It; ++It)
		{
			Terrain = *It;
			break;
		}
	}
}

void ARunsimPawn::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	if (PlayerInputComponent == nullptr)
	{
		return;
	}

	PlayerInputComponent->BindAxis(TEXT("RunsimSpeed"), this, &ARunsimPawn::InputSpeed);
	PlayerInputComponent->BindAxis(TEXT("RunsimHills"), this, &ARunsimPawn::InputHills);
	PlayerInputComponent->BindAxis(TEXT("RunsimTurn"), this, &ARunsimPawn::InputTurn);
	PlayerInputComponent->BindAxis(TEXT("RunsimLookUp"), this, &ARunsimPawn::InputLookUp);
	PlayerInputComponent->BindAxis(TEXT("RunsimZoom"), this, &ARunsimPawn::InputZoom);

	PlayerInputComponent->BindAction(TEXT("RunsimOrbit"), IE_Pressed, this,
		&ARunsimPawn::OnOrbitPressed);
	PlayerInputComponent->BindAction(TEXT("RunsimOrbit"), IE_Released, this,
		&ARunsimPawn::OnOrbitReleased);
	PlayerInputComponent->BindAction(TEXT("RunsimPause"), IE_Pressed, this,
		&ARunsimPawn::OnTogglePause);
	PlayerInputComponent->BindAction(TEXT("RunsimResetView"), IE_Pressed, this,
		&ARunsimPawn::OnResetView);
	PlayerInputComponent->BindAction(TEXT("RunsimQuit"), IE_Pressed, this,
		&ARunsimPawn::OnQuit);
}

void ARunsimPawn::OnQuit()
{
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		PC->ConsoleCommand(TEXT("quit"));
	}
}

void ARunsimPawn::InputSpeed(float Value)
{
	if (FMath::IsNearlyZero(Value))
	{
		return;
	}
	const float Dt = GetWorld() ? GetWorld()->GetDeltaSeconds() : 0.0f;
	TargetSpeedMps += Value * SpeedChangeRate * Dt;
}

void ARunsimPawn::InputHills(float Value)
{
	if (FMath::IsNearlyZero(Value))
	{
		return;
	}
	const float Dt = GetWorld() ? GetWorld()->GetDeltaSeconds() : 0.0f;
	Hilliness = FMath::Clamp(Hilliness + Value * HillsChangeRate * Dt, 0.0f, 1.0f);
}

void ARunsimPawn::InputTurn(float Value)
{
	if (bOrbiting && !FMath::IsNearlyZero(Value))
	{
		OrbitYaw = static_cast<float>(
			FRotator::NormalizeAxis(OrbitYaw + Value * OrbitSensitivity));
	}
}

void ARunsimPawn::InputLookUp(float Value)
{
	if (bOrbiting && !FMath::IsNearlyZero(Value))
	{
		OrbitPitch = FMath::Clamp(OrbitPitch + Value * OrbitSensitivity, -80.0f, 30.0f);
	}
}

void ARunsimPawn::InputZoom(float Value)
{
	if (!FMath::IsNearlyZero(Value))
	{
		ArmLength = FMath::Clamp(ArmLength - Value * ZoomStepCm,
			MinArmLength, MaxArmLength);
	}
}

void ARunsimPawn::OnOrbitPressed()
{
	bOrbiting = true;
}

void ARunsimPawn::OnOrbitReleased()
{
	bOrbiting = false;
}

void ARunsimPawn::OnTogglePause()
{
	bPaused = !bPaused;
}

void ARunsimPawn::OnResetView()
{
	OrbitYaw = DefaultYaw;
	OrbitPitch = DefaultPitch;
	ArmLength = DefaultArmLength;
}

void ARunsimPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	ResolveWorldActors();

	if (Runner)
	{
		if (Runner->GetGaitData() && Runner->GetGaitData()->IsLoaded())
		{
			TargetSpeedMps = FMath::Clamp(TargetSpeedMps,
				Runner->GetGaitData()->GetMinSpeed(),
				Runner->GetGaitData()->GetMaxSpeed());
		}
		Runner->SetTargetSpeed(TargetSpeedMps);
		Runner->SetHilliness(Hilliness);
		Runner->SetPaused(bPaused);
	}
	if (Terrain)
	{
		Terrain->SetHilliness(Hilliness);
		Terrain->UpdateAround(Runner ? Runner->GetDistanceM() : 0.0f);
	}

	// Follow the runner with a velocity-scaled look-ahead; the spring arm's
	// lag does the smoothing, so the focus point itself can snap.
	if (Runner)
	{
		const float LookAheadM =
			Runner->GetSpeedMps() * LookAheadPerMps / RunsimTerrain::UnitsPerMetre;
		const float FocusM = Runner->GetDistanceM() + LookAheadM;
		FVector Focus = RunsimTerrain::GroundLocation(FocusM, Hilliness);
		Focus.Z += EyeHeightCm;
		SetActorLocation(Focus);
	}

	if (SpringArm)
	{
		SpringArm->TargetArmLength = ArmLength;
		SpringArm->SetRelativeRotation(FRotator(OrbitPitch, OrbitYaw, 0.0f));
	}
}
