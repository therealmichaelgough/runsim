"""Solve a single imposed-cadence point of the 3.0 m/s metabolic sweep.

Parallel-execution companion to run_cadence_sweep.py: each process solves
one frequency (seeded from the nearest completed solution passed on the
command line) and writes its stats to cadence_fragments/f<freq>.json.
merge_cadence_fragments.py folds fragments into cadence_sweep_log.json.

Usage: run_one_cadence.py <step_freq_hz> <seed_solution.sto>
"""
import json
import sys
from pathlib import Path

from runsim.tier3 import predict_gait_2d, solution_summary

HERE = Path(__file__).resolve().parent
SPEED = 3.0


def main() -> None:
    freq = float(sys.argv[1])
    seed = Path(sys.argv[2])
    r = predict_gait_2d(SPEED, out_dir=HERE, guess_path=seed,
                        objective="metabolic", step_time_s=1.0 / freq)
    stats = solution_summary(r.grf_path)
    stats.update(speed=SPEED, imposed_step_freq_hz=freq,
                 success=r.success, objective=r.objective,
                 cost_of_transport=r.cost_of_transport,
                 solve_min=round(r.solve_time_s / 60, 2))
    frag_dir = HERE / "cadence_fragments"
    frag_dir.mkdir(exist_ok=True)
    (frag_dir / f"f{freq:.1f}.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
