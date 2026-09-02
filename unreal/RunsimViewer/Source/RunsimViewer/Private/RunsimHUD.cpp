#include "RunsimHUD.h"

#include "RunsimPawn.h"
#include "RunsimRunner.h"
#include "RunsimViewer.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"

namespace
{
	const FLinearColor PanelColor(0.03f, 0.06f, 0.10f, 0.72f);
	const FLinearColor TitleColor(0.55f, 0.66f, 0.78f, 1.0f);
	const FLinearColor LabelColor(0.43f, 0.53f, 0.65f, 1.0f);
	const FLinearColor ValueColor(0.93f, 0.96f, 0.99f, 1.0f);
	const FLinearColor AccentColor(0.39f, 0.85f, 0.78f, 1.0f);
	const FLinearColor WarnColor(1.0f, 0.72f, 0.35f, 1.0f);
	const FLinearColor MutedColor(0.40f, 0.48f, 0.58f, 1.0f);

	const TCHAR* EmDash = TEXT("\u2014");

	FString Cardinal(float HeadingDeg)
	{
		static const TCHAR* Names[] = {
			TEXT("E"), TEXT("SE"), TEXT("S"), TEXT("SW"),
			TEXT("W"), TEXT("NW"), TEXT("N"), TEXT("NE") };
		// Unreal yaw increases clockwise seen from above (+X = east here).
		const float Norm = FMath::Fmod(HeadingDeg + 360.0f + 22.5f, 360.0f);
		return Names[FMath::Clamp(static_cast<int32>(Norm / 45.0f), 0, 7)];
	}
}

FString ARunsimHUD::FormatPace(float SpeedMps, float DistanceMeters)
{
	if (SpeedMps <= 0.05f)
	{
		return TEXT("--:--");
	}
	const float SecondsPer = DistanceMeters / SpeedMps;
	const int32 Minutes = FMath::FloorToInt(SecondsPer / 60.0f);
	const int32 Seconds = FMath::RoundToInt(SecondsPer - Minutes * 60.0f);
	// Guard the 59.6 -> "60" rounding case.
	return (Seconds >= 60)
		? FString::Printf(TEXT("%d:00"), Minutes + 1)
		: FString::Printf(TEXT("%d:%02d"), Minutes, Seconds);
}

float ARunsimHUD::BeginPanel(float X, float Y, float Width, int32 NumRows,
	const FString& Title)
{
	const float Height = TitleHeight + NumRows * RowHeight + InnerPad;
	DrawRect(PanelColor, X, Y, Width, Height);
	DrawRect(AccentColor, X, Y, 3.0f, Height);
	UFont* Small = GEngine ? GEngine->GetSmallFont() : nullptr;
	DrawText(Title, TitleColor, X + InnerPad, Y + 6.0f, Small, 1.0f);
	return Y + TitleHeight;
}

void ARunsimHUD::DrawRow(float X, float Y, float Width, const FString& Label,
	const FString& Value, const FLinearColor& InValueColor)
{
	UFont* Small = GEngine ? GEngine->GetSmallFont() : nullptr;
	DrawText(Label, LabelColor, X + InnerPad, Y + 3.0f, Small, 1.0f);
	float TextW = 0.0f, TextH = 0.0f;
	GetTextSize(Value, TextW, TextH, Small, 1.0f);
	DrawText(Value, InValueColor, X + Width - InnerPad - TextW, Y + 3.0f,
		Small, 1.0f);
}

void ARunsimHUD::DrawHUD()
{
	Super::DrawHUD();

	if (Canvas == nullptr)
	{
		return;
	}

	const ARunsimPawn* Pawn = Cast<ARunsimPawn>(GetOwningPawn());
	ARunsimRunner* Runner = Pawn ? Pawn->GetRunner() : nullptr;
	UFont* Small = GEngine ? GEngine->GetSmallFont() : nullptr;

	if (Runner == nullptr || Runner->GetGaitData() == nullptr
		|| !Runner->GetGaitData()->IsLoaded())
	{
		DrawRect(PanelColor, PanelPadding, PanelPadding, 620.0f, 58.0f);
		DrawText(TEXT("No gait data loaded."), WarnColor,
			PanelPadding + 10.0f, PanelPadding + 8.0f, Small, 1.1f);
		DrawText(TEXT("Run:  .venv/Scripts/python.exe scripts/export_ue_gaits.py"),
			LabelColor, PanelPadding + 10.0f, PanelPadding + 30.0f, Small, 1.0f);
		return;
	}

	const float Speed = Runner->GetSpeedMps();
	const float StrideTime = FMath::Max(0.05f, Runner->GetStrideTimeS());
	// Two steps per stride: 120/strideTime steps per minute, 2/strideTime Hz.
	const float StepsPerMinute = 120.0f / StrideTime;
	const float CadenceHz = 2.0f / StrideTime;
	const float GradePercent = Runner->GetGrade() * 100.0f;
	const bool bWalking = Runner->GetWalkWeight() > 0.5f;
	const bool bPlayback = Runner->IsPlayback3D();

	const float X = PanelPadding;
	float Y = PanelPadding;

	// ---- MOTION ----------------------------------------------------------
	float RowY = BeginPanel(X, Y, PanelWidth, 4, TEXT("MOTION"));
	DrawRow(X, RowY, PanelWidth, TEXT("SPEED"),
		FString::Printf(TEXT("%.1f m/s"), Speed), ValueColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth, TEXT("PACE"),
		FormatPace(Speed) + TEXT(" /km"), ValueColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth, TEXT(""),
		FormatPace(Speed, 1609.344f) + TEXT(" /mi"), ValueColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth, TEXT("HEADING"),
		FString::Printf(TEXT("%03d\u00B0 %s"),
			FMath::RoundToInt(FMath::Fmod(Runner->GetHeadingDeg() + 360.0f, 360.0f)),
			*Cardinal(Runner->GetHeadingDeg())), ValueColor);
	Y = RowY + RowHeight + InnerPad + PanelGap;

	// ---- GAIT ------------------------------------------------------------
	RowY = BeginPanel(X, Y, PanelWidth, 5, TEXT("GAIT"));
	DrawRow(X, RowY, PanelWidth, TEXT("STATE"),
		bPlayback ? TEXT("3D PLAYBACK")
			: (bWalking ? TEXT("WALK") : TEXT("RUN")), AccentColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth, TEXT("CADENCE"),
		FString::Printf(TEXT("%d spm  %.2f Hz"),
			FMath::RoundToInt(StepsPerMinute), CadenceHz), ValueColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth, TEXT("STRIDE"),
		FString::Printf(TEXT("%.2f m"), Runner->GetStrideLenM()), ValueColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth, TEXT("CONTACT"),
		Runner->HasContact()
			? FString::Printf(TEXT("%d ms"),
				FMath::RoundToInt(Runner->GetContactTimeS() * 1000.0f))
			: FString(EmDash),
		Runner->HasContact() ? ValueColor : MutedColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth, TEXT("FLIGHT"),
		Runner->HasContact()
			? FString::Printf(TEXT("%d %%"),
				FMath::RoundToInt(Runner->GetFlightFrac() * 100.0f))
			: FString(EmDash),
		Runner->HasContact() ? ValueColor : MutedColor);
	Y = RowY + RowHeight + InnerPad + PanelGap;

	// ---- GROUND ----------------------------------------------------------
	RowY = BeginPanel(X, Y, PanelWidth, 3, TEXT("GROUND"));
	DrawRow(X, RowY, PanelWidth, TEXT("GRADE"),
		FString::Printf(TEXT("%s%.1f %%%s"),
			GradePercent >= 0.0f ? TEXT("+") : TEXT(""), GradePercent,
			Runner->IsGaitGradeClamped() ? TEXT("  [gait clamped]") : TEXT("")),
		Runner->IsGaitGradeClamped() ? WarnColor : ValueColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth, TEXT("ELEVATION"),
		FString::Printf(TEXT("%.0f m"),
			Runner->GetGroundLocation().Z / 100.0f), ValueColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth, TEXT("HILLINESS"),
		FString::Printf(TEXT("%d %%"),
			FMath::RoundToInt(Runner->GetHilliness() * 100.0f)), ValueColor);
	Y = RowY + RowHeight + InnerPad + PanelGap;

	// ---- ENERGY ----------------------------------------------------------
	// Metabolic rate prefers the baked per-frame Bhargava channel; when a
	// contributing gait lacks it, fall back to COT x speed (same units).
	const bool bDerivedMet = !Runner->HasMetRate() && Runner->HasCot();
	RowY = BeginPanel(X, Y, PanelWidth, 3, TEXT("ENERGY"));
	DrawRow(X, RowY, PanelWidth, TEXT("VERT GRF"),
		Runner->HasGrf()
			? FString::Printf(TEXT("%.2f BW"), Runner->GetGrfBw())
			: FString(EmDash),
		Runner->HasGrf() ? ValueColor : MutedColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth,
		bDerivedMet ? TEXT("MET (COT x V)") : TEXT("MET RATE"),
		Runner->HasMetRate()
			? FString::Printf(TEXT("%.1f W/kg"), Runner->GetMetRateWkg())
			: (bDerivedMet
				? FString::Printf(TEXT("%.1f W/kg"), Runner->GetCot() * Speed)
				: FString(EmDash)),
		(Runner->HasMetRate() || bDerivedMet) ? ValueColor : MutedColor);
	RowY += RowHeight;
	DrawRow(X, RowY, PanelWidth, TEXT("COT"),
		Runner->HasCot()
			? FString::Printf(TEXT("%.2f J/kg/m"), Runner->GetCot())
			: FString(EmDash),
		Runner->HasCot() ? ValueColor : MutedColor);
	Y = RowY + RowHeight + InnerPad + PanelGap;

	if (Runner->IsPaused())
	{
		DrawText(TEXT("PAUSED"), AccentColor, X, Y + 2.0f, Small, 1.3f);
	}

	// ---- provenance + controls, bottom left ------------------------------
	const float BottomY = FMath::Max(Y + 30.0f,
		static_cast<float>(Canvas->SizeY) - 76.0f);
	if (bPlayback)
	{
		DrawText(FString(TEXT("SOURCE: full 3D solution  "))
				+ Runner->GetPlaybackLabel()
				+ TEXT("  (speed/steer inactive; G to cycle)"),
			AccentColor, PanelPadding, BottomY, Small, 1.0f);
	}
	else
	{
		DrawText(Runner->HasArmData()
				? TEXT("SOURCE: blended 2D gaits + 3D arms.  Steering re-aims the straight-line gait (approximation).")
				: TEXT("SOURCE: blended 2D gaits (no arms).  Steering re-aims the straight-line gait (approximation)."),
			LabelColor, PanelPadding, BottomY, Small, 1.0f);
	}
	DrawText(TEXT("W/S speed   A/D steer   H/F hills   G gait source   SPACE pause   ESC quit   RIGHT-MOUSE orbit   WHEEL zoom   R reset"),
		MutedColor, PanelPadding, BottomY + 20.0f, Small, 1.0f);
}
