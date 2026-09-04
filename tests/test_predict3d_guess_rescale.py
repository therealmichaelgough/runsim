"""Guess torque-control rescaling across actuator-strength changes.

A control u under an actuator of F_guess N.m is a torque u*F_guess; under
F_model it must become u*F_guess/F_model. The guess's strengths come from
its `.strength.json` sidecar (stock 10 N.m when there is none). Chained
legs must NOT be rescaled again — that shrank production torques 4-20x
at every restart before the sidecar existed (2026-09-04).
"""
import json
from pathlib import Path

import pytest

osim = pytest.importorskip("opensim")

from runsim.tier3.model3d import RUNNING_ACTUATOR_STRENGTH, build_running_model  # noqa: E402
from runsim.tier3.predict3d import (  # noqa: E402
    STOCK_ACTUATOR_STRENGTH, actuator_strengths, guess_strengths, strength_sidecar,
    torque_scale_factors,
)

MODEL = Path(__file__).resolve().parents[1] / "models" / "LaiUhlrich2022" / "LaiUhlrich2022.osim"
pytestmark = pytest.mark.skipif(not MODEL.exists(), reason="LaiUhlrich2022 model not present")


@pytest.fixture(scope="module")
def strong():
    return build_running_model(MODEL, actuator_strength=RUNNING_ACTUATOR_STRENGTH)


@pytest.fixture(scope="module")
def stock():
    return build_running_model(MODEL)


def test_sidecar_naming_and_reading(tmp_path):
    sol = tmp_path / "solution_x.sto"
    assert strength_sidecar(sol) == tmp_path / "solution_x.strength.json"
    assert guess_strengths(sol) is None
    strength_sidecar(sol).write_text(json.dumps({"lumbar_ext": 200.0}))
    assert guess_strengths(sol) == {"lumbar_ext": 200.0}


def test_stock_guess_into_strong_model_scales_down(strong):
    factors = torque_scale_factors(strong, None)
    assert factors["/forceset/lumbar_ext"] == pytest.approx(STOCK_ACTUATOR_STRENGTH / 200.0)
    assert factors["/forceset/elbow_flex_r"] == pytest.approx(STOCK_ACTUATOR_STRENGTH / 40.0)
    assert "/forceset/pro_sup_r" not in factors  # 10 -> 10: unchanged


def test_strong_guess_into_strong_model_is_identity(strong):
    assert torque_scale_factors(strong, actuator_strengths(strong)) == {}


def test_strong_guess_into_stock_model_scales_up(stock, strong):
    factors = torque_scale_factors(stock, actuator_strengths(strong))
    assert factors["/forceset/lumbar_bend"] == pytest.approx(150.0 / STOCK_ACTUATOR_STRENGTH)


def test_actuator_strengths_reports_all_thirteen(strong):
    s = actuator_strengths(strong)
    assert len(s) == 13 and s["shoulder_rot_l"] == 30.0
