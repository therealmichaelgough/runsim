#include "RunsimHUD.h"

#include "RunsimPawn.h"
#include "RunsimRunner.h"
#include "RunsimViewer.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"

namespace
{
	const FLinearColor PanelColor(0.04f, 0.08f, 0.14f, 0.78f);
	const FLinearColor LabelColor(0.43f, 0.53f, 0.65f, 1.0f);
	const FLinearColor ValueColor(0.92f, 0.95f, 0.99f, 1.0f);
	const FLinearColor AccentColor(0.39f, 0.85f, 0.78f, 1.0f);
	const FLinearColor MutedColor(0.32f, 0.40f, 0.50f, 1.0f);
}

FString ARunsimHUD::FormatPace(float SpeedMps)
{
	if (SpeedMps <= 0.05f)
	{
		return TEXT("--:--");
	}
	const float SecondsPerKm = 1000.0f / SpeedMps;
	const int32 Minutes = FMath::FloorToInt(SecondsPerKm / 60.0f);
	const int32 Seconds = FMath::RoundToInt(SecondsPerKm - Minutes * 60.0f);
	// Guard the 59.6 -> "60" rounding case.
	return (Seconds >= 60)
		? FString::Printf(TEXT("%d:00"), Minutes + 1)
		: FString::Printf(TEXT("%d:%02d"), Minutes, Seconds);
}

void ARunsimHUD::DrawMetric(float X, float Y, float Width, const FString& Label,
	const FString& Value, const FLinearColor& InValueColor)
{
	DrawRect(PanelColor, X, Y, Width, MetricHeight);
	UFont* Small = GEngine ? GEngine->GetSmallFont() : nullptr;
	UFont* Large = GEngine ? GEngine->GetLargeFont() : nullptr;
	DrawText(Label, LabelColor, X + 9.0f, Y + 6.0f, Small, 1.0f);
	DrawText(Value, InValueColor, X + 9.0f, Y + 22.0f, Large, 1.15f);
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
		DrawText(TEXT("No gait data loaded."), FLinearColor(1.0f, 0.55f, 0.4f, 1.0f),
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

	float X = PanelPadding;
	const float Y = PanelPadding;

	DrawMetric(X, Y, MetricWidth, TEXT("SPEED  M/S"),
		FString::Printf(TEXT("%.1f"), Speed), ValueColor);
	X += MetricWidth + MetricGap;

	DrawMetric(X, Y, MetricWidth, TEXT("PACE  MIN/KM"),
		FormatPace(Speed), ValueColor);
	X += MetricWidth + MetricGap;

	DrawMetric(X, Y, MetricWidth, TEXT("GRADE"),
		FString::Printf(TEXT("%s%.1f%%"), GradePercent >= 0.0f ? TEXT("+") : TEXT(""),
			GradePercent), ValueColor);
	X += MetricWidth + MetricGap;

	DrawMetric(X, Y, MetricWidth + 40.0f, TEXT("CADENCE  SPM"),
		FString::Printf(TEXT("%d  (%.2f Hz)"), FMath::RoundToInt(StepsPerMinute),
			CadenceHz), ValueColor);
	X += MetricWidth + 40.0f + MetricGap;

	// COT is hidden whenever a contributing solution has none -- that is the
	// effort-objective walk gaits, whose objective is not metabolic cost.
	DrawMetric(X, Y, MetricWidth, TEXT("COT"),
		Runner->HasCot() ? FString::Printf(TEXT("%.2f"), Runner->GetCot())
			: FString(TEXT("--")),
		Runner->HasCot() ? ValueColor : MutedColor);
	X += MetricWidth + MetricGap;

	DrawMetric(X, Y, MetricWidth, TEXT("GAIT"),
		bWalking ? FString(TEXT("WALK")) : FString(TEXT("RUN")), AccentColor);

	// Provenance + controls, bottom left.
	const float BottomY = FMath::Max(120.0f, static_cast<float>(Canvas->SizeY) - 76.0f);
	DrawText(Runner->HasArmData()
			? TEXT("Moco solutions | 3D-sourced gaits (arms live)")
			: TEXT("Moco solutions | 2D-sourced gaits, metabolic objective (no arms)"),
		LabelColor, PanelPadding, BottomY, Small, 1.0f);
	DrawText(FString(TEXT("W/S or UP/DOWN speed   H/F hills   SPACE pause   "))
			+ TEXT("RIGHT-MOUSE orbit   WHEEL zoom   R reset view"),
		MutedColor, PanelPadding, BottomY + 20.0f, Small, 1.0f);

	if (Runner->IsPaused())
	{
		DrawText(TEXT("PAUSED"), AccentColor, PanelPadding, BottomY - 24.0f,
			Small, 1.2f);
	}
}
