"""Validate transverse-plane (vertical-axis) angular momentum — arm swing —
against Hamner & Delp 2013.

Hamner & Delp (2013), "Muscle contributions to fore-aft and vertical body
mass center accelerations over a range of running speeds", J Biomech
46(4):780-787 (and Hamner, Seth & Delp 2010, J Biomech 43:2709-2716),
report that during running at ~3 m/s the arms swing out of phase with the
legs and their vertical-axis angular momentum about the body's center of
mass counterbalances the majority of the legs' vertical angular momentum,
keeping whole-body vertical angular momentum small.

This script computes, over one gait cycle, the vertical (y-axis, i.e.
transverse-plane) angular momentum about the whole-body COM, decomposed
into segment groups:

  arms  = humerus + ulna + radius + hand   (both sides)
  legs  = femur + tibia + patella + talus + calcn + toes  (both sides;
          patella is included with the leg it belongs to — it is not in
          the task's canonical list but carries ~0.09 kg each and belongs
          physically to the leg)
  trunk = pelvis + torso
  total = every body in the model

for three motions on the same subject01-scaled LaiUhlrich2022 model
(experiments/phase3_3drunning/lai_running_model.osim):

  1. tracked seed        experiments/phase3_3drunning/seed3d_tracking.sto
  2. predicted gait      experiments/phase3_3drunning/solution_p3d_v3_gp0.sto
                         (converged 3D predictive solve, effort objective)
  3. measured reference  the Hamner subject01 RRA cycle-1 states
                         (data/raw/hamner2013/...) retargeted onto the model
                         via runsim.tier3.retarget.retarget_states (carries
                         coordinate speeds, so body velocities are defined)

Method (documented per project convention): for each state the model is
realized to Velocity stage and the angular momentum of each body about the
whole-body COM is

    L_b = m_b (r_b - r_com) x (v_b - v_com)  +  (R_b I_b R_b^T) w_b

with r_b/v_b the body mass-center position/velocity in ground,
I_b the body-frame central inertia, R_b the body-to-ground rotation and
w_b the body angular velocity in ground. The sum over all bodies is
verified against SimTK's calcSystemCentralMomentum at every frame.

Curves are phase-aligned to right-foot strike (descending crossing of the
right calcaneus height 2 cm above that motion's own minimum) and reported
vs % gait cycle. Figure: experiments/phase3_arm_momentum.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import opensim as osim

ROOT = Path(__file__).resolve().parent.parent
D3 = ROOT / "experiments" / "phase3_3drunning"
MODEL = D3 / "lai_running_model.osim"
SEED = D3 / "seed3d_tracking.sto"
PREDICTED = D3 / "solution_p3d_v3_gp0.sto"
RRA_CYCLE = (
    ROOT / "data" / "raw" / "hamner2013" / "subject01" / "rra_multipleSteps"
    / "RRA_Results_v191_Run_30002" / "RRA_Results_v191_Run_30002_cycle1"
    / "subject01_Run_30002_cycle1_states.sto"
)
OUT = ROOT / "experiments" / "phase3_arm_momentum.png"

GROUPS = {
    "arms": [f"{seg}_{side}" for seg in ("humerus", "ulna", "radius", "hand")
             for side in ("r", "l")],
    "legs": [f"{seg}_{side}" for seg in ("femur", "tibia", "patella", "talus",
                                         "calcn", "toes")
             for side in ("r", "l")],
    "trunk": ["pelvis", "torso"],
}

N_PHASE = 101  # resampled points per cycle


def vec3(v) -> np.ndarray:
    return np.array([v.get(0), v.get(1), v.get(2)])


def body_constants(model: osim.Model):
    """Per-body (mass, mass center in body frame, central inertia 3x3)."""
    out = {}
    bs = model.getBodySet()
    for i in range(bs.getSize()):
        b = bs.get(i)
        I = b.getInertia()
        m = vec3(I.getMoments())
        p = vec3(I.getProducts())  # (xy, xz, yz)
        I3 = np.array([[m[0], p[0], p[1]],
                       [p[0], m[1], p[2]],
                       [p[1], p[2], m[2]]])
        out[b.getName()] = (b.getMass(), b.getMassCenter(), I3)
    return out


def angular_momentum_y(model: osim.Model, traj: osim.StatesTrajectory):
    """Vertical angular momentum about the whole-body COM, per body group.

    Returns (t, {group: L_y array}, calcn_r_height array). The per-body sum
    is asserted against SimTK's calcSystemCentralMomentum (<1e-6 relative).
    """
    consts = body_constants(model)
    bs = model.getBodySet()
    names = list(consts)
    n = traj.getSize()
    t = np.empty(n)
    per_body = {name: np.empty(n) for name in names}
    calcn_h = np.empty(n)
    matter = model.getMatterSubsystem()
    for k in range(n):
        s = traj.get(k)
        model.realizeVelocity(s)
        t[k] = s.getTime()
        com = vec3(model.calcMassCenterPosition(s))
        vcom = vec3(model.calcMassCenterVelocity(s))
        total = np.zeros(3)
        for name in names:
            mass, mc, I3 = consts[name]
            b = bs.get(name)
            r = vec3(b.findStationLocationInGround(s, mc))
            v = vec3(b.findStationVelocityInGround(s, mc))
            w = vec3(b.getVelocityInGround(s).get(0))
            R = b.getTransformInGround(s).R()
            Rm = np.array([[R.get(i, j) for j in range(3)] for i in range(3)])
            L = mass * np.cross(r - com, v - vcom) + Rm @ I3 @ Rm.T @ w
            per_body[name][k] = L[1]
            total += L
        ref = vec3(matter.calcSystemCentralMomentum(s).get(0))
        assert np.allclose(total, ref, atol=1e-6 * max(1.0, np.abs(ref).max())), \
            f"frame {k}: per-body momentum sum {total} != SimTK central momentum {ref}"
        calcn_h[k] = bs.get("calcn_r").getPositionInGround(s).get(1)

    groups = {g: sum(per_body[n] for n in members)
              for g, members in GROUPS.items()}
    groups["total"] = sum(per_body[n] for n in names)
    return t, groups, calcn_h


def right_foot_strike(t: np.ndarray, calcn_h: np.ndarray) -> float:
    """Time of the first descending crossing of (min height + 2 cm)."""
    thr = calcn_h.min() + 0.02
    below = calcn_h < thr
    for k in range(1, len(t)):
        if below[k] and not below[k - 1]:
            # linear interp of the crossing
            f = (thr - calcn_h[k - 1]) / (calcn_h[k] - calcn_h[k - 1])
            return float(t[k - 1] + f * (t[k] - t[k - 1]))
    return float(t[0])


def to_cycle(t: np.ndarray, y: np.ndarray, t_rs: float) -> np.ndarray:
    """Resample a (periodic) trace onto N_PHASE points of the gait cycle
    starting at right-foot strike t_rs (wrapping around the cycle end)."""
    T = t[-1] - t[0]
    phase = ((t - t_rs) / T) % 1.0
    order = np.argsort(phase)
    ph, yy = phase[order], y[order]
    grid = np.linspace(0, 1, N_PHASE)
    return np.interp(grid, np.concatenate([ph - 1, ph, ph + 1]),
                     np.concatenate([yy, yy, yy]))


def load_traj(model: osim.Model, path: Path, kind: str,
              decimate: int = 10) -> osim.StatesTrajectory:
    if kind == "moco":
        # keep the MocoTrajectory alive until the table has been consumed —
        # letting the temporary die can leave the exported table dangling
        sol = osim.MocoTrajectory(str(path))
        table = sol.exportToStatesTable()
    else:  # retargeted RRA reference (values + speeds)
        from runsim.tier3.retarget import retarget_states
        table = retarget_states(path, model, decimate=decimate)
        # createFromStatesTable sets missing states to NaN. The retargeted
        # table lacks the knee_angle_*_beta (patellofemoral) columns:
        # assembly projects the beta *positions* onto the coupler
        # constraint, but the beta *speeds* would stay NaN and poison the
        # patella momentum. Pad them with zeros — the patella is ~0.09 kg,
        # so the velocity-level coupling error is negligible.
        have = set(table.getColumnLabels())
        coords = model.getCoordinateSet()
        zeros = osim.Vector(int(table.getNumRows()), 0.0)
        for i in range(coords.getSize()):
            p = coords.get(i).getAbsolutePathString()
            for suffix in ("value", "speed"):
                if f"{p}/{suffix}" not in have:
                    table.appendColumn(f"{p}/{suffix}", zeros)
    traj = osim.StatesTrajectory.createFromStatesTable(
        model, table, True, True, True)  # allowMissing, allowExtra, assemble
    return traj


def analyze(model: osim.Model, path: Path, kind: str, decimate: int = 10):
    """One motion -> dict with phase-aligned group traces and metrics."""
    traj = load_traj(model, path, kind, decimate=decimate)
    t, groups, calcn_h = angular_momentum_y(model, traj)
    t_rs = right_foot_strike(t, calcn_h)
    cyc = {g: to_cycle(t, y, t_rs) for g, y in groups.items()}
    arms, legs = cyc["arms"], cyc["legs"]
    pp = {g: float(np.ptp(y)) for g, y in cyc.items()}
    return {
        "stride_T": float(t[-1] - t[0]),
        "cycle": cyc,
        "pp": pp,
        "corr_arms_legs": float(np.corrcoef(arms, legs)[0, 1]),
        "arms_over_legs": pp["arms"] / pp["legs"],
        "uncancelled": float(np.ptp(arms + legs)) / pp["legs"],
    }


def main() -> None:
    model = osim.Model(str(MODEL))
    model.initSystem()

    motions = {
        "tracked seed": (SEED, "moco"),
        "predicted (effort)": (PREDICTED, "moco"),
        "measured (Hamner RRA)": (RRA_CYCLE, "rra"),
    }
    res = {label: analyze(model, path, kind)
           for label, (path, kind) in motions.items()}

    ref = res["measured (Hamner RRA)"]
    print("\nVertical angular momentum about whole-body COM (kg m^2/s), "
          "one gait cycle from right-foot strike")
    print(f"{'motion':<22}{'pp arms':>9}{'pp legs':>9}{'pp trunk':>9}"
          f"{'pp total':>9}{'arms/legs':>10}{'corr':>7}{'uncanc':>8}")
    for label, r in res.items():
        print(f"{label:<22}{r['pp']['arms']:>9.3f}{r['pp']['legs']:>9.3f}"
              f"{r['pp']['trunk']:>9.3f}{r['pp']['total']:>9.3f}"
              f"{r['arms_over_legs']:>10.2f}{r['corr_arms_legs']:>7.2f}"
              f"{r['uncancelled']:>8.2f}")

    print("\nvs measured reference:")
    for label in ("tracked seed", "predicted (effort)"):
        r = res[label]
        amp = {g: r["pp"][g] / ref["pp"][g] for g in ("arms", "legs", "total")}
        # phase lag of the arms trace vs the reference arms trace
        a, b = r["cycle"]["arms"], ref["cycle"]["arms"]
        a0, b0 = a - a.mean(), b - b.mean()
        xc = [np.dot(np.roll(a0, -s), b0) for s in range(N_PHASE)]
        lag = int(np.argmax(xc))
        lag = lag - N_PHASE if lag > N_PHASE // 2 else lag
        print(f"  {label:<20} arm amp x{amp['arms']:.2f}  leg amp x{amp['legs']:.2f}  "
              f"total amp x{amp['total']:.2f}  arm phase lag {lag:+d}% cycle")

    # ---- figure ----
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.2))
    fig.suptitle("Vertical-axis angular momentum about COM over the gait cycle "
                 "(3.0 m/s) — arm swing vs Hamner & Delp 2013")
    grid = np.linspace(0, 100, N_PHASE)
    colors = {"arms": "tab:red", "legs": "tab:blue",
              "trunk": "tab:green", "total": "k"}
    ymax = 1.05 * max(np.abs(y).max() for r in res.values()
                      for y in r["cycle"].values())
    for ax, (label, r) in zip(axes, res.items()):
        for g in ("arms", "legs", "trunk", "total"):
            ax.plot(grid, r["cycle"][g], color=colors[g],
                    lw=2 if g == "total" else 1.5, label=g)
        ax.axhline(0, color="gray", lw=0.5)
        ax.set(title=label, xlabel="% gait cycle (from R foot strike)",
               ylim=(-ymax, ymax))
        ax.legend(fontsize=7)
    axes[0].set_ylabel("L$_y$ about COM (kg m$^2$/s)")

    ax = axes[3]
    labels = list(res)
    x = np.arange(len(labels))
    w = 0.2
    for i, g in enumerate(("arms", "legs", "trunk", "total")):
        ax.bar(x + (i - 1.5) * w, [res[l]["pp"][g] for l in labels], w,
               color=colors[g], label=g)
    ax.set_xticks(x)
    ax.set_xticklabels(["seed", "predicted", "measured"], fontsize=8)
    ax.set(title="peak-to-peak amplitude", ylabel="kg m$^2$/s")
    ax.legend(fontsize=7)

    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
