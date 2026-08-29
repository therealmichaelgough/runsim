"""Metabolic-objective predictive solves across running speeds, each seeded
from the effort-only solution at the same speed. Logs cost of transport for
comparison against Tier-0 (Minetti) and reports whether the metabolic
objective improves cadence/peak-force realism."""
import json
import time
from pathlib import Path

from runsim.tier3 import predict_gait_2d, solution_summary

HERE = Path(__file__).resolve().parent
SPEEDS = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]


def effort_seed(v: float) -> Path:
    label = f"v{v:g}_gp0".replace(".", "_")
    return HERE / f"solution_{label}.sto"


def met_solution(v: float) -> Path:
    label = f"v{v:g}_gp0_met".replace(".", "_")
    return HERE / f"solution_{label}.sto"


def main() -> None:
    log_path = HERE / "metabolic_chain_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    done = {r["speed"] for r in log}
    prev_met: Path | None = None
    for v in SPEEDS:
        if met_solution(v).exists() and v in done:
            prev_met = met_solution(v)
            continue
        # prefer the previous metabolic solution (same objective) as guess
        guess = prev_met if prev_met is not None else effort_seed(v)
        t0 = time.time()
        r = predict_gait_2d(v, out_dir=HERE, guess_path=guess, objective="metabolic")
        stats = solution_summary(r.grf_path)
        stats.update(speed=v, success=r.success, objective=r.objective,
                     cost_of_transport=r.cost_of_transport,
                     solve_min=round(r.solve_time_s / 60, 2))
        log.append(stats)
        print(json.dumps(stats), flush=True)
        log_path.write_text(json.dumps(log, indent=2))
        if r.objective < 50:
            prev_met = r.solution_path
        print(f"[{v} m/s done in {(time.time() - t0) / 60:.1f} min]", flush=True)


if __name__ == "__main__":
    main()
