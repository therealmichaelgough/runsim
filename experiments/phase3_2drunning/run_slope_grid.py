"""Slope grid at 3.0 m/s with the metabolic objective.

Grades match the Van Hooren dataset conditions (+-3 deg, +-6 deg) plus a
steeper +-9 deg, solved by grade homotopy: flat metabolic solution seeds
+-3 deg, which seeds +-6 deg, and so on. Logs cost of transport per grade
for comparison against the Minetti polynomial.
"""
import json
import math
import time
from pathlib import Path

from runsim.tier3 import predict_gait_2d, solution_summary

HERE = Path(__file__).resolve().parent
SPEED = 3.0
FLAT_SEED = HERE / "solution_v3_gp0_met.sto"
DEG = [3.0, 6.0, 9.0]
LOG = HERE / "slope_grid_log.json"


def main() -> None:
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    done = {round(r["grade"], 4) for r in log}
    for sign in (+1, -1):
        guess = FLAT_SEED
        for deg in DEG:
            grade = sign * math.tan(math.radians(deg))
            if round(grade, 4) in done:
                continue
            t0 = time.time()
            r = predict_gait_2d(SPEED, grade=grade, out_dir=HERE,
                                guess_path=guess, objective="metabolic")
            stats = solution_summary(r.grf_path)
            stats.update(speed=SPEED, grade=grade, grade_deg=sign * deg,
                         success=r.success, objective=r.objective,
                         cost_of_transport=r.cost_of_transport,
                         solve_min=round(r.solve_time_s / 60, 2))
            log.append(stats)
            print(json.dumps(stats), flush=True)
            LOG.write_text(json.dumps(log, indent=2))
            if r.objective < 50:
                guess = r.solution_path
            print(f"[{sign * deg:+.0f} deg done in {(time.time() - t0) / 60:.1f} min]", flush=True)


if __name__ == "__main__":
    main()
