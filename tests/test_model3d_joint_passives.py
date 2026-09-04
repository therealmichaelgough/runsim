"""Knee limit forces and elbow posture springs (model3d.add_joint_passives)."""
import math
from pathlib import Path

import pytest

osim = pytest.importorskip("opensim")

from runsim.tier3.model3d import JOINT_PASSIVES, build_running_model  # noqa: E402

MODEL = Path(__file__).resolve().parents[1] / "models" / "LaiUhlrich2022" / "LaiUhlrich2022.osim"
pytestmark = pytest.mark.skipif(not MODEL.exists(), reason="LaiUhlrich2022 model not present")


@pytest.fixture(scope="module")
def model():
    m = build_running_model(MODEL, joint_passives=True)
    m.initSystem()
    return m


def test_forces_present_only_when_requested():
    plain = build_running_model(MODEL)
    names = [plain.getForceSet().get(i).getName() for i in range(plain.getForceSet().getSize())]
    assert not any(n.startswith(("knee_limit_", "elbow_spring_")) for n in names)


def test_knee_limit_parameters(model):
    f = osim.CoordinateLimitForce.safeDownCast(model.getForceSet().get("knee_limit_r"))
    assert f is not None
    assert f.get_coordinate() == "knee_angle_r"
    assert f.get_lower_limit() == JOINT_PASSIVES["knee_lower_deg"]
    assert f.get_upper_limit() == JOINT_PASSIVES["knee_upper_deg"]
    assert f.get_lower_stiffness() == JOINT_PASSIVES["knee_stiffness_nm_per_deg"]
    assert f.get_transition() == JOINT_PASSIVES["knee_transition_deg"]


def test_elbow_spring_restores_toward_rest_angle(model):
    """At 50 deg away from the 100-deg rest angle the spring gives ~2.5 N.m
    toward it (0.05 N.m/deg); at the rest angle it is zero."""
    state = model.initSystem()
    coord = model.getCoordinateSet().get("elbow_flex_r")
    spring = osim.ExpressionBasedCoordinateForce.safeDownCast(
        model.getForceSet().get("elbow_spring_r"))
    assert spring is not None and spring.get_coordinate() == "elbow_flex_r"

    def torque_at(deg):
        coord.setValue(state, math.radians(deg))
        coord.setSpeedValue(state, 0.0)
        model.realizeDynamics(state)
        return spring.calcExpressionForce(state)

    assert torque_at(JOINT_PASSIVES["elbow_rest_deg"]) == pytest.approx(0.0, abs=1e-5)  # 6-decimal q0 in the expression
    expected = JOINT_PASSIVES["elbow_stiffness_nm_per_deg"] * 50.0
    assert torque_at(50.0) == pytest.approx(expected, rel=1e-3)     # flexing torque
    assert torque_at(150.0) == pytest.approx(-expected, rel=1e-3)   # extending torque
