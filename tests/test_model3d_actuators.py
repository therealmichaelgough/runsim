"""Running-model options: torque-actuator strengths and passive forces."""
from pathlib import Path

import pytest

osim = pytest.importorskip("opensim")

from runsim.tier3.model3d import (  # noqa: E402
    RUNNING_ACTUATOR_STRENGTH, build_running_model, set_actuator_strength,
)

MODEL = Path(__file__).resolve().parents[1] / "models" / "LaiUhlrich2022" / "LaiUhlrich2022.osim"
pytestmark = pytest.mark.skipif(not MODEL.exists(), reason="LaiUhlrich2022 model not present")


def _actuators(model):
    fs = model.getForceSet()
    out = {}
    for i in range(fs.getSize()):
        act = osim.CoordinateActuator.safeDownCast(fs.get(i))
        if act is not None:
            out[act.getName()] = act.getOptimalForce()
    return out


def test_stock_model_ships_10_newton_metre_placeholders():
    model = build_running_model(MODEL)
    strengths = _actuators(model)
    assert len(strengths) == 13
    assert set(strengths.values()) == {10.0}


def test_running_strengths_are_applied_by_prefix():
    model = build_running_model(MODEL, actuator_strength=RUNNING_ACTUATOR_STRENGTH)
    strengths = _actuators(model)
    # literature-order capacities from the RUNNING_ACTUATOR_STRENGTH docstring
    assert strengths["lumbar_ext"] == 200.0
    assert strengths["lumbar_bend"] == 150.0
    assert strengths["shoulder_flex_r"] == strengths["shoulder_flex_l"] == 60.0
    assert strengths["elbow_flex_r"] == 40.0
    assert strengths["pro_sup_l"] == 10.0
    assert all(v > 10.0 for k, v in strengths.items() if not k.startswith("pro_sup"))


def test_set_actuator_strength_reports_what_it_changed():
    model = build_running_model(MODEL)
    applied = set_actuator_strength(model, {"elbow_flex": 40.0})
    assert applied == {"elbow_flex_r": 40.0, "elbow_flex_l": 40.0}
    assert _actuators(model)["lumbar_ext"] == 10.0


def test_passive_forces_flag_controls_the_dgf_property():
    def first_muscle(model):
        for comp in model.getComponentsList():
            m = osim.DeGrooteFregly2016Muscle.safeDownCast(comp)
            if m is not None:
                return m
        raise AssertionError("no DGF muscle")

    assert first_muscle(build_running_model(MODEL)).get_ignore_passive_fiber_force() is True
    assert first_muscle(build_running_model(MODEL, passive_forces=True)).get_ignore_passive_fiber_force() is False
