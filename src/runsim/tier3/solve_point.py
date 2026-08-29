"""Worker for runsim.tier3.parallel: solve one sweep point from a spec
JSON and write its stats fragment. Invoked as

    python -m runsim.tier3.solve_point <spec.json>

Spec: {key, kwargs (for predict_gait_2d), seed, extra, out_dir}.
"""
import json
import sys
from pathlib import Path

from runsim.tier3 import predict_gait_2d, solution_summary


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text())
    out_dir = Path(spec["out_dir"])
    r = predict_gait_2d(out_dir=out_dir, guess_path=spec.get("seed"), **spec["kwargs"])
    stats = solution_summary(r.grf_path)
    stats.update(spec.get("extra", {}))
    stats.update(key=spec["key"], success=r.success, objective=r.objective,
                 cost_of_transport=r.cost_of_transport,
                 solve_min=round(r.solve_time_s / 60, 2))
    frag = out_dir / "fragments" / f"{spec['key']}.json"
    frag.write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
