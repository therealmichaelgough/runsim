# CLAUDE.md — resuming this project

**FIRST: read `AGENTS_LOG.md` (repo root) — the shared coordination log
for AI agents. It records what is currently running (long solves, PIDs,
chained jobs), what is claimed, and recent findings. Append your own
entries there when you start/finish long work.**

Human running simulator: predicts how environment (slope, wind, altitude,
surface) and gait (cadence, foot strike) affect speed, tissue loads, and
energy cost. Four tiers: closed-form energetics (tier0) → spring-mass GRF
surrogate (tier1) → tissue-load surrogates (tier2, not built yet) →
OpenSim Moco musculoskeletal simulation (tier3). See README.md for the
status ledger and the "Running Simulator Blueprint" artifact for the full
survey/plan.

## Setup on a new machine

1. Python 3.12 or 3.13 required (opensim 4.6 wheels are cp311–cp313).
   On macOS use the python.org installer (Homebrew arm64 may be absent or
   x86_64); on Linux any 3.12 works (manylinux wheels exist).
2. ```
   python3.12 -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```
3. **macOS only:** run `./scripts/fix_opensim_wheel_macos.sh` — the wheel
   references its bundled gfortran via absolute /opt/homebrew paths and
   Moco's IPOPT solver won't load without the patch. Re-run after every
   pip install/upgrade of opensim. Linux wheels don't need this.
   **Windows only:** run `.venv\Scripts\python.exe scripts\fix_opensim_dlls_windows.py`
   — CasADi loads its IPOPT plugin via PATH, not Python's DLL dirs, so Moco
   fails with "Plugin 'ipopt' is not found" without it. It installs a
   sitecustomize.py in the venv; re-run after every pip install/upgrade of
   opensim. Also: git checks out the LaiArnold2017 geometry symlinks as text
   stubs on Windows — replace each stub with a copy of the file it names
   (targets are in models/LaiUhlrich2022/Geometry).
4. Verify: `.venv/bin/python scripts/smoke_test_moco.py` (must print
   "Moco toolchain OK") and `.venv/bin/python -m pytest tests/ -q`
   (dataset tests auto-skip until data is downloaded).
5. macOS + python.org quirk: no CA bundle for stdlib SSL. Use
   `SSL_CERT_FILE=$(.venv/bin/python -m certifi)` or `requests`.

## Datasets (git-ignored; re-download into data/raw/)

- `data/raw/fukuchi2017/` — figshare article 4543435; download the .txt +
  .xlsx files (see scripts/fit_tier1_params.py's loader expectations,
  ~430 MB). Tier-1 params.json is already fitted and committed, so this
  is only needed for validation reruns.
- `data/raw/vanhooren2024/` — OSF osf.io/7qbxc; folders "09. Time-normalized
  data" → `09_time_normalized/`, "08. Tissue loading" → `08_tissue_loading/`,
  "02. Scaled models" → `02_scaled_models/` (~1.3 GB). Loader:
  `runsim.data.vanhooren`.
- `data/raw/hamner2013/` — SimTK project nmbl_running (needs a free SimTK
  login; each download has a license form that requires a filled
  description). subject01/subject02 + RAW_EMG_DATA were used so far.
- Layout details and unit conventions: README.md "Datasets" section.

## Hard-won gotchas (do not rediscover these)

- **Never cold-start a Moco gait prediction.** Cold starts burn 40 min and
  land in hopping/flying local optima. Seed from the fast tracking solve
  (`experiments/phase3_2drunning/make_seed.py`, ~20 s) and chain solutions
  across speeds/grades (homotopy). Pass a near-converged (iteration-capped)
  solution forward as a guess whenever its objective is sane (< 50).
- **Tracking with sphere contact: ground the reference INTO the floor.**
  A grazing reference (spheres just touching) is force-free at the guess
  while measured GRFs demand ~2.4 BW, and the dynamically-feasible
  manifold near a force-free guess is ballistic — three 6-7 h solves flew
  or collapsed before this was understood. `retarget.ground_reference`
  (clearance 0.013 m → heel sphere ~1.2 cm deep → ~2.6 BW at deepest
  stance, pre-flight-verify with a static realizeDynamics check) plus a
  warm-start continuation produced the validated 3D seed (obj 5.78,
  joints 3-10 deg RMS, GRFs at measured values). Scale the model to the
  subject first (`scripts/scale_lai_to_subject.py`).
- **Sweeps run parallel by default** (`runsim.tier3.parallel`): one
  process per point, each seeded from the nearest *completed* solution,
  threads split fairly via OPENSIM_MOCO_PARALLEL, per-point fragment
  JSONs merged into the sweep log afterwards. Wall-clock ≈ slowest single
  solve instead of the sum. Reserve sequential homotopy chains for the
  first traversal into a new regime (nothing close enough to seed from).
  Log launched PIDs and chained finishers in AGENTS_LOG.md.
- **Watch solver HEALTH, not just completion.** IPOPT iteration lines
  with an `r` suffix are restoration phase; a solve showing sustained
  restoration with large/growing inf_pr will not recover — kill it
  (7 h were lost learning this). Long-solve watchers must parse the
  iteration tail and auto-kill unambiguous divergence. Related:
  MocoAverageSpeedGoal is an endpoint CONSTRAINT — never ask for a
  speed far from what the guess actually achieves (the tracking seed
  advances ~1.7 m/s due to treadmill-frame slip); homotope speed from
  the guess's effective value.
- `analyzeMocoTrajectory` output paths are **regex patterns**
  (`.*total_metabolic_rate`), not literal `/component|output` paths — a
  literal `|` path returns an empty table.
- Slope is imposed by **rotating gravity** (predict2d.py), so the ground
  stays at y=0 and animations show a flat floor with a leaning runner.
- Solution labels: `v{speed}_g{grade}` with `.`→`_`, `+`→`p`, `-`→`m`,
  plus `_met` for the metabolic objective (e.g. `fullstride_v3_gm0_0524078_met.sto`).
- Long solves run in background with JSON-per-line logs
  (`chain_log.json`, `metabolic_chain_log.json`, `slope_grid_log.json`);
  chain scripts skip already-completed entries, so rerunning is safe.
- View any solution: `scripts/watch_gait.py --motion <fullstride .sto>`
  (camera follows; `--no-follow` for the classic window).

## Where the project stands / what's next

Phases 0–2 complete; Phase 3 has three milestones done on the 2D model
(emergent walk→run transition; metabolic-objective speed sweep matching
Minetti at 2.5–3.5 m/s; slope grid matching Minetti within 2–8% over
±16% grade). Documented model limits: cadence high, COT rises steeply
above 4 m/s, downhill impact peaks unphysiological.

Next steps, in order:
1. Phase 3 finale: 3D predictive running on models/LaiUhlrich2022 (or
   Lai-Arnold for >7 m/s). Expect hours per solve; build a tracking seed
   from Hamner data first; validate against Hamner (2–5 m/s) and
   Van Hooren (gradients/cadences). Validate transverse angular momentum
   (arm swing) against Hamner & Delp 2013.
2. Phase 4: fit tier-2 tissue-load surrogates on tier-3 output (never on
   GRF features — Matijevich 2019), then Miner/Weibull fatigue-damage
   models (tendon damage ~ strain^9).
3. Optional: MyoSuite RL tier, FEBio/OpenSim JAM for ligament/bone stress,
   OpenCap personalization.
4. Experiment backlog (docs/future_experiments.md): altered gravity,
   superhuman-muscle speed limits, technical-terrain optimal running,
   simulated-vs-literature physiological limiting factors.

## Conventions

- Every quantitative model component carries a literature citation in its
  docstring and at least one test pinning it to a published value.
- Validation figures land in `experiments/*.png` via `scripts/analyze_*.py`
  / `scripts/validate_*.py`; regenerate rather than hand-edit.
- Cross-tier consistency checks are part of validation (tier-0 power vs
  tier-1 1/t_c; tier-3 COT vs tier-0 Minetti).
