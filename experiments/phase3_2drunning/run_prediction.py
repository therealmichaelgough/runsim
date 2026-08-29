"""Run one predictive 2D gait solve. Usage:
    python run_prediction.py --speed 3.5 [--grade 0.05] [--guess path.sto]
"""
import argparse
from pathlib import Path

from runsim.tier3 import predict_gait_2d, solution_summary

HERE = Path(__file__).resolve().parent
WALK_GUESS = HERE.parent / "phase0_2dwalking" / "gaitPrediction_solution_fullStride.sto"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, required=True)
    ap.add_argument("--grade", type=float, default=0.0)
    ap.add_argument("--guess", type=Path, default=None)
    ap.add_argument("--mesh", type=int, default=50)
    args = ap.parse_args()

    result = predict_gait_2d(
        args.speed, args.grade, out_dir=HERE, guess_path=args.guess, mesh_intervals=args.mesh
    )
    print(f"success={result.success} objective={result.objective:.4f} "
          f"solve_time={result.solve_time_s / 60:.1f} min")
    for k, v in solution_summary(result.grf_path).items():
        print(f"  {k}: {v if isinstance(v, bool) else round(v, 3)}")


if __name__ == "__main__":
    main()
