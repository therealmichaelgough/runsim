"""Plot the Phase-0 predictive 2D walking solution: joint angles + GRFs."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import opensim as osim

RUN_DIR = Path(__file__).resolve().parent.parent / "experiments" / "phase0_2dwalking"


def sto_to_arrays(path: Path):
    table = osim.TimeSeriesTable(str(path))
    time = np.asarray(table.getIndependentColumn())
    cols = list(table.getColumnLabels())
    data = {c: table.getDependentColumn(c).to_numpy() for c in cols}
    return time, data


def main() -> None:
    t_pred, pred = sto_to_arrays(RUN_DIR / "gaitPrediction_solution_fullStride.sto")
    t_grf, grf = sto_to_arrays(RUN_DIR / "gaitPrediction_solutionGRF_fullStride.sto")
    pct = 100 * (t_pred - t_pred[0]) / (t_pred[-1] - t_pred[0])
    pct_grf = 100 * (t_grf - t_grf[0]) / (t_grf[-1] - t_grf[0])

    fig, axes = plt.subplots(2, 2, figsize=(10, 6.5))
    fig.suptitle("Phase 0: fully predictive 2D walking (Moco, no tracking data)")

    ang = {
        "hip flexion": "/jointset/hip_r/hip_flexion_r/value",
        "knee angle": "/jointset/knee_r/knee_angle_r/value",
        "ankle angle": "/jointset/ankle_r/ankle_angle_r/value",
    }
    for name, key in ang.items():
        axes[0, 0].plot(pct, np.degrees(pred[key]), label=name)
    axes[0, 0].set(title="Right-leg joint angles", xlabel="% gait cycle", ylabel="deg")
    axes[0, 0].legend(fontsize=8)

    axes[0, 1].plot(pct_grf, grf["ground_force_r_vy"], label="right")
    axes[0, 1].plot(pct_grf, grf["ground_force_l_vy"], label="left")
    axes[0, 1].set(title="Vertical GRF", xlabel="% gait cycle", ylabel="N")
    axes[0, 1].legend(fontsize=8)

    axes[1, 0].plot(pct_grf, grf["ground_force_r_vx"], label="right")
    axes[1, 0].plot(pct_grf, grf["ground_force_l_vx"], label="left")
    axes[1, 0].set(title="Fore-aft GRF", xlabel="% gait cycle", ylabel="N")
    axes[1, 0].legend(fontsize=8)

    muscles = [c for c in pred if c.endswith("/activation") and "_r" in c]
    for key in muscles:
        label = key.split("/")[1].replace("_r", "")
        axes[1, 1].plot(pct, pred[key], label=label, lw=1)
    axes[1, 1].set(title="Right-leg muscle activations", xlabel="% gait cycle", ylabel="activation")
    axes[1, 1].legend(fontsize=6, ncol=2)

    fig.tight_layout()
    out = RUN_DIR / "phase0_prediction_summary.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
