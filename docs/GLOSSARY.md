# Glossary

Project and domain terms used across the runsim codebase, README, and
experiment logs. Organized by the layer of the project they belong to.

## Architecture

- **Tier 0** — closed-form energetics engine (`runsim.tier0`): algebraic
  models mapping athlete/environment/gait to speed and energy cost. ~µs.
- **Tier 1** — stride-mechanics surrogate (`runsim.tier1`): regressions +
  spring-mass theory producing stride timing and GRF waveforms. ~ms.
- **Tier 2** — planned tissue-load surrogates fitted to Tier-3 output
  (never to GRF features; see Matijevich caution), then fatigue-damage
  models.
- **Tier 3** — OpenSim Moco musculoskeletal simulation (`runsim.tier3`):
  predictive optimal-control gait. Minutes to hours per solve.

## Energetics (Tier 0)

- **COT (cost of transport)** — metabolic energy per kilogram per metre
  travelled (J/kg/m). The central currency of Tier 0 and the metabolic
  objective in Tier 3.
- **Minetti curve** — polynomial for COT as a function of grade
  (Minetti 2002); anchors the slope cost model and validates Tier-3
  slope predictions.
- **Pugh/Davies drag** — aerodynamic cost model for wind/speed, with ISA
  air density and drafting reduction.
- **Kerdok surface model** — energy cost adjustment for elastic and
  dissipative running surfaces.
- **Critical speed** — hyperbolic speed-duration model separating
  sustainable from unsustainable intensities.
- **VO2max** — maximal oxygen uptake (ml/kg/min); with the endurance
  curve and hypoxic derating it caps sustainable metabolic power.
- **Running economy** — baseline COT on flat ground at moderate speed
  (athlete parameter, ~3.8 J/kg/m default).

## Stride mechanics (Tier 1)

- **GRF (ground reaction force)** — force from ground on foot; vertical
  component's shape/peak is the main Tier-1 output. Often expressed in
  **BW** (multiples of body weight).
- **Contact time (t_c)** — foot-on-ground duration per step (~244 ms at
  3 m/s from the Fukuchi fit). Kram–Taylor: metabolic power tracks 1/t_c.
- **Step frequency / cadence** — steps per second (Hz). Human preferred
  ~2.8–2.9 Hz at 3 m/s; note stride frequency = half step frequency.
- **Duty factor** — contact time / stride time.
- **Spring-mass model** — runner as point mass on a linear leg spring;
  Morin regressions give vertical/leg stiffness; Ferris series-spring
  adds surface compliance.
- **Clark–Weyand two-mass model** — GRF waveform as the sum of a sharp
  impact transient (lower limb) and a broad component (rest of body);
  foot-strike dependent.
- **Foot strike** — rearfoot/midfoot/forefoot landing style; controls
  the impact transient's size.

## Optimal control / Moco (Tier 3)

- **OpenSim / Moco** — musculoskeletal modeling toolkit and its
  optimal-control layer; we drive both from Python.
- **Direct collocation** — transcription of the gait trajectory into a
  large sparse NLP over mesh points, solved by **IPOPT** via **CasADi**
  (with the MUMPS linear solver).
- **Mesh intervals** — number of collocation segments (50 for
  production solves).
- **Tracking vs predictive** — tracking reproduces measured data
  (fast, well-conditioned); predictive generates motion from first
  principles (objective + constraints only).
- **Seeding / homotopy** — never cold-start a predictive solve: seed
  from a tracking solution and chain solutions across nearby
  speeds/grades/cadences. A near-converged solution is a usable seed
  when its objective is sane (< 50).
- **Periodicity (symmetry) goal** — constrains end state = start state
  with left/right swap, so one step represents the full gait.
- **Effort objective** — cubed muscle controls divided by displacement
  (Falisse 2019 default).
- **Metabolic objective** — smoothed Bhargava (2004) whole-body
  metabolic rate divided by displacement and mass ≈ COT; gives more
  realistic cadence and peak forces.
- **Rotated-gravity slope trick** — slope imposed by tilting the gravity
  vector so the ground plane stays at y=0 (predict2d.py); animations
  show a flat floor and a leaning runner.
- **Walk→run transition** — emergent gait change at 2.0–2.5 m/s in the
  2D speed chain; a key face-validity result.
- **Solution labels** — `v{speed}_g{grade}` with `.`→`_`, `+`→`p`,
  `-`→`m`; `_c{hz}` for imposed cadence; `_met` for the metabolic
  objective.

## Musculoskeletal models

- **2D_gait model** — 10-DOF, 18-muscle planar model (gait10dof18musc
  variant) used for all Phase-0–3 2D work.
- **LaiUhlrich2022** — 35-coordinate, 80-muscle full-body 3D model
  (Rajagopal→Lai→Uhlrich lineage; OpenCap default). Phase-3 finale
  target.
- **LaiArnold2017** — high-knee-flexion variant validated to sprinting
  speeds; for >7 m/s work.
- **gait2392 / Rajagopal lineage** — the two big OpenSim model families.
  Hamner's model is gait2392-lineage: its knee angle is negative in
  flexion, while Rajagopal-lineage knees are positive in flexion —
  hence the sign flip in `runsim.tier3.retarget`.
- **DeGrooteFregly2016 muscle** — smooth muscle model required for
  gradient-based optimal control; stock Millard/Thelen muscles are
  converted via ModelProcessor.
- **Contact spheres / SmoothSphereHalfSpaceForce** — smooth foot-ground
  contact (stiffness 3.07 MPa, dissipation 2 s/m, friction 0.8) between
  foot-mounted spheres and the floor half-space; 2 spheres/foot in 2D,
  4/foot in 3D (`runsim.tier3.model3d`).
- **CoordinateActuator / reserves** — ideal torque actuators (lumbar,
  arms) and low-strength helpers that guarantee feasibility.

## Experimental pipeline

- **IK (inverse kinematics)** — fit model joint angles to measured
  marker trajectories (`.trc`).
- **RRA (residual reduction algorithm)** — adjusts kinematics/torso mass
  so dynamics are consistent with measured GRFs; its per-cycle
  `states.sto` (radians + speeds) is our 3D tracking reference.
- **CMC (computed muscle control)** — OpenSim's classic muscle-force
  solver; Hamner's published results use it.
- **IAA (induced acceleration analysis)** — per-muscle contribution to
  mass-center acceleration.
- **EMG** — electromyography; raw recordings staged under
  `data/raw/hamner2013/RAW_EMG_DATA/`.
- **External loads file** — XML mapping GRF data columns
  (`R_ground_force_v/p`) to the body they act on.
- **Retargeting** — mapping one model lineage's kinematics onto
  another's coordinate set (`runsim.tier3.retarget`).
- **File formats** — `.osim` model XML; `.trc` markers; `.mot`/`.sto`
  time-series tables (headers declare rows/columns/degrees).

## Datasets

- **Fukuchi 2017** — 28 treadmill runners at 2.5/3.5/4.5 m/s; fitted
  Tier-1 regressions and stance ensembles (`runsim.data.fukuchi`).
- **Van Hooren 2024** — 19 runners × 13 conditions (speeds, gradients,
  cadences, trunk lean); gradient/cadence validation
  (`runsim.data.vanhooren`).
- **Hamner 2013** — 10 runners at 2–5 m/s with full simulation workflow
  (SimTK nmbl_running); subject01/02 staged; source of the 3D tracking
  seed and arm-swing angular-momentum validation.
- **OpenCap** — Stanford markerless motion-capture project; origin of
  the LaiUhlrich2022 model (and a potential personalization route).

## Fatigue & tissue (planned)

- **Matijevich caution** — tissue loads must be fitted to simulation
  outputs, not GRF features (GRF is a poor proxy for e.g. tibial load).
- **Miner's rule / Weibull** — cumulative fatigue-damage bookkeeping and
  the statistical failure model for repetitive tissue loading; tendon
  damage scales roughly with strain^9.
- **MyoSuite / MJX** — GPU-parallel musculoskeletal RL stack; optional
  future tier, cross-checked against Moco.
