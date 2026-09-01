"""Predictive 3D running chain (Phase-3 finale, milestone 1).

Speed homotopy from the tracking seed's own effective forward speed: the
seed advances at ~1.7 m/s (Hamner's treadmill-frame kinematics over
stationary ground yield partial foot slip), and MocoAverageSpeedGoal is
an endpoint CONSTRAINT — asking for 3.0 m/s straight from the seed
starts the solve ~43% infeasible and IPOPT dives into restoration and
never escapes (first attempt burned 7 h there). So: solve at 1.7 first,
then chain 2.2 -> 2.6 -> 3.0, each seeded from the previous solution.
Resumable via predict3d_log.json (completed speeds are skipped).

Usage: run_predict3d.py [max_iterations]
"""
import json
import sys
import time
from pathlib import Path

from runsim.tier3 import solution_summary
from runsim.tier3.predict3d import predict_gait_3d

HERE = Path(__file__).resolve().parent
SEED = HERE / "seed3d_tracking.sto"
LOG = HERE / "predict3d_log.json"
MASS = 75.16
SPEEDS = [1.7, 2.2, 2.6, 3.0]


def main(max_iterations: int = 2000) -> None:
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    done = {round(r["speed"], 3) for r in log}
    guess = SEED
    for speed in SPEEDS:
        # only entries carrying a 'solution' field count as completed —
        # legacy/smoke-test rows in the log must not skip a real solve
        prior = next((r for r in log if round(r["speed"], 3) == round(speed, 3)
                      and "solution" in r), None)
        if prior is not None:
            if prior.get("objective", 1e9) < 100:
                guess = HERE / Path(prior["solution"]).name
            continue
        t0 = time.time()
        r = predict_gait_3d(speed, out_dir=HERE, guess_path=guess,
                            max_iterations=max_iterations)
        stats = solution_summary(r.grf_path, mass_kg=MASS)
        stats.update(speed=speed, grade=0.0, success=r.success,
                     objective=r.objective,
                     solution=r.solution_path.name,
                     solve_min=round(r.solve_time_s / 60, 2))
        log.append(stats)
        print(json.dumps(stats), flush=True)
        LOG.write_text(json.dumps(log, indent=2))
        if r.objective < 100:  # sane -> usable as the next seed
            guess = r.solution_path
        print(f"[{speed} m/s done in {(time.time() - t0) / 60:.1f} min]", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
