#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"

#include "RunsimHUD.generated.h"

/**
 * Canvas HUD: the simulation's interesting numbers, grouped into panels --
 *
 *   MOTION  speed, pace (min/km + min/mi), heading
 *   GAIT    state, cadence, stride length, contact time, flight fraction
 *   GROUND  grade (with a marker when the gait blend is clamped),
 *           elevation, hilliness
 *   ENERGY  live vertical GRF (BW), metabolic rate (W/kg),
 *           cost of transport (J/kg/m)
 *
 * Values are right-aligned in fixed-width panels; anything the active gait
 * blend cannot report honestly shows an em dash instead of a fake number
 * (COT/metabolic rate on the effort-objective walk gaits, everything
 * GRF-derived if the data were rebaked without the force channels).
 *
 * Drawn in AHUD::DrawHUD rather than UMG because a UMG widget is a .uasset
 * and this project ships no binary content.
 */
UCLASS()
class RUNSIMVIEWER_API ARunsimHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

private:
	/** One "LABEL ....... value" line; the value is right-aligned. */
	void DrawRow(float X, float Y, float Width, const FString& Label,
		const FString& Value, const FLinearColor& ValueColor);

	/** Panel background + title; returns the y where rows start. */
	float BeginPanel(float X, float Y, float Width, int32 NumRows,
		const FString& Title);

	static FString FormatPace(float SpeedMps, float DistanceMeters = 1000.0f);

	static constexpr float PanelPadding = 18.0f;
	static constexpr float PanelWidth = 235.0f;
	static constexpr float RowHeight = 19.0f;
	static constexpr float TitleHeight = 24.0f;
	static constexpr float PanelGap = 10.0f;
	static constexpr float InnerPad = 10.0f;
};
