"""Demo figure for the Tier-0 energetics engine: three what-if sweeps."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from runsim.tier0 import Athlete, Environment, metabolic_power, speed_at_power, speed_for_duration

OUT = Path(__file__).resolve().parent.parent / "experiments" / "tier0_demo.png"


def main() -> None:
    athlete = Athlete(mass_kg=65, vo2max_ml_kg_min=60, running_economy_j_kg_m=3.5)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    fig.suptitle("Tier-0 energetics engine: equal-effort what-ifs (VO2max 60, economy 3.5, 65 kg)")

    # 1) grade-adjusted pace at a fixed threshold effort
    power = metabolic_power(4.44, athlete)  # ~3:45/km flat effort
    grades = np.linspace(-0.30, 0.30, 61)
    paces = [1000 / speed_at_power(power, athlete, Environment(grade=g)).speed_ms / 60 for g in grades]
    axes[0].plot(grades * 100, paces)
    axes[0].axvline(0, lw=0.6, color="grey")
    axes[0].set(title="Equal-effort pace vs gradient", xlabel="gradient (%)", ylabel="pace (min/km)")
    axes[0].invert_yaxis()

    # 2) marathon time vs altitude (hypoxia vs thin-air trade-off)
    alts = np.linspace(0, 3000, 31)
    times = []
    for h in alts:
        v = 3.0
        for _ in range(40):
            t = 42195 / v
            v = speed_for_duration(t, athlete, Environment(altitude_m=h)).speed_ms
        times.append(42195 / v / 3600)
    axes[1].plot(alts, times)
    axes[1].set(title="Marathon time vs altitude", xlabel="altitude (m)", ylabel="time (h)")

    # 3) 10k time vs wind, with and without drafting
    winds = np.linspace(-6, 6, 25)
    for draft, label in [(0.0, "alone"), (0.6, "drafting 60%")]:
        t10k = []
        for w in winds:
            v = 3.5
            for _ in range(40):
                t = 10000 / v
                v = speed_for_duration(t, athlete, Environment(wind_ms=w, drafting=draft)).speed_ms
            t10k.append(10000 / v / 60)
        axes[2].plot(winds, t10k, label=label)
    axes[2].axvline(0, lw=0.6, color="grey")
    axes[2].set(title="10 km time vs wind", xlabel="wind (m/s, + headwind)", ylabel="time (min)")
    axes[2].legend()

    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
