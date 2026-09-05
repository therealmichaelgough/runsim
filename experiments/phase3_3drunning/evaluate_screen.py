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
STATE_BOUNDS = {  # deg, mirrors predict3d._set_running_bounds (grade 0)
    "pelvis_tilt": (-35, 15), "pelvis_list": (-15, 15), "pelvis_rotation": (-30, 30),
    "hip_flexion": (-25, 85), "hip_adduction": (-30, 25), "hip_rotation": (-30, 30),
    "knee_angle": (0, 120), "ankle_angle": (-40, 50),
    "lumbar_extension": (-35, 10), "lumbar_bending": (-20, 20),
    "lumbar_rotation": (-25, 25), "arm_flex": (-90, 60), "arm_add": (-60, 30),
    "arm_rot": (-90, 60), "elbow_flex": (30, 150), "pro_sup": (0, 120),
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


#: torque actuator -> the coordinate it drives (for power = u * F * qdot)
ACTUATOR_COORD = {
    "lumbar_ext": "/jointset/back/lumbar_extension", "lumbar_bend": "/jointset/back/lumbar_bending",
    "lumbar_rot": "/jointset/back/lumbar_rotation",
    "shoulder_flex_r": "/jointset/acromial_r/arm_flex_r", "shoulder_add_r": "/jointset/acromial_r/arm_add_r",
    "shoulder_rot_r": "/jointset/acromial_r/arm_rot_r", "elbow_flex_r": "/jointset/elbow_r/elbow_flex_r",
    "pro_sup_r": "/jointset/radioulnar_r/pro_sup_r",
    "shoulder_flex_l": "/jointset/acromial_l/arm_flex_l", "shoulder_add_l": "/jointset/acromial_l/arm_add_l",
    "shoulder_rot_l": "/jointset/acromial_l/arm_rot_l", "elbow_flex_l": "/jointset/elbow_l/elbow_flex_l",
    "pro_sup_l": "/jointset/radioulnar_l/pro_sup_l",
}
MASS = 75.16


def solution_metrics(sto: Path, torque_weight: float,
                     strength: dict | None = None, power_weight: float | None = None,
                     power_on: tuple | None = None,
                     torque_price: float | None = None) -> dict:
    """torque_price (per (N.m)^2) makes each actuator's control weight
    price * F^2, as predict3d does; otherwise torque_weight applies to all."""
    import opensim as osim
    traj = osim.MocoTrajectory(str(sto))
    t = traj.getTime().to_numpy()
    tx = traj.getState("/jointset/ground_pelvis/pelvis_tx/value").to_numpy()
    disp = float(tx[-1] - tx[0])

    def optimal_force(name: str) -> float:
        for prefix, value in (strength or {}).items():
            if name.startswith(prefix):
                return float(value)
        return 10.0
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
    torque_rms = {}      # control rms (activation-like)
    torque_nm_rms = {}   # actual torque rms, N.m
    power_term = 0.0     # squared-power goal value, J/kg/m units
    power_w_rms = {}     # mechanical power rms, W (priced actuators)
    for name in traj.getControlNames():
        u = traj.getControl(name).to_numpy()
        integ = float(np.trapezoid(u * u, t))
        short = name.split("/")[-1]
        if any(k in name for k in TORQUE_KEYS):
            F = optimal_force(short)
            It += integ * ((torque_price * F * F / torque_weight) if torque_price is not None and torque_weight else 1.0)
            torque_rms[short] = round(float(np.sqrt(np.mean(u * u))), 3)
            torque_nm_rms[short] = round(float(np.sqrt(np.mean(u * u))) * F, 1)
            if power_weight is not None and short in ACTUATOR_COORD and (
                    power_on is None or short.startswith(tuple(power_on))):
                qdot = traj.getState(ACTUATOR_COORD[short] + "/speed").to_numpy()
                p = u * F * qdot
                power_term += power_weight * float(np.trapezoid(p * p, t)) / (MASS * disp)
                power_w_rms[short] = round(float(np.sqrt(np.mean(p * p))), 1)
        else:
            Im += integ
    return {
        "pinned_coords": pinned, "n_pinned": len(pinned),
        "muscle_effort": round(0.1 * Im / disp, 4),
        "torque_effort": round(0.1 * torque_weight * It / disp, 4),
        "power_term": round(power_term, 4),
        "torque_rms_top": dict(sorted(torque_rms.items(), key=lambda kv: -kv[1])[:5]),
        "torque_Nm_rms_top": dict(sorted(torque_nm_rms.items(), key=lambda kv: -kv[1])[:5]),
        "power_W_rms": power_w_rms,
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
                w = r.get("torque_weight", torque_weight) or 0.0
                m = solution_metrics(sol, w, r.get("actuator_strength"),
                                     r.get("torque_power_weight"),
                                     tuple(r["torque_power_actuators"]) if r.get("torque_power_actuators") else None,
                                     r.get("torque_price_per_nm2"))
                m["met"] = round(r["objective"] - m["muscle_effort"] - m["torque_effort"] - m["power_term"], 4)
                out.update(m)
        print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 50.0)
