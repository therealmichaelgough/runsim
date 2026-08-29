import pytest

from runsim.data import fukuchi

pytestmark = pytest.mark.skipif(
    not fukuchi.DEFAULT_ROOT.exists(), reason="fukuchi2017 dataset not downloaded"
)


def test_subjects_table():
    df = fukuchi.subjects()
    assert len(df) >= 28
    assert {"Age", "Height", "Mass", "Gender"} <= set(df.columns)


def test_processed_tidy():
    sub = fukuchi.available_subjects()[0]
    p = fukuchi.processed(sub)
    assert set(p.columns) == {"perc_cycle", "variable", "speed", "value"}
    assert set(p.speed.unique()) <= {2.5, 3.5, 4.5}
    # vertical GRF peak should be 2-3 BW (data are N/kg)
    peak_bw = p[p.variable == "RgrfY"].value.max() / 9.81
    assert 1.8 < peak_bw < 3.5


def test_forces_time_axis():
    sub = fukuchi.available_subjects()[0]
    f = fukuchi.forces(sub, 2.5)
    assert f.Time.iloc[0] == 0
    assert 25 < f.Time.iloc[-1] < 35  # ~30 s trials


def test_bad_speed_rejected():
    with pytest.raises(ValueError):
        fukuchi.forces(1, 3.0)
