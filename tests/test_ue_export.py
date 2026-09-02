"""Numerical checks on the Unreal export pipeline (scripts/export_ue_gaits.py).

Unreal Engine is not installed on the machine that authored the renderer, so
these tests are the only executable verification that the exported transforms
are geometrically correct.  They pin:

  a) the OpenSim -> Unreal rotation conversion (round trip + a known rotation
     whose sign convention is what "uphill lean" depends on);
  b) that an exported frame preserves real geometry -- joint-to-joint
     distances scale by exactly 100, and the exported *quaternions* correctly
     place a child joint when used to rotate a body-frame offset;
  c) that the capsule lengths are plausible human segment lengths.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / "scripts" / "export_ue_gaits.py"
GAITS_JSON = ROOT / "unreal" / "RunsimViewer" / "Content" / "Data" / "gaits_ue.json"


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_ue_gaits", EXPORTER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ue = _load_exporter()


def _rand_rotation(rng: np.random.Generator) -> np.ndarray:
    """Uniformly random rotation matrix via QR of a Gaussian matrix."""
    q, r = np.linalg.qr(rng.standard_normal((3, 3)))
    q = q @ np.diag(np.sign(np.diag(r)))
    if np.linalg.det(q) < 0:
        q[:, 0] = -q[:, 0]
    return q


# --------------------------------------------------------------------------
# (a) coordinate conversion
# --------------------------------------------------------------------------

def test_quat_matrix_round_trip():
    rng = np.random.default_rng(7)
    for _ in range(50):
        R = _rand_rotation(rng)
        q = ue.mat_to_quat(R)
        assert abs(np.linalg.norm(q) - 1.0) < 1e-12
        assert np.allclose(ue.quat_to_mat(q), R, atol=1e-10)


def test_quaternion_conversion_matches_matrix_conjugation():
    """The quaternion shortcut (w,x,y,z) -> (-x,-z,-y,w) must agree with the
    matrix conjugation R_ue = M R M^T for every rotation."""
    rng = np.random.default_rng(11)
    for _ in range(200):
        R = _rand_rotation(rng)
        x, y, z, w = ue.mat_to_quat(R)
        q_short = ue.osim_quat_to_ue((w, x, y, z))
        q_matrix = ue.mat_to_quat(ue.osim_mat_to_ue(R))
        # quaternions are double covers: compare the rotations they encode
        assert np.allclose(ue.quat_to_mat(q_short), ue.quat_to_mat(q_matrix),
                           atol=1e-10)
        # ... and the conversion must be an exact conjugation
        assert np.allclose(ue.quat_to_mat(q_short),
                           ue.AXIS_SWAP @ R @ ue.AXIS_SWAP.T, atol=1e-10)


def test_conversion_is_invertible():
    """Converting back (same map, it is an involution) restores the original."""
    rng = np.random.default_rng(3)
    for _ in range(50):
        R = _rand_rotation(rng)
        assert np.allclose(ue.osim_mat_to_ue(ue.osim_mat_to_ue(R)), R, atol=1e-12)
        p = rng.standard_normal(3)
        p_ue = ue.osim_pos_to_ue(p)
        back = np.array([p_ue[0], p_ue[2], p_ue[1]]) / ue.CM
        assert np.allclose(back, p, atol=1e-12)


def test_sagittal_flexion_becomes_positive_unreal_pitch():
    """A rotation about OpenSim +z (the 2D model's flexion axis) tips the
    forward axis *up*; after conversion the same must hold in Unreal, where
    'nose up' is positive pitch.  This is the sign that decides whether the
    runner leans into a hill or out of it."""
    th = 0.37
    c, s = math.cos(th), math.sin(th)
    # right-handed rotation about +z in a y-up frame: +x tips toward +y (up)
    R_osim = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    assert np.allclose(R_osim @ np.array([1.0, 0.0, 0.0]), [c, s, 0.0])

    R_ue = ue.quat_to_mat(ue.osim_quat_to_ue(
        (ue.mat_to_quat(R_osim)[3], *ue.mat_to_quat(R_osim)[:3])))
    fwd = R_ue @ np.array([1.0, 0.0, 0.0])
    # Unreal: X forward, Z up.  Forward must tip toward +Z by the same angle.
    assert np.allclose(fwd, [c, 0.0, s], atol=1e-12)
    # and the rotation axis is -Y (Unreal positive pitch), magnitude preserved
    q = ue.osim_quat_to_ue((ue.mat_to_quat(R_osim)[3], *ue.mat_to_quat(R_osim)[:3]))
    assert abs(2 * math.acos(min(1.0, abs(q[3]))) - th) < 1e-9
    assert abs(q[0]) < 1e-12 and abs(q[2]) < 1e-12 and q[1] < 0.0


def test_quat_from_z_to_axis():
    rng = np.random.default_rng(5)
    for _ in range(50):
        a = rng.standard_normal(3)
        a /= np.linalg.norm(a)
        R = ue.quat_to_mat(ue.quat_from_z_to(a))
        assert np.allclose(R @ np.array([0.0, 0.0, 1.0]), a, atol=1e-9)


# --------------------------------------------------------------------------
# (b) exported frames preserve geometry
# --------------------------------------------------------------------------

pytestmark_json = pytest.mark.skipif(
    not GAITS_JSON.exists(),
    reason="gaits_ue.json not exported (run scripts/export_ue_gaits.py)",
)


@pytest.fixture(scope="module")
def data():
    if not GAITS_JSON.exists():
        pytest.skip("gaits_ue.json not exported")
    return json.loads(GAITS_JSON.read_text())


def _frame_transforms(gait, frame_index):
    """{body: (pos_cm, quat_xyzw)} for one exported frame."""
    row = gait["frames"][frame_index]
    out = {}
    for i, body in enumerate(gait["bodies"]):
        base = i * 7
        out[body] = (np.array(row[base:base + 3], dtype=float),
                     np.array(row[base + 3:base + 7], dtype=float))
    return out


def test_json_shape(data):
    assert data["format"] == "runsim.ue.gaits"
    assert data["nframes"] == ue.NFRAMES
    assert len(data["gaits"]) == 16
    assert sum(g["source"] == "2d" for g in data["gaits"]) == 14
    assert sum(g["source"] == "3d" for g in data["gaits"]) == 2
    for g in data["gaits"]:
        assert len(g["frames"]) == data["nframes"]
        assert all(len(f) == 7 * len(g["bodies"]) for f in g["frames"])
        assert g["strideTime"] > 0 and g["strideLen"] > 0


def test_all_quaternions_are_unit(data):
    for g in data["gaits"]:
        for f in g["frames"]:
            for i in range(len(g["bodies"])):
                q = np.array(f[i * 7 + 3:i * 7 + 7], dtype=float)
                assert abs(np.linalg.norm(q) - 1.0) < 1e-5


def test_frame_distances_match_opensim_times_100(data):
    """For a real exported frame, every joint-to-joint distance measured in
    Unreal space must equal the OpenSim distance x 100."""
    opensim = pytest.importorskip("opensim")
    gait = next(g for g in data["gaits"]
                if g["speed"] == 3.0 and g["grade"] == 0.0)
    frame_index = 12

    model = opensim.Model(str(ue.MODEL_2D))
    state = model.initSystem()
    t, values = ue.coordinate_values(ue.RUN2D / gait["src"])
    phases = np.linspace(t[0], t[-1], ue.NFRAMES, endpoint=False)
    tk = phases[frame_index]
    coords = model.getCoordinateSet()
    for i in range(coords.getSize()):
        c = coords.get(i)
        lab = f"{c.getAbsolutePathString()}/value"
        if lab in values:
            c.setValue(state, float(np.interp(tk, t, values[lab])), False)
    model.assemble(state)
    model.realizePosition(state)

    xf = _frame_transforms(gait, frame_index)
    pairs = [("femur_l", "tibia_l"), ("tibia_l", "calcn_l"),
             ("pelvis", "torso"), ("femur_r", "calcn_r"),
             ("pelvis", "calcn_l"), ("torso", "tibia_r")]
    for a, b in pairs:
        pa, _ = ue.transform_in_ground(model, state, a)
        pb, _ = ue.transform_in_ground(model, state, b)
        d_osim = float(np.linalg.norm(pb - pa))
        d_ue = float(np.linalg.norm(xf[b][0] - xf[a][0]))
        assert d_ue == pytest.approx(d_osim * 100.0, abs=0.02), (a, b)
        assert d_osim > 1e-3


def test_exported_quaternions_place_child_joints(data):
    """End-to-end rotation check: rotating the child-joint offset (taken in
    the parent's body frame, at this pose) by the parent's exported Unreal
    quaternion must land on the child's exported Unreal position."""
    opensim = pytest.importorskip("opensim")
    gait = next(g for g in data["gaits"]
                if g["speed"] == 3.0 and g["grade"] == 0.0)
    frame_index = 30

    model = opensim.Model(str(ue.MODEL_2D))
    state = model.initSystem()
    t, values = ue.coordinate_values(ue.RUN2D / gait["src"])
    tk = np.linspace(t[0], t[-1], ue.NFRAMES, endpoint=False)[frame_index]
    coords = model.getCoordinateSet()
    for i in range(coords.getSize()):
        c = coords.get(i)
        lab = f"{c.getAbsolutePathString()}/value"
        if lab in values:
            c.setValue(state, float(np.interp(tk, t, values[lab])), False)
    model.assemble(state)
    model.realizePosition(state)

    xf = _frame_transforms(gait, frame_index)
    for parent, child in [("femur_l", "tibia_l"), ("tibia_l", "calcn_l"),
                          ("pelvis", "femur_r"), ("pelvis", "torso"),
                          ("calcn_r", "femur_r")]:
        # offset of the child origin in the parent's frame, at this very pose
        off_osim = ue.body_origin_in_frame(model, state, child, parent)
        off_ue = ue.osim_pos_to_ue(off_osim)
        p_parent, q_parent = xf[parent]
        predicted = p_parent + ue.quat_to_mat(q_parent) @ off_ue
        assert np.allclose(predicted, xf[child][0], atol=0.05), (parent, child)


def test_segment_local_transform_reproduces_length(data):
    """offsetCm + rot must describe a capsule of exactly lengthCm."""
    for seg in data["segments"]:
        axis = ue.quat_to_mat(np.array(seg["rot"], dtype=float)) @ np.array(
            [0.0, 0.0, 1.0])
        half = 0.5 * seg["lengthCm"] * axis
        p0 = np.array(seg["offsetCm"]) - half
        p1 = np.array(seg["offsetCm"]) + half
        assert np.linalg.norm(p1 - p0) == pytest.approx(seg["lengthCm"], abs=1e-3)
        assert seg["radiusCm"] > 0.0


def test_segment_endpoints_match_opensim_joint_positions(data):
    """The thigh capsule, placed through the exported body transform, must
    span hip -> knee in Unreal space."""
    opensim = pytest.importorskip("opensim")
    gait = next(g for g in data["gaits"]
                if g["speed"] == 3.0 and g["grade"] == 0.0)
    frame_index = 5
    model = opensim.Model(str(ue.MODEL_2D))
    state = model.initSystem()
    t, values = ue.coordinate_values(ue.RUN2D / gait["src"])
    tk = np.linspace(t[0], t[-1], ue.NFRAMES, endpoint=False)[frame_index]
    coords = model.getCoordinateSet()
    for i in range(coords.getSize()):
        c = coords.get(i)
        lab = f"{c.getAbsolutePathString()}/value"
        if lab in values:
            c.setValue(state, float(np.interp(tk, t, values[lab])), False)
    model.assemble(state)
    model.realizePosition(state)

    seg = next(s for s in data["segments"] if s["name"] == "thigh_l")
    xf = _frame_transforms(gait, frame_index)
    p_body, q_body = xf["femur_l"]
    R = ue.quat_to_mat(q_body)
    axis = ue.quat_to_mat(np.array(seg["rot"], dtype=float)) @ np.array([0, 0, 1.0])
    world = lambda local: p_body + R @ local
    hip = world(np.array(seg["offsetCm"]) - 0.5 * seg["lengthCm"] * axis)
    knee = world(np.array(seg["offsetCm"]) + 0.5 * seg["lengthCm"] * axis)

    # Positions in the JSON are pelvis_tx-relative, so compare the hip->knee
    # *vector*, which is independent of that offset.
    hip_osim = ue.osim_pos_to_ue(
        ue.transform_in_ground(model, state, "femur_l")[0])
    knee_osim = ue.osim_pos_to_ue(
        ue.transform_in_ground(model, state, "tibia_l")[0])
    # 3 cm: the capsule carries fixed default-pose dimensions, while the real
    # knee centre translates a little with flexion (Rajagopal knee splines).
    assert np.allclose(knee - hip, knee_osim - hip_osim, atol=3.0)
    assert np.linalg.norm(knee - hip) == pytest.approx(
        np.linalg.norm(knee_osim - hip_osim), rel=0.06)
    # the capsule really is the thigh: its proximal end sits on the hip joint
    assert np.linalg.norm(hip - xf["femur_l"][0]) < 1.0  # cm


# --------------------------------------------------------------------------
# (c) human plausibility
# --------------------------------------------------------------------------

def test_capsule_lengths_are_human(data):
    seen = set()
    for seg in data["segments"]:
        rng = ue.HUMAN_LENGTH_RANGE_M.get(seg["class"])
        if rng is None:
            continue
        lo, hi = rng
        assert lo * 100 <= seg["lengthCm"] <= hi * 100, seg["name"]
        seen.add(seg["class"])
    # every class we claim to check must actually be present in the export
    assert {"thigh", "shank", "foot", "torso", "upperarm", "forearm"} <= seen


def test_leg_segments_are_symmetric(data):
    by_name = {s["name"]: s for s in data["segments"]}
    for left, right in [("thigh_l", "thigh_r"), ("shank_l", "shank_r"),
                        ("foot_l", "foot_r")]:
        assert by_name[left]["lengthCm"] == pytest.approx(
            by_name[right]["lengthCm"], abs=0.5)


def test_arm_segments_present_and_sourced_from_3d_gaits(data):
    """Arm segments are declared; 2D-sourced gaits lack the arm bodies (the
    renderer hides/grafts) while 3D-sourced gaits must carry all of them."""
    names = {s["name"] for s in data["segments"]}
    assert {"upperarm_l", "forearm_l", "upperarm_r", "forearm_r"} <= names
    arm_bodies = {s["body"] for s in data["segments"]
                  if s["class"] in ("upperarm", "forearm")}
    for g in data["gaits"]:
        if g["source"] == "2d":
            assert not (arm_bodies & set(g["bodies"]))
        else:
            assert arm_bodies <= set(g["bodies"])


def test_stride_data_matches_web_viewer_cadence(data):
    """M2 acceptance: the 2D-sourced 3.0 m/s gait runs at ~3.8 Hz."""
    g = next(g for g in data["gaits"] if g["speed"] == 3.0 and g["grade"] == 0.0)
    assert 2.0 / g["strideTime"] == pytest.approx(3.8, abs=0.05)
    assert g["strideLen"] / g["strideTime"] == pytest.approx(3.0, rel=0.02)


# --------------------------------------------------------------------------
# (d) the blend algorithm the UE side implements
#
# URunsimGaitData's blend cannot be compiled on this machine, so the algorithm
# (not the C++) is pinned here against the shipped data: the bracket rule, the
# grade-delta cancellation, and the no-foot-skate world advance.
# --------------------------------------------------------------------------

def _bracket(keys, x):
    """Port of bracket() in docs/run_viewer.html and of BracketKeys in C++."""
    n = len(keys)
    if n <= 1:
        return 0, 0, 0.0
    i = 0
    while i < n - 2 and keys[i + 1] <= x:
        i += 1
    span = keys[i + 1] - keys[i]
    w = min(1.0, max(0.0, (x - keys[i]) / (span if abs(span) > 1e-12 else 1.0)))
    return i, i + 1, w


def test_bracket_matches_web_viewer():
    keys = [1.2, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    assert _bracket(keys, 1.2) == (0, 1, 0.0)
    assert _bracket(keys, 0.5) == (0, 1, 0.0)          # clamped below
    assert _bracket(keys, 5.9)[:2] == (6, 7)           # clamped above
    assert _bracket(keys, 5.9)[2] == 1.0
    a, b, w = _bracket(keys, 2.25)
    assert (a, b) == (1, 2) and w == pytest.approx(0.5)


def _frames_array(gait):
    n = len(gait["bodies"])
    rows = np.array(gait["frames"], dtype=float)
    return rows.reshape(len(gait["frames"]), n, 7)


def test_blend_at_a_solved_point_reproduces_that_gait(data):
    """At an exactly-solved (speed, grade) the blend must be the identity:
    the speed bracket lands on the gait and the grade delta cancels."""
    # 3D-sourced gaits are the arm source only and never join the blends
    # (mirrors URunsimGaitData::BuildIndices)
    blendable = [g for g in data["gaits"] if g["source"] != "3d"]
    speed_gaits = sorted([g for g in blendable if g["grade"] == 0.0],
                         key=lambda g: g["speed"])
    grade_gaits = sorted([g for g in blendable
                          if g["speed"] == 3.0 and "_met" in g["src"]],
                         key=lambda g: g["grade"])
    flat3 = next(g for g in speed_gaits if g["speed"] == 3.0)
    skeys = [g["speed"] for g in speed_gaits]
    gkeys = [g["grade"] for g in grade_gaits]

    for target in (3.0, 4.0):
        ia, ib, w = _bracket(skeys, target)
        ja, jb, gw = _bracket(gkeys, 0.0)
        A, B = _frames_array(speed_gaits[ia]), _frames_array(speed_gaits[ib])
        GA, GB = _frames_array(grade_gaits[ja]), _frames_array(grade_gaits[jb])
        F = _frames_array(flat3)
        pose = A[:, :, :3] * (1 - w) + B[:, :, :3] * w
        pose += GA[:, :, :3] * (1 - gw) + GB[:, :, :3] * gw - F[:, :, :3]
        expected = _frames_array(
            next(g for g in speed_gaits if g["speed"] == target))[:, :, :3]
        assert np.allclose(pose, expected, atol=1e-6), target


def test_world_advance_removes_foot_skate(data):
    """The renderer advances the runner at strideLen/strideTime, not at the
    requested speed.  With that rule a stance foot must stay put in world
    space: pose x is pelvis-relative and the advance cancels it exactly."""
    gait = next(g for g in data["gaits"]
                if g["speed"] == 3.0 and g["grade"] == 0.0)
    seg = next(s for s in data["segments"] if s["name"] == "foot_r")
    frames = _frames_array(gait)
    body = gait["bodies"].index(seg["body"])
    axis = ue.quat_to_mat(np.array(seg["rot"], dtype=float)) @ np.array([0, 0, 1.0])
    toe_local = np.array(seg["offsetCm"]) + 0.5 * seg["lengthCm"] * axis

    nframes = data["nframes"]
    step_cm = gait["strideLen"] * 100.0 / nframes  # world advance per frame
    world_x, height = [], []
    for f in range(nframes):
        pos = frames[f, body, :3]
        rot = frames[f, body, 3:]
        toe = pos + ue.quat_to_mat(rot) @ toe_local
        world_x.append(f * step_cm + toe[0])
        height.append(toe[2])

    stance = [i for i, z in enumerate(height) if z < 1.2]
    assert len(stance) >= 5, "no stance frames found"
    # contiguous run of stance frames (the stride starts mid-flight)
    runs, current = [], [stance[0]]
    for a, b in zip(stance, stance[1:]):
        if b == a + 1:
            current.append(b)
        else:
            runs.append(current)
            current = [b]
    runs.append(current)
    longest = max(runs, key=len)
    drift = abs(world_x[longest[-1]] - world_x[longest[0]])
    assert drift < 2.0, f"foot skates {drift:.2f} cm during stance"


def test_feet_reach_the_ground(data):
    """Sanity on the vertical axis: in every gait the foot bodies come within
    a few cm of z = 0 at some phase (the sim ground plane)."""
    for g in data["gaits"]:
        idx = g["bodies"].index("calcn_r")
        lowest = min(f[idx * 7 + 2] for f in g["frames"])
        assert -3.0 < lowest < 12.0, (g["src"], lowest)
