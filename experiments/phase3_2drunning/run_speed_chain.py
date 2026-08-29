"""Chain predictive solves across speeds, seeding each from the previous
solution (speed homotopy). Produces the walk->run progression and the
running solutions for validation."""
import json
import subprocess
import sys
import time
from pathlib import Path

from runsim.tier3 import predict_gait_2d, solution_summary

HERE = Path(__file__).resolve().parent
SPEEDS = [1.2, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
SEED = HERE / "seed_tracking.sto"
#: pass a solution forward as the next guess when its objective is sane,
#: even if IPOPT hit max iterations (near-converged trajectories seed well)
MAX_SANE_OBJECTIVE = 50.0


def main() -> None:
    if not SEED.exists():
        print("generating tracking seed...", flush=True)
        subprocess.run([sys.executable, str(HERE / "make_seed.py")], check=True)

    guess = SEED
    log = []
    for v in SPEEDS:
        t0 = time.time()
        r = predict_gait_2d(v, out_dir=HERE, guess_path=guess)
        stats = solution_summary(r.grf_path)
        stats.update(speed=v, success=r.success, objective=r.objective,
                     solve_min=round(r.solve_time_s / 60, 2))
        log.append(stats)
        print(json.dumps(stats), flush=True)
        (HERE / "chain_log.json").write_text(json.dumps(log, indent=2))
        if r.objective < MAX_SANE_OBJECTIVE:
            guess = r.solution_path  # seed the next speed
        print(f"[{v} m/s done in {(time.time() - t0) / 60:.1f} min]", flush=True)


if __name__ == "__main__":
    main()
