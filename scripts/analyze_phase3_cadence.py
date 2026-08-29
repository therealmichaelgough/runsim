"""Analyze the Phase-3 cadence sweep: cost of transport vs imposed step
frequency at 3.0 m/s (metabolic objective), against the model's free-choice
cadence and the human preferred range (~2.8-2.9 Hz at 3 m/s, Fukuchi 2017 /
Van Hooren 2024; Snyder & Farley 2011 put the preferred stride frequency
within ~3% of the energetic optimum), plus stride-mechanics shifts."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from runsim.tier1 import predict_stride

RUN_DIR = Path(__file__).resolve().parent.parent / "experiments" / "phase3_2drunning"
OUT = RUN_DIR.parent / "phase3_cadence_analysis.png"

TIER1 = predict_stride(3.0)  # Fukuchi-fitted stride mechanics at 3 m/s
# preferred-cadence band: Tier-1 fitted step frequency +-3% (Snyder & Farley 2011)
HUMAN_PREFERRED_HZ = (TIER1.step_freq_hz * 0.97, TIER1.step_freq_hz * 1.03)


def main() -> None:
    log = json.loads((RUN_DIR / "cadence_sweep_log.json").read_text())
    # free-choice metabolic point at 3.0 m/s from the speed chain
    met = json.loads((RUN_DIR / "metabolic_chain_log.json").read_text())
    free = next(r for r in met if r["speed"] == 3.0)

    rows = sorted(log, key=lambda r: r["imposed_step_freq_hz"])
    f = np.array([r["imposed_step_freq_hz"] for r in rows])
    cot = np.array([r["cost_of_transport"] for r in rows])

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    fig.suptitle("Phase 3: cadence sweep at 3.0 m/s (metabolic objective)")

    ax = axes[0]
    ax.plot(f, cot, "o-", label="imposed cadence")
    ax.plot(free["step_freq_hz"], free["cost_of_transport"], "r*", ms=14,
            label=f"free choice ({free['step_freq_hz']:.2f} Hz)")
    ax.axvspan(*HUMAN_PREFERRED_HZ, color="green", alpha=0.15,
               label=f"human preferred ({TIER1.step_freq_hz:.2f} Hz +-3%)")
    ax.set(title="Cost of transport vs step frequency",
           xlabel="step frequency (Hz)", ylabel="J/kg/m")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.plot(f, [1000 * r["contact_time_s"] for r in rows], "o-", label="contact time (ms)")
    ax.plot(f, [100 * r["flight_fraction"] for r in rows], "s-", label="flight fraction (%)")
    ax.plot(f, [100 * r["peak_force_bw"] for r in rows], "^-", label="peak force (BW x100)")
    ax.axhline(1000 * TIER1.contact_time_s, ls=":", color="tab:blue")
    ax.text(f[0], 1000 * TIER1.contact_time_s + 4,
            f"measured t_c at 3 m/s ({1000 * TIER1.contact_time_s:.0f} ms, Tier-1 fit)",
            fontsize=7, color="tab:blue")
    ax.axhline(100 * TIER1.peak_force_bw, ls=":", color="tab:green")
    ax.text(f[0], 100 * TIER1.peak_force_bw + 4,
            f"measured peak ({TIER1.peak_force_bw:.2f} BW, Tier-1 fit)",
            fontsize=7, color="tab:green")
    ax.axvspan(*HUMAN_PREFERRED_HZ, color="green", alpha=0.15)
    ax.set(title="Stride mechanics vs step frequency", xlabel="step frequency (Hz)")
    ax.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"wrote {OUT}")
    for r in rows:
        print(f"{r['imposed_step_freq_hz']:.1f} Hz: COT={r['cost_of_transport']:.2f} "
              f"t_c={r['contact_time_s']*1000:.0f}ms flight={r['flight_fraction']:.0%} "
              f"peak={r['peak_force_bw']:.2f}BW obj={r['objective']:.1f} success={r['success']}")


if __name__ == "__main__":
    main()
