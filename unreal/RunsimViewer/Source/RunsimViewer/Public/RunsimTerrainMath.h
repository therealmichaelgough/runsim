#pragma once

#include "CoreMinimal.h"

/**
 * The one and only definition of the ground.
 *
 * A 2D analytic heightfield h(x, y): a few octaves of deterministic value
 * noise composed into minimalist trail-running country -- rolling hills, an
 * undulating ridgeline to the north, a meandering valley meadow to the
 * south.  Both ARunsimTerrain (which builds the visible chunk meshes) and
 * ARunsimRunner (which reads the grade along its heading to pick a gait
 * blend and to tilt the body) include this header, so the drawn ground and
 * the gait the runner is using can never disagree.
 *
 * Everything here is in *simulation* units: x, y and height in metres, grade
 * dimensionless (the directional derivative dh/ds, i.e. tan of the slope
 * angle along a heading -- the same convention as the exported gait
 * metadata, where grade = tan(3 deg) etc).  x, y are the Unreal world X, Y
 * divided by UnitsPerMetre; height maps to world Z the same way.
 *
 * Hilliness in [0, 1] scales the whole relief: 0 is a perfectly flat plane
 * (the M2 cadence check), 1 is the full landscape with slopes up to ~40%.
 * The default 0.45 keeps most running within the solved gait-grade range
 * (+-16%); the blend clamps itself beyond that while the body still tilts.
 */
namespace RunsimTerrain
{
	/** Unreal units (cm) per simulation metre. */
	static constexpr float UnitsPerMetre = 100.0f;

	/** Central-difference step for slopes (m). Small vs the 23 m finest
	 *  noise wavelength, so the numeric grade tracks the analytic surface. */
	static constexpr float SlopeEpsM = 0.6f;

	/** Deterministic integer lattice hash -> [0, 1). Plain integer mixing:
	 *  identical on every platform, no trig, no global state. */
	FORCEINLINE float Hash01(int32 X, int32 Y)
	{
		uint32 H = static_cast<uint32>(X) * 374761393u
			+ static_cast<uint32>(Y) * 668265263u;
		H = (H ^ (H >> 13)) * 1274126177u;
		H ^= (H >> 16);
		return static_cast<float>(H) * (1.0f / 4294967296.0f);
	}

	/** Value noise in ~[-1, 1] with a quintic fade (C2 across cells). */
	FORCEINLINE float ValueNoise(float X, float Y)
	{
		const float FX = FMath::FloorToFloat(X);
		const float FY = FMath::FloorToFloat(Y);
		const int32 IX = static_cast<int32>(FX);
		const int32 IY = static_cast<int32>(FY);
		const float TX = X - FX;
		const float TY = Y - FY;
		const float UX = TX * TX * TX * (TX * (TX * 6.0f - 15.0f) + 10.0f);
		const float UY = TY * TY * TY * (TY * (TY * 6.0f - 15.0f) + 10.0f);
		const float A = Hash01(IX, IY);
		const float B = Hash01(IX + 1, IY);
		const float C = Hash01(IX, IY + 1);
		const float D = Hash01(IX + 1, IY + 1);
		return 2.0f * FMath::Lerp(FMath::Lerp(A, B, UX), FMath::Lerp(C, D, UX), UY)
			- 1.0f;
	}

	/** Fractional Brownian motion, ~[-1, 1]; per-octave offsets decorrelate
	 *  the lattices. */
	FORCEINLINE float Fbm(float X, float Y, int32 Octaves)
	{
		float Sum = 0.0f;
		float Amp = 0.5f;
		float Freq = 1.0f;
		float Norm = 0.0f;
		for (int32 i = 0; i < Octaves; ++i)
		{
			Sum += Amp * ValueNoise(X * Freq + 17.31f * i, Y * Freq - 11.07f * i);
			Norm += Amp;
			Amp *= 0.5f;
			Freq *= 2.02f;
		}
		return Sum / Norm;
	}

	/**
	 * The landscape at full relief (Hilliness = 1), in metres.
	 *
	 *  - rolling hills everywhere: 4-octave FBM, ~150 m wavelength, +-9 m;
	 *  - a ridgeline running east-west near y = +240 m, crest wandering
	 *    +-55 m, up to ~+24 m above the hills, crest height modulated so it
	 *    reads as a chain of summits rather than a wall;
	 *  - a valley floor meandering near y = -170 m: the hills are flattened
	 *    toward a -7 m meadow (flatter running, the "easy" route);
	 *  - fine 23 m detail everywhere except the meadow floor.
	 */
	FORCEINLINE float ReliefM(float X, float Y)
	{
		float H = 9.0f * Fbm(X / 150.0f, Y / 150.0f, 4);

		const float RidgeLine = 240.0f + 55.0f * FMath::Sin(X / 210.0f);
		const float DR = (Y - RidgeLine) / 95.0f;
		const float RidgeMask = FMath::Exp(-DR * DR);
		H += 24.0f * RidgeMask * (0.70f + 0.30f * Fbm(X / 55.0f, 3.7f, 2));

		const float ValleyLine = -170.0f + 65.0f * FMath::Sin(X / 260.0f + 1.7f);
		const float DV = (Y - ValleyLine) / 120.0f;
		const float Meadow = FMath::Exp(-DV * DV);
		H = FMath::Lerp(H, -7.0f, 0.80f * Meadow);

		H += 1.1f * (1.0f - 0.8f * Meadow) * Fbm(X / 23.0f, Y / 23.0f, 2);
		return H;
	}

	/** Ground height in metres at (x, y) metres, for a hilliness in [0, 1]. */
	FORCEINLINE float HeightM(float XMetres, float YMetres, float Hilliness)
	{
		return Hilliness * ReliefM(XMetres, YMetres);
	}

	/**
	 * Directional slope dh/ds along a heading (radians, 0 = +X, pi/2 = +Y),
	 * i.e. tan of the slope angle the runner experiences -- the "grade" fed
	 * to the gait blend.  Central difference of the same HeightM the meshes
	 * are built from.
	 */
	FORCEINLINE float GradeAlong(float XMetres, float YMetres,
		float HeadingRad, float Hilliness)
	{
		const float C = FMath::Cos(HeadingRad);
		const float S = FMath::Sin(HeadingRad);
		return (HeightM(XMetres + C * SlopeEpsM, YMetres + S * SlopeEpsM, Hilliness)
			- HeightM(XMetres - C * SlopeEpsM, YMetres - S * SlopeEpsM, Hilliness))
			/ (2.0f * SlopeEpsM);
	}

	/** Unit surface normal in Unreal world axes (z up). */
	FORCEINLINE FVector NormalAt(float XMetres, float YMetres, float Hilliness)
	{
		const float DX = (HeightM(XMetres + SlopeEpsM, YMetres, Hilliness)
			- HeightM(XMetres - SlopeEpsM, YMetres, Hilliness)) / (2.0f * SlopeEpsM);
		const float DY = (HeightM(XMetres, YMetres + SlopeEpsM, Hilliness)
			- HeightM(XMetres, YMetres - SlopeEpsM, Hilliness)) / (2.0f * SlopeEpsM);
		return FVector(-DX, -DY, 1.0f).GetSafeNormal();
	}

	/** Ground point in Unreal world space (cm). */
	FORCEINLINE FVector GroundLocation(float XMetres, float YMetres, float Hilliness)
	{
		return FVector(XMetres * UnitsPerMetre, YMetres * UnitsPerMetre,
			HeightM(XMetres, YMetres, Hilliness) * UnitsPerMetre);
	}
}
