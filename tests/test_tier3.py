from pathlib import Path

import pytest

from runsim.tier3 import solution_summary
from runsim.tier3.predict2d import DEFAULT_MODEL

PHASE0_GRF = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "phase0_2dwalking"
    / "gaitPrediction_solutionGRF_fullStride.sto"
)

pytestmark = pytest.mark.skipif(
    not PHASE0_GRF.exists(), reason="phase-0 walking outputs not present"
)


def test_model_available():
    assert DEFAULT_MODEL.exists()


def test_walking_summary_is_not_aerial():
    s = solution_summary(PHASE0_GRF)
    assert not s["aerial"]  # 1.2 m/s prediction is a walk: no double-flight
    assert 1.2 < s["step_freq_hz"] < 2.4
    assert 0.9 < s["peak_force_bw"] < 1.8


def test_summary_fields():
    s = solution_summary(PHASE0_GRF)
    assert {"stride_time_s", "contact_time_s", "flight_fraction", "peak_force_bw"} <= set(s)


def test_step_time_outside_bracket_rejected():
    from runsim.tier3 import predict_gait_2d

    for bad in (0.1, 0.7):  # outside the [0.18, 0.65] s step-duration bracket
        with pytest.raises(ValueError):
            predict_gait_2d(3.0, step_time_s=bad)
