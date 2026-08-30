"""Bake a 3D (LaiUhlrich) Moco solution's skeleton stations to JSON for
the web renderers — sagittal (x, y) projection, same station approach as
export_viewer_gaits.py but with arms. Usage:

    export_seed3d_stations.py <solution.sto> <out.json>
"""
import json
import sys
from pathlib import Path

import numpy as np
import opensim as osim

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "experiments" / "phase3_3drunning" / "lai_running_model.osim"
NFRAMES = 48

STATIONS = [
    ("head", "torso", (0.0, 0.55, 0.0)),
    ("shoulder_l", "humerus_l", (0.0, 0.0, 0.0)),
    ("elbow_l", "ulna_l", (0.0, 0.0, 0.0)),
    ("wrist_l", "hand_l", (0.0, 0.0, 0.0)),
    ("shoulder_r", "humerus_r", (0.0, 0.0, 0.0)),
    ("elbow_r", "ulna_r", (0.0, 0.0, 0.0)),
    ("wrist_r", "hand_r", (0.0, 0.0, 0.0)),
    ("neck", "torso", (0.0, 0.35, 0.0)),
    ("lumbar", "torso", (0.0, 0.0, 0.0)),
    ("pelvis", "pelvis", (0.0, 0.0, 0.0)),
    ("hip_l", "femur_l", (0.0, 0.0, 0.0)),
    ("knee_l", "tibia_l", (0.0, 0.0, 0.0)),
    ("ankle_l", "talus_l", (0.0, 0.0, 0.0)),
    ("heel_l", "calcn_l", (0.0313, 0.0104, 0.0)),
    ("toe_l", "toes_l", (0.055, -0.010, 0.010)),
    ("hip_r", "femur_r", (0.0, 0.0, 0.0)),
    ("knee_r", "tibia_r", (0.0, 0.0, 0.0)),
    ("ankle_r", "talus_r", (0.0, 0.0, 0.0)),
    ("heel_r", "calcn_r", (0.0313, 0.0104, 0.0)),
    ("toe_r", "toes_r", (0.055, -0.010, -0.010)),
]


def main() -> None:
    sol_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    model = osim.Model(str(MODEL))
    model.initSystem()
    sol = osim.MocoTrajectory(str(sol_path))
    st = sol.exportToStatesTable()
    t = np.asarray(st.getIndependentColumn())
    labels = list(st.getColumnLabels())
    data = {lab: st.getDependentColumn(lab).to_numpy()
            for lab in labels if lab.endswith("/value")}
    coords = model.getCoordinateSet()
    state = model.initSystem()
    tx_lab = next(l for l in data if "pelvis_tx" in l)

    phases = np.linspace(t[0], t[-1], NFRAMES, endpoint=False)
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

    out = {
        "stations": [s[0] for s in STATIONS],
        "nframes": NFRAMES,
        "strideTime": round(float(t[-1] - t[0]), 5),
        "strideLen": round(float(data[tx_lab][-1] - data[tx_lab][0]), 4),
        "frames": frames,
        "src": sol_path.name,
    }
    out_path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB); "
          f"strideTime={out['strideTime']}s strideLen={out['strideLen']}m")


if __name__ == "__main__":
    main()
