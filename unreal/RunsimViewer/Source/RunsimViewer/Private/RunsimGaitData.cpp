#include "RunsimGaitData.h"

#include "RunsimViewer.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	/**
	 * Compose two rotations unambiguously.
	 *
	 * Unreal's FQuat::operator* argument order is easy to get backwards;
	 * FTransform's is not (C = A * B is "A expressed in B's space", i.e. apply
	 * A first, then B -- the same rule the component hierarchy uses).  Since
	 * this code cannot be compiled on the authoring machine, it goes through
	 * FTransform rather than betting on the quaternion convention.
	 */
	FORCEINLINE FQuat ComposeThen(const FQuat& First, const FQuat& Then)
	{
		return (FTransform(First) * FTransform(Then)).GetRotation();
	}

	/**
	 * bracket() from docs/run_viewer.html, ported exactly:
	 *   let i = 0; while (i < arr.length - 2 && arr[i+1][key] <= x) i++;
	 *   w = clamp((x - a[key]) / (b[key] - a[key] || 1))
	 */
	void BracketKeys(const TArray<float>& Keys, float X,
		int32& OutA, int32& OutB, float& OutWeight)
	{
		const int32 N = Keys.Num();
		if (N <= 1)
		{
			OutA = OutB = 0;
			OutWeight = 0.0f;
			return;
		}
		int32 i = 0;
		while (i < N - 2 && Keys[i + 1] <= X)
		{
			++i;
		}
		OutA = i;
		OutB = i + 1;
		const float Span = Keys[OutB] - Keys[OutA];
		const float Denom = FMath::IsNearlyZero(Span) ? 1.0f : Span;
		OutWeight = FMath::Clamp((X - Keys[OutA]) / Denom, 0.0f, 1.0f);
	}

	bool ReadNumberArray(const FJsonObject& Obj, const TCHAR* Field,
		int32 Expected, TArray<double>& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (!Obj.TryGetArrayField(Field, Arr) || Arr == nullptr)
		{
			return false;
		}
		if (Expected > 0 && Arr->Num() != Expected)
		{
			return false;
		}
		Out.Reset(Arr->Num());
		for (const TSharedPtr<FJsonValue>& V : *Arr)
		{
			Out.Add(V.IsValid() ? V->AsNumber() : 0.0);
		}
		return true;
	}
}

FString URunsimGaitData::DefaultDataPath()
{
	return FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Data"), TEXT("gaits_ue.json"));
}

bool URunsimGaitData::LoadFromFile(const FString& FullPath)
{
	bLoaded = false;
	bHasArmData = false;
	LoadError.Reset();
	Segments.Reset();
	SegmentBodyIndex.Reset();
	BodyNames.Reset();
	Gaits.Reset();
	SpeedGaits.Reset();
	SpeedKeys.Reset();
	GradeGaits.Reset();
	GradeKeys.Reset();
	Flat3Index = INDEX_NONE;

	FString Raw;
	if (!FFileHelper::LoadFileToString(Raw, *FullPath))
	{
		LoadError = FString::Printf(TEXT("could not read %s"), *FullPath);
		UE_LOG(LogRunsim, Error, TEXT("%s"), *LoadError);
		return false;
	}

	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Raw);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		LoadError = FString::Printf(TEXT("malformed JSON in %s"), *FullPath);
		UE_LOG(LogRunsim, Error, TEXT("%s"), *LoadError);
		return false;
	}

	double Frames = 0.0;
	if (!Root->TryGetNumberField(TEXT("nframes"), Frames) || Frames < 2.0)
	{
		LoadError = TEXT("missing or invalid 'nframes'");
		UE_LOG(LogRunsim, Error, TEXT("%s"), *LoadError);
		return false;
	}
	NumFrames = static_cast<int32>(Frames);

	if (!ParseSegments(Root) || !ParseGaits(Root))
	{
		return false;
	}
	BuildIndices();

	if (SpeedGaits.Num() == 0 || Flat3Index == INDEX_NONE)
	{
		LoadError = TEXT("no flat gaits (need at least a flat 3.0 m/s reference)");
		UE_LOG(LogRunsim, Error, TEXT("%s"), *LoadError);
		return false;
	}

	bLoaded = true;
	UE_LOG(LogRunsim, Log,
		TEXT("gaits_ue.json: %d gaits, %d segments, %d bodies, %d frames, speed %.2f-%.2f m/s, arms %s"),
		Gaits.Num(), Segments.Num(), BodyNames.Num(), NumFrames,
		GetMinSpeed(), GetMaxSpeed(), bHasArmData ? TEXT("present") : TEXT("absent"));
	return true;
}

bool URunsimGaitData::ParseSegments(const TSharedPtr<FJsonObject>& Root)
{
	const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
	if (!Root->TryGetArrayField(TEXT("segments"), Arr) || Arr == nullptr)
	{
		LoadError = TEXT("missing 'segments'");
		UE_LOG(LogRunsim, Error, TEXT("%s"), *LoadError);
		return false;
	}

	for (const TSharedPtr<FJsonValue>& Value : *Arr)
	{
		const TSharedPtr<FJsonObject>* ObjPtr = nullptr;
		if (!Value.IsValid() || !Value->TryGetObject(ObjPtr) || ObjPtr == nullptr)
		{
			continue;
		}
		const FJsonObject& Obj = **ObjPtr;

		FRunsimSegment Seg;
		FString Text;
		Obj.TryGetStringField(TEXT("name"), Text);
		Seg.Name = FName(*Text);
		Text.Reset();
		Obj.TryGetStringField(TEXT("body"), Text);
		Seg.BodyName = FName(*Text);
		Text.Reset();
		Obj.TryGetStringField(TEXT("class"), Text);
		Seg.SegmentClass = FName(*Text);
		Text.Reset();
		Obj.TryGetStringField(TEXT("mesh"), Text);
		Seg.bSphere = Text.Equals(TEXT("sphere"), ESearchCase::IgnoreCase);

		double Number = 0.0;
		Obj.TryGetNumberField(TEXT("lengthCm"), Number);
		Seg.LengthCm = static_cast<float>(Number);
		Number = 0.0;
		Obj.TryGetNumberField(TEXT("radiusCm"), Number);
		Seg.RadiusCm = static_cast<float>(Number);

		TArray<double> Numbers;
		if (ReadNumberArray(Obj, TEXT("offsetCm"), 3, Numbers))
		{
			Seg.LocalOffset = FVector(Numbers[0], Numbers[1], Numbers[2]);
		}
		if (ReadNumberArray(Obj, TEXT("rot"), 4, Numbers))
		{
			// exported as [x, y, z, w], which is FQuat's constructor order
			Seg.LocalRotation = FQuat(Numbers[0], Numbers[1], Numbers[2], Numbers[3]);
			Seg.LocalRotation.Normalize();
		}
		if (ReadNumberArray(Obj, TEXT("color"), 3, Numbers))
		{
			Seg.Color = FLinearColor(
				static_cast<float>(Numbers[0]),
				static_cast<float>(Numbers[1]),
				static_cast<float>(Numbers[2]),
				1.0f);
		}

		if (Seg.Name.IsNone() || Seg.BodyName.IsNone() || Seg.LengthCm <= 0.0f)
		{
			UE_LOG(LogRunsim, Warning, TEXT("skipping malformed segment '%s'"),
				*Seg.Name.ToString());
			continue;
		}
		Segments.Add(Seg);
	}

	if (Segments.Num() == 0)
	{
		LoadError = TEXT("no usable segments");
		UE_LOG(LogRunsim, Error, TEXT("%s"), *LoadError);
		return false;
	}
	return true;
}

bool URunsimGaitData::ParseGaits(const TSharedPtr<FJsonObject>& Root)
{
	const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
	if (!Root->TryGetArrayField(TEXT("gaits"), Arr) || Arr == nullptr)
	{
		LoadError = TEXT("missing 'gaits'");
		UE_LOG(LogRunsim, Error, TEXT("%s"), *LoadError);
		return false;
	}

	// First pass: the global body table is the union of every gait's bodies,
	// in first-seen order.  2D-sourced gaits simply do not carry the arm
	// bodies; segments whose body never appears are hidden by the renderer.
	TArray<TArray<FName>> PerGaitBodies;
	PerGaitBodies.Reserve(Arr->Num());
	for (const TSharedPtr<FJsonValue>& Value : *Arr)
	{
		const TSharedPtr<FJsonObject>* ObjPtr = nullptr;
		TArray<FName> Names;
		if (Value.IsValid() && Value->TryGetObject(ObjPtr) && ObjPtr != nullptr)
		{
			const TArray<TSharedPtr<FJsonValue>>* BodyArr = nullptr;
			if ((*ObjPtr)->TryGetArrayField(TEXT("bodies"), BodyArr) && BodyArr)
			{
				for (const TSharedPtr<FJsonValue>& B : *BodyArr)
				{
					const FName Name(*(B.IsValid() ? B->AsString() : FString()));
					Names.Add(Name);
					BodyNames.AddUnique(Name);
				}
			}
		}
		PerGaitBodies.Add(MoveTemp(Names));
	}

	// Second pass: the frames themselves.
	int32 GaitIndex = 0;
	for (const TSharedPtr<FJsonValue>& Value : *Arr)
	{
		const TSharedPtr<FJsonObject>* ObjPtr = nullptr;
		if (!Value.IsValid() || !Value->TryGetObject(ObjPtr) || ObjPtr == nullptr)
		{
			++GaitIndex;
			continue;
		}
		const FJsonObject& Obj = **ObjPtr;
		const TArray<FName>& Bodies = PerGaitBodies[GaitIndex];
		++GaitIndex;

		FRunsimGait G;
		Obj.TryGetStringField(TEXT("src"), G.SourceFile);
		Obj.TryGetStringField(TEXT("source"), G.SourceKind);

		double Number = 0.0;
		Obj.TryGetNumberField(TEXT("speed"), Number);
		G.Speed = static_cast<float>(Number);
		Number = 0.0;
		Obj.TryGetNumberField(TEXT("grade"), Number);
		G.Grade = static_cast<float>(Number);
		Number = 0.0;
		Obj.TryGetNumberField(TEXT("strideTime"), Number);
		G.StrideTimeS = static_cast<float>(Number);
		Number = 0.0;
		Obj.TryGetNumberField(TEXT("strideLen"), Number);
		G.StrideLenM = static_cast<float>(Number);

		// "cot": null for the effort-objective walk gaits -- TryGetNumberField
		// fails on null, which is exactly the COT-hidden rule.
		double CotValue = 0.0;
		G.bHasCot = Obj.TryGetNumberField(TEXT("cot"), CotValue);
		G.Cot = static_cast<float>(CotValue);

		G.NumBodies = Bodies.Num();
		G.BodyRemap.Init(INDEX_NONE, BodyNames.Num());
		for (int32 Local = 0; Local < Bodies.Num(); ++Local)
		{
			const int32 Global = BodyNames.IndexOfByKey(Bodies[Local]);
			if (Global != INDEX_NONE)
			{
				G.BodyRemap[Global] = Local;
			}
		}

		const TArray<TSharedPtr<FJsonValue>>* FrameArr = nullptr;
		if (!Obj.TryGetArrayField(TEXT("frames"), FrameArr) || FrameArr == nullptr
			|| FrameArr->Num() < NumFrames || G.NumBodies == 0
			|| G.StrideTimeS <= 0.0f)
		{
			UE_LOG(LogRunsim, Warning, TEXT("skipping gait '%s': missing frames"),
				*G.SourceFile);
			continue;
		}

		G.Positions.SetNum(NumFrames * G.NumBodies);
		G.Rotations.SetNum(NumFrames * G.NumBodies);
		bool bOk = true;
		for (int32 f = 0; f < NumFrames && bOk; ++f)
		{
			const TArray<TSharedPtr<FJsonValue>>* Row = nullptr;
			const TSharedPtr<FJsonValue>& RowValue = (*FrameArr)[f];
			if (!RowValue.IsValid() || !RowValue->TryGetArray(Row) || Row == nullptr
				|| Row->Num() != 7 * G.NumBodies)
			{
				bOk = false;
				break;
			}
			for (int32 b = 0; b < G.NumBodies; ++b)
			{
				const int32 O = b * 7;
				const int32 Slot = f * G.NumBodies + b;
				G.Positions[Slot] = FVector(
					(*Row)[O + 0]->AsNumber(),
					(*Row)[O + 1]->AsNumber(),
					(*Row)[O + 2]->AsNumber());
				FQuat Q(
					(*Row)[O + 3]->AsNumber(),
					(*Row)[O + 4]->AsNumber(),
					(*Row)[O + 5]->AsNumber(),
					(*Row)[O + 6]->AsNumber());
				Q.Normalize();
				G.Rotations[Slot] = Q;
			}
		}
		if (!bOk)
		{
			UE_LOG(LogRunsim, Warning, TEXT("skipping gait '%s': bad frame row"),
				*G.SourceFile);
			continue;
		}

		if (G.SourceKind.Equals(TEXT("3d"), ESearchCase::IgnoreCase))
		{
			bHasArmData = true;
		}
		Gaits.Add(MoveTemp(G));
	}

	if (Gaits.Num() == 0)
	{
		LoadError = TEXT("no usable gaits");
		UE_LOG(LogRunsim, Error, TEXT("%s"), *LoadError);
		return false;
	}
	return true;
}

void URunsimGaitData::BuildIndices()
{
	// Segment -> global body index (INDEX_NONE when no gait provides it).
	SegmentBodyIndex.Init(INDEX_NONE, Segments.Num());
	for (int32 i = 0; i < Segments.Num(); ++i)
	{
		SegmentBodyIndex[i] = BodyNames.IndexOfByKey(Segments[i].BodyName);
	}

	// Same partition as the web viewer: flat gaits drive the speed blend,
	// the 3.0 m/s metabolic-objective gaits drive the grade blend.
	for (int32 i = 0; i < Gaits.Num(); ++i)
	{
		if (FMath::IsNearlyZero(Gaits[i].Grade, 1.0e-6f))
		{
			SpeedGaits.Add(i);
		}
		if (FMath::IsNearlyEqual(Gaits[i].Speed, 3.0f, 1.0e-4f)
			&& Gaits[i].SourceFile.Contains(TEXT("_met")))
		{
			GradeGaits.Add(i);
		}
	}
	SpeedGaits.Sort([this](const int32& A, const int32& B)
	{
		return Gaits[A].Speed < Gaits[B].Speed;
	});
	GradeGaits.Sort([this](const int32& A, const int32& B)
	{
		return Gaits[A].Grade < Gaits[B].Grade;
	});

	SpeedKeys.Reset(SpeedGaits.Num());
	for (int32 Index : SpeedGaits)
	{
		SpeedKeys.Add(Gaits[Index].Speed);
	}
	GradeKeys.Reset(GradeGaits.Num());
	for (int32 Index : GradeGaits)
	{
		GradeKeys.Add(Gaits[Index].Grade);
	}

	float Best = TNumericLimits<float>::Max();
	for (int32 Index : SpeedGaits)
	{
		const float D = FMath::Abs(Gaits[Index].Speed - 3.0f);
		if (D < Best)
		{
			Best = D;
			Flat3Index = Index;
		}
	}
}

int32 URunsimGaitData::GetSegmentBodyIndex(int32 SegmentIndex) const
{
	return SegmentBodyIndex.IsValidIndex(SegmentIndex)
		? SegmentBodyIndex[SegmentIndex] : INDEX_NONE;
}

float URunsimGaitData::GetMinSpeed() const
{
	return SpeedKeys.Num() > 0 ? SpeedKeys[0] : 0.0f;
}

float URunsimGaitData::GetMaxSpeed() const
{
	return SpeedKeys.Num() > 0 ? SpeedKeys.Last() : 0.0f;
}

void URunsimGaitData::SampleGait(int32 GaitIndex, float Phase,
	TArray<FVector>& OutPos, TArray<FQuat>& OutRot, TArray<bool>& OutValid) const
{
	const int32 NumGlobalBodies = BodyNames.Num();
	OutPos.SetNum(NumGlobalBodies);
	OutRot.SetNum(NumGlobalBodies);
	OutValid.SetNum(NumGlobalBodies);

	if (!Gaits.IsValidIndex(GaitIndex) || NumFrames <= 0)
	{
		for (int32 b = 0; b < NumGlobalBodies; ++b)
		{
			OutValid[b] = false;
		}
		return;
	}
	const FRunsimGait& G = Gaits[GaitIndex];

	// frameAt() from the web viewer: wrap the stride, lerp between neighbours.
	const float F = FMath::Frac(FMath::Max(0.0f, Phase)) * static_cast<float>(NumFrames);
	const float Floor = FMath::FloorToFloat(F);
	int32 i = static_cast<int32>(Floor) % NumFrames;
	if (i < 0)
	{
		i += NumFrames;
	}
	const int32 j = (i + 1) % NumFrames;
	const float U = F - Floor;

	for (int32 b = 0; b < NumGlobalBodies; ++b)
	{
		const int32 Local = G.BodyRemap.IsValidIndex(b) ? G.BodyRemap[b] : INDEX_NONE;
		if (Local == INDEX_NONE)
		{
			OutValid[b] = false;
			OutPos[b] = FVector::ZeroVector;
			OutRot[b] = FQuat::Identity;
			continue;
		}
		const int32 SlotA = i * G.NumBodies + Local;
		const int32 SlotB = j * G.NumBodies + Local;
		OutValid[b] = true;
		OutPos[b] = FMath::Lerp(G.Positions[SlotA], G.Positions[SlotB], U);
		OutRot[b] = FQuat::Slerp(G.Rotations[SlotA], G.Rotations[SlotB], U).GetNormalized();
	}
}

bool URunsimGaitData::GetBlendedPose(float Speed, float Grade, float Phase,
	FRunsimPose& Out) const
{
	if (!bLoaded || SpeedKeys.Num() == 0 || Flat3Index == INDEX_NONE)
	{
		return false;
	}

	int32 KA = 0, KB = 0;
	float W = 0.0f;
	BracketKeys(SpeedKeys, Speed, KA, KB, W);
	const FRunsimGait& A = Gaits[SpeedGaits[KA]];
	const FRunsimGait& B = Gaits[SpeedGaits[KB]];

	// The grade blend is only defined over the solved slope range; outside it
	// the pose is clamped (the terrain still tilts, the gait does not).
	int32 GA = 0, GB = 0;
	float GW = 0.0f;
	if (GradeKeys.Num() > 0)
	{
		const float Clamped = FMath::Clamp(Grade, GradeKeys[0], GradeKeys.Last());
		BracketKeys(GradeKeys, Clamped, GA, GB, GW);
	}
	const bool bHaveGradeGaits = GradeKeys.Num() > 1;
	const FRunsimGait& GAG = bHaveGradeGaits ? Gaits[GradeGaits[GA]] : Gaits[Flat3Index];
	const FRunsimGait& GBG = bHaveGradeGaits ? Gaits[GradeGaits[GB]] : Gaits[Flat3Index];
	const FRunsimGait& Flat3 = Gaits[Flat3Index];

	TArray<FVector> PosA, PosB, PosGA, PosGB, PosF;
	TArray<FQuat> RotA, RotB, RotGA, RotGB, RotF;
	TArray<bool> ValA, ValB, ValGA, ValGB, ValF;
	SampleGait(SpeedGaits[KA], Phase, PosA, RotA, ValA);
	SampleGait(SpeedGaits[KB], Phase, PosB, RotB, ValB);
	SampleGait(bHaveGradeGaits ? GradeGaits[GA] : Flat3Index, Phase, PosGA, RotGA, ValGA);
	SampleGait(bHaveGradeGaits ? GradeGaits[GB] : Flat3Index, Phase, PosGB, RotGB, ValGB);
	SampleGait(Flat3Index, Phase, PosF, RotF, ValF);

	const int32 NumGlobalBodies = BodyNames.Num();
	Out.BodyPosition.SetNum(NumGlobalBodies);
	Out.BodyRotation.SetNum(NumGlobalBodies);
	Out.bBodyValid.SetNum(NumGlobalBodies);

	for (int32 b = 0; b < NumGlobalBodies; ++b)
	{
		const bool bValid = ValA[b] && ValB[b] && ValGA[b] && ValGB[b] && ValF[b];
		Out.bBodyValid[b] = bValid;
		if (!bValid)
		{
			Out.BodyPosition[b] = FVector::ZeroVector;
			Out.BodyRotation[b] = FQuat::Identity;
			continue;
		}

		// Position: speed lerp plus the grade gaits' offset from flat-3.0.
		FVector P = FMath::Lerp(PosA[b], PosB[b], W);
		P += FMath::Lerp(PosGA[b], PosGB[b], GW) - PosF[b];
		Out.BodyPosition[b] = P;

		// Rotation: the same idea, but the "difference" of two orientations is
		// a relative rotation, applied on top of the speed-blended pose.
		const FQuat QSpeed = FQuat::Slerp(RotA[b], RotB[b], W).GetNormalized();
		const FQuat QGrade = FQuat::Slerp(RotGA[b], RotGB[b], GW).GetNormalized();
		const FQuat QDelta = ComposeThen(RotF[b].Inverse(), QGrade);
		Out.BodyRotation[b] = ComposeThen(QSpeed, QDelta).GetNormalized();
	}

	// lerp2() from the web viewer, for the scalar metadata.
	auto Lerp2 = [W, GW](float a, float b, float ga, float gb, float flat)
	{
		return (a * (1.0f - W) + b * W) + (ga * (1.0f - GW) + gb * GW) - flat;
	};
	Out.StrideTimeS = FMath::Max(0.05f, Lerp2(A.StrideTimeS, B.StrideTimeS,
		GAG.StrideTimeS, GBG.StrideTimeS, Flat3.StrideTimeS));
	Out.StrideLenM = FMath::Max(0.05f, Lerp2(A.StrideLenM, B.StrideLenM,
		GAG.StrideLenM, GBG.StrideLenM, Flat3.StrideLenM));

	// COT is only meaningful when every contributing solution reports one --
	// the effort-objective walk gaits (1.2, 2.0 m/s) do not, so the HUD hides
	// it there.  Same rule as the web viewer.
	Out.bHasCot = A.bHasCot && B.bHasCot && GAG.bHasCot && GBG.bHasCot && Flat3.bHasCot;
	Out.Cot = Out.bHasCot
		? Lerp2(A.Cot, B.Cot, GAG.Cot, GBG.Cot, Flat3.Cot)
		: 0.0f;

	// walkW: 1 while both brackets are walk gaits, fading out across the
	// walk -> run bracket.
	Out.WalkWeight = (A.Speed <= 2.0f)
		? 1.0f - W * (B.Speed > 2.0f ? 1.0f : 0.0f)
		: 0.0f;

	return true;
}
