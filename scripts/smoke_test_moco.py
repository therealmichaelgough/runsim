"""Verify the Moco optimal-control toolchain (CasADi + IPOPT) works end to end.

Solves the canonical minimum-effort sliding-mass problem: move a 2 kg point
mass 1 m in 1 s. Should converge in a few seconds; analytic solution is a
bang-bang-like smooth control, final state (1, 0).
"""
import opensim as osim


def build_model() -> osim.Model:
    model = osim.Model()
    model.setName("sliding_mass")
    model.set_gravity(osim.Vec3(0, 0, 0))
    body = osim.Body("body", 2.0, osim.Vec3(0), osim.Inertia(0))
    model.addComponent(body)

    joint = osim.SliderJoint("slider", model.getGround(), body)
    joint.updCoordinate().setName("position")
    model.addComponent(joint)

    actu = osim.CoordinateActuator()
    actu.setCoordinate(joint.updCoordinate())
    actu.setName("actuator")
    actu.setOptimalForce(1)
    model.addComponent(actu)
    model.finalizeConnections()
    return model


def main() -> None:
    study = osim.MocoStudy()
    problem = study.updProblem()
    problem.setModel(build_model())
    problem.setTimeBounds(0, 1)
    problem.setStateInfo("/slider/position/value", [-5, 5], 0, 1)
    problem.setStateInfo("/slider/position/speed", [-50, 50], 0, 0)
    problem.setControlInfo("/actuator", [-50, 50])
    problem.addGoal(osim.MocoControlGoal("effort"))

    solver = study.initCasADiSolver()
    solver.set_num_mesh_intervals(50)
    solution = study.solve()

    final_pos = solution.getState("/slider/position/value").to_numpy()[-1]
    print(f"solved: {solution.success()}, final position = {final_pos:.4f} (expect 1.0)")
    assert solution.success() and abs(final_pos - 1.0) < 1e-3
    print("Moco toolchain OK")


if __name__ == "__main__":
    main()
