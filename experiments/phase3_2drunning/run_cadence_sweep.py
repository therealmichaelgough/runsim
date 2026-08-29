"""Cadence sweep at 3.0 m/s with the metabolic objective.

The free-choice metabolic solution at 3.0 m/s runs at ~3.8 Hz step
frequency, well above the ~2.8-2.9 Hz humans prefer at that speed
(Fukuchi 2017; Van Hooren 2024 cadence conditions; Snyder & Farley 2011
found preferred stride frequency within ~3% of the energetic optimum).
This sweep imposes step frequency by fixing the problem's final time and
maps the model's cost-of-transport-vs-cadence curve, to answer:

1. Where is the 2D model's energetic optimum, and how sharp is the bowl?
2. Does forcing physiological cadence (~2.9 Hz) recover realistic contact
   times and GRF shapes, and at what COT penalty?

Homotopy: descending frequencies chain from the free v3 metabolic
solution (3.82 Hz) downward; ascending frequencies chain upward from the
same seed. Resumable via cadence_sweep_log.json (rerunning skips
completed frequencies).
"""
import json
import time
from pathlib import Path

from runsim.tier3 import predict_gait_2d, solution_summary

HERE = Path(__file__).resolve().parent
SPEED = 3.0
FREE_SEED = HERE / "solution_v3_gp0_met.sto"
FREE_STEP_FREQ = 3.816  # from metabolic_chain_log.json
DESCENDING = [3.8, 3.6, 3.4, 3.2, 3.0, 2.9, 2.8, 2.6]
ASCENDING = [4.0, 4.2, 4.4]
LOG = HERE / "cadence_sweep_log.json"


def main() -> None:
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    done = {round(r["imposed_step_freq_hz"], 4) for r in log}
    for chain in (DESCENDING, ASCENDING):
        guess = FREE_SEED
        for freq in chain:
            if round(freq, 4) in done:
                continue
            t0 = time.time()
            r = predict_gait_2d(SPEED, out_dir=HERE, guess_path=guess,
                                objective="metabolic", step_time_s=1.0 / freq)
            stats = solution_summary(r.grf_path)
            stats.update(speed=SPEED, imposed_step_freq_hz=freq,
                         success=r.success, objective=r.objective,
                         cost_of_transport=r.cost_of_transport,
                         solve_min=round(r.solve_time_s / 60, 2))
            log.append(stats)
            print(json.dumps(stats), flush=True)
            LOG.write_text(json.dumps(log, indent=2))
            if r.objective < 50:
                guess = r.solution_path
            print(f"[{freq:.1f} Hz done in {(time.time() - t0) / 60:.1f} min]", flush=True)


if __name__ == "__main__":
    main()
