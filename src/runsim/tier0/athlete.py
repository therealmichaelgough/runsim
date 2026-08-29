"""Athlete parameters: anthropometrics, aerobic capacity, drag area.

Projected frontal area from body surface area (Livingston & Lee formula;
A_p = 0.266 * BSA per Pugh 1970). Drag coefficient ~0.8 (Pugh 1970; range
0.73-0.91 across studies). VO2 -> power at ~20.9 J per ml O2.
"""
from __future__ import annotations

from dataclasses import dataclass

J_PER_ML_O2 = 20.9
#: baseline level-running cost the Minetti polynomial passes through at grade 0
MINETTI_LEVEL_COST = 3.6


@dataclass(frozen=True)
class Athlete:
    mass_kg: float = 70.0
    height_m: float = 1.75
    #: level-ground energy cost of running, J/kg/m (running economy).
    #: 3.6 = the Minetti treadmill cohort; trained runners ~3.3-3.8, elite ~3.0-3.3.
    running_economy_j_kg_m: float = 3.8
    #: maximal aerobic capacity; None disables VO2-based predictions
    vo2max_ml_kg_min: float | None = 50.0
    #: critical speed (m/s) and D' (m) for the speed-duration model; optional
    cs_ms: float | None = None
    d_prime_m: float | None = None
    drag_coefficient: float = 0.8
    #: override projected frontal area; None derives it from mass
    projected_area_m2: float | None = None

    @property
    def economy_factor(self) -> float:
        """Scale on the Minetti cost curve so grade 0 matches this athlete's economy."""
        return self.running_economy_j_kg_m / MINETTI_LEVEL_COST

    @property
    def frontal_area_m2(self) -> float:
        if self.projected_area_m2 is not None:
            return self.projected_area_m2
        bsa = 0.1173 * self.mass_kg**0.6466  # Livingston & Lee
        return 0.266 * bsa

    def aerobic_power_w_kg(self, fraction_of_vo2max: float = 1.0) -> float:
        """Metabolic power (W/kg) at a fraction of VO2max."""
        if self.vo2max_ml_kg_min is None:
            raise ValueError("athlete has no vo2max set")
        return self.vo2max_ml_kg_min * fraction_of_vo2max * J_PER_ML_O2 / 60.0
