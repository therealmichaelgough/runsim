"""Energy cost of running under environmental and gait conditions.

Components and sources:
- Slope: Minetti et al. 2002 (J Appl Physiol 93:1039) 5th-order polynomial,
  treadmill, validated for gradients within +-0.45.
- Aerodynamic drag: F = 1/2 rho v_rel^2 Cd Ap (Pugh 1970/1971, Davies 1980),
  converted to metabolic cost at +6.13% per 1% body weight of horizontal
  impeding force (Da Silva et al. 2022). Tailwind assistance is treated
  symmetrically (a simplification; measured benefit is somewhat smaller
  than the headwind penalty).
- Elastic surface stiffness: Kerdok et al. 2002 - a 12.5x decrease in
  surface stiffness lowered metabolic rate ~12% with mechanics conserved;
  modeled log-linearly between the study's stiffness bounds.
- Dissipative surfaces (sand, trail): direct cost multiplier.
- Cadence deviation: quadratic penalty (see gait.py).

All costs are J per kg body mass per metre travelled along the slope.
"""
from __future__ import annotations

import math

from runsim.tier0.athlete import Athlete
from runsim.tier0.environment import Environment
from runsim.tier0.gait import Gait

G = 9.81

#: metabolic cost increase per unit of horizontal force / body weight
#: (Da Silva 2022: +6.13% per 1% BW)
HORIZONTAL_FORCE_COST_GAIN = 6.13

#: Kerdok 2002 study bounds and effect size
_KERDOK_K_HARD = 945.7  # kN/m
_KERDOK_K_SOFT = 75.4
_KERDOK_SAVING = 0.12


def minetti_running_cost(grade: float) -> float:
    """Energy cost of running (J/kg/m) vs grade i (rise/run), Minetti 2002."""
    i = grade
    return 155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3 + 46.3 * i**2 + 19.5 * i + 3.6


def surface_factor(env: Environment) -> float:
    """Multiplier on cost from the running surface (elastic + dissipative)."""
    s = env.surface_props
    factor = s.cost_multiplier
    if s.stiffness_kn_m is not None:
        k = min(max(s.stiffness_kn_m, _KERDOK_K_SOFT), _KERDOK_K_HARD)
        saving = _KERDOK_SAVING * math.log(_KERDOK_K_HARD / k) / math.log(
            _KERDOK_K_HARD / _KERDOK_K_SOFT
        )
        factor *= 1.0 - saving
    return factor


def drag_force(speed_ms: float, athlete: Athlete, env: Environment) -> float:
    """Net aerodynamic drag (N) at running speed; signed (+ opposes motion)."""
    v_rel = speed_ms + env.wind_ms  # + headwind adds to relative air speed
    force = 0.5 * env.air_density() * athlete.drag_coefficient * athlete.frontal_area_m2
    force *= v_rel * abs(v_rel)  # signed square: tailwind faster than run -> assist
    return force * (1.0 - env.drafting)


def cost_of_transport(
    speed_ms: float,
    athlete: Athlete = Athlete(),
    env: Environment = Environment(),
    gait: Gait = Gait(),
) -> float:
    """Total energy cost of running (J/kg/m) under the given conditions."""
    base = minetti_running_cost(env.grade) * athlete.economy_factor
    base *= surface_factor(env)
    base *= gait.cost_multiplier
    aero = HORIZONTAL_FORCE_COST_GAIN * drag_force(speed_ms, athlete, env) / (
        athlete.mass_kg * G
    )
    return base * (1.0 + aero)


def metabolic_power(
    speed_ms: float,
    athlete: Athlete = Athlete(),
    env: Environment = Environment(),
    gait: Gait = Gait(),
) -> float:
    """Metabolic power (W/kg) to run at the given speed under the conditions."""
    return cost_of_transport(speed_ms, athlete, env, gait) * speed_ms
