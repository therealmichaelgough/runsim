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
) -> osim.Model:
    """LaiUhlrich2022 -> Moco-ready running model (muscles converted,
    contacts added). Optionally writes the processed model to out_path.

    passive_forces: keep the DeGrooteFregly2016 passive fiber forces (the
    physiological restoring torques that keep joints off their range
    limits; Falisse 2019 models these plus explicit limit torques). Off by
    default, matching the validated tracking/effort solves.
    actuator_strength: optimal forces for the lumbar/arm CoordinateActuators
    by name prefix (see RUNNING_ACTUATOR_STRENGTH); None keeps the model's
    10 N.m placeholders."""
    processor = osim.ModelProcessor(str(model_path))
    processor.append(osim.ModOpReplaceMusclesWithDeGrooteFregly2016())
    processor.append(osim.ModOpIgnoreTendonCompliance())
    if not passive_forces:
        processor.append(osim.ModOpIgnorePassiveFiberForcesDGF())
    processor.append(osim.ModOpScaleActiveFiberForceCurveWidthDGF(1.5))
    model = processor.process()
    if actuator_strength:
        set_actuator_strength(model, actuator_strength)
    add_running_contacts(model)
    model.finalizeConnections()
    if out_path is not None:
        model.printToXML(str(out_path))
    return model
