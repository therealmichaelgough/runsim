#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"

#include "RunsimGaitData.generated.h"

/**
 * One render primitive, rigidly attached to one simulated body.
 *
 * LengthCm / RadiusCm / LocalOffset / LocalRotation all come out of
 * gaits_ue.json, which derives them from joint-to-joint distances in the
 * OpenSim model (scripts/export_ue_gaits.py).  LocalRotation takes the
 * mesh's +Z axis onto the segment axis, in the body's frame.
 */
struct FRunsimSegment
{
	FName Name;
	FName BodyName;
	FName SegmentClass;
	bool bSphere = false;
	float LengthCm = 0.0f;
	float RadiusCm = 0.0f;
	FVector LocalOffset = FVector::ZeroVector;
	FQuat LocalRotation = FQuat::Identity;
	FLinearColor Color = FLinearColor::White;
};

/** One baked Moco solution, resampled to a fixed number of stride phases. */
struct FRunsimGait
{
	FString SourceFile;
	FString SourceKind;          // "2d" or "3d"
	float Speed = 0.0f;          // m/s
	float Grade = 0.0f;          // dz/dx
	float StrideTimeS = 0.0f;
	float StrideLenM = 0.0f;
	bool bHasCot = false;
	float Cot = 0.0f;

	int32 NumBodies = 0;         // bodies present in *this* gait
	/** Global body index -> index within this gait, or INDEX_NONE. */
	TArray<int32> BodyRemap;
	/** NumFrames * NumBodies, frame-major. Centimetres, simulation frame. */
	TArray<FVector> Positions;
	TArray<FQuat> Rotations;
};

/** Result of blending gaits at one (speed, grade, phase). */
struct FRunsimPose
{
	/** Indexed by *global* body index; check bBodyValid first. */
	TArray<FVector> BodyPosition;
	TArray<FQuat> BodyRotation;
	TArray<bool> bBodyValid;

	float StrideTimeS = 0.5f;
	float StrideLenM = 1.5f;
	float WalkWeight = 0.0f;
	bool bHasCot = false;
	float Cot = 0.0f;
};

/**
 * Loads gaits_ue.json and blends it.
 *
 * The blend is a straight port of docs/run_viewer.html: bracket the two
 * nearest flat gaits by speed and interpolate, then add the *difference*
 * between the bracketed slope gaits and the flat 3.0 m/s reference.  The only
 * addition is that orientations, which the 2D web viewer did not have, are
 * slerped and the grade term is applied as a rotation delta rather than an
 * additive one.
 */
UCLASS()
class RUNSIMVIEWER_API URunsimGaitData : public UObject
{
	GENERATED_BODY()

public:
	/** Content/Data/gaits_ue.json, staged as UFS (see DefaultGame.ini). */
	static FString DefaultDataPath();

	bool LoadFromFile(const FString& FullPath);
	bool IsLoaded() const { return bLoaded; }
	const FString& GetLoadError() const { return LoadError; }

	const TArray<FRunsimSegment>& GetSegments() const { return Segments; }
	const TArray<FName>& GetBodyNames() const { return BodyNames; }
	int32 GetNumFrames() const { return NumFrames; }

	/** Index into GetBodyNames() for a segment, or INDEX_NONE. */
	int32 GetSegmentBodyIndex(int32 SegmentIndex) const;

	float GetMinSpeed() const;
	float GetMaxSpeed() const;

	/** True if any loaded gait carries the arm bodies (3D-sourced). */
	bool HasArmData() const { return bHasArmData; }

	/**
	 * Blend to (Speed m/s, Grade dz/dx, Phase in [0,1)).  Returns false and
	 * leaves Out untouched if no data is loaded.
	 */
	bool GetBlendedPose(float Speed, float Grade, float Phase, FRunsimPose& Out) const;

	/** 3D-sourced gaits, playable wholesale (every body, arms included). */
	const TArray<int32>& Get3DGaits() const { return ThreeDGaits; }

	/** One gait sampled directly at Phase — no blending. */
	bool GetGaitPose(int32 GaitIndex, float Phase, FRunsimPose& Out) const;

	/** Source-file label for the HUD. */
	FString GetGaitLabel(int32 GaitIndex) const;

private:
	bool ParseSegments(const TSharedPtr<class FJsonObject>& Root);
	bool ParseGaits(const TSharedPtr<class FJsonObject>& Root);
	void BuildIndices();

	/** Pose of one gait at a fractional frame, into pre-sized scratch arrays. */
	void SampleGait(int32 GaitIndex, float Phase,
		TArray<FVector>& OutPos, TArray<FQuat>& OutRot,
		TArray<bool>& OutValid) const;

	bool bLoaded = false;
	bool bHasArmData = false;
	FString LoadError;

	int32 NumFrames = 0;
	TArray<FName> BodyNames;           // global union of every gait's bodies
	TArray<FRunsimSegment> Segments;
	TArray<int32> SegmentBodyIndex;    // per segment -> global body index
	TArray<FRunsimGait> Gaits;

	TArray<int32> SpeedGaits;          // flat gaits, ascending speed
	TArray<float> SpeedKeys;           // their speeds, same order
	TArray<int32> GradeGaits;          // 3.0 m/s gaits, ascending grade
	TArray<float> GradeKeys;           // their grades, same order
	int32 Flat3Index = INDEX_NONE;     // the flat 3.0 m/s reference gait
	int32 ArmGaitIndex = INDEX_NONE;   // 3D arm-source gait (never blended)
	TArray<int32> ThreeDGaits;         // all 3D-sourced gaits, load order
};
