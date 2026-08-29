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


HAMNER_RRA = (
    Path(__file__).resolve().parents[1]
    / "data" / "raw" / "hamner2013" / "subject01" / "rra_multipleSteps"
    / "RRA_Results_v191_Run_30002" / "RRA_Results_v191_Run_30002_cycle1"
    / "subject01_Run_30002_cycle1_states.sto"
)
LAI_MODEL = Path(__file__).resolve().parents[1] / "models" / "LaiUhlrich2022" / "LaiUhlrich2022.osim"


@pytest.mark.skipif(not HAMNER_RRA.exists(), reason="hamner2013 data not downloaded")
def test_retarget_hamner_to_lai():
    import numpy as np

    from runsim.tier3.model3d import build_running_model
    from runsim.tier3.retarget import retarget_states

    model = build_running_model(LAI_MODEL)
    model.initSystem()
    table = retarget_states(HAMNER_RRA, model, decimate=50)
    labels = list(table.getColumnLabels())
    # every non-beta coordinate mapped, with value+speed columns
    assert len(labels) == 66
    assert not any("beta" in lab or "wrist" in lab for lab in labels)
    # Rajagopal knee convention: flexion positive, physiological running range
    knee = table.getDependentColumn("/jointset/walker_knee_r/knee_angle_r/value").to_numpy()
    assert 0 < np.degrees(knee.max()) < 140
    assert np.degrees(knee.min()) > -15


def test_running_model_has_contacts():
    from runsim.tier3.model3d import CONTACT_FORCES_LEFT, CONTACT_FORCES_RIGHT, build_running_model

    model = build_running_model(LAI_MODEL)
    model.initSystem()
    force_names = {model.getForceSet().get(i).getName()
                   for i in range(model.getForceSet().getSize())}
    assert set(CONTACT_FORCES_RIGHT + CONTACT_FORCES_LEFT) <= force_names
    assert model.getMuscles().get(0).getConcreteClassName() == "DeGrooteFregly2016Muscle"
