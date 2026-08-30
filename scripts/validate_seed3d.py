"""Validate the 3D tracking seed: joint-angle tracking error vs the
retargeted Hamner RRA reference, model contact GRFs vs measured GRFs,
and stride metrics. Figure: experiments/phase3_seed3d_validation.png."""
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import opensim as osim

from runsim.tier3.model3d import CONTACT_FORCES_LEFT, CONTACT_FORCES_RIGHT

ROOT = Path(__file__).resolve().parent.parent
D3 = ROOT / "experiments" / "phase3_3drunning"
GRF_MOT = ROOT / "data" / "raw" / "hamner2013" / "subject01" / "ExportedData" / "Run_300 02_newCOP3_v24.mot"
OUT = ROOT / "experiments" / "phase3_seed3d_validation.png"

KEY_COORDS = [
    "hip_flexion_r", "hip_adduction_r", "knee_angle_r", "ankle_angle_r",
    "pelvis_tilt", "pelvis_list", "lumbar_extension", "arm_flex_r", "elbow_flex_r",
]


def col(table, name):
    return table.getDependentColumn(name).to_numpy()


def main() -> None:
    model = osim.Model(str(D3 / "lai_running_model.osim"))
    model.initSystem()
    sol = osim.MocoTrajectory(str(D3 / "seed3d_tracking.sto"))
    st = sol.exportToStatesTable()
    ref = osim.TimeSeriesTable(str(D3 / "states_ref_v3.sto"))
    t = np.asarray(st.getIndependentColumn())
    tr = np.asarray(ref.getIndependentColumn())

    # --- kinematic tracking error ---
    print("joint-angle tracking RMS (deg):")
    rms = {}
    coords = model.getCoordinateSet()
    for i in range(coords.getSize()):
        c = coords.get(i)
        name = c.getName()
        lab = f"{c.getAbsolutePathString()}/value"
        if lab not in ref.getColumnLabels() or "beta" in name:
            continue
        sim = col(st, lab)
        refv = np.interp(t, tr, col(ref, lab))
        if name.startswith("pelvis_t"):
            continue  # translations tracked implicitly
        rms[name] = math.degrees(float(np.sqrt(np.mean((sim - refv) ** 2))))
    for k in KEY_COORDS:
        if k in rms:
            print(f"  {k:20s} {rms[k]:6.2f}")
    worst = sorted(rms.items(), key=lambda kv: -kv[1])[:3]
    print("  worst:", ", ".join(f"{k}={v:.1f}" for k, v in worst))

    # --- GRFs: model contact vs measured ---
    right = osim.StdVectorString(); left = osim.StdVectorString()
    for f in CONTACT_FORCES_RIGHT: right.append(f)
    for f in CONTACT_FORCES_LEFT: left.append(f)
    grf = osim.createExternalLoadsTableForGait(model, sol, right, left)
    tg = np.asarray(grf.getIndependentColumn())
    meas = osim.TimeSeriesTable(str(GRF_MOT))
    tm = np.asarray(meas.getIndependentColumn())
    sel = (tm >= t[0]) & (tm <= t[-1])
    mass = 75.337  # model total mass; weight for BW normalization
    bw = mass * 9.81

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    fig.suptitle("3D tracking seed vs Hamner subject01 (3.0 m/s, cycle 1)")

    ax = axes[0]
    ax.bar(range(len(KEY_COORDS)), [rms.get(k, np.nan) for k in KEY_COORDS], color="tab:blue")
    ax.set_xticks(range(len(KEY_COORDS)))
    ax.set_xticklabels([k.replace("_r", "").replace("_", "\n") for k in KEY_COORDS], fontsize=7)
    ax.set(title="Tracking RMS", ylabel="deg")

    for ax, comp, lab in ((axes[1], "vy", "vertical"), (axes[2], "vx", "fore-aft")):
        ax.plot(tm[sel], col(meas, f"R_ground_force_{comp}")[sel] / bw, "k-", lw=1.5, label="measured R")
        ax.plot(tg, col(grf, f"ground_force_r_{comp}") / bw, "-", color="tab:red", label="model R")
        ax.plot(tm[sel], col(meas, f"L_ground_force_{comp}")[sel] / bw, "k--", lw=1, alpha=0.5, label="measured L")
        ax.plot(tg, col(grf, f"ground_force_l_{comp}") / bw, "--", color="tab:orange", alpha=0.8, label="model L")
        ax.set(title=f"GRF {lab}", xlabel="time (s)", ylabel="BW")
        ax.legend(fontsize=7)

    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"wrote {OUT}")

    fy_r = col(grf, "ground_force_r_vy")
    on = fy_r > 0.05 * bw
    stride_T = tg[-1] - tg[0]
    print(f"stride {stride_T:.3f}s  step_freq {2/stride_T:.2f}Hz  "
          f"t_c {on.mean()*stride_T:.3f}s  peak {fy_r.max()/bw:.2f}BW")


if __name__ == "__main__":
    main()
