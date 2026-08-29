"""What-if calculator over the Tier-0 energetics engine.

Examples:
    .venv/bin/python scripts/whatif.py --speed 4.0 --grade 0.05
    .venv/bin/python scripts/whatif.py --duration 60 --wind 4 --altitude 1600
    .venv/bin/python scripts/whatif.py --distance 42.195 --vo2max 60 --economy 3.5
"""
import argparse

from runsim.tier0 import (
    Athlete,
    Environment,
    Gait,
    cost_of_transport,
    drag_force,
    metabolic_power,
    speed_for_duration,
)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--speed", type=float, help="analyze a fixed speed (m/s)")
    mode.add_argument("--duration", type=float, help="best speed for an effort (minutes)")
    mode.add_argument("--distance", type=float, help="race a distance (km)")
    ap.add_argument("--grade", type=float, default=0.0, help="rise/run, + uphill (default 0)")
    ap.add_argument("--wind", type=float, default=0.0, help="m/s, + headwind, - tailwind")
    ap.add_argument("--altitude", type=float, default=0.0, help="metres")
    ap.add_argument("--temp", type=float, default=15.0, help="deg C (affects air density)")
    ap.add_argument("--surface", default="asphalt")
    ap.add_argument("--drafting", type=float, default=0.0, help="0..0.8 drag removed")
    ap.add_argument("--cadence", type=float, default=1.0, help="step frequency vs preferred")
    ap.add_argument("--mass", type=float, default=70.0)
    ap.add_argument("--vo2max", type=float, default=50.0)
    ap.add_argument("--economy", type=float, default=3.8, help="level cost J/kg/m")
    ap.add_argument("--cs", type=float, help="critical speed m/s (with --dprime)")
    ap.add_argument("--dprime", type=float, help="D' in metres")
    return ap


def pace(v: float) -> str:
    s = round(1000 / v)
    return f"{s // 60}:{s % 60:02d}/km"


def main() -> None:
    args = build_parser().parse_args()
    athlete = Athlete(
        mass_kg=args.mass,
        vo2max_ml_kg_min=args.vo2max,
        running_economy_j_kg_m=args.economy,
        cs_ms=args.cs,
        d_prime_m=args.dprime,
    )
    env = Environment(
        grade=args.grade, wind_ms=args.wind, altitude_m=args.altitude,
        temperature_c=args.temp, surface=args.surface, drafting=args.drafting,
    )
    gait = Gait(cadence_factor=args.cadence)
    flat = Environment()

    if args.speed is not None:
        v = args.speed
        header = f"analysis at fixed speed {v:.2f} m/s ({pace(v)})"
    elif args.duration is not None:
        p = speed_for_duration(args.duration * 60, athlete, env, gait)
        v = p.speed_ms
        header = f"best speed for {args.duration:.0f} min effort [{p.detail['model']}]"
    else:
        # race a distance: iterate speed<->duration to a fixed point
        v = 3.0
        for _ in range(60):
            t = args.distance * 1000 / v
            v = speed_for_duration(t, athlete, env, gait).speed_ms
        t = args.distance * 1000 / v
        header = (f"race {args.distance:g} km -> {int(t // 3600)}h"
                  f"{int(t % 3600 // 60):02d}m{int(t % 60):02d}s")

    cost = cost_of_transport(v, athlete, env, gait)
    cost_flat = cost_of_transport(v, athlete, flat, Gait())
    power = metabolic_power(v, athlete, env, gait)
    vo2 = power * 60 / 20.9

    print(header)
    print(f"  conditions: grade {env.grade:+.1%}, wind {env.wind_ms:+.1f} m/s, "
          f"{env.altitude_m:.0f} m, {env.temperature_c:.0f} C, {env.surface}"
          + (f", drafting {env.drafting:.0%}" if env.drafting else "")
          + (f", cadence x{gait.cadence_factor}" if gait.cadence_factor != 1 else ""))
    print(f"  speed             {v:6.2f} m/s   ({pace(v)})")
    print(f"  energy cost       {cost:6.2f} J/kg/m   ({cost / cost_flat - 1:+.1%} vs flat/calm)")
    print(f"  metabolic power   {power:6.1f} W/kg   (~VO2 {vo2:.1f} ml/kg/min)")
    print(f"  aerodynamic drag  {drag_force(v, athlete, env):6.2f} N")
    print(f"  total energy      {cost * athlete.mass_kg / 4184 * 1000:6.0f} kcal per km")


if __name__ == "__main__":
    main()
