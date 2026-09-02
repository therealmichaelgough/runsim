import pytest

from runsim.data import vanhooren

pytestmark = pytest.mark.skipif(
    not vanhooren.DEFAULT_ROOT.exists(), reason="vanhooren2024 dataset not downloaded"
)


def test_available_products():
    df = vanhooren.available()
    counts = df.groupby("product").size()
    # 19 subjects x 12 loader conditions, minus a few missing trials
    assert counts["time_normalized"] >= 200
    assert counts["tissue_loading"] >= 180
    assert set(df.subject.unique()) == set(range(1, 20))
    assert set(df.condition.unique()) <= set(vanhooren.CONDITIONS)


def test_time_normalized_grf():
    grf = vanhooren.time_normalized(1, "3ms", "GRF")
    assert len(grf) == 100  # 0-99 % gait cycle
    assert grf.index.name == "perc_cycle"
    # vertical GRF peak in Newtons: ~2.3-2.9 BW for an adult runner at 3 m/s
    assert 1000 < grf.L_ground_force_vy.max() < 3000


def test_variables_listed():
    names = vanhooren.variables(1, "3ms")
    assert {"GRF", "IK", "ID", "JRA"} <= set(names)


def test_tissue_loading():
    tl = vanhooren.tissue_loading(1, "3ms")
    assert "time" in tl.columns
    assert "Patellofemoral_Stress_r" in tl.columns
    assert len(tl) > 1000  # continuous per-sample trace, not gait-normalized


def test_scaled_model_paths():
    assert vanhooren.scaled_model_path(1).exists()
    assert vanhooren.scaled_model_path(1, doubled_strength=True).exists()


def test_bad_condition_rejected():
    with pytest.raises(ValueError):
        vanhooren.time_normalized(1, "9ms", "GRF")
