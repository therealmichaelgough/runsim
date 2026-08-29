"""Compare metabolic-objective vs effort-objective predictions vs data.

Panels: cadence and contact time vs speed (both objectives vs Tier-1
Fukuchi fits), peak force, and metabolic cost of transport vs the Tier-0
(Minetti-anchored) curve - the key cross-tier energy validation.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from runsim.tier0 import Athlete, cost_of_transport
from runsim.tier1 import predict_stride

RUN_DIR = Path(__file__).resolve().parent.parent / "experiments" / "phase3_2drunning"
OUT = RUN_DIR.parent / "phase3_metabolic_analysis.png"


def main() -> None:
    effort = json.loads((RUN_DIR / "chain_log.json").read_text())
    met = json.loads((RUN_DIR / "metabolic_chain_log.json").read_text())
    effort = [r for r in effort if r["speed"] >= 2.5]

    fig, axes = plt.subplots(1, 4, figsize=(15.5, 3.9))
    fig.suptitle("Phase 3: metabolic vs effort objective (2D predictive running)")
    tier1_v = np.linspace(2.5, 5.0, 11)

    def series(log, key):
        return [r["speed"] for r in log], [r[key] for r in log]

    axes[0].plot(*series(effort, "step_freq_hz"), "o-", label="effort³")
    axes[0].plot(*series(met, "step_freq_hz"), "s-", label="metabolic")
    axes[0].plot(tier1_v, [predict_stride(v).step_freq_hz for v in tier1_v], "--",
                 color="k", label="Fukuchi fit")
    axes[0].set(title="Step frequency", xlabel="speed (m/s)", ylabel="Hz")
    axes[0].legend(fontsize=8)

    axes[1].plot(*series(effort, "contact_time_s"), "o-", label="effort³")
    axes[1].plot(*series(met, "contact_time_s"), "s-", label="metabolic")
    axes[1].plot(tier1_v, [predict_stride(v).contact_time_s for v in tier1_v], "--",
                 color="k", label="Fukuchi fit")
    axes[1].set(title="Contact time", xlabel="speed (m/s)", ylabel="s")
    axes[1].legend(fontsize=8)

    axes[2].plot(*series(effort, "peak_force_bw"), "o-", label="effort³")
    axes[2].plot(*series(met, "peak_force_bw"), "s-", label="metabolic")
    axes[2].plot(tier1_v, [predict_stride(v).peak_force_bw for v in tier1_v], "--",
                 color="k", label="Fukuchi fit / Morin")
    axes[2].set(title="Peak vertical GRF", xlabel="speed (m/s)", ylabel="BW")
    axes[2].legend(fontsize=8)

    v_met, cot = series(met, "cost_of_transport")
    axes[3].plot(v_met, cot, "s-", label="Moco (Bhargava)")
    model_athlete = Athlete(mass_kg=62.0, running_economy_j_kg_m=3.8)
    axes[3].plot(tier1_v, [cost_of_transport(v, model_athlete) for v in tier1_v], "--",
                 color="k", label="Tier-0 (Minetti-anchored)")
    axes[3].set(title="Metabolic cost of transport", xlabel="speed (m/s)", ylabel="J/kg/m")
    axes[3].legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"wrote {OUT}")
    for r in met:
        print(f"v={r['speed']}: COT={r['cost_of_transport']:.2f} J/kg/m "
              f"f={r['step_freq_hz']:.2f}Hz t_c={r['contact_time_s']*1000:.0f}ms "
              f"peak={r['peak_force_bw']:.2f}BW success={r['success']} ({r['solve_min']:.1f} min)")


if __name__ == "__main__":
    main()
