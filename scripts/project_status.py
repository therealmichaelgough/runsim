"""Compose the live project-status document for the status page.

Reads local state — git log, the active solver log, the segmented-leg
log, AGENTS_LOG headers — and writes scripts/status_current.json, which
is pushed to the status artifact's database (document `status/current`)
by the coordinating session. Run it any time; it is read-only.

Usage: project_status.py [--solver-log PATH] [--budget N]
"""
import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D3 = ROOT / "experiments" / "phase3_3drunning"
OUT = Path(__file__).resolve().parent / "status_current.json"
ITER_RE = re.compile(r"^ *(\d+)(r?) +([0-9.e+-]+) +([0-9.e+-]+) +([0-9.e+-]+)")


def git_log(n: int = 8) -> list[dict]:
    out = subprocess.run(
        ["git", "log", f"-{n}", "--format=%h|%cI|%s"], cwd=ROOT,
        capture_output=True, text=True).stdout
    rows = []
    for line in out.strip().splitlines():
        h, when, subj = line.split("|", 2)
        rows.append({"hash": h, "when": when, "subject": subj[:90]})
    return rows


def solver_progress(log: Path, budget: int) -> dict:
    if not log.exists():
        return {"state": "no log"}
    lines = log.read_text(errors="ignore").splitlines()
    iters = [ITER_RE.match(l) for l in lines]
    iters = [m for m in iters if m]
    banked = any("[leg00 banked]" in l or "metabolic done" in l for l in lines)
    age_min = (time.time() - log.stat().st_mtime) / 60
    if not iters:
        return {"state": "starting" if age_min < 40 else "dead/stalled",
                "log": log.name}
    last = iters[-1]
    it = int(last.group(1))
    restoration = bool(last.group(2))
    started = datetime.fromtimestamp(log.stat().st_ctime, tz=timezone.utc)
    elapsed_h = max(1e-6, (time.time() - log.stat().st_ctime) / 3600)
    rate = it / elapsed_h
    remaining = max(0, budget - it)
    eta_h = remaining / rate if rate > 0 else None
    tail_r = sum(1 for m in iters[-10:] if m.group(2))
    state = ("banked" if banked else
             "dead/stalled" if age_min > 40 else
             "RESTORATION" if tail_r >= 5 else "healthy")
    return {
        "state": state, "log": log.name, "iteration": it, "budget": budget,
        "objective": float(last.group(3)), "inf_pr": float(last.group(4)),
        "inf_du": float(last.group(5)), "restoration_tail": tail_r,
        "rate_per_hr": round(rate, 1), "started": started.isoformat(),
        "eta_hours": round(eta_h, 1) if eta_h is not None else None,
        "log_age_min": round(age_min, 1),
    }


def legs() -> list[dict]:
    path = D3 / "predict3d_met_log.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text())
    out = []
    for r in rows:
        if r.get("speed") != 3.0:
            continue
        out.append({
            "leg": r.get("leg", "-"), "objective": round(r.get("objective", 0), 3),
            "converged": bool(r.get("success")),
            "cot": r.get("cost_of_transport"),
            "peak_bw": round(r.get("peak_force_bw", 0), 2),
            "min": r.get("solve_min"), "verdict": r.get("verdict", "banked"
                                                          if r.get("banked") else "-"),
        })
    return out[-8:]


def agent_entries(n: int = 6) -> list[dict]:
    path = ROOT / "AGENTS_LOG.md"
    if not path.exists():
        return []
    heads = re.findall(r"^## (\S+) — (.+?) — ", path.read_text(encoding="utf-8"), re.M)
    return [{"ts": ts, "who": who} for ts, who in heads[-n:]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solver-log", default=str(D3 / "met_leg0.log"))
    ap.add_argument("--budget", type=int, default=1100)
    ap.add_argument("--headline", default="")
    args = ap.parse_args()

    doc = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "headline": args.headline,
        "solve": solver_progress(Path(args.solver_log), args.budget),
        "legs": legs(),
        "commits": git_log(),
        "agents": agent_entries(),
    }
    OUT.write_text(json.dumps(doc, indent=1))
    print(json.dumps(doc["solve"]))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
