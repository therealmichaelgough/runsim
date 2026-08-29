"""Play back a simulated gait in OpenSim's 3D visualizer.

Defaults to the Phase-0 predictive walking solution. Examples:

    .venv/bin/python scripts/watch_gait.py
    .venv/bin/python scripts/watch_gait.py --loops 10
    .venv/bin/python scripts/watch_gait.py \
        --model experiments/phase0_2dwalking/2D_gait.osim \
        --motion experiments/phase0_2dwalking/gaitTracking_solution_fullStride.sto

Controls in the visualizer window: drag to orbit, scroll to zoom.
Close the window (or Ctrl+C in the terminal) to exit.
"""
import argparse
from pathlib import Path

import numpy as np
import opensim as osim

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = REPO / "experiments" / "phase0_2dwalking" / "2D_gait.osim"
DEFAULT_MOTION = REPO / "experiments" / "phase0_2dwalking" / "gaitPrediction_solution_fullStride.sto"


def tile_strides(table: osim.TimeSeriesTable, loops: int) -> osim.TimeSeriesTable:
    """Repeat a single-stride states table `loops` times so playback lasts longer."""
    if loops <= 1:
        return table
    time = np.asarray(table.getIndependentColumn())
    labels = list(table.getColumnLabels())
    data = np.column_stack([table.getDependentColumn(c).to_numpy() for c in labels])
    stride_T = time[-1] - time[0]

    pelvis_tx = labels.index("/jointset/groundPelvis/pelvis_tx/value") if "/jointset/groundPelvis/pelvis_tx/value" in labels else None
    dx = data[-1, pelvis_tx] - data[0, pelvis_tx] if pelvis_tx is not None else 0.0

    out = osim.TimeSeriesTable()
    out.setColumnLabels(labels)
    for i in range(loops):
        # skip the duplicated first frame on repeats
        start = 0 if i == 0 else 1
        for k in range(start, len(time)):
            row = data[k].copy()
            if pelvis_tx is not None:
                row[pelvis_tx] += i * dx  # keep moving forward instead of teleporting back
            out.appendRow(float(time[k] + i * stride_T), osim.RowVector(row.tolist()))
    # the visualizer requires this metadata; Moco state solutions are radians
    in_degrees = "no"
    if "inDegrees" in table.getTableMetaDataKeys():
        in_degrees = table.getTableMetaDataAsString("inDegrees")
    out.addTableMetaDataString("inDegrees", in_degrees)
    return out


def play_following(model: osim.Model, table: osim.TimeSeriesTable, slow: float) -> None:
    """Play back states with the camera tracking the pelvis."""
    import time as _time

    model.setUseVisualizer(True)
    model.initSystem()
    traj = osim.StatesTrajectory.createFromStatesTable(model, table, True, True, True)
    viz = model.updVisualizer().updSimbodyVisualizer()
    viz.setCameraFieldOfView(0.9)
    viz.setShutdownWhenDestructed(True)  # close the window when playback ends

    tx_label = next(
        (lbl for lbl in table.getColumnLabels() if lbl.endswith("pelvis_tx/value")), None
    )
    tx = table.getDependentColumn(tx_label).to_numpy() if tx_label else None
    times = np.asarray(table.getIndependentColumn())
    for i in range(traj.getSize()):
        s = traj.get(i)
        model.realizePosition(s)
        if tx is not None:
            cam = osim.Transform(osim.Rotation(), osim.Vec3(float(tx[i]), 1.0, 3.5))
            viz.setCameraTransform(cam)
        model.getVisualizer().show(s)
        if i + 1 < len(times):
            _time.sleep(max(times[i + 1] - times[i], 0.0) / max(slow, 1e-3))
    viz.shutdown()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="model .osim file")
    ap.add_argument("--motion", type=Path, default=DEFAULT_MOTION, help="states .sto file (e.g. a Moco solution)")
    ap.add_argument("--loops", type=int, default=5, help="times to repeat the stride (default 5)")
    ap.add_argument("--no-follow", action="store_true",
                    help="use the classic showMotion window (free camera, replay controls)")
    ap.add_argument("--slow", type=float, default=0.5,
                    help="playback speed factor (1.0 = real time, default 0.5)")
    args = ap.parse_args()

    # let the visualizer find bone meshes shared across our models
    osim.ModelVisualizer.addDirToGeometrySearchPaths(
        str(REPO / "models" / "LaiUhlrich2022" / "Geometry")
    )
    model = osim.Model(str(args.model))
    table = osim.TimeSeriesTable(str(args.motion))
    table = tile_strides(table, args.loops)

    print(f"model:  {args.model.name}")
    print(f"motion: {args.motion.name}  ({table.getNumRows()} frames, "
          f"{table.getIndependentColumn()[-1]:.2f} s)")
    if args.no_follow:
        print("Opening visualizer... close the window to exit.")
        osim.VisualizerUtilities.showMotion(model, table)
    else:
        print("Opening visualizer with a following camera... playback ends when done.")
        play_following(model, table, slow=args.slow)


if __name__ == "__main__":
    main()
