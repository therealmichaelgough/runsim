"""Compare the configurations of a screen_barrier.py run.

For every experiments/phase3_3drunning/screen/<name>/ with a run.log:
solver trace summary (iterations, objective, unscaled violation, deepest
barrier lg(mu), median primal step over the last 10 iterations,
restoration iterations, seconds per iteration) and, when the capped
solution exists, how hard the torque-driven coordinates lean on their
bounds and the objective split (met / muscle effort / torque effort).

Usage: evaluate_screen.py [torque_weight]   (default 50)
"""
import json
import math
import re
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SCREEN = HERE / "screen"
ITER_RE = re.compile(r"^ *(\d+)(r?) +(\S+) +(\S+) +(\S+) +(\S+) +(\S+) +(\S+) +(\S+) +(\S+)")
D2R = math.pi / 180
TORQUE_KEYS = ("lumbar", "shoulder", "elbow", "pro_sup")
STATE_BOUNDS = {  # deg, mirrors predict3d._set_running_bounds
    "lumbar_extension": (-35, 10), "lumbar_bending": (-20, 20),
    "lumbar_rotation": (-25, 25), "arm_flex": (-90, 60), "arm_add": (-60, 30),
    "arm_rot": (-90, 60), "elbow_flex": (30, 150), "pro_sup": (0, 120),
    "hip_rotation": (-30, 30), "knee_angle": (0, 120),
}


def trace(log: Path) -> dict:
    rows = [m for m in (ITER_RE.match(l) for l in log.read_text(errors="ignore").splitlines()) if m]
    if not rows:
        return {"iterations": 0}
    last = rows[-1]
    # groups: 1 iter, 2 r-flag, 3 obj, 4 inf_pr, 5 inf_du, 6 lg(mu), 7 ||d||,
    # 8 lg(rg), 9 alpha_du, 10 alpha_pr (with its h/f/... suffix)
    alphas = [float(re.sub(r"[a-zA-Z]+$", "", m.group(10))) for m in rows[-10:]]
    mus = [float(m.group(6)) for m in rows]
    st = log.stat()
    secs = (st.st_mtime - st.st_ctime) / max(1, int(last.group(1)))
    return {
        "iterations": int(last.group(1)), "objective": float(last.group(3)),
        "inf_pr": float(last.group(4)), "inf_du": float(last.group(5)),
        "min_lg_mu": min(mus), "alpha_med10": statistics.median(alphas),
        "restoration": sum(1 for m in rows if m.group(2)),
        "sec_per_iter": round(secs, 1),
    }


def solution_metrics(sto: Path, torque_weight: float) -> dict:
    import opensim as osim
    traj = osim.MocoTrajectory(str(sto))
    t = traj.getTime().to_numpy()
    tx = traj.getState("/jointset/ground_pelvis/pelvis_tx/value").to_numpy()
    disp = float(tx[-1] - tx[0])
    pinned = []
    for name in traj.getStateNames():
        if not name.endswith("/value"):
            continue
        for key, (lo, hi) in STATE_BOUNDS.items():
            if key in name:
                col = traj.getState(name).to_numpy() / D2R
                span = hi - lo
                gap = min(col.min() - lo, hi - col.max()) / span
                if gap < 0.01:
                    pinned.append(name.split("/")[-2])
                break
    Im = It = 0.0
    torque_rms = {}
    for name in traj.getControlNames():
        u = traj.getControl(name).to_numpy()
        integ = float(np.trapezoid(u * u, t))
        if any(k in name for k in TORQUE_KEYS):
            It += integ
            torque_rms[name.split("/")[-1]] = round(float(np.sqrt(np.mean(u * u))), 3)
        else:
            Im += integ
    return {
        "pinned_coords": pinned, "n_pinned": len(pinned),
        "muscle_effort": round(0.1 * Im / disp, 4),
        "torque_effort": round(0.1 * torque_weight * It / disp, 4),
        "torque_rms_top": dict(sorted(torque_rms.items(), key=lambda kv: -kv[1])[:5]),
    }


def main(torque_weight: float = 50.0) -> None:
    for run in sorted(p for p in SCREEN.iterdir() if (p / "run.log").exists()):
        out = {"name": run.name, **trace(run / "run.log")}
        res = run / "result.json"
        if res.exists():
            r = json.loads(res.read_text())
            out.update(final_objective=r.get("objective"), success=r.get("success"),
                       cot=r.get("cost_of_transport"), solve_min=r.get("solve_min"),
                       step_freq_hz=r.get("step_freq_hz"), peak_bw=r.get("peak_force_bw"))
            sol = run / r["solution"]
            if sol.exists():
                m = solution_metrics(sol, torque_weight)
                m["met"] = round(r["objective"] - m["muscle_effort"] - m["torque_effort"], 4)
                out.update(m)
        print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 50.0)
