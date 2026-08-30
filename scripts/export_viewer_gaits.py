"""Bake Moco full-stride solutions into a compact JSON for the run viewer.

For each solution, poses the 2D_gait model at N uniformly-spaced phases of
the stride and records ground-frame 2D positions of the skeleton stations
(exact OpenSim forward kinematics — nothing re-derived downstream), plus
stride time/length and available cost-of-transport. Positions are stored
relative to the pelvis x of each frame so the viewer can advance the
runner along terrain without baked-in drift.

Output: scripts/viewer_gaits.json (consumed by build_run_viewer.py).
"""
import json
import math
from pathlib import Path

import numpy as np
import opensim as osim

ROOT = Path(__file__).resolve().parent.parent
RUN2D = ROOT / "experiments" / "phase3_2drunning"
MODEL = ROOT / "experiments" / "phase0_2dwalking" / "2D_gait.osim"
OUT = Path(__file__).resolve().parent / "viewer_gaits.json"
NFRAMES = 48

# (station name, body, location in body frame) — 2D sagittal view (x, y)
STATIONS = [
    ("head", "torso", (0.02, 0.52, 0.0)),
    ("shoulder", "torso", (0.0, 0.32, 0.0)),
    ("lumbar", "torso", (0.0, 0.0, 0.0)),
    ("pelvis", "pelvis", (0.0, 0.0, 0.0)),
    ("hip_l", "femur_l", (0.0, 0.0, 0.0)),
    ("knee_l", "tibia_l", (0.0, 0.0, 0.0)),
    ("ankle_l", "talus_l", (0.0, 0.0, 0.0)),
    ("heel_l", "calcn_l", (0.0313, 0.0104, 0.0)),
    ("toe_l", "calcn_l", (0.1774, -0.0157, 0.0)),
    ("hip_r", "femur_r", (0.0, 0.0, 0.0)),
    ("knee_r", "tibia_r", (0.0, 0.0, 0.0)),
    ("ankle_r", "talus_r", (0.0, 0.0, 0.0)),
    ("heel_r", "calcn_r", (0.0313, 0.0104, 0.0)),
    ("toe_r", "calcn_r", (0.1774, -0.0157, 0.0)),
]

DEG = math.pi / 180
GAITS = [
    # (fullstride file, speed m/s, grade, cot or None)
    ("fullstride_v1_2_gp0.sto", 1.2, 0.0, None),
    ("fullstride_v2_gp0.sto", 2.0, 0.0, None),
    ("fullstride_v2_5_gp0_met.sto", 2.5, 0.0, 3.370),
    ("fullstride_v3_gp0_met.sto", 3.0, 0.0, 3.490),
    ("fullstride_v3_5_gp0_met.sto", 3.5, 0.0, 3.741),
    ("fullstride_v4_gp0_met.sto", 4.0, 0.0, 4.317),
    ("fullstride_v4_5_gp0_met.sto", 4.5, 0.0, 5.454),
    ("fullstride_v5_gp0_met.sto", 5.0, 0.0, 6.298),
    ("fullstride_v3_gp0_0524078_met.sto", 3.0, math.tan(3 * DEG), 3.87),
    ("fullstride_v3_gp0_105104_met.sto", 3.0, math.tan(6 * DEG), 4.55),
    ("fullstride_v3_gp0_158384_met.sto", 3.0, math.tan(9 * DEG), 5.44),
    ("fullstride_v3_gm0_0524078_met.sto", 3.0, -math.tan(3 * DEG), 3.25),
    ("fullstride_v3_gm0_105104_met.sto", 3.0, -math.tan(6 * DEG), 2.94),
    ("fullstride_v3_gm0_158384_met.sto", 3.0, -math.tan(9 * DEG), 2.80),
]


def export_gait(model, state, path: Path):
    table = osim.TimeSeriesTable(str(path))
    labels = [l for l in table.getColumnLabels() if l.endswith("/value")]
    t = np.asarray(table.getIndependentColumn())
    data = {lab: table.getDependentColumn(lab).to_numpy() for lab in labels}
    coords = model.getCoordinateSet()
    phases = np.linspace(t[0], t[-1], NFRAMES, endpoint=False)

    tx_lab = next(l for l in labels if "pelvis_tx" in l)
    frames = []
    for tk in phases:
        for i in range(coords.getSize()):
            c = coords.get(i)
            lab = f"{c.getAbsolutePathString()}/value"
            if lab in data:
                c.setValue(state, float(np.interp(tk, t, data[lab])), False)
        model.assemble(state)
        model.realizePosition(state)
        px = float(np.interp(tk, t, data[tx_lab]))
        pts = []
        for _, body, loc in STATIONS:
            p = model.getBodySet().get(body).findStationLocationInGround(
                state, osim.Vec3(*loc))
            pts.append([round(p.get(0) - px, 4), round(p.get(1), 4)])
        frames.append(pts)

    return {
        "strideTime": round(float(t[-1] - t[0]), 5),
        "strideLen": round(float(data[tx_lab][-1] - data[tx_lab][0]), 4),
        "frames": frames,
    }


def main() -> None:
    model = osim.Model(str(MODEL))
    state = model.initSystem()
    gaits = []
    for fname, speed, grade, cot in GAITS:
        path = RUN2D / fname
        if not path.exists():
            print(f"skip (missing): {fname}")
            continue
        g = export_gait(model, state, path)
        g.update(speed=speed, grade=round(grade, 5), cot=cot, src=fname)
        gaits.append(g)
        print(f"{fname}: strideTime={g['strideTime']}s strideLen={g['strideLen']}m")
    out = {"stations": [s[0] for s in STATIONS], "nframes": NFRAMES, "gaits": gaits}
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB, {len(gaits)} gaits)")


if __name__ == "__main__":
    main()
