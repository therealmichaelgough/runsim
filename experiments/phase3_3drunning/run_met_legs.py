"""Segmented metabolic solve: checkpointing by construction.

Moco writes trajectories only at solve completion, so long solves are
run as short capped LEGS (~300 iterations): every leg completes normally
and banks its iterate to disk; the next leg warm-starts from it. A
collapse can cost at most one leg, and each boundary applies a health
gate — a leg whose objective degrades is discarded and re-run from the
prior good file (the barrier reset alone often clears the pathology).

Usage: run_met_legs.py [start_solution] [leg_iters] [max_legs]
Defaults: solution_p3d_v3_gp0_met.sto (the capped first leg's output),
300, 12. Stops early when a leg converges (success=True).
"""
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

from runsim.tier3 import solution_summary
from runsim.tier3.model3d import JOINT_PASSIVES, RUNNING_ACTUATOR_STRENGTH
from runsim.tier3.predict3d import gait_label, predict_gait_3d, strength_sidecar

HERE = Path(__file__).resolve().parent
LOG = HERE / "predict3d_met_log.json"
MASS = 75.16


def main(start: str = "solution_p3d_v3_gp0_met.sto",
         leg_iters: int = 300, max_legs: int = 12,
         torque_weight: float | None = None,
         mesh_intervals: int = 50,
         passive_forces: bool = False,
         actuator_strength: bool = False,
         torque_power_weight: float | None = None,
         torque_power_actuators: tuple[str, ...] | None = None,
         joint_passives: bool = False,
         torque_price_per_nm2: float | None = None,
         effort_blend: float | None = None,
         objective: str = "metabolic",
         tag: str = "") -> Path | None:
    """Run capped legs from `start`; returns the last banked solution (or
    None). `tag` names the banked files met_<tag>_legNN.sto so continuation
    stages do not overwrite one another."""
    guess = Path(start) if Path(start).is_absolute() else HERE / start
    if not guess.exists():
        raise SystemExit(f"start solution missing: {guess}")
    strength = RUNNING_ACTUATOR_STRENGTH if actuator_strength else None
    # the joint-passive PARAMETERS are part of the formulation: v10 and v11
    # differed only in them, and a bool key let v11's leg 1 be judged
    # against v10's objective, discarded, and re-run in a loop (2026-09-05)
    passives_key = (hashlib.md5(json.dumps(JOINT_PASSIVES, sort_keys=True).encode()).hexdigest()[:8]
                    if joint_passives else None)
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    # gate baseline: best objective already recorded for this FORMULATION
    # (same torque weight, passive-force, actuator-strength and power-price
    # settings — objectives across formulations are not comparable), so
    # leg 1 is judged against prior legs of its own kind, or ungated if none
    formulation = dict(objective_kind=objective,
                       torque_weight=torque_weight, passive_forces=passive_forces,
                       actuator_strength=strength,
                       torque_power_weight=torque_power_weight,
                       torque_power_actuators=list(torque_power_actuators) if torque_power_actuators else None,
                       joint_passives=passives_key,
                       torque_price_per_nm2=torque_price_per_nm2,
                       effort_blend=effort_blend)
    prev_objs = [r["objective"] for r in log
                 if r.get("speed") == 3.0 and "objective" in r
                 and all(r.get(k) == v for k, v in formulation.items())]
    prev_obj = min(prev_objs) if prev_objs else None
    last_banked: Path | None = None
    prefix = f"met_{tag}_leg" if tag else "met_leg"
    # provenance: IPOPT reads ./ipopt.opt from the CWD at every solver start
    opt_file = Path.cwd() / "ipopt.opt"
    ipopt_opts = ([l.strip() for l in opt_file.read_text().splitlines()
                   if l.strip() and not l.startswith("#")]
                  if opt_file.exists() else [])

    for leg in range(1, max_legs + 1):
        t0 = time.time()
        # the driver's working solution must never collide with a hand-run
        # solution of the same speed/grade/objective (Stage A overwrote the
        # validated effort gait solution_p3d_v3_gp0.sto on 2026-09-05)
        label = gait_label(3.0, 0.0, objective) + "_legs" + (f"_{tag}" if tag else "")
        r = predict_gait_3d(3.0, out_dir=HERE, guess_path=guess, label=label,
                            max_iterations=leg_iters, objective=objective,
                            torque_weight=torque_weight,
                            mesh_intervals=mesh_intervals,
                            passive_forces=passive_forces,
                            actuator_strength=strength,
                            torque_power_weight=torque_power_weight,
                            torque_power_actuators=torque_power_actuators,
                            joint_passives=joint_passives,
                            torque_price_per_nm2=torque_price_per_nm2,
                            effort_blend=effort_blend)
        stats = solution_summary(r.grf_path, mass_kg=MASS)
        stats.update(speed=3.0, grade=0.0, leg=leg, success=r.success,
                     objective=r.objective,
                     cost_of_transport=r.cost_of_transport,
                     solution=r.solution_path.name,
                     **formulation, ipopt=ipopt_opts,
                     mesh_intervals=mesh_intervals,
                     solve_min=round(r.solve_time_s / 60, 2))

        # health gate: a degraded leg is not chained. 5%: a leg that ends
        # worse than the best prior one of its kind was in a collapse
        # (2026-09-04, met_legs7 leg 2: obj 2.74 -> 2.86 with rising
        # violation), and chaining from it compounds the damage.
        if prev_obj is not None and r.objective > prev_obj * 1.05:
            stats["verdict"] = "DEGRADED - discarded, re-running from prior"
            stats["joint_passive_params"] = JOINT_PASSIVES if joint_passives else None
            log.append(stats)
            LOG.write_text(json.dumps(log, indent=2))
            print(json.dumps(stats), flush=True)
            print(f"[leg {leg} DEGRADED: {r.objective:.4f} > 1.05 x {prev_obj:.4f} - discarded, "
                  f"retrying from {guess.name}]", flush=True)
            continue  # guess unchanged -> barrier-reset retry from prior good

        # bank this leg under its own name, then chain from it — with its
        # strength sidecar, or the next leg rescales the torques as if the
        # iterate had been solved with the stock 10 N.m actuators
        banked = HERE / f"{prefix}{leg:02d}.sto"
        shutil.copyfile(r.solution_path, banked)
        side = strength_sidecar(r.solution_path)
        if side.exists():
            shutil.copyfile(side, strength_sidecar(banked))
        last_banked = banked
        stats["banked"] = banked.name
        stats["joint_passive_params"] = JOINT_PASSIVES if joint_passives else None
        log.append(stats)
        LOG.write_text(json.dumps(log, indent=2))
        print(json.dumps(stats), flush=True)
        print(f"[leg {leg} done in {(time.time() - t0) / 60:.1f} min]", flush=True)
        guess = banked
        prev_obj = min(prev_obj, r.objective) if prev_obj is not None else r.objective

        if r.success:
            print("[converged - metabolic solve COMPLETE]", flush=True)
            return last_banked
    print("[leg budget exhausted without formal convergence]", flush=True)
    return last_banked


if __name__ == "__main__":
    # run_met_legs.py [start.sto] [leg_iters] [max_legs] [torque_weight] [mesh]
    #                 [--passive] [--strength] [--power=W] [--power-on=lumbar,...]
    #                 [--joints]  (knee limit forces + elbow posture springs)
    #                 [--torque-price=P]  (torque^2 price per (N.m)^2, all actuators)
    #                 [--effort-blend=W]  (cubed effort term kept at weight W: continuation)
    #                 [--objective=effort]  (Stage A of the continuation: effort objective)
    #                 [--tag=NAME]  (bank as met_NAME_legNN.sto instead of met_legNN.sto)
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    power = next((float(a.split("=", 1)[1]) for a in flags if a.startswith("--power=")), None)
    power_on = next((tuple(a.split("=", 1)[1].split(",")) for a in flags
                     if a.startswith("--power-on=")), None)
    torque_price = next((float(a.split("=", 1)[1]) for a in flags
                         if a.startswith("--torque-price=")), None)
    effort_blend = next((float(a.split("=", 1)[1]) for a in flags
                         if a.startswith("--effort-blend=")), None)
    objective = next((a.split("=", 1)[1] for a in flags
                      if a.startswith("--objective=")), "metabolic")
    tag = next((a.split("=", 1)[1] for a in flags if a.startswith("--tag=")), "")
    main(*(args[:1] or []),
         *([int(args[1])] if len(args) > 1 else []),
         *([int(args[2])] if len(args) > 2 else []),
         *([float(args[3])] if len(args) > 3 else []),
         *([int(args[4])] if len(args) > 4 else []),
         passive_forces="--passive" in flags,
         actuator_strength="--strength" in flags,
         torque_power_weight=power, torque_power_actuators=power_on,
         joint_passives="--joints" in flags, torque_price_per_nm2=torque_price,
         effort_blend=effort_blend, objective=objective, tag=tag)
