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


PASSIVE_PREFIXES = ("knee_limit_", "hip_rot_limit_", "elbow_spring_", "shoulder_spring_",
                    "shoulder_damper_", "lumbar_spring_", "shoulder_add_limit_",
                    "shoulder_rot_limit_", "shoulder_flex_limit_", "elbow_limit_",
                    "ankle_limit_", "lumbar_bend_limit", "lumbar_rot_limit")


def _names(m):
    return [m.getForceSet().get(i).getName() for i in range(m.getForceSet().getSize())]


def test_forces_present_only_when_requested(model):
    plain = build_running_model(MODEL)
    assert not any(n.startswith(PASSIVE_PREFIXES) for n in _names(plain))
    added = [n for n in _names(model) if n.startswith(PASSIVE_PREFIXES)]
    # 2 knees + 2 hips + 2 elbow springs + 4 shoulder springs + 2 shoulder
    # flexion dampers + 3 lumbar springs + 6 shoulder end-range limits
    # + 2 elbow end-range limits + 2 ankle end-range limits
    # + 2 lumbar end-range limits
    assert len(added) == 27
    ankle = osim.CoordinateLimitForce.safeDownCast(model.getForceSet().get("ankle_limit_r"))
    assert ankle.get_coordinate() == "ankle_angle_r"
    assert (ankle.get_lower_limit(), ankle.get_upper_limit()) == JOINT_PASSIVES["ankle_limits_deg"]
    assert {"lumbar_spring_extension", "lumbar_spring_bending", "lumbar_spring_rotation",
            "shoulder_spring_add_r", "shoulder_spring_rot_l", "hip_rot_limit_r",
            "shoulder_add_limit_l", "shoulder_rot_limit_r", "shoulder_flex_limit_r",
            "elbow_limit_l", "lumbar_bend_limit", "lumbar_rot_limit"} <= set(added)


def test_end_range_limits_use_running_ranges(model):
    add = osim.CoordinateLimitForce.safeDownCast(model.getForceSet().get("shoulder_add_limit_r"))
    assert add.get_coordinate() == "arm_add_r"
    assert (add.get_lower_limit(), add.get_upper_limit()) == JOINT_PASSIVES["shoulder_add_limits_deg"]
    assert add.get_upper_stiffness() == JOINT_PASSIVES["range_limit_stiffness_nm_per_deg"]
    bend = osim.CoordinateLimitForce.safeDownCast(model.getForceSet().get("lumbar_bend_limit"))
    assert bend.get_coordinate() == "lumbar_bending"
    assert bend.get_upper_limit() == JOINT_PASSIVES["lumbar_bend_limit_deg"]
    assert bend.get_lower_limit() == -JOINT_PASSIVES["lumbar_bend_limit_deg"]
    flex = osim.CoordinateLimitForce.safeDownCast(model.getForceSet().get("shoulder_flex_limit_l"))
    assert flex.get_coordinate() == "arm_flex_l"
    assert (flex.get_lower_limit(), flex.get_upper_limit()) == JOINT_PASSIVES["shoulder_flex_limits_deg"]
    elbow = osim.CoordinateLimitForce.safeDownCast(model.getForceSet().get("elbow_limit_r"))
    assert elbow.get_coordinate() == "elbow_flex_r"
    assert (elbow.get_lower_limit(), elbow.get_upper_limit()) == JOINT_PASSIVES["elbow_limits_deg"]


def test_hip_rotation_limit_parameters(model):
    f = osim.CoordinateLimitForce.safeDownCast(model.getForceSet().get("hip_rot_limit_l"))
    assert f.get_coordinate() == "hip_rotation_l"
    assert f.get_upper_limit() == JOINT_PASSIVES["hip_rot_limit_deg"]
    assert f.get_lower_limit() == -JOINT_PASSIVES["hip_rot_limit_deg"]


def test_lumbar_spring_stiffness_and_damping(model):
    """2 N.m/deg toward neutral: 10 deg of extension gives -20 N.m; a
    speed of 100 deg/s at neutral gives -2 N.m of damping; rotation is
    the softer 1 N.m/deg."""
    state = model.initSystem()
    k = JOINT_PASSIVES["lumbar_stiffness_nm_per_deg"]
    coord = model.getCoordinateSet().get("lumbar_extension")
    spring = osim.ExpressionBasedCoordinateForce.safeDownCast(
        model.getForceSet().get("lumbar_spring_extension"))
    coord.setValue(state, math.radians(10.0)); coord.setSpeedValue(state, 0.0)
    model.realizeDynamics(state)
    assert spring.calcExpressionForce(state) == pytest.approx(-10.0 * k, rel=1e-3)
    coord.setValue(state, 0.0); coord.setSpeedValue(state, math.radians(100.0))
    model.realizeDynamics(state)
    assert spring.calcExpressionForce(state) == pytest.approx(
        -100.0 * JOINT_PASSIVES["lumbar_damping_nm_s_per_deg"], rel=1e-3)
    rot = osim.ExpressionBasedCoordinateForce.safeDownCast(
        model.getForceSet().get("lumbar_spring_rotation"))
    c = model.getCoordinateSet().get("lumbar_rotation")
    c.setValue(state, math.radians(10.0)); c.setSpeedValue(state, 0.0)
    model.realizeDynamics(state)
    assert rot.calcExpressionForce(state) == pytest.approx(
        -10.0 * JOINT_PASSIVES["lumbar_rot_stiffness_nm_per_deg"], rel=1e-3)


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


def test_shoulder_flexion_damper_is_pure_damping(model):
    """No spring on arm flexion (the swing is predicted), only damping:
    0.02 N.m.s/deg -> -2 N.m at 100 deg/s, zero at rest anywhere."""
    state = model.initSystem()
    coord = model.getCoordinateSet().get("arm_flex_r")
    damper = osim.ExpressionBasedCoordinateForce.safeDownCast(
        model.getForceSet().get("shoulder_damper_flex_r"))
    coord.setValue(state, math.radians(-40.0)); coord.setSpeedValue(state, 0.0)
    model.realizeDynamics(state)
    assert damper.calcExpressionForce(state) == pytest.approx(0.0, abs=1e-9)
    coord.setSpeedValue(state, math.radians(100.0))
    model.realizeDynamics(state)
    assert damper.calcExpressionForce(state) == pytest.approx(
        -100.0 * JOINT_PASSIVES["shoulder_damping_nm_s_per_deg"], rel=1e-3)
