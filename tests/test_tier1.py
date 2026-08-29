import numpy as np
import pytest

from runsim.tier0 import Athlete, Environment, Gait
from runsim.tier1 import grf_waveform, predict_stride


class TestStride:
    def test_timing_matches_fukuchi_fits(self):
        # medians extracted from the dataset: 272/226/195 ms at 2.5/3.5/4.5
        for speed, tc_ms in [(2.5, 272), (3.5, 226), (4.5, 195)]:
            s = predict_stride(speed)
            assert s.contact_time_s * 1000 == pytest.approx(tc_ms, abs=12)

    def test_faster_means_shorter_contact_higher_cadence(self):
        s3, s5 = predict_stride(3.0), predict_stride(5.0)
        assert s5.contact_time_s < s3.contact_time_s
        assert s5.step_freq_hz > s3.step_freq_hz

    def test_peak_force_range(self):
        # Fukuchi measured 2.4-2.8 BW over 2.5-4.5 m/s
        for speed, fmax in [(2.5, 2.40), (3.5, 2.64), (4.5, 2.81)]:
            assert predict_stride(speed).peak_force_bw == pytest.approx(fmax, abs=0.35)

    def test_leg_stiffness_literature_range(self):
        # human running k_leg typically ~7-16 kN/m
        for speed in (2.5, 3.5, 4.5):
            assert 7 < predict_stride(speed).k_leg_kn_m < 16

    def test_soft_elastic_surface_stiffens_leg(self):
        hard = predict_stride(3.5, env=Environment(surface="asphalt"))
        soft = predict_stride(3.5, env=Environment(surface="tuned_track"))
        assert soft.k_leg_kn_m > hard.k_leg_kn_m

    def test_higher_cadence_shortens_step(self):
        base = predict_stride(3.5)
        quick = predict_stride(3.5, gait=Gait(cadence_factor=1.1))
        assert quick.step_length_m < base.step_length_m
        assert quick.peak_force_bw < base.peak_force_bw  # more, gentler steps

    def test_speed_bounds(self):
        with pytest.raises(ValueError):
            predict_stride(10.0)


class TestGRF:
    def test_impulse_closure(self):
        # average vertical force over the full stride must equal body weight
        a = Athlete()
        s = predict_stride(3.5, a)
        w = grf_waveform(s, a)
        impulse = np.trapezoid(w.vertical_n, w.time_s)
        expected = a.mass_kg * 9.81 * (s.contact_time_s + s.flight_time_s)
        assert impulse == pytest.approx(expected, rel=0.01)

    def test_peak_close_to_morin_prediction(self):
        a = Athlete()
        s = predict_stride(3.5, a)
        w = grf_waveform(s, a)
        assert w.vertical_n.max() / (a.mass_kg * 9.81) == pytest.approx(
            s.peak_force_bw, rel=0.2
        )

    def test_rearfoot_has_impact_transient_forefoot_not(self):
        a = Athlete()
        s = predict_stride(4.0, a)
        rear = grf_waveform(s, a, Gait(foot_strike="rearfoot"))
        fore = grf_waveform(s, a, Gait(foot_strike="forefoot"))
        assert rear.impact_peak_n is not None
        assert fore.impact_peak_n is None
        assert rear.loading_rate_bw_s > fore.loading_rate_bw_s

    def test_fore_aft_net_impulse_zero(self):
        s = predict_stride(3.5)
        w = grf_waveform(s)
        assert abs(np.trapezoid(w.fore_aft_n, w.time_s)) < 1.0

    def test_braking_peak_scales_with_speed(self):
        a = Athlete()
        b3 = -grf_waveform(predict_stride(2.5, a), a).fore_aft_n.min()
        b5 = -grf_waveform(predict_stride(4.5, a), a).fore_aft_n.min()
        assert b5 > b3
