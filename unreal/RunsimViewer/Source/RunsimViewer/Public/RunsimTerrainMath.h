#pragma once

#include "CoreMinimal.h"

/**
 * The one and only definition of the ground.
 *
 * Ported verbatim from the sum-of-sines terrain in docs/run_viewer.html
 * (functions terrainH / terrainG).  Both ARunsimTerrain (which builds the
 * visible ribbon) and ARunsimRunner (which reads the grade to pick a gait
 * blend and to pitch the runner) include this header, so the drawn ground and
 * the gait the runner is using can never disagree.
 *
 * Everything here is in *simulation* units: x and height in metres, grade
 * dimensionless (dz/dx, i.e. tan of the slope angle -- the same convention as
 * the exported gait metadata, where grade = tan(3 deg) etc).  Convert to
 * Unreal units with RunsimTerrain::UnitsPerMetre at the last moment.
 */
namespace RunsimTerrain
{
	/** Unreal units (cm) per simulation metre. */
	static constexpr float UnitsPerMetre = 100.0f;

	/** Amplitudes (m) and wavelengths (m) of the three terrain harmonics. */
	static constexpr float A0 = 1.9f, L0 = 24.0f, P0 = 0.0f;
	static constexpr float A1 = 1.1f, L1 = 9.7f, P1 = 1.3f;
	static constexpr float A2 = 0.5f, L2 = 4.9f, P2 = 4.1f;

	/** Ground height in metres at x metres, for a hilliness in [0, 1]. */
	FORCEINLINE float HeightM(float XMetres, float Hilliness)
	{
		return Hilliness * (A0 * FMath::Sin(XMetres / L0 + P0)
			+ A1 * FMath::Sin(XMetres / L1 + P1)
			+ A2 * FMath::Sin(XMetres / L2 + P2));
	}

	/** Analytic dz/dx at x metres -- no line traces needed. */
	FORCEINLINE float GradeAt(float XMetres, float Hilliness)
	{
		return Hilliness * (A0 / L0 * FMath::Cos(XMetres / L0 + P0)
			+ A1 / L1 * FMath::Cos(XMetres / L1 + P1)
			+ A2 / L2 * FMath::Cos(XMetres / L2 + P2));
	}

	/**
	 * Local slope as an Unreal pitch, in degrees.
	 *
	 * Unreal's positive pitch tips the forward axis (+X) up towards +Z, which
	 * is exactly the sign of atan(dz/dx); the exporter's rotation conversion
	 * is pinned to the same convention by
	 * tests/test_ue_export.py::test_sagittal_flexion_becomes_positive_unreal_pitch.
	 */
	FORCEINLINE float PitchDegrees(float XMetres, float Hilliness)
	{
		return FMath::RadiansToDegrees(FMath::Atan(GradeAt(XMetres, Hilliness)));
	}

	/** Ground point in Unreal world space (cm) on the centre line. */
	FORCEINLINE FVector GroundLocation(float XMetres, float Hilliness)
	{
		return FVector(XMetres * UnitsPerMetre, 0.0f,
			HeightM(XMetres, Hilliness) * UnitsPerMetre);
	}
}
