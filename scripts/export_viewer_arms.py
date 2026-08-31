"""Bake the arm-swing layer for the web run viewer.

From the validated 3D seed's stations (export_seed3d_stations.py), store
per-phase arm-chain offsets (shoulder/elbow/wrist per side) relative to
the 3D neck station, phase-rolled so the arm cycle aligns with the 2D
gaits' event convention (cross-correlation of ankle_l forward position
against the flat 3.0 m/s gait, same method as export_ue_gaits.align_phase).
The viewer anchors these offsets at its 2D shoulder point, phase-locked
to whatever gait blend is active.

Output: scripts/viewer_arms.json
"""
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SEED = HERE / "seed3d_stations.json"
GAITS = HERE / "viewer_gaits.json"
OUT = HERE / "viewer_arms.json"


def main() -> None:
    seed = json.loads(SEED.read_text())
    gaits = json.loads(GAITS.read_text())
    s3 = {n: i for i, n in enumerate(seed["stations"])}
    v3 = next(g for g in gaits["gaits"] if g["speed"] == 3.0 and g["grade"] == 0
              and "_met" in g["src"])
    s2 = {n: i for i, n in enumerate(gaits["stations"])}
    assert seed["nframes"] == gaits["nframes"]

    def sig(frames, idx):
        a = np.array([f[idx][0] for f in frames], dtype=float)
        return a - a.mean()

    a = sig(seed["frames"], s3["ankle_l"])
    b = sig(v3["frames"], s2["ankle_l"])
    shift = int(np.argmax([float(np.dot(np.roll(a, -k), b))
                           for k in range(len(a))]))
    rolled = seed["frames"][shift:] + seed["frames"][:shift]

    frames = []
    for f in rolled:
        neck = np.array(f[s3["neck"]])
        row = []
        for side in ("l", "r"):
            for joint in ("shoulder", "elbow", "wrist"):
                p = np.array(f[s3[f"{joint}_{side}"]]) - neck
                row.append([round(float(p[0]), 4), round(float(p[1]), 4)])
        frames.append(row)

    OUT.write_text(json.dumps({
        "src": seed["src"], "note": "offsets from 3D neck; l then r; "
        "shoulder/elbow/wrist", "shift": shift, "frames": frames,
    }, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB, shift={shift})")


if __name__ == "__main__":
    main()
