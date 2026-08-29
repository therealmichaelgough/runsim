"""Tier 0: closed-form running energetics.

Analytic what-if engine: given an athlete, an environment (grade, wind,
altitude, temperature, surface), and gait tweaks, compute energy cost of
transport, metabolic power, and achievable speed. Runs in microseconds;
validated component-by-component against the literature (see module
docstrings for citations).
"""
from runsim.tier0.athlete import Athlete
from runsim.tier0.energetics import cost_of_transport, drag_force, metabolic_power, minetti_running_cost
from runsim.tier0.environment import SURFACES, Environment, Surface, air_density
from runsim.tier0.gait import Gait
from runsim.tier0.solve import Prediction, speed_at_power, speed_for_duration

__all__ = [
    "Athlete",
    "Environment",
    "Surface",
    "SURFACES",
    "Gait",
    "air_density",
    "minetti_running_cost",
    "cost_of_transport",
    "drag_force",
    "metabolic_power",
    "speed_at_power",
    "speed_for_duration",
    "Prediction",
]
