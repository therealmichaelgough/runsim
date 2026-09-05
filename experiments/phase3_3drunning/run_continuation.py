"""Continuation from an effort gait to the metabolic objective.

Runs run_met_legs.main once per stage with a cubed-control effort term
kept in the metabolic problem at decreasing weights (effort_blend), each
stage warm-started from the previous stage's last banked leg. The v6
formulation flags are fixed here; the schedule is the argument.

Usage: run_continuation.py <start.sto> [--blends=10,3,1,0.3,0]
         [--stage-legs=3] [--leg-iters=150] [--torque-weight=50]
         [--power=0.01] [--power-on=lumbar] [--torque-price=0.006]
Banked files: met_blend<w>_legNN.sto (+ .strength.json sidecars);
the last stage (blend 0) is the pure metabolic problem.
"""
import sys
from pathlib import Path

from run_met_legs import main as run_legs

HERE = Path(__file__).resolve().parent


def flag(flags: set[str], name: str, default: str) -> str:
    return next((a.split("=", 1)[1] for a in flags if a.startswith(f"--{name}=")), default)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        raise SystemExit(__doc__)
    start = Path(args[0]) if Path(args[0]).is_absolute() else HERE / args[0]
    blends = [float(b) for b in flag(flags, "blends", "10,3,1,0.3,0").split(",")]
    stage_legs = int(flag(flags, "stage-legs", "3"))
    leg_iters = int(flag(flags, "leg-iters", "150"))
    torque_weight = float(flag(flags, "torque-weight", "50"))
    power = float(flag(flags, "power", "0.01"))
    power_on = tuple(flag(flags, "power-on", "lumbar").split(","))
    torque_price = float(flag(flags, "torque-price", "0.006"))

    current = start
    for w in blends:
        tag = f"blend{w:g}".replace(".", "_")
        print(f"\n===== continuation stage effort_blend={w:g} from {current.name} =====", flush=True)
        banked = run_legs(str(current), leg_iters, stage_legs, torque_weight, 50,
                          passive_forces=True, actuator_strength=True,
                          torque_power_weight=power, torque_power_actuators=power_on,
                          joint_passives=True, torque_price_per_nm2=torque_price,
                          effort_blend=(w if w > 0 else None), objective="metabolic",
                          tag=tag)
        if banked is None:
            print(f"[stage effort_blend={w:g} banked nothing - stopping the continuation]", flush=True)
            return
        current = banked
    print(f"[continuation complete - final iterate {current.name}]", flush=True)


if __name__ == "__main__":
    main()
