"""Retarget Hamner 2013 (gait2392-lineage) running kinematics onto the
LaiUhlrich2022 (Rajagopal-lineage) coordinate set.

The two models share coordinate names almost 1:1; the conversions are:

- knee_angle_{r,l} sign flips (gait2392: negative = flexion; Rajagopal:
  positive = flexion, cf. Rajagopal 2016 supplementary model docs).
- Hamner wrist coordinates (wrist_flex/wrist_dev) have no LaiUhlrich
  counterpart and are dropped.
- LaiUhlrich's knee_angle_{r,l}_beta (patellofemoral coupling) and any
  other unmatched coordinate default to the model value (0) so the
  reference stays complete.

Input is an RRA states file (radians, flat column names, `<coord>_u`
speed columns) from data/raw/hamner2013/<subject>/rra_multipleSteps.
Output is a Moco states-reference TimeSeriesTable keyed by model state
paths (/jointset/.../value and /speed).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import opensim as osim

SIGN_FLIP = {"knee_angle_r", "knee_angle_l"}


def retarget_states(
    states_path: str | Path,
    model: osim.Model,
    decimate: int = 10,
    with_speeds: bool = True,
) -> osim.TimeSeriesTable:
    """Map an RRA states.sto onto `model`'s coordinate state paths.

    decimate: keep every Nth row (RRA states are stored at ~10 kHz).
    Returns a TimeSeriesTable whose columns are model state-variable
    paths, suitable for MocoTrack.setStatesReference.
    """
    src = osim.TimeSeriesTable(str(states_path))
    labels = list(src.getColumnLabels())
    t = np.asarray(src.getIndependentColumn())
    rows = np.arange(0, len(t), max(1, decimate))

    def col(name: str) -> np.ndarray | None:
        if name not in labels:
            return None
        return src.getDependentColumn(name).to_numpy()[rows]

    data: list[tuple[str, np.ndarray]] = []
    coords = model.getCoordinateSet()
    for i in range(coords.getSize()):
        c = coords.get(i)
        name = c.getName()
        sign = -1.0 if name in SIGN_FLIP else 1.0
        q = col(name)
        if q is None:
            continue
        path = c.getAbsolutePathString()
        data.append((f"{path}/value", sign * q))
        if with_speeds:
            u = col(f"{name}_u")
            if u is not None:
                data.append((f"{path}/speed", sign * u))

    if not data:
        raise ValueError(f"no matching coordinate columns found in {states_path}")

    out = osim.TimeSeriesTable()
    for i, k in enumerate(rows):
        row = osim.RowVector(len(data), 0.0)
        for j, (_, values) in enumerate(data):
            row[j] = float(values[i])
        out.appendRow(float(t[k]), row)
    out.setColumnLabels([label for label, _ in data])
    out.addTableMetaDataString("inDegrees", "no")
    return out


def ground_reference(
    table: osim.TimeSeriesTable,
    model: osim.Model,
    clearance: float = 0.024,
) -> float:
    """Shift the pelvis_ty reference so the lowest stance foot reaches
    contact height. Retargeting onto an unscaled model leaves a
    limb-length gap (feet floating ~0.1 m); the smooth contact force has
    near-zero gradient at that distance, so a tracking solve otherwise
    converges to a ballistic, contact-free gait. clearance is the calcn
    height at which the heel sphere touches the floor. Returns the drop
    applied (m)."""
    state = model.initSystem()
    labels = list(table.getColumnLabels())
    coords = model.getCoordinateSet()
    lowest = np.inf
    for i in range(table.getNumRows()):
        row = table.getRowAtIndex(i)
        for k in range(coords.getSize()):
            c = coords.get(k)
            lab = f"{c.getAbsolutePathString()}/value"
            if lab in labels:
                c.setValue(state, float(row[labels.index(lab)]), False)
        model.assemble(state)
        model.realizePosition(state)
        for body in ("calcn_l", "calcn_r"):
            lowest = min(lowest, model.getBodySet().get(body)
                         .getPositionInGround(state).get(1))
    drop = lowest - clearance
    ty = next(lab for lab in labels if "pelvis_ty/value" in lab)
    j = labels.index(ty)
    for i in range(table.getNumRows()):
        table.getRowAtIndex(i)[j] -= drop
    return drop


def write_states_reference(
    states_path: str | Path,
    model: osim.Model,
    out_path: str | Path,
    decimate: int = 10,
    ground: bool = True,
    clearance: float = 0.013,
) -> Path:
    """clearance: target calcn height at the deepest stance frame. The
    default 0.013 m sinks the heel sphere ~1.2 cm into the floor, where
    the smooth contact produces ~2.6 BW at the deepest stance pose —
    matching the measured peak, so the guess itself carries running-scale
    support. A grazing reference (clearance ~0.024, sphere just touching)
    leaves the guess force-free, and tracking + dynamics then settle on a
    ballistic gait (two rejected solves, see AGENTS_LOG 2026-08-30)."""
    table = retarget_states(states_path, model, decimate=decimate)
    if ground:
        drop = ground_reference(table, model, clearance=clearance)
        print(f"[retarget] grounded reference: pelvis_ty shifted by {-drop:+.3f} m "
              f"(clearance {clearance} m)")
    osim.STOFileAdapter.write(table, str(out_path))
    return Path(out_path)
