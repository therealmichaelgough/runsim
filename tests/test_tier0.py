import math

import pytest

from runsim.tier0 import (
    Athlete,
    Environment,
    Gait,
    air_density,
    cost_of_transport,
    drag_force,
    metabolic_power,
    minetti_running_cost,
    speed_at_power,
    speed_for_duration,
)


class TestMinetti:
    def test_level_baseline(self):
        assert minetti_running_cost(0.0) == pytest.approx(3.6)

    def test_uphill_expensive_downhill_cheap(self):
        assert minetti_running_cost(0.10) > minetti_running_cost(0.0)
        assert minetti_running_cost(-0.10) < minetti_running_cost(0.0)

    def test_published_shape(self):
        # cost minimum sits slightly downhill; steep downhill rises again
        grades = [g / 100 for g in range(-45, 46)]
        gmin = min(grades, key=minetti_running_cost)
        assert -0.25 < gmin < -0.05
        assert minetti_running_cost(-0.45) > minetti_running_cost(gmin)

    def test_ten_percent_uphill_magnitude(self):
        # Minetti 2002: ~+50-60% cost at +10% grade
        ratio = minetti_running_cost(0.10) / minetti_running_cost(0.0)
        assert 1.4 < ratio < 1.7

    def test_validity_bounds_enforced(self):
        with pytest.raises(ValueError):
            Environment(grade=0.5)


class TestAir:
    def test_sea_level_density(self):
        assert air_density(0, 15) == pytest.approx(1.225, rel=0.01)

    def test_altitude_thins_air(self):
        assert air_density(2200, 15) < 0.8 * air_density(0, 15) + 0.2

    def test_heat_thins_air(self):
        assert air_density(0, 35) < air_density(0, 5)


class TestDrag:
    def test_still_air_share_of_cost(self):
        # Davies 1980: drag ~2-8% of total energy in still air at distance speeds
        a, e = Athlete(), Environment()
        v = 5.0
        share = (cost_of_transport(v, a, e) - cost_of_transport(v, a, e) /
                 (1 + 6.13 * drag_force(v, a, e) / (a.mass_kg * 9.81))) / cost_of_transport(v, a, e)
        assert 0.02 < share < 0.08

    def test_headwind_hurts_tailwind_helps(self):
        a = Athlete()
        head = cost_of_transport(5.0, a, Environment(wind_ms=+3.0))
        tail = cost_of_transport(5.0, a, Environment(wind_ms=-3.0))
        still = cost_of_transport(5.0, a, Environment())
        assert head > still > tail

    def test_drafting_reduces_drag(self):
        a = Athlete()
        assert drag_force(5, a, Environment(drafting=0.8)) == pytest.approx(
            0.2 * drag_force(5, a, Environment()), rel=1e-9
        )

    def test_altitude_reduces_drag_cost(self):
        a = Athlete()
        assert cost_of_transport(5, a, Environment(altitude_m=2200)) < cost_of_transport(5, a, Environment())


class TestSurface:
    def test_softer_elastic_surface_cheaper(self):
        base = cost_of_transport(4, env=Environment(surface="asphalt"))
        track = cost_of_transport(4, env=Environment(surface="tuned_track"))
        assert track < base
        # Kerdok effect bounded at ~12%
        assert track > 0.85 * base

    def test_sand_expensive(self):
        ratio = cost_of_transport(3, env=Environment(surface="sand")) / cost_of_transport(
            3, env=Environment(surface="asphalt")
        )
        assert 1.4 < ratio < 1.7


class TestGait:
    def test_preferred_cadence_optimal(self):
        assert Gait(1.0).cost_multiplier == 1.0
        assert Gait(1.1).cost_multiplier > 1.0
        assert Gait(0.9).cost_multiplier > 1.0

    def test_magnitude(self):
        assert Gait(1.2).cost_multiplier == pytest.approx(1.06, abs=0.02)


class TestSolve:
    def test_roundtrip(self):
        a = Athlete()
        p = speed_at_power(metabolic_power(4.0, a), a)
        assert p.speed_ms == pytest.approx(4.0, abs=1e-6)

    def test_uphill_slower_at_same_power(self):
        a = Athlete()
        flat = speed_at_power(15.0, a, Environment())
        hill = speed_at_power(15.0, a, Environment(grade=0.05))
        assert hill.speed_ms < flat.speed_ms

    def test_elite_marathon_plausible(self):
        # Joyner-style elite: VO2max 75, economy 3.2
        elite = Athlete(mass_kg=60, vo2max_ml_kg_min=75, running_economy_j_kg_m=3.2)
        p = speed_for_duration(2.1 * 3600, elite)
        marathon_h = 42195 / p.speed_ms / 3600
        assert 1.9 < marathon_h < 2.4

    def test_recreational_marathon_plausible(self):
        rec = Athlete(mass_kg=75, vo2max_ml_kg_min=50, running_economy_j_kg_m=3.9)
        p = speed_for_duration(4 * 3600, rec)
        marathon_h = 42195 / p.speed_ms / 3600
        assert 3.2 < marathon_h < 5.0

    def test_critical_speed_model(self):
        a = Athlete(cs_ms=4.0, d_prime_m=200)
        p10 = speed_for_duration(600, a)
        p60 = speed_for_duration(3600, a)
        assert p10.speed_ms > p60.speed_ms > 3.9

    def test_headwind_slows_race_pace(self):
        a = Athlete(vo2max_ml_kg_min=60)
        still = speed_for_duration(3600, a)
        wind = speed_for_duration(3600, a, Environment(wind_ms=5.0))
        assert wind.speed_ms < still.speed_ms


class TestAltitude:
    def test_marathon_slower_at_altitude(self):
        a = Athlete(vo2max_ml_kg_min=60, running_economy_j_kg_m=3.5, mass_kg=65)
        sea = speed_for_duration(2.6 * 3600, a)
        alt = speed_for_duration(2.6 * 3600, a, Environment(altitude_m=1600))
        assert alt.speed_ms < sea.speed_ms
        # net penalty a few percent at 1600 m (hypoxia beats thin-air drag gain)
        assert 0.90 < alt.speed_ms / sea.speed_ms < 0.99

    def test_sprint_would_benefit_from_thin_air(self):
        # at fixed metabolic power (no ceiling), thinner air -> faster
        a = Athlete()
        sea = speed_at_power(25, a, Environment())
        alt = speed_at_power(25, a, Environment(altitude_m=2200))
        assert alt.speed_ms > sea.speed_ms
