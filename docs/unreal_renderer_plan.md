# Minimal Unreal Engine renderer — plan

Goal: an Unreal Engine (5.4+) equivalent of `docs/run_viewer.html` — animate
baked Moco solutions on variable-slope terrain with a chase camera and
user-controlled speed — but genuinely 3D, so pelvis list, mediolateral foot
placement, and arm–leg transverse counter-rotation are visible. Minimal
means: no skeletal mesh, no retargeting, no animation assets — segment
primitives driven directly by baked simulation transforms.

## Non-goals (v1)

- No MetaHuman/mannequin retargeting, no Control Rig, no Live Link.
- No physics in-engine — Unreal renders; all motion comes from the solver.
- No muscle/force visualization (v2 candidate: GRF arrows, muscle lines).

## 1. Data pipeline (Python side)

Extend `scripts/export_seed3d_stations.py` into `export_ue_gaits.py`:

- For each gait (2D chain, slope grid, 3D seed), sample N=48 phases and
  record **per-body world transforms** — position + quaternion in ground
  frame — for the ~12 render segments (pelvis, torso, head, thigh/shank/
  foot ×2, upper arm/forearm ×2), via `body.getTransformInGround(state)`.
  Positions stored relative to the frame's `pelvis_tx` (same looping
  convention as the web viewer).
- Also per gait: `strideTime`, `strideLen`, `speed`, `grade`, `cot`, plus
  per-segment capsule dimensions (length from parent–child joint distance,
  radius fixed per segment class).
- **Coordinate conversion** (do it in the exporter so UE code stays dumb):
  OpenSim is right-handed y-up meters; Unreal is left-handed z-up
  centimeters. Map position `(x, y, z)_osim → (x·100, z·100, y·100)_ue`
  and convert quaternions with the same axis swap + handedness flip
  (negate the appropriate component; verify with a T-pose frame in M1).
- Output: one `gaits_ue.json` (~1–2 MB) checked into the UE project's
  `Content/Data/`.

## 2. UE project skeleton

- Blank **C++** project (one module), engine basic shapes only — no
  content packs. C++ because JSON parsing and per-tick transform setting
  are cleaner than Blueprint for this; Blueprints only for input bindings
  and the HUD widget.
- Classes:
  - `URunsimGaitData` (UObject): loads/parses `gaits_ue.json` via
    `FJsonSerializer` at startup; owns the blend logic.
  - `ARunsimRunner` (Actor): one `UStaticMeshComponent` capsule per
    segment; per tick asks GaitData for the blended pose and sets world
    transforms.
  - `ARunsimTerrain` (Actor): procedural spline/heightfield (below).
  - `ARunsimPawn`: SpringArm + Camera + Enhanced Input; owns speed state.

## 3. Runner animation (port of the web viewer's blend)

- Phase advance: `phase += dt / strideTime(blend)`; world advance
  `x += strideLen/strideTime · cos(atan(grade)) · dt`.
- Speed blending: bracket the two nearest flat gaits, slerp rotations /
  lerp positions per segment. Grade blending: additive delta of the
  bracketed slope gaits vs flat-3.0, applied before slope rotation
  (identical math to the web viewer — port, don't redesign).
- Whole-runner rotation by local terrain pitch, then translate so the
  simulation ground plane is tangent to the terrain at the runner.
- Arm segments exist only in 3D-sourced gaits; when the active blend is
  2D-sourced, arms use the 3D seed's arm cycle phase-locked to the legs
  (flagged in the HUD as sourced from 3.0 m/s).

## 4. Terrain

- v1: `USplineMeshComponent` ribbon generated from the same
  sum-of-sines height function as the web viewer (port constants
  verbatim), 200 m loop, regenerated when hilliness changes. Grade =
  analytic derivative — no line traces needed.
- Keep the function in one C++ file shared by terrain and runner so
  ground and gait can never disagree.

## 5. Camera & input

- SpringArm on the pawn, target = runner, with `CameraLagSpeed` ~3 and a
  velocity-scaled look-ahead offset; default 3/4 view (yaw ~35°), mouse
  orbit enabled — this is the payoff over the web viewer.
- Enhanced Input: axis for speed (W/S, gamepad trigger), axis for
  hilliness, toggle pause, camera orbit on right-mouse drag.

## 6. HUD

- One UMG widget: speed, pace, grade, cadence, COT (same interpolation
  rules as the web viewer; COT hidden for effort-objective walk gaits).

## 7. Milestones

| # | Deliverable | Check | Est. |
|---|---|---|---|
| M1 | Exporter + static T-pose/first-frame render | limb lengths & axes correct vs OpenSim screenshot | 0.5 d |
| M2 | Single gait looping (3.0 m/s flat) | cadence on screen = 2.8 Hz (3D seed) / 3.8 Hz (2D) | 0.5 d |
| M3 | Speed blending + input | walk↔run transition below ~2.4 m/s | 0.5 d |
| M4 | Terrain + slope blending + chase camera | uphill lean & downhill mechanics visible; no foot-skate on flat | 1 d |
| M5 | HUD + orbit camera + polish | parity with web viewer metrics | 0.5 d |

Total ≈ 3 days of focused work. Every milestone renders something — no
big-bang integration.

## 8. Risks & later

- **Risk: quaternion axis conversion.** Contained by M1's explicit
  verification frame; get it right once in the exporter.
- **Risk: data staleness.** The exporter runs from committed .sto files;
  regenerate `gaits_ue.json` in CI or by convention when solutions change.
- Later: mannequin retarget via IK Rig (visual upgrade), Live Link UDP
  streaming for watching solves converge in real time, GRF arrows and
  muscle-activation coloring from the solution's control trajectories,
  VR pace-runner mode.
