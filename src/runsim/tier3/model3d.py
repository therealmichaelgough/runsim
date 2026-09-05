"""Moco-ready 3D model preparation for LaiUhlrich2022.

Converts the stock OpenCap LaiUhlrich2022 model (Millard muscles, no
contact geometry) into a form Moco's direct collocation can use for
running, following the recipe validated in the 2D phases:

- DeGrooteFregly2016 muscles, rigid tendons, passive fiber forces off
  (Falisse 2019, Dembia 2020 example2DWalking / exampleMocoTrack).
- SmoothSphereHalfSpaceForce foot-ground contacts with the parameter set
  from the 2D_gait model (stiffness 3.07 MPa, dissipation 2 s/m,
  friction 0.8/0.8/0.5, transition velocity 0.2 m/s; Serrancoli 2019).
  Sphere layout extends the 2D two-sphere foot with a medial/lateral
  forefoot split plus a toe sphere for mediolateral balance, as in 3D
  predictive gait models (Falisse 2019).
"""
from __future__ import annotations

from pathlib import Path

import opensim as osim

# (name, body, location in body frame (right side), radius); left mirrors z
_RIGHT_SPHERES = [
    ("heel_r", "calcn_r", (0.0313, 0.0104, 0.0), 0.035),
    ("frontLat_r", "calcn_r", (0.1774, -0.0157, 0.030), 0.020),
    ("frontMed_r", "calcn_r", (0.1774, -0.0157, -0.025), 0.020),
    ("toe_r", "toes_r", (0.055, -0.010, -0.010), 0.020),
]

CONTACT_PARAMS = dict(
    stiffness=3067776.0,
    dissipation=2.0,
    static_friction=0.8,
    dynamic_friction=0.8,
    viscous_friction=0.5,
    transition_velocity=0.2,
)

#: contact force paths per side, for MocoContactTrackingGoal groups
CONTACT_FORCES_RIGHT = [f"/forceset/contact_{name}" for name, *_ in _RIGHT_SPHERES]
CONTACT_FORCES_LEFT = [f.replace("_r", "_l") for f in CONTACT_FORCES_RIGHT]

#: Optimal forces (N.m) for the model's ideal lumbar/arm CoordinateActuators,
#: keyed by name prefix, replacing the stock 10 N.m placeholders (which are
#: static-optimization reserves, not a predictive-simulation trunk). Values
#: are order-of-magnitude isometric capacities, de-rated for a sub-maximal
#: dynamic task: lumbar extension / lateral bending / axial rotation
#: ~200 / 150 / 100 (Graves et al. 1990 isolated lumbar extension; McGill
#: 1991 trunk moment capacities), shoulder flexion / adduction / rotation
#: ~60 / 60 / 30 and elbow flexion ~40 (Askew et al. 1987; Murray et al.
#: 1985 isometric shoulder and elbow strength), forearm pro/supination ~10.
#: Predictive 3D gait formulations drive the trunk and arms with ideal
#: torque actuators of this order (Falisse et al. 2019).
RUNNING_ACTUATOR_STRENGTH: dict[str, float] = {
    "lumbar_ext": 200.0, "lumbar_bend": 150.0, "lumbar_rot": 100.0,
    "shoulder_flex": 60.0, "shoulder_add": 60.0, "shoulder_rot": 30.0,
    "elbow_flex": 40.0, "pro_sup": 10.0,
}


#: Passive joint elements for the coordinates that rest on their problem
#: bounds once muscle passive forces are on (2026-09-04 screens and leg-1
#: iterate): knees at full extension, the muscle-less elbows and lumbar
#: joint, shoulder adduction/rotation, and hip rotation.
#: - knee_limit_*: CoordinateLimitForce engaging below 5 deg flexion (and
#:   above 120), 5 N.m/deg beyond the limit with a 5-deg transition and
#:   light damping — the passive knee-extension stop every gait model
#:   carries (Anderson & Pandy 1999 passive joint moments; Falisse 2019
#:   exponential limit torques).
#: - elbow_spring_*: a weak linear spring toward 100 deg flexion,
#:   0.05 N.m/deg (2.5 N.m at 50 deg away), standing in for the flexor
#:   tone that keeps runners' elbows at ~110-130 deg (Hamner & Delp 2013);
#:   the arm swing itself stays free to be predicted.
#: - lumbar_spring_*: linear stiffness + damping toward neutral on the
#:   lumbar coordinates, 2 N.m/deg extension/bending, 1 N.m/deg rotation,
#:   0.02 N.m.s/deg — the spine's passive tissues beyond the neutral zone
#:   (Panjabi 1992; Falisse 2019 passive linear trunk torques). The lumbar
#:   joint has no muscles here, so without this the trunk swings between
#:   its bounds (leg-1 iterate: all three lumbar coordinates pinned; 1
#:   N.m/deg still left extension and bending pinned).
#: - shoulder_spring_*: springs toward neutral on arm adduction and
#:   rotation, 0.3 N.m/deg (9 N.m at 30 deg: capsule and end-range
#:   passive stiffness); arm flexion stays free so the swing itself is
#:   predicted. 0.05 N.m/deg left both coordinates sweeping their bounds.
#: - hip_rot_limit_*: CoordinateLimitForce at +-25 deg hip rotation
#:   (5 N.m/deg beyond, 5-deg transition), the ligamentous end range.
#: - shoulder_add/rot_limit_*, lumbar_bend/rot_limit: end-range limit
#:   forces (3 N.m/deg beyond the physiological running range: shoulder
#:   abduction 30 / adduction 15 deg, rotation -45..30, lumbar bending
#:   +-10, rotation +-15). With linear springs alone the v5 iterate still
#:   swept 60 deg of abduction and 90 deg of rotation: a 60 N.m actuator
#:   overrides an 18 N.m spring, while a real shoulder's passive stiffness
#:   rises steeply at end range (Panjabi 1992 neutral zone for the spine).
#: - shoulder_flex_limit_*, elbow_limit_*: the same end-range treatment
#:   for arm flexion (-60..30; the running swing is -45..+15, Hamner 2010)
#:   and elbow flexion (40..145): once the other planes were closed, the
#:   metabolic objective swung the arms to the flexion bound and an elbow
#:   to its bound (nomono iterate, 2026-09-04). The weak elbow posture
#:   spring stays for the neutral zone.
JOINT_PASSIVES = dict(
    knee_lower_deg=5.0, knee_upper_deg=120.0, knee_stiffness_nm_per_deg=5.0,
    knee_damping=0.5, knee_transition_deg=5.0,
    elbow_rest_deg=100.0, elbow_stiffness_nm_per_deg=0.05,
    lumbar_stiffness_nm_per_deg=2.0, lumbar_rot_stiffness_nm_per_deg=1.0,
    lumbar_damping_nm_s_per_deg=0.02,
    shoulder_stiffness_nm_per_deg=0.3,
    hip_rot_limit_deg=15.0, hip_rot_stiffness_nm_per_deg=10.0,
    hip_rot_damping=0.5, hip_rot_transition_deg=2.0,
    # end-range limits (neutral zone inside, steep passive stiffness beyond;
    # Panjabi 1992 for the spine, capsular end-range for the shoulder):
    # ranges are the physiological running ranges, not anatomical maxima
    shoulder_add_limits_deg=(-30.0, 15.0),   # 30 deg abduction .. 15 adduction
    shoulder_rot_limits_deg=(-45.0, 30.0),
    shoulder_flex_limits_deg=(-60.0, 30.0),  # running swing -45..+15 (Hamner 2010)
    elbow_limits_deg=(40.0, 145.0),          # runners hold 110-130 deg; never straight
    lumbar_bend_limit_deg=6.0,   # v10: running lumbar bending ~+-5 deg
    lumbar_rot_limit_deg=8.0,    # v10: the v9 iterate counter-rotated the trunk +-15
                                 # against a +-8 trunk yaw, giving +-23 of pelvis yaw
    range_limit_stiffness_nm_per_deg=10.0, range_limit_damping=0.2,
    range_limit_transition_deg=2.0,
)
# v9 (2026-09-05): with 3 N.m/deg and 5-deg transitions the v8 iterate rode
# 5-7 deg into every limit (pelvis rotation +-27, hips +-25, lumbar bending
# and rotation +-17, arm flexion sweeping 115 deg); stiffer, sharper limits
# make the running ranges actual end ranges, and hip rotation is held to
# +-15 (running uses ~+-10).
_RAD = 180.0 / 3.141592653589793


def _spring(coord: str, name: str, k_nm_per_deg: float, rest_deg: float = 0.0,
            c_nm_s_per_deg: float = 0.0) -> osim.ExpressionBasedCoordinateForce:
    """Linear coordinate spring (+ optional damper) in N.m about rest_deg."""
    k = k_nm_per_deg * _RAD          # N.m/rad
    c = c_nm_s_per_deg * _RAD        # N.m.s/rad
    q0 = rest_deg / _RAD
    expr = f"-{k:.6f}*(q-({q0:.6f}))" + (f"-{c:.6f}*qdot" if c else "")
    f = osim.ExpressionBasedCoordinateForce(coord, expr)
    f.setName(name)
    return f


def add_joint_passives(model: osim.Model, p: dict | None = None) -> list[str]:
    """Add the passive joint elements listed above JOINT_PASSIVES; returns
    the names of the forces added."""
    p = {**JOINT_PASSIVES, **(p or {})}
    added = []
    for side in ("r", "l"):
        knee = osim.CoordinateLimitForce(
            f"knee_angle_{side}", p["knee_upper_deg"], p["knee_stiffness_nm_per_deg"],
            p["knee_lower_deg"], p["knee_stiffness_nm_per_deg"], p["knee_damping"],
            p["knee_transition_deg"])
        knee.setName(f"knee_limit_{side}")
        model.addForce(knee)
        added.append(knee.getName())
        hip = osim.CoordinateLimitForce(
            f"hip_rotation_{side}", p["hip_rot_limit_deg"], p["hip_rot_stiffness_nm_per_deg"],
            -p["hip_rot_limit_deg"], p["hip_rot_stiffness_nm_per_deg"], p["hip_rot_damping"],
            p["hip_rot_transition_deg"])
        hip.setName(f"hip_rot_limit_{side}")
        model.addForce(hip)
        added.append(hip.getName())
        for f in (
            _spring(f"elbow_flex_{side}", f"elbow_spring_{side}",
                    p["elbow_stiffness_nm_per_deg"], p["elbow_rest_deg"]),
            _spring(f"arm_add_{side}", f"shoulder_spring_add_{side}", p["shoulder_stiffness_nm_per_deg"]),
            _spring(f"arm_rot_{side}", f"shoulder_spring_rot_{side}", p["shoulder_stiffness_nm_per_deg"]),
        ):
            model.addForce(f)
            added.append(f.getName())
    for coord in ("lumbar_extension", "lumbar_bending", "lumbar_rotation"):
        k = p["lumbar_rot_stiffness_nm_per_deg" if coord == "lumbar_rotation"
              else "lumbar_stiffness_nm_per_deg"]
        f = _spring(coord, f"lumbar_spring_{coord.split('_')[1]}",
                    k, 0.0, p["lumbar_damping_nm_s_per_deg"])
        model.addForce(f)
        added.append(f.getName())
    # end-range limits: the neutral zone stays soft, beyond it stiffness rises
    ks, cd, tr = (p["range_limit_stiffness_nm_per_deg"], p["range_limit_damping"],
                  p["range_limit_transition_deg"])
    limits = [("lumbar_bending", "lumbar_bend_limit",
               -p["lumbar_bend_limit_deg"], p["lumbar_bend_limit_deg"]),
              ("lumbar_rotation", "lumbar_rot_limit",
               -p["lumbar_rot_limit_deg"], p["lumbar_rot_limit_deg"])]
    for side in ("r", "l"):
        limits.append((f"arm_add_{side}", f"shoulder_add_limit_{side}", *p["shoulder_add_limits_deg"]))
        limits.append((f"arm_rot_{side}", f"shoulder_rot_limit_{side}", *p["shoulder_rot_limits_deg"]))
        limits.append((f"arm_flex_{side}", f"shoulder_flex_limit_{side}", *p["shoulder_flex_limits_deg"]))
        limits.append((f"elbow_flex_{side}", f"elbow_limit_{side}", *p["elbow_limits_deg"]))
    for coord, name, lo, hi in limits:
        f = osim.CoordinateLimitForce(coord, hi, ks, lo, ks, cd, tr)
        f.setName(name)
        model.addForce(f)
        added.append(name)
    return added


def set_actuator_strength(model: osim.Model,
                          strength: dict[str, float]) -> dict[str, float]:
    """Set each CoordinateActuator's optimal force from the first matching
    name prefix in `strength`; returns {actuator name: N.m} as applied."""
    applied: dict[str, float] = {}
    fs = model.updForceSet()
    for i in range(fs.getSize()):
        act = osim.CoordinateActuator.safeDownCast(fs.get(i))
        if act is None:
            continue
        for prefix, value in strength.items():
            if act.getName().startswith(prefix):
                act.setOptimalForce(float(value))
                applied[act.getName()] = float(value)
                break
    return applied


def _all_spheres():
    for name, body, loc, radius in _RIGHT_SPHERES:
        yield name, body, loc, radius
        lname = name.replace("_r", "_l")
        lbody = body.replace("_r", "_l")
        yield lname, lbody, (loc[0], loc[1], -loc[2]), radius


def add_running_contacts(model: osim.Model) -> None:
    """Add the floor half-space, contact spheres, and smooth contact forces."""
    floor = osim.ContactHalfSpace(
        osim.Vec3(0), osim.Vec3(0, 0, -1.5707963267948966), model.getGround(), "floor"
    )
    model.addContactGeometry(floor)
    for name, body, loc, radius in _all_spheres():
        frame = model.getBodySet().get(body)
        sphere = osim.ContactSphere(radius, osim.Vec3(*loc), frame, name)
        model.addContactGeometry(sphere)
        force = osim.SmoothSphereHalfSpaceForce(f"contact_{name}", sphere, floor)
        force.set_stiffness(CONTACT_PARAMS["stiffness"])
        force.set_dissipation(CONTACT_PARAMS["dissipation"])
        force.set_static_friction(CONTACT_PARAMS["static_friction"])
        force.set_dynamic_friction(CONTACT_PARAMS["dynamic_friction"])
        force.set_viscous_friction(CONTACT_PARAMS["viscous_friction"])
        force.set_transition_velocity(CONTACT_PARAMS["transition_velocity"])
        model.addForce(force)


def build_running_model(
    model_path: str | Path,
    out_path: str | Path | None = None,
    *,
    passive_forces: bool = False,
    actuator_strength: dict[str, float] | None = None,
    joint_passives: bool = False,
) -> osim.Model:
    """LaiUhlrich2022 -> Moco-ready running model (muscles converted,
    contacts added). Optionally writes the processed model to out_path.

    passive_forces: keep the DeGrooteFregly2016 passive fiber forces (the
    physiological restoring torques that keep joints off their range
    limits; Falisse 2019 models these plus explicit limit torques). Off by
    default, matching the validated tracking/effort solves.
    actuator_strength: optimal forces for the lumbar/arm CoordinateActuators
    by name prefix (see RUNNING_ACTUATOR_STRENGTH); None keeps the model's
    10 N.m placeholders.
    joint_passives: knee extension limit forces and elbow posture springs
    (see JOINT_PASSIVES / add_joint_passives)."""
    processor = osim.ModelProcessor(str(model_path))
    processor.append(osim.ModOpReplaceMusclesWithDeGrooteFregly2016())
    processor.append(osim.ModOpIgnoreTendonCompliance())
    if not passive_forces:
        processor.append(osim.ModOpIgnorePassiveFiberForcesDGF())
    processor.append(osim.ModOpScaleActiveFiberForceCurveWidthDGF(1.5))
    model = processor.process()
    if actuator_strength:
        set_actuator_strength(model, actuator_strength)
    if joint_passives:
        add_joint_passives(model)
    add_running_contacts(model)
    model.finalizeConnections()
    if out_path is not None:
        model.printToXML(str(out_path))
    return model
