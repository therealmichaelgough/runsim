"""Scale LaiUhlrich2022 to Hamner subject01 via segment-length ratios.

The proper fix for the 3D seed's limb-length mismatch (airborne solve,
then collapse — see AGENTS_LOG 2026-08-30): rather than shifting the
pelvis reference, scale the model so the subject's kinematics put the
feet on the floor. Per-segment factors come from comparing characteristic
joint-offset lengths between subject01's scaled Hamner model and the
generic Hamner model; the ratio transfers to the same-named LaiUhlrich
segment (both are Delp-lineage models with matching body names).

Output: experiments/phase3_3drunning/lai_subject01.osim
"""
import math
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parent.parent
HAMNER_DIR = ROOT / "data" / "raw" / "hamner2013" / "subject01"
# the loadable FullBodyModel IS subject01's scaled model (2.4 format);
# the scale/ *_v191.osim duplicates are OpenSim 1.9.1 and unreadable here
SUBJ = HAMNER_DIR / "FullBodyModel_SimpleArms_Hamner2010_HPLMarkers_subject01.osim"
LAI = ROOT / "models" / "LaiUhlrich2022" / "LaiUhlrich2022.osim"
OUT = ROOT / "experiments" / "phase3_3drunning" / "lai_subject01.osim"

# body -> (proximal body, distal body): segment length measured as the
# distance between body-frame origins at the default pose (convention-
# independent — joint-offset conventions differ between the lineages,
# e.g. both knees carry their translation in the joint's spatial
# transform, not the frame offset). factor = subject / lai directly.
SEGMENT_SPANS = {
    "pelvis": ("pelvis", "femur_r"),
    "femur_r": ("femur_r", "tibia_r"), "femur_l": ("femur_l", "tibia_l"),
    "tibia_r": ("tibia_r", "talus_r"), "tibia_l": ("tibia_l", "talus_l"),
    "talus_r": ("talus_r", "calcn_r"), "talus_l": ("talus_l", "calcn_l"),
    "calcn_r": ("calcn_r", "toes_r"), "calcn_l": ("calcn_l", "toes_l"),
    "torso": ("torso", "humerus_r"),
    "humerus_r": ("humerus_r", "ulna_r"), "humerus_l": ("humerus_l", "ulna_l"),
    "ulna_r": ("ulna_r", "hand_r"), "ulna_l": ("ulna_l", "hand_l"),
}
# segments without a clean distal joint borrow a neighbour's factor
BORROW = {"toes_r": "calcn_r", "toes_l": "calcn_l",
          "radius_r": "ulna_r", "radius_l": "ulna_l",
          "hand_r": "ulna_r", "hand_l": "ulna_l",
          "patella_r": "femur_r", "patella_l": "femur_l"}


def span_len(model: osim.Model, state, body_a: str, body_b: str) -> float:
    model.realizePosition(state)
    pa = model.getBodySet().get(body_a).getPositionInGround(state)
    pb = model.getBodySet().get(body_b).getPositionInGround(state)
    return math.sqrt(sum((pa.get(k) - pb.get(k)) ** 2 for k in range(3)))


def main() -> None:
    subj = osim.Model(str(SUBJ))
    subj_state = subj.initSystem()
    subj_mass = subj.getTotalMass(subj_state)
    lai = osim.Model(str(LAI))
    state = lai.initSystem()

    factors = {}
    for body, (a, b) in SEGMENT_SPANS.items():
        factors[body] = span_len(subj, subj_state, a, b) / span_len(lai, state, a, b)
    for body, src in BORROW.items():
        factors[body] = factors[src]

    scale_set = osim.ScaleSet()
    bodies = lai.getBodySet()
    for i in range(bodies.getSize()):
        name = bodies.get(i).getName()
        f = factors.get(name, 1.0)
        s = osim.Scale()
        s.setSegmentName(name)
        s.setScaleFactors(osim.Vec3(f, f, f))
        s.setApply(True)
        scale_set.cloneAndAppend(s)

    ok = lai.scale(state, scale_set, True, subj_mass)
    if not ok:
        raise SystemExit("model.scale() failed")
    lai.setName("LaiUhlrich2022_subject01")
    lai.printToXML(str(OUT))

    for body in ("pelvis", "femur_r", "tibia_r", "torso", "humerus_r"):
        print(f"  {body:10s} x{factors[body]:.4f}")
    print(f"subject mass: {subj_mass:.2f} kg")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
