"""Validate Tier-1 GRF waveforms against measured Fukuchi stance ensembles.

For each speed (2.5/3.5/4.5 m/s): extract every stance phase from every
subject's raw vertical GRF, time-normalize to 0-100% stance, average, and
overlay the two-mass model prediction for the cohort-mean athlete.
Also checks Kram-Taylor consistency: Tier-0 metabolic power should rise
roughly in proportion to 1/t_c (cost of generating force).
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from runsim.data import fukuchi
from runsim.tier0 import Athlete, metabolic_power
from runsim.tier1 import grf_waveform, predict_stride

OUT = Path(__file__).resolve().parent.parent / "experiments" / "tier1_validation.png"
measured_ensemble = fukuchi.stance_ensemble


def main() -> None:
    subs = fukuchi.subjects()
    cohort = Athlete(mass_kg=float(subs.Mass.mean()),
                     height_m=float(subs.Height.mean()) / 100.0)
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.8))
    fig.suptitle("Tier-1 two-mass GRF model vs Fukuchi 2017 measured stance ensembles")

    for ax, speed in zip(axes[:3], (2.5, 3.5, 4.5)):
        mean, sd, n = measured_ensemble(speed)
        pct = np.linspace(0, 100, len(mean))
        ax.fill_between(pct, mean - sd, mean + sd, alpha=0.25, label=f"measured ±1SD (n={n})")
        ax.plot(pct, mean, lw=2, label="measured mean")

        s = predict_stride(speed, cohort)
        w = grf_waveform(s, cohort)
        model = w.vertical_n / (cohort.mass_kg * 9.81)
        model_pct = 100 * w.time_s / s.contact_time_s
        ax.plot(model_pct, model, "--", lw=2, label="two-mass model")

        model_i = np.interp(pct, model_pct, model)
        rmse = float(np.sqrt(np.mean((model_i - mean) ** 2)))
        r2 = 1 - np.sum((model_i - mean) ** 2) / np.sum((mean - mean.mean()) ** 2)
        ax.set(title=f"{speed} m/s   RMSE {rmse:.2f} BW, R² {r2:.2f}",
               xlabel="% stance", ylabel="vertical GRF (BW)")
        ax.legend(fontsize=7)
        print(f"v={speed}: RMSE {rmse:.3f} BW, R2 {r2:.3f}, "
              f"peak model {model.max():.2f} vs measured {mean.max():.2f} BW")

    # Kram-Taylor: P_metab vs 1/t_c across speeds
    speeds = np.linspace(2.5, 5.5, 13)
    inv_tc = np.array([1 / predict_stride(v, cohort).contact_time_s for v in speeds])
    power = np.array([metabolic_power(v, cohort) for v in speeds])
    axes[3].plot(inv_tc, power, "o-")
    b, a = np.polyfit(inv_tc, power, 1)
    r = np.corrcoef(inv_tc, power)[0, 1]
    axes[3].set(title=f"Kram–Taylor check: P vs 1/t_c (r={r:.3f})",
                xlabel="1/contact time (1/s)", ylabel="metabolic power (W/kg)")
    print(f"Kram-Taylor: corr(P, 1/t_c) = {r:.3f} over 2.5-5.5 m/s")

    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
