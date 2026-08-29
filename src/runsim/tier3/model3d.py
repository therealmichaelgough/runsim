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

#: contact force names per side, for MocoContactTrackingGoal groups
CONTACT_FORCES_RIGHT = [f"contact_{name}" for name, *_ in _RIGHT_SPHERES]
CONTACT_FORCES_LEFT = [f.replace("_r", "_l") for f in CONTACT_FORCES_RIGHT]


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
) -> osim.Model:
    """LaiUhlrich2022 -> Moco-ready running model (muscles converted,
    contacts added). Optionally writes the processed model to out_path."""
    processor = osim.ModelProcessor(str(model_path))
    processor.append(osim.ModOpReplaceMusclesWithDeGrooteFregly2016())
    processor.append(osim.ModOpIgnoreTendonCompliance())
    processor.append(osim.ModOpIgnorePassiveFiberForcesDGF())
    processor.append(osim.ModOpScaleActiveFiberForceCurveWidthDGF(1.5))
    model = processor.process()
    add_running_contacts(model)
    model.finalizeConnections()
    if out_path is not None:
        model.printToXML(str(out_path))
    return model
