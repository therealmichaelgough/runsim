"""Generate the seed for the prediction chain: the example2DWalking tracking
solve (fast, ~20 s), whose single-step solution is the guess that made the
Phase-0 prediction converge. Writes seed_tracking.sto next to this script."""
import math
import os
import re
from pathlib import Path

import opensim as osim

HERE = Path(__file__).resolve().parent
PHASE0 = HERE.parent / "phase0_2dwalking"


def main() -> None:
    os.chdir(PHASE0)  # referenceGRF.xml points at referenceGRF.sto relatively

    track = osim.MocoTrack()
    track.setName("gaitTrackingSeed")
    tableProcessor = osim.TableProcessor("referenceCoordinates.sto")
    tableProcessor.append(osim.TabOpLowPassFilter(6))
    modelProcessor = osim.ModelProcessor("2D_gait.osim")
    track.setModel(modelProcessor)
    track.setStatesReference(tableProcessor)
    track.set_states_global_tracking_weight(1)
    track.set_allow_unused_references(True)
    track.set_track_reference_position_derivatives(True)
    track.set_apply_tracked_states_to_guess(True)
    track.set_initial_time(0.0)
    track.set_final_time(0.470089)
    study = track.initialize()
    problem = study.updProblem()

    symmetryGoal = osim.MocoPeriodicityGoal("symmetryGoal")
    problem.addGoal(symmetryGoal)
    model = modelProcessor.process()
    model.initSystem()
    for i in range(model.getNumStateVariables()):
        name = model.getStateVariableNames().getitem(i)
        is_joint = name.startswith("/jointset")
        is_act = name.endswith("/activation")
        if not (is_joint or is_act):
            continue
        if "_r" in name:
            symmetryGoal.addStatePair(osim.MocoPeriodicityGoalPair(name, re.sub(r"_r", "_l", name)))
        elif "_l" in name:
            symmetryGoal.addStatePair(osim.MocoPeriodicityGoalPair(name, re.sub(r"_l", "_r", name)))
        elif is_joint and "pelvis_tx/value" not in name:
            symmetryGoal.addStatePair(osim.MocoPeriodicityGoalPair(name))
    symmetryGoal.addControlPair(osim.MocoPeriodicityGoalPair("/lumbarAct"))

    effort = osim.MocoControlGoal.safeDownCast(problem.updGoal("control_effort"))
    effort.setWeight(10)

    contactTracking = osim.MocoContactTrackingGoal("contact", 1)
    contactTracking.setExternalLoadsFile("referenceGRF.xml")
    right = osim.StdVectorString()
    right.append("contactHeel_r")
    right.append("contactFront_r")
    contactTracking.addContactGroup(right, "Right_GRF")
    left = osim.StdVectorString()
    left.append("contactHeel_l")
    left.append("contactFront_l")
    contactTracking.addContactGroup(left, "Left_GRF")
    contactTracking.setProjection("plane")
    contactTracking.setProjectionVector(osim.Vec3(0, 0, 1))
    problem.addGoal(contactTracking)

    d = math.pi / 180
    problem.setStateInfo("/jointset/groundPelvis/pelvis_tilt/value", [-20 * d, -10 * d])
    problem.setStateInfo("/jointset/groundPelvis/pelvis_tx/value", [0, 1])
    problem.setStateInfo("/jointset/groundPelvis/pelvis_ty/value", [0.75, 1.25])
    for s in ("l", "r"):
        problem.setStateInfo(f"/jointset/hip_{s}/hip_flexion_{s}/value", [-10 * d, 60 * d])
        problem.setStateInfo(f"/jointset/knee_{s}/knee_angle_{s}/value", [-50 * d, 0])
        problem.setStateInfo(f"/jointset/ankle_{s}/ankle_angle_{s}/value", [-15 * d, 25 * d])
    problem.setStateInfo("/jointset/lumbar/lumbar/value", [0, 20 * d])

    solution = study.solve()
    solution.unseal()
    out = HERE / "seed_tracking.sto"
    solution.write(str(out))
    print(f"seed written: {out} (success={solution.success()})")


if __name__ == "__main__":
    main()
