"""Loader for the Fukuchi et al. 2017 running biomechanics dataset (PeerJ 3298).

28 runners on an instrumented treadmill at 2.5, 3.5, and 4.5 m/s.
Files (tab-separated text, one directory):
  RBDS<sub>runT<speed>markers.txt  - marker trajectories, 150 Hz
  RBDS<sub>runT<speed>forces.txt   - GRF/COP/torque, 300 Hz (Time column = sample index)
  RBDS<sub>processed.txt           - gait-cycle-normalized (0-100%) joint angles,
                                     moments, GRF (N/kg; divide by 9.81 for BW),
                                     powers; columns suffixed by speed code (25/35/45)
  RBDSinfo.txt                     - per-file subject metadata
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

SPEEDS = {"25": 2.5, "35": 3.5, "45": 4.5}
FORCES_HZ = 300.0
MARKERS_HZ = 150.0

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "raw" / "fukuchi2017"


def subjects(root: Path = DEFAULT_ROOT) -> pd.DataFrame:
    """One row per subject with demographics (deduplicated from RBDSinfo)."""
    info = pd.read_csv(root / "RBDSinfo.txt", sep="\t")
    return (
        info.drop(columns=["FileName"])
        .drop_duplicates(subset="Subject")
        .set_index("Subject")
    )


def forces(subject: int, speed: float, root: Path = DEFAULT_ROOT) -> pd.DataFrame:
    """Raw GRF for one subject/speed with a real time column in seconds."""
    code = _speed_code(speed)
    df = pd.read_csv(root / f"RBDS{subject:03d}runT{code}forces.txt", sep="\t")
    df["Time"] = (df["Time"] - df["Time"].iloc[0]) / FORCES_HZ
    return df


def markers(subject: int, speed: float, root: Path = DEFAULT_ROOT) -> pd.DataFrame:
    code = _speed_code(speed)
    df = pd.read_csv(root / f"RBDS{subject:03d}runT{code}markers.txt", sep="\t")
    df["Time"] = (df["Time"] - df["Time"].iloc[0]) / MARKERS_HZ
    return df


def processed(subject: int, root: Path = DEFAULT_ROOT) -> pd.DataFrame:
    """Gait-cycle-normalized variables in tidy long form.

    Columns: perc_cycle, variable (e.g. RkneeAngX), speed (m/s), value.
    """
    wide = pd.read_csv(root / f"RBDS{subject:03d}processed.txt", sep="\t")
    long = wide.melt(id_vars="PercGcycle", var_name="raw", value_name="value")
    parsed = long["raw"].str.extract(r"^(?P<variable>.*?)(?P<code>25|35|45)$")
    long = pd.concat([long, parsed], axis=1).dropna(subset=["code"])
    long["speed"] = long["code"].map(SPEEDS)
    return long.rename(columns={"PercGcycle": "perc_cycle"})[
        ["perc_cycle", "variable", "speed", "value"]
    ]


def available_subjects(root: Path = DEFAULT_ROOT) -> list[int]:
    return sorted(
        int(m.group(1))
        for f in root.glob("RBDS*processed.txt")
        if (m := re.match(r"RBDS(\d+)processed", f.name))
    )


def stance_ensemble(
    speed: float, root: Path = DEFAULT_ROOT, n_pts: int = 101, thresh_n: float = 40.0
):
    """Mean and SD of the BW-normalized vertical-GRF stance waveform across
    all subjects at one speed. Returns (mean, sd, n_subjects), each curve
    time-normalized to 0-100% stance."""
    import numpy as np

    curves = []
    subs = subjects(root)
    for sub in available_subjects(root):
        if sub not in subs.index:
            continue
        try:
            f = forces(sub, speed, root)
        except FileNotFoundError:
            continue
        fy = f["Fy"].to_numpy()
        bw = subs.loc[sub, "Mass"] * 9.81
        on = fy > thresh_n
        edges = np.flatnonzero(np.diff(on.astype(int)))
        per_sub = []
        for a, b in zip(edges[:-1], edges[1:]):
            if not on[a + 1]:
                continue
            if not 0.15 < (b - a) / FORCES_HZ < 0.4:
                continue
            phase = fy[a + 1 : b + 1] / bw
            per_sub.append(
                np.interp(np.linspace(0, 1, n_pts), np.linspace(0, 1, len(phase)), phase)
            )
        if per_sub:
            curves.append(np.mean(per_sub, axis=0))
    return np.mean(curves, axis=0), np.std(curves, axis=0), len(curves)


def _speed_code(speed: float) -> str:
    for code, v in SPEEDS.items():
        if abs(v - speed) < 1e-9:
            return code
    raise ValueError(f"speed must be one of {sorted(SPEEDS.values())}, got {speed}")
