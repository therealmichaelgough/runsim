"""Segmented metabolic solve: checkpointing by construction.

Moco writes trajectories only at solve completion, so long solves are
run as short capped LEGS (~300 iterations): every leg completes normally
and banks its iterate to disk; the next leg warm-starts from it. A
collapse can cost at most one leg, and each boundary applies a health
gate — a leg whose objective degrades is discarded and re-run from the
prior good file (the barrier reset alone often clears the pathology).

Usage: run_met_legs.py [start_solution] [leg_iters] [max_legs]
Defaults: solution_p3d_v3_gp0_met.sto (the capped first leg's output),
300, 12. Stops early when a leg converges (success=True).
"""
import json
import shutil
import sys
import time
from pathlib import Path

from runsim.tier3 import solution_summary
from runsim.tier3.predict3d import predict_gait_3d

HERE = Path(__file__).resolve().parent
LOG = HERE / "predict3d_met_log.json"
MASS = 75.16


def main(start: str = "solution_p3d_v3_gp0_met.sto",
         leg_iters: int = 300, max_legs: int = 12,
         torque_weight: float | None = None,
         mesh_intervals: int = 50) -> None:
    guess = HERE / start
    if not guess.exists():
        raise SystemExit(f"start solution missing: {guess}")
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    # gate baseline: best objective already recorded for this problem, so
    # leg 1 is judged against the start file's provenance, not ungated
    # a torque_weight run adds penalty by construction, so its objectives
    # are not comparable to unpenalized legs: gate only among its own legs
    prev_objs = [r["objective"] for r in log
                 if r.get("speed") == 3.0 and "objective" in r
                 and (torque_weight is None) == (r.get("torque_weight") is None)]
    prev_obj = min(prev_objs) if prev_objs else None

    for leg in range(1, max_legs + 1):
        t0 = time.time()
        r = predict_gait_3d(3.0, out_dir=HERE, guess_path=guess,
                            max_iterations=leg_iters, objective="metabolic",
                            torque_weight=torque_weight,
                            mesh_intervals=mesh_intervals)
        stats = solution_summary(r.grf_path, mass_kg=MASS)
        stats.update(speed=3.0, grade=0.0, leg=leg, success=r.success,
                     objective=r.objective,
                     cost_of_transport=r.cost_of_transport,
                     solution=r.solution_path.name,
                     torque_weight=torque_weight,
                     solve_min=round(r.solve_time_s / 60, 2))

        # health gate: a degraded leg is not chained
        if prev_obj is not None and r.objective > prev_obj * 1.5:
            stats["verdict"] = "DEGRADED - discarded, re-running from prior"
            log.append(stats)
            LOG.write_text(json.dumps(log, indent=2))
            print(json.dumps(stats), flush=True)
            continue  # guess unchanged -> barrier-reset retry from prior good

        # bank this leg under its own name, then chain from it
        banked = HERE / f"met_leg{leg:02d}.sto"
        shutil.copyfile(r.solution_path, banked)
        stats["banked"] = banked.name
        log.append(stats)
        LOG.write_text(json.dumps(log, indent=2))
        print(json.dumps(stats), flush=True)
        print(f"[leg {leg} done in {(time.time() - t0) / 60:.1f} min]", flush=True)
        guess = banked
        prev_obj = min(prev_obj, r.objective) if prev_obj is not None else r.objective

        if r.success:
            print("[converged - metabolic solve COMPLETE]", flush=True)
            return
    print("[leg budget exhausted without formal convergence]", flush=True)


if __name__ == "__main__":
    # run_met_legs.py [start.sto] [leg_iters] [max_legs] [torque_weight] [mesh]
    args = sys.argv[1:]
    main(*(args[:1] or []),
         *([int(args[1])] if len(args) > 1 else []),
         *([int(args[2])] if len(args) > 2 else []),
         *([float(args[3])] if len(args) > 3 else []),
         *([int(args[4])] if len(args) > 4 else []))
