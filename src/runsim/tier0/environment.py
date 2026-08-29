"""Environmental conditions: grade, wind, air density, running surface.

Air density from the ISA barometric formula. Surfaces carry two parameters
(Section 3 of the survey): an elastic stiffness (Kerdok et al. 2002,
J Appl Physiol 92:469 - softer *elastic* surfaces cost LESS) and a
dissipative cost multiplier (Lejeune et al. 1998 - sand costs ~1.6x because
energy is lost, not returned).
"""
from __future__ import annotations

from dataclasses import dataclass

P0_PA = 101325.0
R_AIR = 287.05


@dataclass(frozen=True)
class Surface:
    name: str
    #: vertical stiffness in kN/m; None means rigid (asphalt/concrete-like)
    stiffness_kn_m: float | None
    #: multiplier on cost of transport for non-elastic energy loss
    cost_multiplier: float = 1.0


SURFACES = {
    s.name: s
    for s in [
        Surface("asphalt", None),
        Surface("concrete", None),
        Surface("treadmill", 400.0),
        Surface("track", 250.0),
        # McMahon & Greene 1979 tuned-track optimum band
        Surface("tuned_track", 195.0),
        Surface("grass", 300.0, 1.05),
        Surface("trail", 250.0, 1.10),
        # Lejeune et al. 1998: running on dry sand ~1.6x
        Surface("sand", 100.0, 1.60),
    ]
}


@dataclass(frozen=True)
class Environment:
    """Steady-state running conditions.

    grade: rise/run (tan of slope angle); + uphill. Valid to +-0.45.
    wind_ms: wind along the running direction; + headwind, - tailwind.
    drafting: fraction of aerodynamic drag removed by drafting (0..0.8,
        Davies 1980 measured up to ~80% one metre behind another runner).
    """

    grade: float = 0.0
    wind_ms: float = 0.0
    altitude_m: float = 0.0
    temperature_c: float = 15.0
    surface: str = "asphalt"
    drafting: float = 0.0

    def __post_init__(self) -> None:
        if abs(self.grade) > 0.45:
            raise ValueError("grade outside +-0.45, beyond Minetti (2002) validity")
        if not 0.0 <= self.drafting <= 0.8:
            raise ValueError("drafting must be within 0..0.8")
        if self.surface not in SURFACES:
            raise ValueError(f"unknown surface {self.surface!r}; one of {sorted(SURFACES)}")

    @property
    def surface_props(self) -> Surface:
        return SURFACES[self.surface]

    def air_density(self) -> float:
        return air_density(self.altitude_m, self.temperature_c)


def air_density(altitude_m: float = 0.0, temperature_c: float = 15.0) -> float:
    """Air density (kg/m^3): ISA pressure at altitude, ideal gas at the given temperature."""
    pressure = P0_PA * (1.0 - 2.25577e-5 * altitude_m) ** 5.25588
    return pressure / (R_AIR * (temperature_c + 273.15))
