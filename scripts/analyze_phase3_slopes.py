"""Analyze the Phase-3 slope grid: predicted cost of transport vs grade
against the Minetti (2002) polynomial / Tier-0 curve, plus stride-metric
shifts with grade (contact time, cadence, peak force)."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from runsim.tier0 import Athlete, Environment, cost_of_transport

RUN_DIR = Path(__file__).resolve().parent.parent / "experiments" / "phase3_2drunning"
OUT = RUN_DIR.parent / "phase3_slope_analysis.png"


def main() -> None:
    log = json.loads((RUN_DIR / "slope_grid_log.json").read_text())
    # include the flat metabolic point from the speed chain
    met = json.loads((RUN_DIR / "metabolic_chain_log.json").read_text())
    flat = next(r for r in met if r["speed"] == 3.0)
    flat = {**flat, "grade": 0.0, "grade_deg": 0.0}
    rows = sorted(log + [flat], key=lambda r: r["grade"])

    g = np.array([r["grade"] for r in rows])
    cot = np.array([r["cost_of_transport"] for r in rows])

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    fig.suptitle("Phase 3: slope grid at 3.0 m/s (metabolic objective) vs Minetti")

    gg = np.linspace(-0.17, 0.17, 100)
    athlete = Athlete(mass_kg=62.0, running_economy_j_kg_m=3.8)
    tier0 = [cost_of_transport(3.0, athlete, Environment(grade=x)) for x in gg]
    axes[0].plot(gg * 100, tier0, "--", color="k", label="Tier-0 (Minetti)")
    axes[0].plot(g * 100, cot, "o-", label="Moco (Bhargava)")
    axes[0].set(title="Cost of transport vs grade", xlabel="grade (%)", ylabel="J/kg/m")
    axes[0].legend()

    ax = axes[1]
    ax.plot(g * 100, [1000 * r["contact_time_s"] for r in rows], "o-", label="contact time (ms)")
    ax.plot(g * 100, [100 * r["flight_fraction"] for r in rows], "s-", label="flight fraction (%)")
    ax.plot(g * 100, [100 * r["peak_force_bw"] for r in rows], "^-", label="peak force (BW x100)")
    ax.set(title="Stride mechanics vs grade", xlabel="grade (%)")
    ax.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"wrote {OUT}")
    for r in rows:
        print(f"grade {r['grade_deg']:+.0f} deg: COT={r['cost_of_transport']:.2f} "
              f"t_c={r['contact_time_s']*1000:.0f}ms flight={r['flight_fraction']:.0%} "
              f"peak={r['peak_force_bw']:.2f}BW success={r['success']}")


if __name__ == "__main__":
    main()
