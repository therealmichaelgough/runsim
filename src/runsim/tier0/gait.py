"""Gait deviations from self-selected form.

Self-selected step frequency sits very close to the metabolic optimum
(Cavanagh & Williams 1982; Snyder & Farley 2011, J Exp Biol 214:2089).
Deviations cost energy roughly quadratically; the curvature here gives
~+1.5% at a 10% deviation and ~+6% at 20%, consistent with the range
reported across level/incline studies.
"""
from __future__ import annotations

from dataclasses import dataclass

CADENCE_CURVATURE = 1.5


FOOT_STRIKES = ("rearfoot", "midfoot", "forefoot")


@dataclass(frozen=True)
class Gait:
    #: step frequency relative to self-selected (1.0 = preferred)
    cadence_factor: float = 1.0
    #: strike pattern; shapes the impact transient in Tier-1 GRF waveforms
    foot_strike: str = "rearfoot"

    def __post_init__(self) -> None:
        if not 0.7 <= self.cadence_factor <= 1.3:
            raise ValueError("cadence_factor outside modeled range 0.7-1.3")
        if self.foot_strike not in FOOT_STRIKES:
            raise ValueError(f"foot_strike must be one of {FOOT_STRIKES}")

    @property
    def cost_multiplier(self) -> float:
        return 1.0 + CADENCE_CURVATURE * (self.cadence_factor - 1.0) ** 2
