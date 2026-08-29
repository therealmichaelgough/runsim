"""3D tracking seed for the Phase-3 finale: MocoTrack of Hamner subject01
running at 3.0 m/s on the Moco-ready LaiUhlrich2022 model.

Tracks the RRA-adjusted cycle-1 kinematics (retargeted onto the LaiUhlrich
coordinate set) plus measured GRFs via contact tracking, one full gait
cycle. The solution seeds the predictive 3D problem, mirroring the 2D
strategy (never cold-start a gait prediction).

Outputs land next to this script:
  lai_running_model.osim  - processed model (DGF muscles + contacts)
  states_ref_v3.sto       - retargeted states reference
  grf_v3.xml / (local GRF .mot is referenced in place)
  seed3d_tracking.sto     - the tracking solution (the seed)
"""
import re
from pathlib import Path

import opensim as osim

from runsim.tier3.model3d import (
    CONTACT_FORCES_LEFT,
    CONTACT_FORCES_RIGHT,
    build_running_model,
)
from runsim.tier3.retarget import write_states_reference

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MODEL = ROOT / "models" / "LaiUhlrich2022" / "LaiUhlrich2022.osim"
SUBJ = ROOT / "data" / "raw" / "hamner2013" / "subject01"
RRA_CYCLE = (
    SUBJ / "rra_multipleSteps" / "RRA_Results_v191_Run_30002"
    / "RRA_Results_v191_Run_30002_cycle1"
    / "subject01_Run_30002_cycle1_states.sto"
)
GRF_MOT = SUBJ / "ExportedData" / "Run_300 02_newCOP3_v24.mot"

GRF_XML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<OpenSimDocument Version="40000">
  <ExternalLoads name="externalloads">
    <objects>
      <ExternalForce name="Right_GRF">
        <applied_to_body>calcn_r</applied_to_body>
        <force_expressed_in_body>ground</force_expressed_in_body>
        <point_expressed_in_body>ground</point_expressed_in_body>
        <force_identifier>R_ground_force_v</force_identifier>
        <point_identifier>R_ground_force_p</point_identifier>
        <torque_identifier>R_ground_torque_</torque_identifier>
      </ExternalForce>
      <ExternalForce name="Left_GRF">
        <applied_to_body>calcn_l</applied_to_body>
        <force_expressed_in_body>ground</force_expressed_in_body>
        <point_expressed_in_body>ground</point_expressed_in_body>
        <force_identifier>L_ground_force_v</force_identifier>
        <point_identifier>L_ground_force_p</point_identifier>
        <torque_identifier>L_ground_torque_</torque_identifier>
      </ExternalForce>
    </objects>
    <datafile>{datafile}</datafile>
  </ExternalLoads>
</OpenSimDocument>
"""


def cycle_window(states_path: Path) -> tuple[float, float]:
    """Time range of an RRA cycle from its SIMM header (`range a b`)."""
    text = states_path.with_name(
        states_path.name.replace("_states.sto", "_Kinematics_q.sto")
    ).read_text().split("endheader")[0]
    m = re.search(r"range\s+([\d.]+)\s+([\d.]+)", text)
    if not m:
        raise ValueError(f"no range header in {states_path}")
    return float(m.group(1)), float(m.group(2))


def main(mesh_intervals: int = 50, max_iterations: int = 2000) -> None:
    model = build_running_model(MODEL, out_path=HERE / "lai_running_model.osim")
    model.initSystem()
    states_ref = write_states_reference(RRA_CYCLE, model, HERE / "states_ref_v3.sto")
    t0, t1 = cycle_window(RRA_CYCLE)

    grf_xml = HERE / "grf_v3.xml"
    grf_xml.write_text(GRF_XML_TEMPLATE.format(datafile=GRF_MOT.resolve()))

    track = osim.MocoTrack()
    track.setName("seed3d")
    track.setModel(osim.ModelProcessor(model))
    track.setStatesReference(osim.TableProcessor(str(states_ref)))
    track.set_states_global_tracking_weight(1.0)
    track.set_allow_unused_references(True)
    track.set_track_reference_position_derivatives(True)
    track.set_apply_tracked_states_to_guess(True)
    track.set_initial_time(t0)
    track.set_final_time(t1)
    track.set_mesh_interval((t1 - t0) / mesh_intervals)

    study = track.initialize()
    problem = study.updProblem()

    effort = osim.MocoControlGoal.safeDownCast(problem.updGoal("control_effort"))
    effort.setWeight(0.1)

    contact = osim.MocoContactTrackingGoal("contact", 1.0)
    contact.setExternalLoadsFile(str(grf_xml))
    right = osim.StdVectorString()
    for f in CONTACT_FORCES_RIGHT:
        right.append(f)
    contact.addContactGroup(right, "Right_GRF")
    left = osim.StdVectorString()
    for f in CONTACT_FORCES_LEFT:
        left.append(f)
    contact.addContactGroup(left, "Left_GRF")
    problem.addGoal(contact)

    solver = osim.MocoCasADiSolver.safeDownCast(study.updSolver())
    solver.set_optim_convergence_tolerance(1e-3)
    solver.set_optim_constraint_tolerance(1e-3)
    solver.set_optim_max_iterations(max_iterations)

    solution = study.solve()
    solution.unseal()
    out = HERE / "seed3d_tracking.sto"
    solution.write(str(out))
    print(f"seed written: {out} (success={solution.success()}, "
          f"objective={solution.getObjective():.3f})")


if __name__ == "__main__":
    import sys

    kwargs = {}
    if len(sys.argv) > 1:
        kwargs["max_iterations"] = int(sys.argv[1])
    main(**kwargs)
