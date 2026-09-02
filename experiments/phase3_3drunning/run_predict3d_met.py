"""3D predictive running with the metabolic objective at 3.0 m/s,
seeded from the converged effort solution (never cold-start). The 2D
experience: the metabolic objective improves cadence and peak-force
realism and its COT is comparable against Tier-0/Minetti.

Usage: run_predict3d_met.py [max_iterations]
"""
import json
import sys
import time
from pathlib import Path

from runsim.tier3 import solution_summary
from runsim.tier3.predict3d import predict_gait_3d

HERE = Path(__file__).resolve().parent
SEED = HERE / "solution_p3d_v3_gp0.sto"
LOG = HERE / "predict3d_met_log.json"
MASS = 75.16


def main(max_iterations: int = 2000) -> None:
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    t0 = time.time()
    r = predict_gait_3d(3.0, out_dir=HERE, guess_path=SEED,
                        max_iterations=max_iterations, objective="metabolic")
    stats = solution_summary(r.grf_path, mass_kg=MASS)
    stats.update(speed=3.0, grade=0.0, success=r.success,
                 objective=r.objective, cost_of_transport=r.cost_of_transport,
                 solution=r.solution_path.name,
                 solve_min=round(r.solve_time_s / 60, 2))
    log.append(stats)
    print(json.dumps(stats), flush=True)
    LOG.write_text(json.dumps(log, indent=2))
    print(f"[3.0 m/s metabolic done in {(time.time() - t0) / 60:.1f} min]", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
