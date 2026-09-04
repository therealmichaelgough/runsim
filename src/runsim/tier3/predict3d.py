"""Predictive 3D muscle-driven running at arbitrary speed and slope.

Extends the 2D formulation (predict2d, after Falisse 2019 / Dembia 2020)
to the subject-scaled LaiUhlrich model prepared by model3d: one FULL gait
cycle with all-states periodicity (except forward translation), a
prescribed average speed, and cubed-control effort divided by
displacement. Full-cycle periodicity is chosen over half-cycle left-right
symmetry so the validated tracking seed (a full Hamner cycle) is a
drop-in guess and no 3D sign-pairing bookkeeping is needed; the cost is a
doubled horizon. Slope via rotated gravity, as in 2D.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import opensim as osim

from .model3d import CONTACT_FORCES_LEFT, CONTACT_FORCES_RIGHT, build_running_model

DEFAULT_MODEL = (
    Path(__file__).resolve().parents[3] / "experiments" / "phase3_3drunning"
    / "lai_subject01.osim"
)
D2R = math.pi / 180.0


@dataclass
class GaitPrediction3D:
    speed_ms: float
    grade: float
    solution_path: Path
    grf_path: Path
    success: bool
    objective: float
    solve_time_s: float
    cost_of_transport: float | None = None


def _attach_metabolics(model: osim.Model) -> None:
    """Smoothed Bhargava (2004) metabolics over every muscle (Falisse
    2019 / example2DWalkingMetabolics), as in predict2d."""
    metabolics = osim.Bhargava2004SmoothedMuscleMetabolics()
    metabolics.setName("metabolic_cost")
    metabolics.set_use_smoothing(True)
    for comp in model.getComponentsList():
        muscle = osim.Muscle.safeDownCast(comp)
        if muscle is not None:
            metabolics.addMuscle(muscle.getName(), muscle)
    model.addComponent(metabolics)


def _cost_of_transport(model: osim.Model, solution: osim.MocoTrajectory) -> float:
    """Whole-body metabolic energy per kg per metre (J/kg/m)."""
    state = model.initSystem()
    paths = osim.StdVectorString()
    # analyzeMocoTrajectory entries are regex patterns (CLAUDE.md gotcha)
    paths.append(".*metabolic_cost.*total_metabolic_rate")
    table = osim.analyzeMocoTrajectory(model, solution, paths)
    labels = list(table.getColumnLabels())
    if not labels:
        raise RuntimeError("metabolic output not found")
    t = np.asarray(table.getIndependentColumn())
    rate = table.getDependentColumn(labels[0]).to_numpy()
    energy = float(np.trapezoid(rate, t))
    tx = solution.getState("/jointset/ground_pelvis/pelvis_tx/value").to_numpy()
    return energy / (model.getTotalMass(state) * float(tx[-1] - tx[0]))


def _add_periodicity(problem: osim.MocoProblem, model: osim.Model) -> None:
    """Full-cycle periodicity: every state returns to its initial value
    except the forward translation."""
    goal = osim.MocoPeriodicityGoal("periodicity")
    problem.addGoal(goal)
    for i in range(model.getNumStateVariables()):
        name = model.getStateVariableNames().getitem(i)
        if "pelvis_tx/value" in name:
            continue
        goal.addStatePair(osim.MocoPeriodicityGoalPair(name))
    # torque actuators (lumbar + arms) get periodic controls, as the 2D
    # formulation did for its lumbar actuator; muscle controls are tied
    # down through their periodic activation states
    fs = model.getForceSet()
    for i in range(fs.getSize()):
        f = fs.get(i)
        if f.getConcreteClassName() == "CoordinateActuator":
            goal.addControlPair(
                osim.MocoPeriodicityGoalPair(f.getAbsolutePathString()))


def _set_running_bounds(problem: osim.MocoProblem, grade: float) -> None:
    tilt_shift = math.atan(grade)
    problem.setStateInfo("/jointset/ground_pelvis/pelvis_tilt/value",
                         [(-35 * D2R) + tilt_shift, (15 * D2R) + tilt_shift])
    problem.setStateInfo("/jointset/ground_pelvis/pelvis_list/value",
                         [-15 * D2R, 15 * D2R])
    problem.setStateInfo("/jointset/ground_pelvis/pelvis_rotation/value",
                         [-30 * D2R, 30 * D2R])
    problem.setStateInfo("/jointset/ground_pelvis/pelvis_tx/value", [0, 5])
    problem.setStateInfo("/jointset/ground_pelvis/pelvis_ty/value", [0.6, 1.25])
    problem.setStateInfo("/jointset/ground_pelvis/pelvis_tz/value", [-0.4, 0.4])
    for side in ("l", "r"):
        problem.setStateInfo(f"/jointset/hip_{side}/hip_flexion_{side}/value",
                             [-25 * D2R, 85 * D2R])
        problem.setStateInfo(f"/jointset/hip_{side}/hip_adduction_{side}/value",
                             [-30 * D2R, 25 * D2R])
        problem.setStateInfo(f"/jointset/hip_{side}/hip_rotation_{side}/value",
                             [-30 * D2R, 30 * D2R])
        # Rajagopal knee convention: flexion positive
        problem.setStateInfo(f"/jointset/walker_knee_{side}/knee_angle_{side}/value",
                             [0, 120 * D2R])
        problem.setStateInfo(f"/jointset/ankle_{side}/ankle_angle_{side}/value",
                             [-38 * D2R, 30 * D2R])
    problem.setStateInfo("/jointset/back/lumbar_extension/value",
                         [-35 * D2R, 10 * D2R])


def predict_gait_3d(
    speed_ms: float,
    grade: float = 0.0,
    out_dir: Path | str = ".",
    guess_path: Path | str | None = None,
    model_path: Path | str = DEFAULT_MODEL,
    mesh_intervals: int = 50,
    max_iterations: int = 3000,
    label: str | None = None,
    objective: str = "effort",
    torque_weight: float | None = None,
) -> GaitPrediction3D:
    """Solve one predictive full-cycle 3D running problem; write the
    solution and GRFs into out_dir.

    objective: "effort" (cubed controls / distance) or "metabolic"
    (Bhargava cost of transport + small quadratic effort regularizer)."""
    if objective not in ("effort", "metabolic"):
        raise ValueError("objective must be 'effort' or 'metabolic'")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = label or (
        "p3d_" + f"v{speed_ms:g}_g{grade:+g}".replace("+", "p")
        .replace("-", "m").replace(".", "_")
        + ("_met" if objective == "metabolic" else "")
    )

    study = osim.MocoStudy()
    study.setName(f"gaitPrediction3D_{label}")
    problem = study.updProblem()

    model = build_running_model(model_path)
    theta = math.atan(grade)
    model.set_gravity(osim.Vec3(-9.81 * math.sin(theta), -9.81 * math.cos(theta), 0))
    if objective == "metabolic":
        _attach_metabolics(model)
    model.finalizeConnections()
    problem.setModelProcessor(osim.ModelProcessor(model))

    init = build_running_model(model_path)
    init.initSystem()
    _add_periodicity(problem, init)

    speed_goal = osim.MocoAverageSpeedGoal("speed")
    speed_goal.set_desired_average_speed(speed_ms)
    problem.addGoal(speed_goal)

    if objective == "metabolic":
        met = osim.MocoOutputGoal("met", 1.0)
        met.setOutputPath("/metabolic_cost|total_metabolic_rate")
        met.setDivideByDisplacement(True)
        met.setDivideByMass(True)
        problem.addGoal(met)
        effort = osim.MocoControlGoal("effort", 0.1)
        effort.setExponent(2)
        effort.setDivideByDisplacement(True)
        if torque_weight is not None:
            # Bhargava prices muscles only; the lumbar/arm CoordinateActuators
            # are otherwise nearly free under this objective (banked iterate:
            # arm flexion 91 deg RMS off the human reference). Weight their
            # controls in the regularizer so torque-driven flailing costs.
            fs = init.getForceSet()
            for i in range(fs.getSize()):
                f = fs.get(i)
                if f.getConcreteClassName() == "CoordinateActuator":
                    effort.setWeightForControl(f.getAbsolutePathString(), torque_weight)
        problem.addGoal(effort)
    else:
        effort = osim.MocoControlGoal("effort", 10)
        effort.setExponent(3)
        effort.setDivideByDisplacement(True)
        problem.addGoal(effort)

    # full-cycle duration bracket around the seed's 0.715 s
    problem.setTimeBounds(0, [0.4, 1.0])
    _set_running_bounds(problem, grade)

    solver = study.initCasADiSolver()
    solver.set_num_mesh_intervals(mesh_intervals)
    solver.set_verbosity(2)
    solver.set_optim_solver("ipopt")
    solver.set_optim_convergence_tolerance(1e-3)
    solver.set_optim_constraint_tolerance(1e-3)
    solver.set_optim_max_iterations(max_iterations)
    if guess_path is not None:
        solver.setGuessFile(str(guess_path))

    import time

    t0 = time.time()
    solution = study.solve()
    solve_time = time.time() - t0
    success = solution.success()
    solution.unseal()

    sol_path = out_dir / f"solution_{label}.sto"
    solution.write(str(sol_path))

    right = osim.StdVectorString()
    left = osim.StdVectorString()
    for c in CONTACT_FORCES_RIGHT:
        right.append(c)
    for c in CONTACT_FORCES_LEFT:
        left.append(c)
    grf = osim.createExternalLoadsTableForGait(model, solution, right, left)
    grf_path = out_dir / f"grf_{label}.sto"
    osim.STOFileAdapter.write(grf, str(grf_path))

    cot = None
    if objective == "metabolic":
        try:
            cot = _cost_of_transport(model, solution)
        except Exception as exc:  # never let post-processing waste a solve
            print(f"[warn] cost-of-transport extraction failed: {exc}")

    return GaitPrediction3D(
        speed_ms=speed_ms, grade=grade, solution_path=sol_path,
        grf_path=grf_path, success=success,
        objective=solution.getObjective(), solve_time_s=solve_time,
        cost_of_transport=cot,
    )
