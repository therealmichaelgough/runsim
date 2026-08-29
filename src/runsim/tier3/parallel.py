"""Parallel sweep execution for tier-3 solves — the default for sweeps.

Instead of a sequential homotopy chain (one solve at a time, each seeded
from the previous), a sweep launches every point as its own process, each
seeded from the nearest *already completed* solution and capped to a fair
share of the machine's threads via OPENSIM_MOCO_PARALLEL. Wall-clock cost
drops from sum-of-solves to roughly the slowest single solve, at a small
seed-quality penalty. Use a sequential chain only when no completed
solution is close enough to seed from (e.g. the first traversal into a
new regime, like the original walk-to-run speed chain).

Each point writes an isolated fragment JSON (no shared-log races);
merge_fragments folds them into the sweep's log after the batch drains.
Points whose fragment already exists are skipped, so re-running a sweep
is safe (same convention as the sequential chains).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TOTAL_THREADS = os.cpu_count() or 8


@dataclass
class SweepPoint:
    """One solve: kwargs for runsim.tier3.predict_gait_2d plus a seed."""

    key: str  # unique, filesystem-safe, e.g. "f2.8" or "g+0.05"
    kwargs: dict = field(default_factory=dict)  # passed to predict_gait_2d
    seed: str | None = None  # guess_path
    extra: dict = field(default_factory=dict)  # merged into the stats row


def threads_per_point(n_points: int, total: int = DEFAULT_TOTAL_THREADS) -> int:
    """Fair per-process thread share, at least 1."""
    return max(1, total // max(1, n_points))


def launch(
    points: list[SweepPoint],
    out_dir: Path | str,
    total_threads: int = DEFAULT_TOTAL_THREADS,
    below_normal: bool = True,
) -> list[subprocess.Popen]:
    """Start one worker process per point (skipping completed fragments).

    Returns the Popen handles; combine with wait_and_merge, or hand the
    PIDs to a detached finisher script for session-proof chaining.
    """
    out_dir = Path(out_dir)
    frag_dir = out_dir / "fragments"
    frag_dir.mkdir(parents=True, exist_ok=True)
    todo = [p for p in points if not (frag_dir / f"{p.key}.json").exists()]
    if not todo:
        return []
    env = dict(os.environ, OPENSIM_MOCO_PARALLEL=str(threads_per_point(len(todo), total_threads)))
    flags = 0
    if below_normal and os.name == "nt":
        flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS
    procs = []
    for p in todo:
        spec = {"key": p.key, "kwargs": p.kwargs, "seed": p.seed, "extra": p.extra,
                "out_dir": str(out_dir)}
        spec_path = frag_dir / f"{p.key}.spec.json"
        spec_path.write_text(json.dumps(spec, indent=2))
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "runsim.tier3.solve_point", str(spec_path)],
            stdout=open(out_dir / f"par_{p.key}.out.log", "w"),
            stderr=open(out_dir / f"par_{p.key}.err.log", "w"),
            env=env, creationflags=flags,
        ))
    return procs


def merge_fragments(out_dir: Path | str, log_path: Path | str, sort_by: str) -> int:
    """Fold fragments/*.json into log_path (dedup by `key`), sorted."""
    out_dir, log_path = Path(out_dir), Path(log_path)
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    seen = {r.get("key") for r in log}
    added = 0
    for frag in sorted((out_dir / "fragments").glob("*.json")):
        if frag.name.endswith(".spec.json"):
            continue
        r = json.loads(frag.read_text())
        if r.get("key") not in seen:
            log.append(r)
            added += 1
    log.sort(key=lambda r: r.get(sort_by, 0))
    log_path.write_text(json.dumps(log, indent=2))
    return added


def wait_and_merge(
    procs: list[subprocess.Popen],
    out_dir: Path | str,
    log_path: Path | str,
    sort_by: str,
) -> int:
    for p in procs:
        p.wait()
    return merge_fragments(out_dir, log_path, sort_by)
