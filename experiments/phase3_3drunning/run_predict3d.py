"""First predictive 3D running solve (Phase-3 finale, milestone 1):
3.0 m/s on the flat, effort objective, seeded from the validated
tracking solution (never cold-start). Resumable via predict3d_log.json.

Usage: run_predict3d.py [max_iterations]
"""
import json
import sys
import time
from pathlib import Path

from runsim.tier1 import predict_stride  # noqa: F401  (import check)
from runsim.tier3 import solution_summary
from runsim.tier3.predict3d import predict_gait_3d

HERE = Path(__file__).resolve().parent
SEED = HERE / "seed3d_tracking.sto"
LOG = HERE / "predict3d_log.json"
MASS = 75.16


def main(max_iterations: int = 3000) -> None:
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    t0 = time.time()
    r = predict_gait_3d(3.0, out_dir=HERE, guess_path=SEED,
                        max_iterations=max_iterations)
    stats = solution_summary(r.grf_path, mass_kg=MASS)
    stats.update(speed=3.0, grade=0.0, success=r.success,
                 objective=r.objective,
                 solve_min=round(r.solve_time_s / 60, 2))
    log.append(stats)
    print(json.dumps(stats), flush=True)
    LOG.write_text(json.dumps(log, indent=2))
    print(f"[done in {(time.time() - t0) / 60:.1f} min]", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3000)
