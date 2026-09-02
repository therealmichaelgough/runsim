"""Pin the arm-swing angular-momentum validation (Hamner & Delp 2013,
J Biomech 46(4):780-787): during running at ~3 m/s the arms' vertical-axis
angular momentum about the whole-body COM counter-rotates against the
legs' and cancels most of it.

The quantitative pins run on the *measured* reference (Hamner subject01
RRA cycle-1 states retargeted onto the LaiUhlrich model), so they gate on
the git-ignored dataset being present. The per-body momentum computation
itself is cross-checked against SimTK's calcSystemCentralMomentum at
every frame inside analyze_arm_momentum.angular_momentum_y (assert).
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "analyze_arm_momentum.py"

spec = importlib.util.spec_from_file_location("analyze_arm_momentum", SCRIPT)
aam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aam)

needs_data = pytest.mark.skipif(
    not (aam.RRA_CYCLE.exists() and aam.MODEL.exists()),
    reason="hamner2013 RRA states or lai_running_model.osim not present",
)


@pytest.fixture(scope="module")
def reference_metrics():
    import opensim as osim

    model = osim.Model(str(aam.MODEL))
    model.initSystem()
    # decimate=80 -> ~99 frames, enough for the cycle-level metrics
    return aam.analyze(model, aam.RRA_CYCLE, "rra", decimate=80)


@needs_data
def test_arms_counter_rotate_legs(reference_metrics):
    """Arms and legs must carry opposite-signed vertical angular momentum
    (strong anticorrelation over the cycle), per Hamner & Delp 2013."""
    assert reference_metrics["corr_arms_legs"] < -0.9


@needs_data
def test_arms_cancel_most_of_leg_momentum(reference_metrics):
    """The arms' amplitude is comparable to the legs' and cancels the
    majority of it: peak-to-peak of (arms+legs) is well under half the
    legs' own peak-to-peak."""
    assert 0.7 < reference_metrics["arms_over_legs"] < 1.5
    assert reference_metrics["uncancelled"] < 0.5
