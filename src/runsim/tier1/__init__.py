"""Tier 1: spring-mass / two-mass running mechanics surrogate.

From (speed, athlete, environment, gait) to contact/flight times, leg and
vertical stiffness, and full ground-reaction-force waveforms - in
milliseconds, with timing regressions fitted to the Fukuchi 2017 dataset.
"""
from runsim.tier1.grf import GRFWaveform, grf_waveform
from runsim.tier1.stride import (
    StrideMechanics,
    contact_length_m,
    predict_stride,
    self_selected_step_freq,
)

__all__ = [
    "StrideMechanics",
    "predict_stride",
    "self_selected_step_freq",
    "contact_length_m",
    "GRFWaveform",
    "grf_waveform",
]
