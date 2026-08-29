"""Predictive 2D muscle-driven gait at arbitrary speed and slope.

Formulation (after Moco's example2DWalking, Dembia 2020; running bounds
widened): one step with left-right periodicity, prescribed average speed,
cubed-control effort divided by displacement. Slope is imposed by rotating
the gravity vector, keeping the contact plane at y=0:

    g = 9.81 * (-sin(theta), -cos(theta), 0),  theta = atan(grade)

so +grade tilts gravity against +x travel (uphill).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import opensim as osim

DEFAULT_MODEL = (
    Path(__file__).resolve().parents[3] / "experiments" / "phase0_2dwalking" / "2D_gait.osim"
)
D2R = math.pi / 180.0


@dataclass
class GaitPrediction:
    speed_ms: float
    grade: float
    solution_path: Path
    full_stride_path: Path
    grf_path: Path
    success: bool
    objective: float
    solve_time_s: float
    #: metabolic cost of transport (J/kg/m, Bhargava incl. basal); None for
    #: effort-only solves
    cost_of_transport: float | None = None


def _attach_metabolics(model: osim.Model) -> None:
    """Add the smoothed Bhargava (2004) metabolics component covering every
    muscle in the model (Falisse 2019 / example2DWalkingMetabolics)."""
    metabolics = osim.Bhargava2004SmoothedMuscleMetabolics()
    metabolics.setName("metabolic_cost")
    metabolics.set_use_smoothing(True)
    for comp in model.getComponentsList():
        muscle = osim.Muscle.safeDownCast(comp)
        if muscle is not None:
            metabolics.addMuscle(muscle.getName(), muscle)
    model.addComponent(metabolics)


def _add_symmetry(problem: osim.MocoProblem, model: osim.Model) -> None:
    goal = osim.MocoPeriodicityGoal("symmetryGoal")
    problem.addGoal(goal)
    for i in range(model.getNumStateVariables()):
        name = model.getStateVariableNames().getitem(i)
        is_joint = name.startswith("/jointset")
        is_act = name.endswith("/activation")
        if not (is_joint or is_act):
            continue
        if "_r" in name:
            goal.addStatePair(osim.MocoPeriodicityGoalPair(name, re.sub(r"_r", "_l", name)))
        elif "_l" in name:
            goal.addStatePair(osim.MocoPeriodicityGoalPair(name, re.sub(r"_l", "_r", name)))
        elif is_joint and "pelvis_tx/value" not in name:
            goal.addStatePair(osim.MocoPeriodicityGoalPair(name))
    goal.addControlPair(osim.MocoPeriodicityGoalPair("/lumbarAct"))


def _set_running_bounds(problem: osim.MocoProblem, grade: float) -> None:
    tilt_shift = math.atan(grade)  # let the trunk rotate with the slope
    problem.setStateInfo(
        "/jointset/groundPelvis/pelvis_tilt/value",
        [(-35 * D2R) + tilt_shift, (10 * D2R) + tilt_shift],
    )
    problem.setStateInfo("/jointset/groundPelvis/pelvis_tx/value", [0, 3])
    problem.setStateInfo("/jointset/groundPelvis/pelvis_ty/value", [0.6, 1.35])
    for side in ("l", "r"):
        problem.setStateInfo(f"/jointset/hip_{side}/hip_flexion_{side}/value", [-25 * D2R, 85 * D2R])
        problem.setStateInfo(f"/jointset/knee_{side}/knee_angle_{side}/value", [-115 * D2R, 5 * D2R])
        problem.setStateInfo(f"/jointset/ankle_{side}/ankle_angle_{side}/value", [-38 * D2R, 30 * D2R])
    problem.setStateInfo("/jointset/lumbar/lumbar/value", [-5 * D2R, 30 * D2R])


def predict_gait_2d(
    speed_ms: float,
    grade: float = 0.0,
    out_dir: Path | str = ".",
    guess_path: Path | str | None = None,
    model_path: Path | str = DEFAULT_MODEL,
    mesh_intervals: int = 50,
    max_iterations: int = 2000,
    label: str | None = None,
    objective: str = "effort",
) -> GaitPrediction:
    """Solve a predictive one-step gait problem; write solution, full
    stride, and GRFs into out_dir. Returns paths and solve metadata.

    objective: "effort" (cubed controls / distance) or "metabolic"
    (Bhargava cost of transport + small quadratic effort regularizer).
    """
    if objective not in ("effort", "metabolic"):
        raise ValueError("objective must be 'effort' or 'metabolic'")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = label or (
        f"v{speed_ms:g}_g{grade:+g}".replace("+", "p").replace("-", "m").replace(".", "_")
        + ("_met" if objective == "metabolic" else "")
    )

    study = osim.MocoStudy()
    study.setName(f"gaitPrediction_{label}")
    problem = study.updProblem()

    model = osim.Model(str(model_path))
    theta = math.atan(grade)
    model.set_gravity(osim.Vec3(-9.81 * math.sin(theta), -9.81 * math.cos(theta), 0))
    if objective == "metabolic":
        _attach_metabolics(model)
    model.finalizeConnections()
    problem.setModelProcessor(osim.ModelProcessor(model))

    init = osim.Model(str(model_path))
    init.initSystem()
    _add_symmetry(problem, init)

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
        problem.addGoal(effort)
    else:
        effort = osim.MocoControlGoal("effort", 10)
        effort.setExponent(3)
        effort.setDivideByDisplacement(True)
        problem.addGoal(effort)

    # step duration bracket: generous around the Tier-1 fitted cadence
    problem.setTimeBounds(0, [0.18, 0.65])
    _set_running_bounds(problem, grade)

    solver = study.initCasADiSolver()
    solver.set_num_mesh_intervals(mesh_intervals)
    solver.set_verbosity(2)
    solver.set_optim_solver("ipopt")
    solver.set_optim_convergence_tolerance(1e-4)
    solver.set_optim_constraint_tolerance(1e-4)
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

    full = osim.createPeriodicTrajectory(solution)
    full_path = out_dir / f"fullstride_{label}.sto"
    full.write(str(full_path))

    contact_r = osim.StdVectorString()
    contact_l = osim.StdVectorString()
    for c in ("contactHeel_r", "contactFront_r"):
        contact_r.append(c)
    for c in ("contactHeel_l", "contactFront_l"):
        contact_l.append(c)
    grf = osim.createExternalLoadsTableForGait(model, full, contact_r, contact_l)
    grf_path = out_dir / f"grf_{label}.sto"
    osim.STOFileAdapter.write(grf, str(grf_path))

    cot = None
    if objective == "metabolic":
        try:
            cot = _cost_of_transport(model, solution)
        except Exception as exc:  # never let post-processing waste a solve
            print(f"[warn] cost-of-transport extraction failed: {exc}")

    return GaitPrediction(
        speed_ms=speed_ms,
        grade=grade,
        solution_path=sol_path,
        full_stride_path=full_path,
        grf_path=grf_path,
        success=success,
        objective=solution.getObjective(),
        solve_time_s=solve_time,
        cost_of_transport=cot,
    )


def _cost_of_transport(model: osim.Model, solution: osim.MocoTrajectory) -> float:
    """Whole-body metabolic energy per kg per metre for a solved step."""
    state = model.initSystem()
    paths = osim.StdVectorString()
    # analyzeMocoTrajectory treats entries as regex patterns over output paths
    paths.append(".*metabolic_cost.*total_metabolic_rate")
    table = osim.analyzeMocoTrajectory(model, solution, paths)
    labels = list(table.getColumnLabels())
    if not labels:
        raise RuntimeError("metabolic output not found in analysis table")
    t = np.asarray(table.getIndependentColumn())
    rate = table.getDependentColumn(labels[0]).to_numpy()
    energy = float(np.trapezoid(rate, t))
    tx = solution.getState("/jointset/groundPelvis/pelvis_tx/value").to_numpy()
    distance = float(tx[-1] - tx[0])
    return energy / (model.getTotalMass(state) * distance)


def solution_summary(grf_path: Path | str, mass_kg: float = 62.0) -> dict:
    """Stride metrics from a full-stride GRF file: contact/flight times,
    step frequency, peak vertical force (BW), duty factor."""
    table = osim.TimeSeriesTable(str(grf_path))
    t = np.asarray(table.getIndependentColumn())
    fy_r = table.getDependentColumn("ground_force_r_vy").to_numpy()
    fy_l = table.getDependentColumn("ground_force_l_vy").to_numpy()
    stride_T = t[-1] - t[0]
    bw = mass_kg * 9.81

    on = fy_r > 0.05 * bw
    frac_contact = on.mean()
    t_c = frac_contact * stride_T
    t_step = stride_T / 2.0
    both_off = (fy_r < 0.05 * bw) & (fy_l < 0.05 * bw)
    return {
        "stride_time_s": float(stride_T),
        "step_freq_hz": float(1.0 / t_step),
        "contact_time_s": float(t_c),
        "flight_fraction": float(both_off.mean()),
        "aerial": bool(both_off.mean() > 0.02),
        "peak_force_bw": float(max(fy_r.max(), fy_l.max()) / bw),
    }
