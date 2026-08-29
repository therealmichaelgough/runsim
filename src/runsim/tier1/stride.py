"""Spring-mass stride mechanics from speed, cadence, and surface.

Timing comes from regressions fitted to the Fukuchi 2017 treadmill data
(params.json, scripts/fit_tier1_params.py): contact length L_c = a + b*v
(Weyand 2000 framing) and self-selected step frequency f = c + d*v.

Spring-mass quantities use the Morin et al. 2005 sine-wave method:
    F_max = m g (pi/2) (t_f / t_c + 1)
    dy    = F_max t_c^2 / (m pi^2) - g t_c^2 / 8
    k_vert = F_max / dy
    k_leg  = F_max / dL,  dL = L0 - sqrt(L0^2 - (v t_c / 2)^2) + dy

Elastic surfaces: runners adjust leg stiffness so the series combination of
leg and surface stays at the hard-surface value (Ferris, Louie & Farley
1998); k_leg_surface solves 1/k_leg_hard = 1/k_leg_surface + 1/k_surface.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from runsim.tier0 import Athlete, Environment, Gait

G = 9.81
_PARAMS = json.loads((Path(__file__).parent / "params.json").read_text())
#: leg length as a fraction of stature (Winter's anthropometry)
LEG_LENGTH_STATURE = 0.53


@dataclass(frozen=True)
class StrideMechanics:
    speed_ms: float
    contact_time_s: float
    flight_time_s: float
    step_freq_hz: float
    duty_factor: float
    peak_force_bw: float
    com_drop_m: float
    k_vert_kn_m: float
    k_leg_kn_m: float
    leg_compression_m: float

    @property
    def step_length_m(self) -> float:
        return self.speed_ms / self.step_freq_hz


def self_selected_step_freq(speed_ms: float) -> float:
    p = _PARAMS["step_freq_hz"]
    return p["intercept"] + p["slope_per_ms"] * speed_ms


def contact_length_m(speed_ms: float) -> float:
    p = _PARAMS["contact_length_m"]
    return p["intercept"] + p["slope_per_ms"] * speed_ms


def predict_stride(
    speed_ms: float,
    athlete: Athlete = Athlete(),
    env: Environment = Environment(),
    gait: Gait = Gait(),
) -> StrideMechanics:
    if not 1.5 <= speed_ms <= 7.0:
        raise ValueError("speed outside fitted range 1.5-7 m/s")

    # contact time is set by contact length over the foot (geometry, Weyand
    # 2000) and barely changes with cadence; flight time absorbs the change,
    # so higher cadence -> shorter flights -> lower peak force
    f = self_selected_step_freq(speed_ms) * gait.cadence_factor
    t_step = 1.0 / f
    t_c = contact_length_m(speed_ms) / speed_ms
    t_f = t_step - t_c
    if t_f <= 0.0:
        raise ValueError("cadence too high for aerial running at this speed")
    duty = t_c / t_step

    m = athlete.mass_kg
    f_max = m * G * (math.pi / 2.0) * (t_f / t_c + 1.0)
    dy = f_max * t_c**2 / (m * math.pi**2) - G * t_c**2 / 8.0

    l0 = LEG_LENGTH_STATURE * athlete.height_m
    half_sweep = min(speed_ms * t_c / 2.0, 0.95 * l0)
    dl = l0 - math.sqrt(l0**2 - half_sweep**2) + dy
    k_leg = f_max / dl

    # Ferris: total stiffness conserved on elastic surfaces -> leg stiffens
    k_surf = env.surface_props.stiffness_kn_m
    if k_surf is not None:
        k_surf_n_m = k_surf * 1000.0
        if k_surf_n_m > 1.05 * k_leg:
            k_leg = 1.0 / (1.0 / k_leg - 1.0 / k_surf_n_m)

    return StrideMechanics(
        speed_ms=speed_ms,
        contact_time_s=t_c,
        flight_time_s=t_f,
        step_freq_hz=f,
        duty_factor=duty,
        peak_force_bw=f_max / (m * G),
        com_drop_m=dy,
        k_vert_kn_m=(f_max / dy) / 1000.0,
        k_leg_kn_m=k_leg / 1000.0,
        leg_compression_m=dl,
    )
