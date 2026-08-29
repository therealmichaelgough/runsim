"""Fit Tier-1 timing regressions from the Fukuchi 2017 raw force data.

Extracts per-trial stance/flight timing and step frequency from 30 s of
treadmill GRF at 2.5/3.5/4.5 m/s for every subject, then fits:
  - contact length:  L_c = v * t_c = a + b * v   (Weyand 2000 framing)
  - step frequency:  f = c + d * v
Writes the medians/coefficients to src/runsim/tier1/params.json.
"""
import json
from pathlib import Path

import numpy as np

from runsim.data import fukuchi

THRESH_N = 40.0
MIN_PHASE_S = 0.08  # ignore contacts/flights shorter than this (noise)


def phases(fy: np.ndarray, hz: float):
    """Yield (kind, duration_s) for alternating stance/flight phases."""
    on = fy > THRESH_N
    edges = np.flatnonzero(np.diff(on.astype(int)))
    for a, b in zip(edges[:-1], edges[1:]):
        dur = (b - a) / hz
        yield ("stance" if on[a + 1] else "flight"), dur


def trial_stats(subject: int, speed: float):
    if subject not in fukuchi.subjects().index:
        return None  # trial files exist for a few subjects missing from RBDSinfo
    f = fukuchi.forces(subject, speed)
    fy = f["Fy"].to_numpy()
    tc, tf = [], []
    for kind, dur in phases(fy, fukuchi.FORCES_HZ):
        if dur < MIN_PHASE_S or dur > 0.6:
            continue
        (tc if kind == "stance" else tf).append(dur)
    if len(tc) < 20 or len(tf) < 20:
        return None
    t_c, t_f = float(np.median(tc)), float(np.median(tf))
    mass = fukuchi.subjects().loc[subject, "Mass"]
    return {
        "subject": subject,
        "speed": speed,
        "t_c": t_c,
        "t_f": t_f,
        "step_freq": 1.0 / (t_c + t_f),
        "fmax_bw": float(np.percentile(fy, 99.5) / (mass * 9.81)),
    }


def main() -> None:
    rows = []
    for sub in fukuchi.available_subjects():
        for speed in (2.5, 3.5, 4.5):
            try:
                s = trial_stats(sub, speed)
            except FileNotFoundError:
                continue
            if s:
                rows.append(s)
    v = np.array([r["speed"] for r in rows])
    t_c = np.array([r["t_c"] for r in rows])
    freq = np.array([r["step_freq"] for r in rows])

    lc_b, lc_a = np.polyfit(v, v * t_c, 1)
    f_b, f_a = np.polyfit(v, freq, 1)

    params = {
        "source": "Fukuchi 2017 treadmill dataset, fitted by scripts/fit_tier1_params.py",
        "n_trials": len(rows),
        "contact_length_m": {"intercept": lc_a, "slope_per_ms": lc_b},
        "step_freq_hz": {"intercept": f_a, "slope_per_ms": f_b},
    }
    out = Path(__file__).resolve().parent.parent / "src" / "runsim" / "tier1" / "params.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(params, indent=2))

    pred_tc = (lc_a + lc_b * v) / v
    print(f"{len(rows)} trials from {len(set(r['subject'] for r in rows))} subjects")
    print(f"contact length L_c = {lc_a:.3f} + {lc_b:.3f} v   "
          f"(t_c residual sd {np.std(t_c - pred_tc) * 1000:.1f} ms)")
    print(f"step freq      f  = {f_a:.3f} + {f_b:.3f} v   "
          f"(residual sd {np.std(freq - (f_a + f_b * v)):.3f} Hz)")
    for speed in (2.5, 3.5, 4.5):
        sel = v == speed
        print(f"  v={speed}: t_c {np.mean(t_c[sel])*1000:.0f} ms, "
              f"f {np.mean(freq[sel]):.2f} Hz, "
              f"Fmax {np.mean([r['fmax_bw'] for r in rows if r['speed'] == speed]):.2f} BW")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
