"""Leg 0 of the segmented metabolic solve, with banking.

Faithful reproduction of the run that reached obj 2.330: 3.0 m/s
metabolic objective, default barrier, 1100-iteration cap, seeded from
the converged effort solution. Banks the result as met_leg00.sto (the
first attempt's iterate was overwritten by a later leg — never again)
and prints a marker the monitor keys on.

Usage: run_met_leg0.py [max_iterations]
"""
import json
import shutil
import sys
import time
from pathlib import Path

from runsim.tier3 import solution_summary
from runsim.tier3.predict3d import predict_gait_3d

HERE = Path(__file__).resolve().parent
SEED = HERE / "solution_p3d_v3_gp0.sto"
LOG = HERE / "predict3d_met_log.json"
BANK = HERE / "met_leg00.sto"
MASS = 75.16


def main(max_iterations: int = 1100) -> None:
    t0 = time.time()
    r = predict_gait_3d(3.0, out_dir=HERE, guess_path=SEED,
                        max_iterations=max_iterations, objective="metabolic")
    shutil.copyfile(r.solution_path, BANK)
    stats = solution_summary(r.grf_path, mass_kg=MASS)
    stats.update(speed=3.0, grade=0.0, leg=0, success=r.success,
                 objective=r.objective, cost_of_transport=r.cost_of_transport,
                 solution=r.solution_path.name, banked=BANK.name,
                 solve_min=round(r.solve_time_s / 60, 2))
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    log.append(stats)
    LOG.write_text(json.dumps(log, indent=2))
    print(json.dumps(stats), flush=True)
    print(f"[leg00 banked] {BANK.name} obj={r.objective:.4f} "
          f"in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1100)
