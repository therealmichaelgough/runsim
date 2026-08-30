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
# subject01-scaled LaiUhlrich (scripts/scale_lai_to_subject.py); the
# generic model leaves the stance foot ~14 cm off the floor at the
# reference kinematics and the solve goes airborne or collapses
MODEL = HERE / "lai_subject01.osim"
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


def main(mesh_intervals: int = 50, max_iterations: int = 2000) -> None:
    model = build_running_model(MODEL, out_path=HERE / "lai_running_model.osim")
    model.initSystem()
    states_ref = write_states_reference(RRA_CYCLE, model, HERE / "states_ref_v3.sto")
    # track exactly the window the (decimated) reference covers
    ref = osim.TimeSeriesTable(str(states_ref))
    times = ref.getIndependentColumn()
    t0, t1 = times[0], times[ref.getNumRows() - 1]

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
    for paths, ext_name, alt_frame in (
        (CONTACT_FORCES_RIGHT, "Right_GRF", "/bodyset/toes_r"),
        (CONTACT_FORCES_LEFT, "Left_GRF", "/bodyset/toes_l"),
    ):
        forces = osim.StdVectorString()
        for f in paths:
            forces.append(f)
        group = osim.MocoContactTrackingGoalGroup(forces, ext_name)
        # the toe sphere sits on the toes body while the measured GRF is
        # applied to the calcaneus; let the goal accept both frames
        group.append_alternative_frame_paths(alt_frame)
        contact.addContactGroup(group)
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
