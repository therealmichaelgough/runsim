"""The predictive 3D problem's objective terms, assembled without solving."""
from pathlib import Path

import pytest

osim = pytest.importorskip("opensim")

from runsim.tier3.model3d import RUNNING_ACTUATOR_STRENGTH  # noqa: E402
from runsim.tier3.predict3d import build_running_study, gait_label  # noqa: E402

MODEL = Path(__file__).resolve().parents[1] / "models" / "LaiUhlrich2022" / "LaiUhlrich2022.osim"
pytestmark = pytest.mark.skipif(not MODEL.exists(), reason="LaiUhlrich2022 model not present")


def _goals(problem):
    """{name: goal object} via the generic property accessor (the Moco
    bindings do not wrap MocoPhase's typed goal-list accessors)."""
    prop = problem.getPhase(0).getPropertyByName("goals")
    return {prop.getValueAsObject(i).getName(): prop.getValueAsObject(i)
            for i in range(prop.size())}


def _goal_names(problem):
    return list(_goals(problem))


def test_label_convention():
    assert gait_label(3.0, 0.0, "metabolic") == "p3d_v3_gp0_met"
    assert gait_label(2.5, -0.05, "effort") == "p3d_v2_5_gm0_05"


def test_metabolic_problem_prices_only_the_requested_actuators(tmp_path):
    study, model, label = build_running_study(
        3.0, out_dir=tmp_path, model_path=MODEL, objective="metabolic",
        torque_weight=5.0, actuator_strength=RUNNING_ACTUATOR_STRENGTH,
        torque_power_weight=0.01, torque_power_actuators=("lumbar",))
    names = _goal_names(study.getProblem())
    assert label == "p3d_v3_gp0_met"
    assert {"periodicity", "speed", "met", "effort"} <= set(names)
    power = sorted(n for n in names if n.startswith("power_"))
    assert power == ["power_lumbar_bend", "power_lumbar_ext", "power_lumbar_rot"]
    goal = osim.MocoOutputGoal.safeDownCast(_goals(study.getProblem())["power_lumbar_ext"])
    assert goal.getOutputPath() == "/forceset/lumbar_ext|power"
    assert goal.getExponent() == 2
    assert goal.getWeight() == pytest.approx(0.01)
    # the metabolics component is attached and the actuators strengthened
    assert model.hasComponent("metabolic_cost")
    lumbar = osim.CoordinateActuator.safeDownCast(model.getForceSet().get("lumbar_ext"))
    assert lumbar.getOptimalForce() == 200.0


def test_torque_price_scales_control_weights_with_capacity(tmp_path):
    """0.006 per (N.m)^2: a 200 N.m actuator gets weight 240, a 10 N.m one 0.6."""
    study, _, _ = build_running_study(
        3.0, out_dir=tmp_path, model_path=MODEL, objective="metabolic",
        actuator_strength=RUNNING_ACTUATOR_STRENGTH, torque_price_per_nm2=0.006)
    effort = osim.MocoControlGoal.safeDownCast(_goals(study.getProblem())["effort"])
    # the bindings expose neither getter; go through the generic property
    weights = osim.MocoWeightSet.safeDownCast(
        effort.getPropertyByName("control_weights").getValueAsObject(0))

    def weight(path):
        return weights.get(path).getWeight()

    assert weight("/forceset/lumbar_ext") == pytest.approx(0.006 * 200 ** 2)
    assert weight("/forceset/shoulder_flex_r") == pytest.approx(0.006 * 60 ** 2)
    assert weight("/forceset/pro_sup_l") == pytest.approx(0.006 * 10 ** 2)


def test_all_thirteen_actuators_priced_when_no_subset_given(tmp_path):
    study, _, _ = build_running_study(
        3.0, out_dir=tmp_path, model_path=MODEL, objective="metabolic",
        torque_power_weight=0.01)
    names = _goal_names(study.getProblem())
    assert sum(n.startswith("power_") for n in names) == 13


def test_effort_problem_has_no_metabolic_terms(tmp_path):
    study, model, label = build_running_study(3.0, out_dir=tmp_path, model_path=MODEL)
    names = _goal_names(study.getProblem())
    assert "met" not in names and not any(n.startswith("power_") for n in names)
    assert label == "p3d_v3_gp0"
    assert not model.hasComponent("metabolic_cost")
