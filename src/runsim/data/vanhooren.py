"""Loader for the Van Hooren et al. 2024 treadmill running dataset (osf.io/7qbxc).

19 runners, 13 conditions: speeds 2.78/3/3.33/4/5 m/s, gradients +-3/6 deg,
low/high step frequency, forward trunk lean. Downloaded subsets:

  09_time_normalized/Sub_XX_<cond>_TimeNorm.xlsx
      One sheet pair (<Var>Mean, <Var>Std) per variable, each 100 rows
      (0-99 % gait cycle). Variables include GRF, IK, ID, DOact/DOfor
      (static-optimization muscle activations/forces), NorTendonForce,
      FiberLength, JRA (joint reaction analysis), FS (foot strike).
  08_tissue_loading/Sub_XX_<cond>_FS.xlsx
      Continuous per-sample tissue loads (patellofemoral compressive
      force/stress, tibial axial force/stress, Achilles load, ...) in the
      sheet named after the file.
  02_scaled_models/Sub_XX_scaled.osim
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "raw" / "vanhooren2024"


@dataclass(frozen=True)
class Condition:
    key: str
    speed_ms: float  # treadmill belt speed
    grade_deg: float  # + uphill, - downhill
    note: str = ""


CONDITIONS = {
    c.key: c
    for c in [
        Condition("278ms", 2.78, 0),
        Condition("3ms", 3.0, 0),
        Condition("333ms", 3.33, 0),
        Condition("4ms", 4.0, 0),
        Condition("5ms", 5.0, 0),
        Condition("3deg_up", 3.0, 3),
        Condition("3deg_down", 3.0, -3),
        Condition("6deg_up", 3.0, 6),
        Condition("6deg_down", 3.0, -6),
        Condition("lowfreq", 3.0, 0, "reduced step frequency"),
        Condition("highfreq", 3.0, 0, "increased step frequency"),
        Condition("trunklean", 3.0, 0, "forward trunk lean"),
    ]
}


def available(root: Path = DEFAULT_ROOT) -> pd.DataFrame:
    """DataFrame of (subject, condition) pairs present on disk, per product."""
    rows = []
    for f in (root / "09_time_normalized").glob("Sub_*_TimeNorm.xlsx"):
        m = re.match(r"Sub_(\d+)_(.+)_TimeNorm", f.stem)
        if m:
            rows.append({"subject": int(m.group(1)), "condition": m.group(2), "product": "time_normalized"})
    for f in (root / "08_tissue_loading").glob("Sub_*_FS.xlsx"):
        m = re.match(r"Sub_(\d+)_(.+)_FS", f.stem)
        if m:
            rows.append({"subject": int(m.group(1)), "condition": m.group(2), "product": "tissue_loading"})
    return pd.DataFrame(rows).sort_values(["subject", "condition"]).reset_index(drop=True)


def variables(subject: int, condition: str, root: Path = DEFAULT_ROOT) -> list[str]:
    """Variable groups available in a time-normalized workbook (e.g. GRF, IK, JRA)."""
    xl = pd.ExcelFile(_timenorm_path(subject, condition, root))
    return sorted({s[:-4] for s in xl.sheet_names if s.endswith("Mean")})


def time_normalized(
    subject: int, condition: str, variable: str, root: Path = DEFAULT_ROOT, std: bool = False
) -> pd.DataFrame:
    """One variable group, gait-cycle-normalized (100 rows), indexed by % cycle."""
    sheet = f"{variable}{'Std' if std else 'Mean'}"
    df = pd.read_excel(_timenorm_path(subject, condition, root), sheet_name=sheet)
    return df.rename(columns={"Time (%)": "perc_cycle"}).set_index("perc_cycle")


def tissue_loading(subject: int, condition: str, root: Path = DEFAULT_ROOT) -> pd.DataFrame:
    """Continuous per-sample tissue loads for one subject/condition."""
    name = f"Sub_{subject:02d}_{condition}_FS"
    return pd.read_excel(root / "08_tissue_loading" / f"{name}.xlsx", sheet_name=name)


def scaled_model_path(subject: int, root: Path = DEFAULT_ROOT, doubled_strength: bool = False) -> Path:
    suffix = "_2xmaxforce" if doubled_strength else ""
    return root / "02_scaled_models" / f"Sub_{subject:02d}_scaled{suffix}.osim"


def _timenorm_path(subject: int, condition: str, root: Path) -> Path:
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}; one of {sorted(CONDITIONS)}")
    return root / "09_time_normalized" / f"Sub_{subject:02d}_{condition}_TimeNorm.xlsx"
