"""Two-mass ground reaction force waveforms (Clark, Ryan & Weyand 2017).

Total vertical GRF is the sum of two raised-cosine bells:
- F1: the impact transient - the lower limb (m1 ~ 8% of body mass) arrested
  at touchdown. Short and early for rearfoot strikes; longer and merged
  into the body curve for forefoot strikes.
- F2: the rest of the body (m2 = 92%) over the whole contact.

Impulse closure: the vertical impulse over one step equals m g / f (body
weight supported over the step), so J2 = m g t_step - J1.

Fore-aft force is modeled as a single sine (braking then propulsion) with
speed-scaled amplitude - adequate for net-impulse and loading-rate work,
not for detailed propulsion mechanics.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from runsim.tier0 import Athlete, Gait
from runsim.tier1.stride import G, StrideMechanics

#: distal mass fraction (foot + shank), Clark 2017
M1_FRACTION = 0.08

#: impact-bell duration as a fraction of contact time, and distal-limb
#: touchdown speed added on top of the COM's, by strike pattern
STRIKE_PARAMS = {
    "rearfoot": {"t1_frac": 0.25, "extra_td_ms": 1.0},
    "midfoot": {"t1_frac": 0.375, "extra_td_ms": 0.5},
    "forefoot": {"t1_frac": 0.50, "extra_td_ms": 0.2},
}


@dataclass(frozen=True)
class GRFWaveform:
    time_s: np.ndarray  # 0..contact_time
    vertical_n: np.ndarray
    fore_aft_n: np.ndarray  # - braking, + propulsion
    impact_peak_n: float | None
    loading_rate_bw_s: float  # peak dF/dt in the first 20-80% of rise, BW/s


def _bell(t: np.ndarray, start: float, width: float, impulse: float) -> np.ndarray:
    """Raised-cosine bump of the given impulse on [start, start+width]."""
    x = (t - start) / width
    inside = (x >= 0) & (x <= 1)
    amp = 2.0 * impulse / width
    out = np.zeros_like(t)
    out[inside] = amp * 0.5 * (1.0 - np.cos(2.0 * np.pi * x[inside]))
    return out


def grf_waveform(
    stride: StrideMechanics,
    athlete: Athlete = Athlete(),
    gait: Gait = Gait(),
    n: int = 300,
) -> GRFWaveform:
    m = athlete.mass_kg
    t_c, t_f = stride.contact_time_s, stride.flight_time_s
    t = np.linspace(0.0, t_c, n)
    p = STRIKE_PARAMS[gait.foot_strike]

    # impact bell: arrest the distal limb falling with the COM + strike extra
    v_td = G * t_f / 2.0 + p["extra_td_ms"]
    j1 = M1_FRACTION * m * v_td
    t1_width = p["t1_frac"] * t_c
    f1 = _bell(t, 0.0, t1_width, j1)

    # body curve: half-sine over the whole contact (the Morin/McMahon shape)
    # carrying the remaining step impulse
    j_total = m * G * (t_c + t_f)
    j2 = j_total - j1
    f2 = (np.pi * j2 / (2.0 * t_c)) * np.sin(np.pi * t / t_c)

    fz = f1 + f2
    dfdt = np.gradient(fz, t)
    i_peak = int(np.argmax(fz))
    loading_rate = float(dfdt[: max(i_peak, 2)].max()) / (m * G)

    # impact transient: present when the impact bell is a substantial bump
    # (at speed it can merge into a shoulder rather than a local maximum)
    impact = None
    if f1.max() > 0.3 * m * G:
        k = int(np.argmax(f1))
        impact = float(fz[k])

    # fore-aft: braking then propulsion, ~0.08 BW amplitude per m/s of speed
    a_ap = 0.08 * stride.speed_ms * m * G
    fap = -a_ap * np.sin(2.0 * np.pi * t / t_c)

    return GRFWaveform(
        time_s=t,
        vertical_n=fz,
        fore_aft_n=fap,
        impact_peak_n=impact,
        loading_rate_bw_s=loading_rate,
    )
