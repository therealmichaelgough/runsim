"""Cheap parallel screen of IPOPT barrier/scaling settings for the 3D
metabolic solve (run several of these at once, one per configuration).

Each run lives in its own directory (experiments/phase3_3drunning/screen/
<name>/) so its ipopt.opt — read by IPOPT from the current working
directory at solver start — and its Moco stop sentinel are private.
The solve is a capped metabolic leg from the bound-pinned leg-1 iterate,
so barrier pathologies show up immediately rather than at iteration 200.

Usage: screen_barrier.py <name> <torque_weight> <max_iters> [key=value ...]
    e.g. screen_barrier.py adaptive 50 80 mu_strategy=adaptive
Writes <run>/result.json and prints it; the solution stays in <run>/ for
use as the production start point.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MASS = 75.16


def main(name: str, torque_weight: float, max_iters: int, opts: list[str],
         start: str = "met_leg01.sto") -> None:
    run = HERE / "screen" / name
    run.mkdir(parents=True, exist_ok=True)
    pairs = [o.split("=", 1) for o in opts]
    (run / "ipopt.opt").write_text(
        "".join(f"{k} {v}\n" for k, v in pairs) + "print_user_options yes\n")
    os.chdir(run)  # IPOPT reads ./ipopt.opt; Moco drops its sentinel here

    from runsim.tier3 import solution_summary
    from runsim.tier3.predict3d import predict_gait_3d

    r = predict_gait_3d(3.0, out_dir=run, guess_path=HERE / start,
                        max_iterations=max_iters, objective="metabolic",
                        torque_weight=torque_weight, label=f"screen_{name}")
    stats = solution_summary(r.grf_path, mass_kg=MASS)
    stats.update(name=name, torque_weight=torque_weight, start=start,
                 ipopt=dict(pairs), objective=r.objective, success=r.success,
                 cost_of_transport=r.cost_of_transport,
                 solution=r.solution_path.name,
                 solve_min=round(r.solve_time_s / 60, 2))
    (run / "result.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats), flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], float(a[1]), int(a[2]), a[3:])
