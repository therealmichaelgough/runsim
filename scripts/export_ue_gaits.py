"""Bake Moco full-stride solutions into per-body rigid transforms for the
Unreal Engine renderer (docs/unreal_renderer_plan.md, section 1).

Where ``export_viewer_gaits.py`` bakes 2D *stations* for the canvas viewer,
this bakes full 3D **per-body world transforms** (position + quaternion in
the ground frame) plus the capsule dimensions needed to draw one primitive
per body segment.  Positions are stored relative to the frame's
``pelvis_tx`` so the engine can advance the runner along terrain without
baked-in drift (same looping convention as the web viewer).

Coordinate conversion (done here so the UE side stays dumb):

    OpenSim  right-handed, y-up, metres
    Unreal   left-handed, z-up, centimetres

    position   (x, y, z)_osim -> (100x, 100z, 100y)_ue
    rotation   R_ue = M R_osim M^T   with M = swap(y, z), det(M) = -1
               which in quaternions is (w, x, y, z) -> (w, -x, -z, -y),
               i.e. the axis maps a -> -M a and the angle is unchanged
               (Q R(a,th) Q^T = R(det(Q) Q a, th) for orthogonal Q).

Quaternions are written in Unreal's component order ``[x, y, z, w]``.

v1 exports the 2D-sourced gaits only (the same 14 solutions as
``export_viewer_gaits.py``).  The segment table already carries the arm
segments; the 2D model has no arm bodies, so those segments resolve their
capsule dimensions from the LaiUhlrich model and are simply absent from
every 2D gait's body list.  See ``GAITS_3D`` below for the extension point.

Output: unreal/RunsimViewer/Content/Data/gaits_ue.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import opensim as osim

ROOT = Path(__file__).resolve().parent.parent
RUN2D = ROOT / "experiments" / "phase3_2drunning"
MODEL_2D = ROOT / "experiments" / "phase0_2dwalking" / "2D_gait.osim"
MODEL_3D = ROOT / "models" / "LaiUhlrich2022" / "LaiUhlrich2022.osim"
OUT = ROOT / "unreal" / "RunsimViewer" / "Content" / "Data" / "gaits_ue.json"

NFRAMES = 48
CM = 100.0  # metres -> Unreal units
DEG = math.pi / 180

# ---------------------------------------------------------------------------
# Segment table
#
# Each segment is one render primitive rigidly attached to one body.  ``prox``
# and ``dist`` are the capsule's end points *in the body frame*, given either
# as a literal (x, y, z) in metres, as ``("body", name)`` meaning "the origin
# of that body at the model's default pose" (i.e. a joint-to-joint distance),
# or as a per-model dict keyed by model tag.
#
# Dimensions are resolved from the first model in MODELS that owns every body
# the segment needs, so the leg/torso capsules come from the 2D model that
# produced the v1 gaits and the arms come from LaiUhlrich.
# ---------------------------------------------------------------------------

NEAR = [0.56, 0.78, 0.91]   # left limb  (bright, matches the web viewer)
FAR = [0.25, 0.37, 0.52]    # right limb (dim)
TRUNK = [0.50, 0.66, 0.81]

SEGMENTS = [
    dict(name="pelvis", body="pelvis", cls="pelvis", mesh="cylinder",
         prox=(0.0, 0.0, -0.085), dist=(0.0, 0.0, 0.085),
         radius=0.085, color=TRUNK),
    dict(name="torso", body="torso", cls="torso", mesh="cylinder",
         prox=(0.0, 0.0, 0.0),
         dist={"2d": (0.0, 0.32, 0.0), "3d": (0.0, 0.38, 0.0)},
         radius=0.105, color=TRUNK),
    dict(name="head", body="torso", cls="head", mesh="sphere",
         prox={"2d": (0.02, 0.42, 0.0), "3d": (0.0, 0.44, 0.0)},
         dist={"2d": (0.02, 0.60, 0.0), "3d": (0.0, 0.62, 0.0)},
         radius=0.085, color=TRUNK),

    dict(name="thigh_l", body="femur_l", cls="thigh", mesh="cylinder",
         prox=(0.0, 0.0, 0.0), dist=("body", "tibia_l"),
         radius=0.065, color=NEAR),
    dict(name="shank_l", body="tibia_l", cls="shank", mesh="cylinder",
         prox=(0.0, 0.0, 0.0), dist=("body", "talus_l"),
         radius=0.050, color=NEAR),
    dict(name="foot_l", body="calcn_l", cls="foot", mesh="cylinder",
         prox=(0.0, 0.01, 0.0), dist=("body", "toes_l"),
         radius=0.035, color=NEAR),

    dict(name="thigh_r", body="femur_r", cls="thigh", mesh="cylinder",
         prox=(0.0, 0.0, 0.0), dist=("body", "tibia_r"),
         radius=0.065, color=FAR),
    dict(name="shank_r", body="tibia_r", cls="shank", mesh="cylinder",
         prox=(0.0, 0.0, 0.0), dist=("body", "talus_r"),
         radius=0.050, color=FAR),
    dict(name="foot_r", body="calcn_r", cls="foot", mesh="cylinder",
         prox=(0.0, 0.01, 0.0), dist=("body", "toes_r"),
         radius=0.035, color=FAR),

    # --- extension point: 3D gaits with arms -------------------------------
    # These bodies do not exist on the 2D model, so 2D gaits omit them and
    # the renderer hides the segment.  Adding a 3D solution to GAITS_3D is
    # all that is needed to make them move.
    dict(name="upperarm_l", body="humerus_l", cls="upperarm", mesh="cylinder",
         prox=(0.0, 0.0, 0.0), dist=("body", "ulna_l"),
         radius=0.045, color=NEAR),
    dict(name="forearm_l", body="ulna_l", cls="forearm", mesh="cylinder",
         prox=(0.0, 0.0, 0.0), dist=("body", "hand_l"),
         radius=0.038, color=NEAR),
    dict(name="upperarm_r", body="humerus_r", cls="upperarm", mesh="cylinder",
         prox=(0.0, 0.0, 0.0), dist=("body", "ulna_r"),
         radius=0.045, color=FAR),
    dict(name="forearm_r", body="ulna_r", cls="forearm", mesh="cylinder",
         prox=(0.0, 0.0, 0.0), dist=("body", "hand_r"),
         radius=0.038, color=FAR),
]

# Plausible adult ranges (m) for the joint-to-joint capsule lengths; pinned by
# tests/test_ue_export.py.  Winter (2009), Biomechanics and Motor Control of
# Human Movement, Table 4.1 segment lengths for a 1.7-1.8 m adult.
HUMAN_LENGTH_RANGE_M = {
    "thigh": (0.33, 0.50),
    "shank": (0.33, 0.48),
    "foot": (0.12, 0.30),
    "torso": (0.25, 0.60),
    "upperarm": (0.24, 0.40),
    "forearm": (0.20, 0.36),
}

GAITS = [
    # (fullstride file, speed m/s, grade (tan of slope angle), cot or None)
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

# --- extension point: 3D gaits with arms -----------------------------------
# Entries: (solution .sto, speed, grade, cot).  Solutions are read with
# MocoTrajectory (they carry states, not a plain fullstride table) and posed
# on MODEL_3D, which owns the arm bodies.
# The validated attempt-5 tracking seed (obj 5.78, joints 3-10 deg RMS,
# GRFs at measured values — see AGENTS_LOG 2026-08-30). Serves as the arm
# source only: the renderer excludes 3D gaits from the speed/grade blends
# and grafts their arm bodies onto the blended pose, phase-aligned at
# export (frames rolled to the 2D flat-3.0 event convention).
GAITS_3D: list[tuple[str, float, float, float | None]] = [
    ("experiments/phase3_3drunning/seed3d_tracking.sto", 3.0, 0.0, None),
    # converged fully-predictive gait (Phase-3 finale milestone 1)
    ("experiments/phase3_3drunning/solution_p3d_v3_gp0.sto", 3.0, 0.0, None),
    # metabolic-objective predictive gait, formulation v12 (Phase-3 finale
    # milestone 2, 2026-09-05): restores human arm swing; muscle COT 2.9 J/kg/m
    ("experiments/phase3_3drunning/solution_p3d_v3_gp0_met_v12.sto", 3.0, 0.0, 2.9),
]


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------

# M swaps the y and z axes; det(M) = -1, which is the handedness flip.
AXIS_SWAP = np.array([[1.0, 0.0, 0.0],
                      [0.0, 0.0, 1.0],
                      [0.0, 1.0, 0.0]])


def osim_pos_to_ue(p) -> np.ndarray:
    """(x, y, z) metres, y-up right-handed -> (x, y, z) cm, z-up left-handed."""
    p = np.asarray(p, dtype=float)
    return np.array([p[0] * CM, p[2] * CM, p[1] * CM])


def osim_mat_to_ue(R: np.ndarray) -> np.ndarray:
    """Rotation matrix conjugated into the Unreal basis: R_ue = M R M^T."""
    return AXIS_SWAP @ np.asarray(R, dtype=float) @ AXIS_SWAP.T


def mat_to_quat(R: np.ndarray) -> np.ndarray:
    """Rotation matrix -> quaternion [x, y, z, w] (Hamilton, Shepperd's method)."""
    R = np.asarray(R, dtype=float)
    t = R[0, 0] + R[1, 1] + R[2, 2]
    if t > 0.0:
        s = math.sqrt(t + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    q = np.array([x, y, z, w])
    if q[3] < 0.0:  # keep the scalar part positive so slerp neighbours agree
        q = -q
    return q / np.linalg.norm(q)


def quat_to_mat(q) -> np.ndarray:
    """Quaternion [x, y, z, w] -> rotation matrix (Hamilton convention)."""
    x, y, z, w = (float(v) for v in q)
    n = math.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def osim_quat_to_ue(q_osim_wxyz) -> np.ndarray:
    """OpenSim quaternion (w, x, y, z) -> Unreal quaternion [x, y, z, w].

    Conjugation by the improper axis swap M maps rotation(a, th) to
    rotation(det(M) * M a, th) = rotation(-(x, z, y), th), the angle (and so
    the scalar part) being unchanged.
    """
    w, x, y, z = (float(v) for v in q_osim_wxyz)
    q = np.array([-x, -z, -y, w])
    if q[3] < 0.0:
        q = -q
    return q / np.linalg.norm(q)


def quat_from_z_to(axis: np.ndarray) -> np.ndarray:
    """Shortest-arc quaternion [x, y, z, w] rotating +Z onto ``axis``."""
    a = np.asarray(axis, dtype=float)
    n = np.linalg.norm(a)
    if n < 1e-12:
        return np.array([0.0, 0.0, 0.0, 1.0])
    a = a / n
    z = np.array([0.0, 0.0, 1.0])
    d = float(np.dot(z, a))
    if d > 1.0 - 1e-9:
        return np.array([0.0, 0.0, 0.0, 1.0])
    if d < -1.0 + 1e-9:
        return np.array([1.0, 0.0, 0.0, 0.0])  # 180 deg about X
    c = np.cross(z, a)
    q = np.array([c[0], c[1], c[2], 1.0 + d])
    return q / np.linalg.norm(q)


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------

def body_names(model) -> set[str]:
    bs = model.getBodySet()
    return {bs.get(i).getName() for i in range(bs.getSize())}


def transform_in_ground(model, state, body: str) -> tuple[np.ndarray, np.ndarray]:
    """(position metres, rotation matrix) of a body frame in ground."""
    X = model.getBodySet().get(body).getTransformInGround(state)
    p = X.p()
    R = X.R()
    pos = np.array([p.get(0), p.get(1), p.get(2)])
    rot = np.array([[R.get(i, j) for j in range(3)] for i in range(3)])
    return pos, rot


def body_origin_in_frame(model, state, of_body: str, in_body: str) -> np.ndarray:
    """Origin of ``of_body`` expressed in ``in_body``'s frame (metres)."""
    X = model.getBodySet().get(in_body).getTransformInGround(state)
    p = model.getBodySet().get(of_body).getTransformInGround(state).p()
    loc = X.shiftBaseStationToFrame(p)
    return np.array([loc.get(0), loc.get(1), loc.get(2)])


def resolve_point(spec, tag: str, model, state, seg_body: str) -> np.ndarray:
    """Resolve a prox/dist spec to a point in the segment body's frame."""
    if isinstance(spec, dict):
        spec = spec.get(tag, spec.get("*"))
    if isinstance(spec, tuple) and len(spec) == 2 and spec[0] == "body":
        return body_origin_in_frame(model, state, spec[1], seg_body)
    return np.array([float(v) for v in spec])


def resolve_segments(models: list[tuple[str, "osim.Model", object]]) -> list[dict]:
    """Resolve every segment's capsule geometry against the first model that
    owns all the bodies it references.  Segments no model provides are
    dropped (they simply cannot be drawn)."""
    out = []
    for seg in SEGMENTS:
        needed = {seg["body"]}
        for key in ("prox", "dist"):
            spec = seg[key]
            if isinstance(spec, tuple) and len(spec) == 2 and spec[0] == "body":
                needed.add(spec[1])
        chosen = None
        for tag, model, state in models:
            if needed <= body_names(model):
                chosen = (tag, model, state)
                break
        if chosen is None:
            print(f"  segment {seg['name']}: no model owns {sorted(needed)} - skipped")
            continue
        tag, model, state = chosen
        prox = resolve_point(seg["prox"], tag, model, state, seg["body"])
        dist = resolve_point(seg["dist"], tag, model, state, seg["body"])
        axis = dist - prox
        length_m = float(np.linalg.norm(axis))
        mid_ue = osim_pos_to_ue(0.5 * (prox + dist))
        # The axis is a difference of two points, so it converts with the same
        # (linear) position map; normalising afterwards is safe.
        axis_ue = osim_pos_to_ue(axis)
        rot = quat_from_z_to(axis_ue)
        out.append({
            "name": seg["name"],
            "body": seg["body"],
            "class": seg["cls"],
            "mesh": seg["mesh"],
            "model": tag,
            "lengthCm": round(length_m * CM, 4),
            "radiusCm": round(float(seg["radius"]) * CM, 4),
            "offsetCm": [round(float(v), 4) for v in mid_ue],
            "rot": [round(float(v), 6) for v in rot],
            "color": [round(float(v), 4) for v in seg["color"]],
        })
    return out


# ---------------------------------------------------------------------------
# Gait baking
# ---------------------------------------------------------------------------

def coordinate_values(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Time column and {coordinate path + '/value': samples} for a solution."""
    try:
        table = osim.TimeSeriesTable(str(path))
        labels = [l for l in table.getColumnLabels() if l.endswith("/value")]
        if not labels:
            raise RuntimeError("no /value columns")
        t = np.asarray(table.getIndependentColumn())
        data = {lab: table.getDependentColumn(lab).to_numpy() for lab in labels}
    except Exception:  # MocoTrajectory files need the trajectory reader
        traj = osim.MocoTrajectory(str(path))
        st = traj.exportToStatesTable()
        t = np.asarray(st.getIndependentColumn())
        data = {lab: st.getDependentColumn(lab).to_numpy()
                for lab in st.getColumnLabels() if lab.endswith("/value")}
    return t, data


def align_phase(g3d: dict, bodies_3d: list[str],
                g2d: dict, bodies_2d: list[str]) -> int:
    """Cyclic shift (frames) that best aligns a 3D gait's leg events with
    the 2D flat-3.0 gait, via cross-correlation of the forward (UE x)
    position of calcn_l relative to the pelvis. The two solution families
    start their cycles at different events; arms grafted onto the blended
    2D pose must swing against the correct leg."""
    def signal(g, bodies):
        b = bodies.index("calcn_l") * 7  # 7 floats per body: pos3 + quat4
        s = np.array([f[b] for f in g["frames"]], dtype=float)
        return s - s.mean()

    a, b = signal(g3d, bodies_3d), signal(g2d, bodies_2d)
    n = len(a)
    scores = [float(np.dot(np.roll(a, -k), b)) for k in range(n)]
    return int(np.argmax(scores))


GRF_MODEL_3D = ROOT / "experiments" / "phase3_3drunning" / "lai_running_model.osim"


def _resample48(t: np.ndarray, y: np.ndarray, ndp: int = 4) -> list[float]:
    """Resample onto the same 48-phase grid bake_gait uses (endpoint=False)."""
    phases = np.linspace(t[0], t[-1], NFRAMES, endpoint=False)
    return [round(float(np.interp(tk, t, y)), ndp) for tk in phases]


def grf_bw_from_table(table, mass_kg: float) -> tuple[list[float], list[float]]:
    """Per-foot vertical GRF in bodyweights on the 48-phase grid."""
    t = np.asarray(table.getIndependentColumn())
    bw = mass_kg * 9.81
    left = _resample48(t, table.getDependentColumn("ground_force_l_vy").to_numpy() / bw)
    right = _resample48(t, table.getDependentColumn("ground_force_r_vy").to_numpy() / bw)
    return left, right


def met_rate_wkg(model_met, sol_path: Path, mass_kg: float) -> list[float]:
    """Whole-body Bhargava metabolic rate (W/kg) on the 48-phase grid.
    analyzeMocoTrajectory entries are regex patterns (CLAUDE.md gotcha)."""
    traj = osim.MocoTrajectory(str(sol_path))
    paths = osim.StdVectorString()
    paths.append(".*metabolic_cost.*total_metabolic_rate")
    table = osim.analyzeMocoTrajectory(model_met, traj, paths)
    t = np.asarray(table.getIndependentColumn())
    rate = table.getDependentColumn(list(table.getColumnLabels())[0]).to_numpy()
    return _resample48(t, rate / mass_kg, ndp=2)


def bake_gait(model, state, bodies: list[str], path: Path) -> dict:
    """Pose the model at NFRAMES phases and record per-body UE transforms."""
    t, data = coordinate_values(path)
    coords = model.getCoordinateSet()
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
        row = []
        for body in bodies:
            pos, rot = transform_in_ground(model, state, body)
            pos = pos - np.array([px, 0.0, 0.0])  # pelvis-relative, ground kept
            p_ue = osim_pos_to_ue(pos)
            q_ue = mat_to_quat(osim_mat_to_ue(rot))
            row.extend([round(float(v), 3) for v in p_ue])
            row.extend([round(float(v), 6) for v in q_ue])
        frames.append(row)

    return {
        "strideTime": round(float(t[-1] - t[0]), 5),
        "strideLen": round(float(data[tx_lab][-1] - data[tx_lab][0]), 4),
        "frames": frames,
    }


def main() -> None:
    m2d = osim.Model(str(MODEL_2D))
    s2d = m2d.initSystem()
    m2d.realizePosition(s2d)

    models = [("2d", m2d, s2d)]
    if MODEL_3D.exists():
        m3d = osim.Model(str(MODEL_3D))
        s3d = m3d.initSystem()
        m3d.realizePosition(s3d)
        models.append(("3d", m3d, s3d))
    else:
        print(f"note: {MODEL_3D} missing - arm segments will be dropped")

    segments = resolve_segments(models)
    print(f"resolved {len(segments)} segments:")
    for s in segments:
        print(f"  {s['name']:<11s} {s['model']} len={s['lengthCm']:7.2f}cm "
              f"r={s['radiusCm']:5.2f}cm")

    gaits = []
    mass_2d = m2d.getTotalMass(s2d)
    m2d_met = None  # lazy: metabolics-instrumented copy for _met gaits
    bodies_2d = [b for b in dict.fromkeys(s["body"] for s in segments)
                 if b in body_names(m2d)]
    for fname, speed, grade, cot in GAITS:
        path = RUN2D / fname
        if not path.exists():
            print(f"skip (missing): {fname}")
            continue
        g = bake_gait(m2d, s2d, bodies_2d, path)
        g.update(speed=speed, grade=round(grade, 5), cot=cot, src=fname,
                 source="2d", bodies=bodies_2d)
        # per-frame vertical GRF (BW) from the solution's sibling grf table
        grf_path = RUN2D / fname.replace("fullstride_", "grf_")
        if grf_path.exists():
            table = osim.TimeSeriesTable(str(grf_path))
            g["grfBwL"], g["grfBwR"] = grf_bw_from_table(table, mass_2d)
        # per-frame Bhargava rate (W/kg) for metabolic-objective solutions
        if "_met" in fname:
            if m2d_met is None:
                from runsim.tier3.predict2d import _attach_metabolics
                m2d_met = osim.Model(str(MODEL_2D))
                _attach_metabolics(m2d_met)
                m2d_met.finalizeConnections()
                m2d_met.initSystem()
            try:
                g["metRateWkg"] = met_rate_wkg(m2d_met, path, mass_2d)
            except Exception as exc:
                print(f"  [warn] metabolic rate failed for {fname}: {exc}")
        gaits.append(g)
        print(f"{fname}: strideTime={g['strideTime']}s "
              f"strideLen={g['strideLen']}m "
              f"cadence={2 / g['strideTime']:.2f}Hz")

    if GAITS_3D:  # extension point - see the module docstring
        grf_model_3d = None  # lazy: contact-instrumented model for 3d GRFs
        grf_r3 = grf_l3 = None
        m3d = next(m for tag, m, _ in models if tag == "3d")
        s3d = next(s for tag, _, s in models if tag == "3d")
        bodies_3d = [b for b in dict.fromkeys(s["body"] for s in segments)
                     if b in body_names(m3d)]
        for fname, speed, grade, cot in GAITS_3D:
            path = Path(fname)
            if not path.is_absolute():
                path = ROOT / fname
            if not path.exists():
                print(f"skip (missing): {fname}")
                continue
            g = bake_gait(m3d, s3d, bodies_3d, path)
            g.update(speed=speed, grade=round(grade, 5), cot=cot,
                     src=path.name, source="3d", bodies=bodies_3d)
            shift = align_phase(g, bodies_3d,
                                next(x for x in gaits
                                     if x["speed"] == 3.0 and x["grade"] == 0),
                                bodies_2d)
            g["frames"] = g["frames"][shift:] + g["frames"][:shift]
            # contact GRFs computed from the running model's spheres, rolled
            # by the SAME shift so forces stay aligned with the frames
            try:
                if grf_model_3d is None:
                    from runsim.tier3.model3d import (CONTACT_FORCES_LEFT,
                                                      CONTACT_FORCES_RIGHT)
                    grf_model_3d = osim.Model(str(GRF_MODEL_3D))
                    grf_model_3d.initSystem()
                    grf_r3 = osim.StdVectorString()
                    grf_l3 = osim.StdVectorString()
                    for c in CONTACT_FORCES_RIGHT:
                        grf_r3.append(c)
                    for c in CONTACT_FORCES_LEFT:
                        grf_l3.append(c)
                traj = osim.MocoTrajectory(str(path))
                table = osim.createExternalLoadsTableForGait(
                    grf_model_3d, traj, grf_r3, grf_l3)
                mass_3d = grf_model_3d.getTotalMass(grf_model_3d.initSystem())
                L, R = grf_bw_from_table(table, mass_3d)
                g["grfBwL"] = [round(v, 4) for v in np.roll(L, -shift)]
                g["grfBwR"] = [round(v, 4) for v in np.roll(R, -shift)]
            except Exception as exc:
                print(f"  [warn] 3d GRF failed for {path.name}: {exc}")
            print(f"{path.name}: 3d arm source, phase-rolled {shift} frames")
            gaits.append(g)

    out = {
        "format": "runsim.ue.gaits",
        "version": 1,
        "units": {"length": "cm", "angle": "quaternion", "frame": "unreal"},
        "nframes": NFRAMES,
        "segments": segments,
        "gaits": gaits,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB, {len(gaits)} gaits, "
          f"{len(segments)} segments)")


if __name__ == "__main__":
    main()
