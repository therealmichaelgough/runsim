# running_sim

Simulator for anatomically-accurate human bipedal running: experiments on how
environmental parameters (slope, wind, altitude, surface stiffness) and gait
parameters (cadence, stride length, foot strike) affect running speed, tissue
stress (muscle, bone, ligament, tendon), and energy expenditure.

Design survey and phased plan: see the "Running Simulator Blueprint" artifact.

## Status

- **Phase 0 (foundation) — done.** OpenSim 4.6 + Moco verified end-to-end on
  macOS arm64: the stock 2D walking example solves a tracking problem (~17 s)
  and a fully predictive gait (~4.5 min) on this machine. Models and
  validation datasets are staged (below) with tested loaders.
- **Phase 1 (Tier-0 energetics engine) — done.** `runsim.tier0`: Minetti
  slope cost, Pugh/Davies drag with ISA air density and drafting, Kerdok
  elastic-surface + dissipative-surface model, cadence penalty, VO2max
  endurance curve with hypoxic derating, critical-speed model, and a speed
  solver. 24 tests anchor each component to literature values. Try it:
  `.venv/bin/python scripts/whatif.py --distance 42.195 --vo2max 60 --grade 0.02 --wind 3`
- **Phase 2 (Tier-1 mechanics surrogate) — done.** `runsim.tier1`: stride
  timing from regressions fitted to the Fukuchi force data
  (`scripts/fit_tier1_params.py` → `params.json`), Morin spring-mass
  stiffness with the Ferris series-spring surface adjustment, and
  Clark–Weyand two-mass GRF waveforms with foot-strike-dependent impact
  transients. Validated against 28-subject measured stance ensembles
  (R² 0.86–0.91 at 2.5/3.5/4.5 m/s, `scripts/validate_tier1.py`); Tier-0
  power tracks 1/t_c (Kram–Taylor, r=0.99). Known bias: model peak ~8% low,
  symmetric shape vs slightly early-skewed measured curves.
- **Phase 3 (Moco predictive running, Tier-3) — first milestone done.**
  `runsim.tier3`: predictive one-step gait formulation (periodicity +
  average speed + cubed effort, slope via rotated gravity) on the 2D
  18-muscle model. A speed-homotopy chain (1.2→5.0 m/s, seeded from a fast
  tracking solve — `experiments/phase3_2drunning/`) reproduces the
  **emergent walk→run transition at 2.0–2.5 m/s** with 2.5–25 min solves.
  Known deviations vs data: cadence high (~4 vs ~2.9 Hz), contact times
  ~20% short at speed, GRF waveforms impact-dominated (contact-sphere
  artifact). **Metabolic objective added** (smoothed Bhargava cost of
  transport, `objective="metabolic"`; `run_metabolic_chain.py`): improves
  cadence and peak-force realism, and predicted cost of transport matches
  the Tier-0/Minetti curve within ~5% at 2.5–3.5 m/s, then rises steeply
  above 4 m/s where humans stay flat — the 2D model loses economy at speed
  (documented benchmark caveat). **Slope grid done** (`run_slope_grid.py`,
  ±3/6/9° at 3.0 m/s): predicted cost of transport tracks the Minetti
  polynomial across the whole ±16% range, mostly within 2–8% (slight
  systematic undershoot; −9° short by ~17% — eccentric cost under-priced),
  with physiological uphill mechanics (lower peaks, quicker steps) and an
  exaggerated downhill impact artifact (up to 6.5 BW). Next:
  cadence-constraint experiments and the 3D LaiUhlrich model.

## Architecture (planned)

| Tier | What | Speed |
|------|------|-------|
| 0 | Closed-form energetics (Minetti slope, Pugh drag, surface, critical speed) | ~µs |
| 1 | Spring-mass / two-mass GRF mechanics surrogate | ~ms |
| 2 | Tissue-load surrogates + fatigue damage (fit to Tier-3 output) | ~ms |
| 3 | OpenSim Moco musculoskeletal inner loop | min–h |

## Setup (macOS, Apple Silicon)

Requires python.org Python 3.12 (OpenSim 4.6 ships cp311–cp313 universal2 wheels).

```bash
/usr/local/bin/python3.12 -m venv .venv
.venv/bin/pip install -e .
./scripts/fix_opensim_wheel_macos.sh   # fixes gfortran paths in the opensim wheel
.venv/bin/python scripts/smoke_test_moco.py
```

Notes:
- `fix_opensim_wheel_macos.sh` is needed after every `pip install/upgrade` of
  `opensim`: the wheel bundles the gfortran runtime but references it via
  absolute `/opt/homebrew` paths, so Moco's IPOPT solver fails to load without
  the patch.
- python.org Python has no default CA bundle; for scripts that hit HTTPS APIs
  use `SSL_CERT_FILE=$(.venv/bin/python -m certifi)` or the `requests` library.

## Layout

- `src/runsim/` — the package: `runsim.tier0` (energetics engine: athlete,
  environment, gait, cost model, speed solver), `runsim.tier1` (stride
  mechanics + GRF waveforms: `predict_stride`, `grf_waveform`), and the
  dataset loaders (`runsim.data.fukuchi`, `runsim.data.vanhooren`).
- `tests/` — pytest suite (`.venv/bin/python -m pytest tests/ -q`); dataset
  tests auto-skip when the data is not downloaded.
- `scripts/` — setup, verification, and viewing:
  - `fix_opensim_wheel_macos.sh` — patches the opensim wheel (see Notes)
  - `smoke_test_moco.py` — verifies the Moco/IPOPT toolchain (~5 s)
  - `plot_phase0_walking.py` — regenerates the Phase-0 summary figure
  - `watch_gait.py` — plays a simulated gait in the OpenSim 3D visualizer
    (defaults to the Phase-0 predictive solution; `--model`/`--motion`/`--loops`)
  - `whatif.py` — CLI over the Tier-0 engine: fixed speed, fixed duration, or
    race-a-distance mode; all environment/gait/athlete knobs as flags
  - `plot_tier0_demo.py` — regenerates the Tier-0 demo figure
    (`experiments/tier0_demo.png`)
- `experiments/phase0_2dwalking/` — stock Moco 2D walking example (tracking +
  fully predictive) with its solutions and summary figure, our end-to-end
  toolchain check
- `models/` — musculoskeletal models (downloaded, with geometry)
- `data/raw/` — datasets (git-ignored)

## Models

- `models/LaiUhlrich2022/` — 35-coordinate, 80-muscle full-body model
  (Rajagopal→Lai→Uhlrich lineage), the OpenCap default; validated for running.
  Source: opencap-org/opencap-core.
- `models/LaiArnold2017/` — Lai-Arnold high-flexion model (refined + arms +
  torso variants), EMG-validated up to sprinting speeds. Geometry dir is
  symlinks into the LaiUhlrich2022 geometry (+2 extra meshes). Source:
  simtk.org/projects/model-high-flex (OpenSim 3.x format; 4.6 auto-updates).

## Datasets

- `data/raw/fukuchi2017/` — Fukuchi et al. 2017 (PeerJ): 28 runners,
  treadmill 2.5/3.5/4.5 m/s, markers + GRF + processed kinematics. CC-BY.
- `data/raw/vanhooren2024/` — Van Hooren et al. 2024 (Data in Brief,
  osf.io/7qbxc): 19 runners × 13 conditions (5 speeds, ±3/6° gradients,
  3 cadences, trunk lean). Downloaded subsets: time-normalized data, tissue
  loading, scaled models, subject info. Raw C3D/GRF/EMG (~45 GB) left on OSF.
- `data/raw/hamner2013/` — Hamner & Delp 2013 (simtk.org/projects/nmbl_running):
  subject01 + subject02 (markers, GRF, EMG, scaled models, RRA/CMC results at
  2/3/4/5 m/s) plus the study-wide raw EMG zip. Subjects 03-19 remain on SimTK.
- `data/raw/hamner_runningsim/` — Hamner 2010 example running simulation
  package (simtk.org/projects/runningsim).

Loader quick check:

```bash
.venv/bin/python -c "from runsim.data import fukuchi, vanhooren; print(fukuchi.subjects().shape); print(vanhooren.available().groupby('product').size())"
```

Notes on units/conventions: Fukuchi `processed` GRFs are N/kg (divide by 9.81
for body weights); forces files sample at 300 Hz, markers at 150 Hz. Van
Hooren time-normalized sheets are 100 points per gait cycle, one
`<Variable>Mean`/`<Variable>Std` sheet pair per variable; speeds are encoded
in condition keys (`278ms` = 2.78 m/s, `333ms` = 3.33 m/s).
