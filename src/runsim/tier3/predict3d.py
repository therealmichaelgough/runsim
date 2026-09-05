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

import json
import math
import time
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
    passive_forces: bool = False
    actuator_strength: dict[str, float] | None = None
    torque_power_weight: float | None = None
    torque_power_actuators: tuple[str, ...] | None = None
    joint_passives: bool = False
    torque_price_per_nm2: float | None = None


STOCK_ACTUATOR_STRENGTH = 10.0  # the model's placeholder optimal force, N.m


def strength_sidecar(solution_path: Path | str) -> Path:
    """`<solution>.strength.json`: the torque actuators' optimal forces a
    solution was solved with, so a later solve can rescale its controls."""
    p = Path(solution_path)
    return p.with_name(p.stem + ".strength.json")


def actuator_strengths(model: osim.Model) -> dict[str, float]:
    """{CoordinateActuator name: optimal force (N.m)} of a model."""
    out = {}
    fs = model.getForceSet()
    for i in range(fs.getSize()):
        act = osim.CoordinateActuator.safeDownCast(fs.get(i))
        if act is not None:
            out[act.getName()] = float(act.getOptimalForce())
    return out


def guess_strengths(guess_path: Path | str) -> dict[str, float] | None:
    """Optimal forces the guess was solved with: from its sidecar, else
    None (a solution predating sidecars: the stock actuators)."""
    side = strength_sidecar(guess_path)
    return json.loads(side.read_text()) if side.exists() else None


def torque_scale_factors(model: osim.Model,
                         guess: dict[str, float] | None) -> dict[str, float]:
    """Per-actuator factor turning the guess's controls into this model's:
    a control u under F_guess N.m is torque u*F_guess, i.e. control
    u*F_guess/F_model under F_model. Only factors != 1 are returned."""
    factors = {}
    fs = model.getForceSet()
    for i in range(fs.getSize()):
        act = osim.CoordinateActuator.safeDownCast(fs.get(i))
        if act is None:
            continue
        f_guess = (guess or {}).get(act.getName(), STOCK_ACTUATOR_STRENGTH)
        f_model = float(act.getOptimalForce())
        if f_guess != f_model:
            factors[act.getAbsolutePathString()] = f_guess / f_model
    return factors


def _rescale_guess_torques(guess_path: Path | str, model: osim.Model,
                           out_path: Path) -> Path:
    """Rewrite a guess so its torque-actuator controls express the same
    torques under this model's optimal forces (see torque_scale_factors);
    returns the original path when nothing needs scaling. Muscle controls
    are untouched. Without this, chaining legs across an actuator-strength
    change shrinks or inflates the trunk/arm torques at every restart."""
    factors = torque_scale_factors(model, guess_strengths(guess_path))
    if not factors:
        return Path(guess_path)
    traj = osim.MocoTrajectory(str(guess_path))
    names = set(traj.getControlNames())
    for path, factor in factors.items():
        if path in names:
            col = traj.getControl(path).to_numpy() * factor
            traj.setControl(path, osim.Vector.createFromMat(col))
    traj.write(str(out_path))
    return out_path


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
    # The model ships arm coordinates with +-10 rad ranges; unbounded arms
    # (plus torque actuators the metabolic objective does not price) were
    # an escape route into restoration collapse. Physiological running
    # ranges (Hamner reference arm_flex -47..-32 deg, elbow ~110-130 deg).
    problem.setStateInfo("/jointset/back/lumbar_bending/value", [-20 * D2R, 20 * D2R])
    problem.setStateInfo("/jointset/back/lumbar_rotation/value", [-25 * D2R, 25 * D2R])
    for side in ("l", "r"):
        problem.setStateInfo(f"/jointset/acromial_{side}/arm_flex_{side}/value",
                             [-90 * D2R, 60 * D2R])
        problem.setStateInfo(f"/jointset/acromial_{side}/arm_add_{side}/value",
                             [-60 * D2R, 30 * D2R])
        problem.setStateInfo(f"/jointset/acromial_{side}/arm_rot_{side}/value",
                             [-90 * D2R, 60 * D2R])
        problem.setStateInfo(f"/jointset/elbow_{side}/elbow_flex_{side}/value",
                             [30 * D2R, 150 * D2R])
        problem.setStateInfo(f"/jointset/radioulnar_{side}/pro_sup_{side}/value",
                             [0, 120 * D2R])


def gait_label(speed_ms: float, grade: float, objective: str) -> str:
    return ("p3d_" + f"v{speed_ms:g}_g{grade:+g}".replace("+", "p")
            .replace("-", "m").replace(".", "_")
            + ("_met" if objective == "metabolic" else ""))


def build_running_study(
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
    passive_forces: bool = False,
    actuator_strength: dict[str, float] | None = None,
    torque_power_weight: float | None = None,
    torque_power_actuators: tuple[str, ...] | None = None,
    joint_passives: bool = False,
    torque_price_per_nm2: float | None = None,
) -> tuple[osim.MocoStudy, osim.Model, str]:
    """Assemble the predictive problem without solving it: returns the
    study, the (metabolics-equipped) model, and the solution label.
    Parameters as for predict_gait_3d."""
    if objective not in ("effort", "metabolic"):
        raise ValueError("objective must be 'effort' or 'metabolic'")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = label or gait_label(speed_ms, grade, objective)
    build = dict(passive_forces=passive_forces, actuator_strength=actuator_strength,
                 joint_passives=joint_passives)

    study = osim.MocoStudy()
    study.setName(f"gaitPrediction3D_{label}")
    problem = study.updProblem()

    model = build_running_model(model_path, **build)
    theta = math.atan(grade)
    model.set_gravity(osim.Vec3(-9.81 * math.sin(theta), -9.81 * math.cos(theta), 0))
    if objective == "metabolic":
        _attach_metabolics(model)
    model.finalizeConnections()
    problem.setModelProcessor(osim.ModelProcessor(model))

    init = build_running_model(model_path, **build)
    init.initSystem()
    _add_periodicity(problem, init)
    if guess_path is not None:
        guess_path = _rescale_guess_torques(
            guess_path, init, out_dir / f"guess_rescaled_{label}.sto")

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
        if torque_price_per_nm2 is not None or torque_weight is not None:
            # Bhargava prices muscles only; the lumbar/arm CoordinateActuators
            # are otherwise nearly free under this objective (banked iterate:
            # arm flexion 91 deg RMS off the human reference). Weight their
            # controls in the regularizer so torque-driven flailing costs.
            # torque_price_per_nm2 prices TORQUE squared uniformly across
            # actuators of different capacity: control weight = price * F^2.
            fs = init.getForceSet()
            for i in range(fs.getSize()):
                act = osim.CoordinateActuator.safeDownCast(fs.get(i))
                if act is not None:
                    w = (torque_price_per_nm2 * act.getOptimalForce() ** 2
                         if torque_price_per_nm2 is not None else torque_weight)
                    effort.setWeightForControl(act.getAbsolutePathString(), w)
        problem.addGoal(effort)
        if torque_power_weight is not None:
            fs = init.getForceSet()
            for i in range(fs.getSize()):
                f = fs.get(i)
                if f.getConcreteClassName() == "CoordinateActuator" and (
                        torque_power_actuators is None
                        or f.getName().startswith(tuple(torque_power_actuators))):
                    power = osim.MocoOutputGoal(f"power_{f.getName()}", torque_power_weight)
                    power.setOutputPath(f"{f.getAbsolutePathString()}|power")
                    power.setExponent(2)
                    power.setDivideByMass(True)
                    power.setDivideByDisplacement(True)
                    problem.addGoal(power)
    else:
        effort = osim.MocoControlGoal("effort", 10)
        effort.setExponent(3)
        effort.setDivideByDisplacement(True)
        if actuator_strength:
            # cubed-control effort prices activation; with literature-strength
            # actuators that makes 20 N.m of trunk torque cost 0.001. Price the
            # torque actuators' CONTROLS as if they were still the stock 10 N.m
            # units (weight (F/10)^3): the validated effort gait's pricing scale,
            # independent of the actuator strength chosen for the model.
            fs = init.getForceSet()
            for i in range(fs.getSize()):
                act = osim.CoordinateActuator.safeDownCast(fs.get(i))
                if act is not None:
                    effort.setWeightForControl(
                        act.getAbsolutePathString(),
                        (act.getOptimalForce() / STOCK_ACTUATOR_STRENGTH) ** 3)
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
    return study, model, label


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
    passive_forces: bool = False,
    actuator_strength: dict[str, float] | None = None,
    torque_power_weight: float | None = None,
    torque_power_actuators: tuple[str, ...] | None = None,
    joint_passives: bool = False,
    torque_price_per_nm2: float | None = None,
) -> GaitPrediction3D:
    """Solve one predictive full-cycle 3D running problem; write the
    solution and GRFs into out_dir.

    objective: "effort" (cubed controls / distance) or "metabolic"
    (Bhargava cost of transport + small quadratic effort regularizer).
    torque_weight: metabolic objective only — weight on the lumbar/arm
    torque-actuator controls in the quadratic regularizer, in control
    (activation-like, torque / optimal force) space.
    torque_price_per_nm2: replaces torque_weight with a price on torque
    squared that is the same for every actuator regardless of its optimal
    force (control weight = price * F^2). In activation space a 60-200 N.m
    actuator's 5-20 N.m of holding torque is nearly free and the arms and
    trunk rock across their bounds; 0.006 per (N.m)^2 makes ~25 N.m rms of
    trunk torque cost ~0.4 J/kg/m, a tenth of running's metabolic cost.
    torque_power_weight: metabolic objective only — prices the ideal
    torque actuators' MECHANICAL WORK, which Bhargava (muscles only)
    leaves free: sum over actuators of squared power, per kg per metre,
    i.e. the same units as the metabolic term. Squared power leaves a
    gentle arm swing (~10 W) nearly free while trunk flailing (~200 W)
    costs several J/kg/m; 0.01 makes ~50 W rms per lumbar actuator cost
    ~0.3 J/kg/m, about a tenth of running's metabolic cost.
    torque_power_actuators: name prefixes of the actuators to price this
    way (None = all CoordinateActuators). Each priced actuator is one more
    finite-differenced goal callback in the transcription, so pricing only
    the trunk ("lumbar",) where the free work occurs is much cheaper than
    pricing all thirteen.
    passive_forces / actuator_strength / joint_passives: see
    model3d.build_running_model.
    The guess's torque controls are rescaled from the strengths it was
    solved with (its `.strength.json` sidecar; stock 10 N.m if none) so
    the guessed torques are unchanged; every solution gets a sidecar."""
    out_dir = Path(out_dir)
    study, model, label = build_running_study(
        speed_ms, grade, out_dir, guess_path, model_path, mesh_intervals,
        max_iterations, label, objective, torque_weight, passive_forces,
        actuator_strength, torque_power_weight, torque_power_actuators,
        joint_passives, torque_price_per_nm2)

    t0 = time.time()
    solution = study.solve()
    solve_time = time.time() - t0
    success = solution.success()
    solution.unseal()

    sol_path = out_dir / f"solution_{label}.sto"
    solution.write(str(sol_path))
    strength_sidecar(sol_path).write_text(json.dumps(actuator_strengths(model), indent=1))

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
        cost_of_transport=cot, passive_forces=passive_forces,
        actuator_strength=dict(actuator_strength) if actuator_strength else None,
        torque_power_weight=torque_power_weight,
        torque_power_actuators=tuple(torque_power_actuators) if torque_power_actuators else None,
        joint_passives=joint_passives, torque_price_per_nm2=torque_price_per_nm2,
    )
