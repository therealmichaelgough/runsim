#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"

#include "RunsimHUD.generated.h"

/**
 * Canvas HUD: speed, pace, grade, cadence, COT, gait label.
 *
 * Drawn in AHUD::DrawHUD rather than UMG because a UMG widget is a .uasset
 * and this project ships no binary content.  Metric rules match
 * docs/run_viewer.html, including hiding COT whenever any contributing
 * solution lacks one (the effort-objective walk gaits).
 */
UCLASS()
class RUNSIMVIEWER_API ARunsimHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

private:
	void DrawMetric(float X, float Y, float Width, const FString& Label,
		const FString& Value, const FLinearColor& ValueColor);

	static FString FormatPace(float SpeedMps);

	static constexpr float PanelPadding = 18.0f;
	static constexpr float MetricWidth = 132.0f;
	static constexpr float MetricHeight = 52.0f;
	static constexpr float MetricGap = 8.0f;
};
