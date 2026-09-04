"""One-command finish for a converged 3D metabolic solution.

Runs, in order, against experiments/phase3_3drunning/<solution>:
  1. validate_seed3d.py   — joint tracking vs Hamner RRA + GRF overlay
  2. analyze_arm_momentum.py with the solution as an extra motion —
     does the metabolic objective restore arm-leg counter-rotation?
  3. export_seed3d_stations.py — stations JSON for the web renderers
Prints the produced files. Add the solution to GAITS_3D in
export_ue_gaits.py (and rerun it) to bring it into the Unreal viewer.

Usage: finalize_met_solution.py <solution.sto> [tag]
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
D3 = ROOT / "experiments" / "phase3_3drunning"


def run(*args: str) -> None:
    print(f"\n$ {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main(solution: str, tag: str = "met3d") -> None:
    if not (D3 / solution).exists():
        raise SystemExit(f"missing: {D3 / solution}")
    run(str(SCRIPTS / "validate_seed3d.py"), solution, tag)
    run(str(SCRIPTS / "analyze_arm_momentum.py"),
        f"predicted (metabolic)={D3 / solution}")
    run(str(SCRIPTS / "export_seed3d_stations.py"), str(D3 / solution),
        str(SCRIPTS / f"{tag}_stations.json"))
    print("\nproduced:")
    for p in (ROOT / "experiments" / f"phase3_{tag}_validation.png",
              ROOT / "experiments" / "phase3_arm_momentum.png",
              SCRIPTS / f"{tag}_stations.json"):
        print(f"  {p}  ({'ok' if p.exists() else 'MISSING'})")


if __name__ == "__main__":
    main(*sys.argv[1:3])
