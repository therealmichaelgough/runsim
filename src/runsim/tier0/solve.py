"""Invert the cost model: what speed is achievable?

Two athlete parameterizations:
- VO2max + endurance curve: sustainable %VO2max falls roughly linearly in
  log-duration (~94% at 10 min, ~85% at 60 min - Joyner 1991 framing).
- Critical speed + D': flat-equivalent speed v(t) = CS + D'/t, converted to
  the given conditions at equal metabolic power (the grade-adjusted-pace
  equivalence).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from runsim.tier0.athlete import Athlete
from runsim.tier0.energetics import cost_of_transport, drag_force, metabolic_power
from runsim.tier0.environment import Environment
from runsim.tier0.gait import Gait

_V_LO, _V_HI = 0.3, 13.0


@dataclass(frozen=True)
class Prediction:
    speed_ms: float
    power_w_kg: float
    cost_j_kg_m: float
    drag_n: float
    detail: dict = field(default_factory=dict)

    @property
    def pace_s_per_km(self) -> float:
        return 1000.0 / self.speed_ms

    @property
    def pace_str(self) -> str:
        s = round(self.pace_s_per_km)
        return f"{s // 60}:{s % 60:02d}/km"


def speed_at_power(
    power_w_kg: float,
    athlete: Athlete = Athlete(),
    env: Environment = Environment(),
    gait: Gait = Gait(),
) -> Prediction:
    """Speed at which metabolic power equals the budget (bisection; power is
    monotone in speed over the modeled range)."""
    lo, hi = _V_LO, _V_HI
    if metabolic_power(hi, athlete, env, gait) < power_w_kg:
        raise ValueError("power budget exceeds model range (>13 m/s)")
    if metabolic_power(lo, athlete, env, gait) > power_w_kg:
        raise ValueError("power budget below walking range")
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if metabolic_power(mid, athlete, env, gait) < power_w_kg:
            lo = mid
        else:
            hi = mid
    v = 0.5 * (lo + hi)
    return Prediction(
        speed_ms=v,
        power_w_kg=metabolic_power(v, athlete, env, gait),
        cost_j_kg_m=cost_of_transport(v, athlete, env, gait),
        drag_n=drag_force(v, athlete, env),
    )


def sustainable_fraction(duration_s: float) -> float:
    """Sustainable %VO2max vs duration: 0.94 at 10 min, ~ -0.116/decade of time."""
    frac = 0.94 - 0.1157 * math.log10(max(duration_s, 60.0) / 600.0)
    return min(1.0, max(0.5, frac))


def hypoxic_vo2max_factor(altitude_m: float) -> float:
    """VO2max derating with altitude: ~ -6.3% per 1000 m above 300 m
    (Wehrlin & Hallen 2006, trained/acclimatized). Altitude therefore has two
    opposing effects here: thinner air lowers drag, hypoxia lowers the
    aerobic ceiling - the ceiling loss dominates for distance running."""
    return max(0.6, 1.0 - 0.063 * max(0.0, altitude_m - 300.0) / 1000.0)


def speed_for_duration(
    duration_s: float,
    athlete: Athlete = Athlete(),
    env: Environment = Environment(),
    gait: Gait = Gait(),
) -> Prediction:
    """Best sustainable speed for an effort of the given duration."""
    if athlete.cs_ms is not None and athlete.d_prime_m is not None:
        # CS/D' assumed measured near sea level; derate like an aerobic ceiling
        v_flat = athlete.cs_ms + athlete.d_prime_m / duration_s
        target_power = metabolic_power(v_flat, athlete, Environment(), Gait())
        target_power *= hypoxic_vo2max_factor(env.altitude_m)
        model = "critical_speed"
    else:
        frac = sustainable_fraction(duration_s)
        target_power = athlete.aerobic_power_w_kg(frac)
        target_power *= hypoxic_vo2max_factor(env.altitude_m)
        model = f"vo2max@{frac:.0%}"
    pred = speed_at_power(target_power, athlete, env, gait)
    pred.detail.update(model=model, duration_s=duration_s)
    return pred
