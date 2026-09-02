# RunsimViewer — Unreal Engine renderer

An Unreal Engine renderer for baked OpenSim Moco running solutions: capsule
segments driven directly by solver output, running free over a procedural
1 km² heightfield with user-controlled speed **and direction**, a chase
camera, and a HUD surfacing the simulation's interesting numbers. It is the
3D counterpart of `docs/run_viewer.html`, grown well past
`docs/unreal_renderer_plan.md` v1.

**Status: built and running** on the Windows workstation: **Unreal Engine
5.8.2** (`D:\unreal\UE_5.8`) with **MSVC 14.44** and the Windows 10.0.22621
SDK, zero warnings. The Python exporter and its tests are run and passing
(`tests/test_ue_export.py`).

## What is in the box

```
RunsimViewer.uproject             UE project, one C++ module, no plugins beyond
                                  the stock ProceduralMeshComponent
Config/DefaultEngine.ini          default map + global game mode + renderer flags
Config/DefaultGame.ini            stages Content/Data as non-asset files
Config/DefaultInput.ini           legacy axis/action bindings (no Enhanced Input assets)
Content/Data/gaits_ue.json        baked gaits (generated)
Source/RunsimViewer/
  Public/RunsimTerrainMath.h      analytic heightfield h(x,y); the single source of truth
  Public/RunsimGaitData.h         JSON load + speed/grade blend + arm graft + live channels
  Public/RunsimRunner.h           capsule-per-segment actor, heading + per-tick posing
  Public/RunsimTerrain.h          chunked procedural-mesh heightfield renderer
  Public/RunsimPawn.h             spring-arm chase camera, input, orbit
  Public/RunsimHUD.h              Canvas HUD (grouped metric panels)
  Public/RunsimGameMode.h         spawns the whole scene, so no level asset is needed
```

There are **no `.uasset` files** — the project is deliberately text-only.
Meshes are engine basic shapes plus runtime-generated procedural meshes; the
sky is a spawned `SkyAtmosphere` + real-time-capture `SkyLight` (both fully
procedural engine classes — no cubemap asset needed); depth comes from a
spawned `ExponentialHeightFog`. The level is any empty map, because
`ARunsimGameMode` spawns terrain, runner, lights, sky, fog and a player
start itself.

## Controls

| Input | Action |
|---|---|
| `W` / `S` (or `Up` / `Down`, gamepad triggers) | target speed 1.2–5.0 m/s |
| `A` / `D` (or `Left` / `Right`, gamepad left stick) | steer (rate-limited yaw, 60°/s max) |
| `H` / `F` (gamepad D-pad) | hilliness 0–100% (relief scale; 0 = flat plane) |
| `G` | gait source: blended 2D ↔ each full-3D solution wholesale |
| `Space` | pause |
| hold right mouse (gamepad right stick) | orbit camera (heading-relative) |
| mouse wheel | zoom |
| `R` | reset view |
| `Esc` | quit |

## Terrain design

`Public/RunsimTerrainMath.h` defines one analytic function `h(x, y)` —
deterministic integer-hash value noise (quintic fade) composed as:

- **rolling hills** everywhere: 4-octave FBM, ~150 m wavelength, ±9 m;
- **a ridgeline** running east–west near y = +240 m, crest wandering ±55 m
  and modulated so it reads as a chain of summits (~+24 m);
- **a valley meadow** meandering near y = −170 m: hills flatten toward a
  −7 m floor — the flat, easy running;
- **fine detail** at 23 m wavelength, suppressed on the meadow floor.

Hilliness scales the whole relief. At the default 45%, the p95 slope is
~9.5% grade (inside the solved ±16% gait range); at 100% the ridge flanks
reach ~46% and the HUD shows `[gait clamped]` while the body still tilts.
Grade queries are central differences of the same `h` the meshes sample, so
ground and gait can never disagree.

Rendering: an 11×11 ring buffer of 96 m chunks (a 1056 m window ≥ 1 km²),
each one `UProceduralMeshComponent` with 4 m flat-shaded facets. Triangles
are partitioned by relief height/slope into five palette bands (meadow,
grass, dry grass, rock, pale ridge) drawn as separate sections tinted by
shared dynamic material instances. Chunk rebuilds are budgeted at 4 per
tick, nearest first — crossing a chunk boundary or scrubbing hilliness
sweeps outward instead of hitching. Height fog + aerial perspective fold
the window edge into the horizon so draw distance and fog stay consistent.

## HUD legend

| Panel | Rows |
|---|---|
| MOTION | speed (m/s); pace (min/km and min/mi); heading (deg + cardinal) |
| GAIT | state (WALK / RUN / 3D PLAYBACK); cadence (spm + Hz); stride length (m); contact time (ms); flight fraction (%) |
| GROUND | grade (%, `[gait clamped]` marker beyond the solved ±16%); elevation (m); hilliness (%) |
| ENERGY | live vertical GRF (BW, per-frame baked channel); metabolic rate (W/kg, per-frame Bhargava where solved, else COT × v fallback); COT (J/kg/m) |

An em dash means the active blend cannot report that number honestly (e.g.
COT/metabolic rate while the effort-objective walk gaits contribute).
Contact time and flight fraction are derived from the baked per-foot GRF
channels (contact = vGRF > 0.05 BW), so they agree with the GRF meter by
construction. WALK/RUN switches at walk-weight 0.5, same as the web viewer.

## Known approximations

- **Steering re-aims straight-line gaits.** No curve-specific solutions
  exist; yaw is rate-limited (60°/s command, first-order follow) so turns
  read plausibly, but the biomechanics of curve running (lean-into-turn
  kinetics, asymmetric stride) are not simulated. Noted on the HUD.
- **Grade clamping.** The gait blend covers ±16% grade; on steeper ground
  the pose clamps while the body tilts to the true tangent plane.
- **Downhill GRF spike.** The −9° gait carries the project's documented
  impact artifact (up to ~6.4 BW total); the GRF meter shows it honestly.
- **3D playback recentring.** The tracked 3D seed advances ~1.7 m/s over
  ground with partial foot slip and a ~35 cm lateral offset; playback
  subtracts the mean pelvis XY so it stays on the path.

## Build and run

1. **Unreal Engine 5.4+** (5.8.2 is what this machine runs) and **Visual
   Studio 2022** with the C++ game-dev workload (MSVC v143, Windows SDK,
   .NET Framework SDK 4.6+ — UBT needs the *SDK*, not just the targeting
   pack).
2. Build:
   ```
   "D:\unreal\UE_5.8\Engine\Build\BatchFiles\Build.bat" ^
       RunsimViewerEditor Win64 Development ^
       -Project="D:\runsim\unreal\RunsimViewer\RunsimViewer.uproject" -WaitMutex
   ```
   (run at BelowNormal priority if solves are running; close any running
   game/editor first — Live Coding locks the DLL.)
3. Run windowed:
   ```
   "D:\unreal\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe" ^
       "D:\runsim\unreal\RunsimViewer\RunsimViewer.uproject" ^
       -game -windowed -resx=1600 -resy=900
   ```
4. Or open the project and press Play in any empty level — the game mode
   spawns everything.

## Regenerating the gait data

`Content/Data/gaits_ue.json` is generated from the committed Moco
solutions — regenerate whenever those change:

```
cd D:\runsim
.venv\Scripts\python.exe scripts\export_ue_gaits.py
.venv\Scripts\python.exe -m pytest tests\test_ue_export.py -q
```

Per gait it bakes: 48 frames × per-body transforms (positions
pelvis_tx-relative), stride time/length, speed/grade/COT, **per-foot
vertical GRF in BW** (`grfBwL`/`grfBwR`, all gaits) and **per-frame
metabolic rate in W/kg** (`metRateWkg`, the 2D metabolic-objective gaits).
3D solutions listed in `GAITS_3D` are phase-rolled onto the 2D event
convention (frames and GRF alike) and serve two roles: arm source for the
blended mode, and wholesale playback via `G`.

## The arm graft (and the bug it replaced)

2D gaits have no arm bodies; in blended mode the arm chain is grafted from
the first 3D solution at the same phase. The graft is **torso-relative**:
each arm body is expressed in the 3D gait's own torso frame and composed
onto the blended torso. Pasting the pelvis-relative transforms verbatim
(the original rule) left the arms floating 36–40 cm from the shoulders —
the 3D tracking seed's torso carries a ~35 cm lateral drift and 10–22° of
lean mismatch vs the 2D torso. The invariant is pinned by
`test_blended_arm_graft_attaches_to_shoulder` (attachment < 2 cm at every
phase, and the naive rule must measurably detach so the test stays
discriminating), plus elbow-rigidity and playback-attachment tests.

## Verification without a screen

- `tests/test_ue_export.py` (27 tests): rotation conversion, geometry
  preservation, capsule dimensions, blend algorithm port, foot-skate rule,
  GRF/met data contract, arm-graft invariants.
- Startup log (`Saved/Logs/RunsimViewer.log`) must show:
  `spawned runsim scene (terrain, runner, lights, sky, fog)`,
  `terrain: 121 chunks of 96 m (121 clean), 1056 m window`,
  `gaits_ue.json: 16 gaits, 13 segments, 12 bodies, 48 frames,
  speed 1.20-5.00 m/s, arms present` — and no `LogRunsim` errors.
- M2 cadence: at 3.0 m/s with hilliness 0 the HUD reads **229 spm
  (3.82 Hz)** (`2 / 0.5241 s`; a 3D solution plays at 2.8–3.3 Hz instead).

What still needs human eyes: the minimalist look (palette, fog density,
band thresholds), steering feel, arm placement on screen, and the M1
side-view pose comparison against `scripts/watch_gait.py`.

## Deviations from plan

The plan assumed an editor for authoring small binary assets; this repo is
text-only. Deviations that remain:

| Plan | Shipped | Why |
|---|---|---|
| Enhanced Input | Legacy ini mappings + `DefaultPlayerInputClass=/Script/Engine.PlayerInput` | Enhanced Input needs `.uasset` mapping contexts |
| UMG HUD | `AHUD::DrawHUD` Canvas panels | UMG widgets are `.uasset`s |
| A level with actors placed | `ARunsimGameMode` spawns everything at `StartPlay` | a `.umap` is binary |
| Authored materials | Dynamic instances of `/Engine/BasicShapes/BasicShapeMaterial` (`Color` parameter) | a material is an asset; the palette rides on shared MIDs |

Superseded v1 deviations: the spline-mesh ribbon terrain is replaced by the
procedural heightfield; the "no sky" fill-light hack is replaced by the
procedural SkyAtmosphere + real-time-capture SkyLight (which needs no
assets after all); the spline-mesh material usage warning is gone with the
ribbon.
