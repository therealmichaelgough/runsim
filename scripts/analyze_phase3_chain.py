"""Analyze the Phase-3 speed-chain predictions.

Panels:
1. Walk->run transition: flight fraction vs speed (Falisse 2019 reproduced
   the human transition near 2-2.5 m/s with this class of model).
2. Stride metrics vs speed: model contact time and step frequency against
   the Tier-1 regressions (fitted to Fukuchi) and peak force vs measured.
3. Predicted vertical GRF waveform vs the Fukuchi measured ensemble at the
   speeds where both exist (2.5/3.5/4.5 m/s).
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import opensim as osim

from runsim.data import fukuchi
from runsim.tier1 import predict_stride

RUN_DIR = Path(__file__).resolve().parent.parent / "experiments" / "phase3_2drunning"
OUT = RUN_DIR.parent / "phase3_chain_analysis.png"
MODEL_MASS = 62.0  # 2D_gait.osim


def model_stance_waveform(grf_path: Path):
    table = osim.TimeSeriesTable(str(grf_path))
    t = np.asarray(table.getIndependentColumn())
    fy = table.getDependentColumn("ground_force_r_vy").to_numpy() / (MODEL_MASS * 9.81)
    on = fy > 0.05
    edges = np.flatnonzero(np.diff(on.astype(int)))
    best = None
    for a, b in zip(edges[:-1], edges[1:]):
        if on[a + 1] and (best is None or b - a > best[1] - best[0]):
            best = (a, b)
    a, b = best
    phase = fy[a + 1 : b + 1]
    return np.interp(np.linspace(0, 1, 101), np.linspace(0, 1, len(phase)), phase)


def main() -> None:
    log = json.loads((RUN_DIR / "chain_log.json").read_text())
    ok = [r for r in log if r["success"]]
    v = np.array([r["speed"] for r in ok])

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    fig.suptitle("Phase 3: predictive 2D gait across speeds (Moco, effort-optimal, no tracking data)")

    axes[0].plot(v, [100 * r["flight_fraction"] for r in ok], "o-")
    axes[0].axhline(0, lw=0.6, color="grey")
    axes[0].set(title="Walk-run transition emerges", xlabel="speed (m/s)",
                ylabel="flight fraction of stride (%)")

    tier1_v = np.linspace(2.5, 5.0, 11)
    axes[1].plot(v, [1000 * r["contact_time_s"] for r in ok], "o-", label="Moco t_c")
    axes[1].plot(tier1_v, [1000 * predict_stride(x).contact_time_s for x in tier1_v],
                 "--", label="Tier-1 fit (Fukuchi)")
    ax2 = axes[1].twinx()
    ax2.plot(v, [r["peak_force_bw"] for r in ok], "s-", color="tab:red", label="Moco peak (BW)")
    ax2.plot(tier1_v, [predict_stride(x).peak_force_bw for x in tier1_v],
             ":", color="tab:red", label="Tier-1 peak")
    ax2.set_ylabel("peak vGRF (BW)", color="tab:red")
    axes[1].set(title="Stride metrics vs Tier-1/data", xlabel="speed (m/s)", ylabel="contact time (ms)")
    lines = axes[1].get_lines() + ax2.get_lines()
    axes[1].legend(lines, [ln.get_label() for ln in lines], fontsize=7)

    pct = np.linspace(0, 100, 101)
    for speed, color in [(2.5, "tab:blue"), (3.5, "tab:orange"), (4.5, "tab:green")]:
        grf_path = RUN_DIR / f"grf_v{speed:g}_gp0.sto".replace(".sto", ".sto")
        candidates = list(RUN_DIR.glob(f"grf_v{str(speed).replace('.', '_')}*.sto"))
        if not candidates:
            continue
        mean, sd, _ = fukuchi.stance_ensemble(speed)
        axes[2].plot(pct, mean, color=color, lw=1.5, label=f"measured {speed} m/s")
        axes[2].plot(pct, model_stance_waveform(candidates[0]), "--", color=color, lw=1.5)
    axes[2].set(title="Predicted (dashed) vs measured vGRF", xlabel="% stance", ylabel="vGRF (BW)")
    axes[2].legend(fontsize=7)

    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"wrote {OUT}")
    for r in ok:
        print(f"v={r['speed']}: aerial={r['aerial']} t_c={r['contact_time_s']*1000:.0f}ms "
              f"f={r['step_freq_hz']:.2f}Hz peak={r['peak_force_bw']:.2f}BW "
              f"({r['solve_min']:.1f} min)")


if __name__ == "__main__":
    main()
