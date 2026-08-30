# RunsimViewer — Unreal Engine renderer

An Unreal Engine 5.4 renderer for baked OpenSim Moco running solutions:
capsule segments driven directly by solver output, on procedural
variable-slope terrain, with a chase camera and user-controlled speed. It is
the 3D counterpart of `docs/run_viewer.html`, implementing
`docs/unreal_renderer_plan.md`.

**Status: built and running.** As of 2026-08-30 this compiles clean and renders
on the Windows workstation: **Unreal Engine 5.8.2** (`D:\unreal\UE_5.8`) with
**MSVC 14.44** and the Windows 10.0.22621 SDK. The first build succeeded with
zero errors and zero warnings — the 5.4-era code needed no changes for 5.8, and
the legacy input path (`Config/DefaultInput.ini` +
`DefaultPlayerInputClass=/Script/Engine.PlayerInput`) still works. The Python
exporter and its tests are run and passing.

## What is in the box

```
RunsimViewer.uproject             UE 5.4 project, one C++ module, no plugins
Config/DefaultEngine.ini          default map + global game mode
Config/DefaultGame.ini            stages Content/Data as non-asset files
Config/DefaultInput.ini           legacy axis/action bindings (no Enhanced Input assets)
Content/Data/gaits_ue.json        baked gaits (generated; 246 KB)
Source/RunsimViewer/
  Public/RunsimTerrainMath.h      sum-of-sines ground; the single source of truth
  Public/RunsimGaitData.h         JSON load + speed/grade blend (port of the web viewer)
  Public/RunsimRunner.h           capsule-per-segment actor, per-tick posing
  Public/RunsimTerrain.h          spline-mesh ribbon + distance posts
  Public/RunsimPawn.h             spring-arm chase camera, input, orbit
  Public/RunsimHUD.h              Canvas HUD (speed/pace/grade/cadence/COT)
  Public/RunsimGameMode.h         spawns the whole scene, so no level asset is needed
```

There are **no `.uasset` files**. Meshes are the engine basic shapes
(`/Engine/BasicShapes/Cylinder`, `Sphere`, `Cube`); the level is any empty
map, because `ARunsimGameMode` spawns the terrain, the runner, a player start
and two directional lights itself.

## Build and run

1. **Install Unreal Engine 5.4 or newer** via the Epic Games Launcher
   (Library → + → 5.4.x). Any 5.4+ works; the `.uproject` says `5.4`.
2. **Install Visual Studio 2022** with the **"Game development with C++"**
   workload (the free Community edition or the Build Tools are both fine).
   Make sure these individual components are ticked:
   - MSVC v143 x64/x86 build tools
   - Windows 10/11 SDK
   - .NET Framework 4.6.2 targeting pack (UnrealBuildTool needs it)
3. **Generate the project files.** Right-click
   `unreal/RunsimViewer/RunsimViewer.uproject` in Explorer →
   *Generate Visual Studio project files*. (If that entry is missing, run
   `"C:\Program Files\Epic Games\UE_5.4\Engine\Binaries\Win64\UnrealVersionSelector.exe" /projectfiles <path to .uproject>`.)
   If the engine version prompt appears, pick your installed 5.x.
4. **Build.** Open the generated `RunsimViewer.sln`, set the configuration to
   **Development Editor / Win64**, and build the `RunsimViewer` target.
   Equivalent from a command line:
   ```
   "D:\unreal\UE_5.8\Engine\Build\BatchFiles\Build.bat" ^
       RunsimViewerEditor Win64 Development ^
       -Project="D:\runsim\unreal\RunsimViewer\RunsimViewer.uproject" -WaitMutex
   ```
   To skip the editor and go straight to the render in a window:
   ```
   "D:\unreal\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe" ^
       "D:\runsim\unreal\RunsimViewer\RunsimViewer.uproject" ^
       -game -windowed -resx=1600 -resy=900
   ```
5. **Open** `RunsimViewer.uproject` (double-click, or F5 from Visual Studio).
   The editor opens on `/Engine/Maps/Entry`, an empty engine map.
6. **Press Play.** The game mode spawns everything. If the editor opened some
   other level, either open `/Engine/Maps/Entry` (Content Browser → settings →
   *Show Engine Content*, then Engine → Maps) or make any empty level — the
   game mode is global, so Play works in all of them.

Controls: `W`/`S` or `Up`/`Down` change speed, `H`/`F` change hilliness,
`Space` pauses, hold **right mouse** to orbit, mouse wheel zooms, `R` resets
the view. Gamepad: triggers for speed, right stick to orbit, D-pad for hills.

## Regenerating the gait data

`Content/Data/gaits_ue.json` is generated from the committed Moco solutions —
regenerate it whenever those change:

```
cd D:\runsim
.venv\Scripts\python.exe scripts\export_ue_gaits.py
.venv\Scripts\python.exe -m pytest tests\test_ue_export.py -q
```

The exporter prints the resolved capsule dimensions and each gait's stride
time, stride length and cadence. It writes straight into
`unreal/RunsimViewer/Content/Data/`. The file is plain JSON, not a `.uasset`,
so `DefaultGame.ini` stages `Content/Data` explicitly for packaged builds
(`+DirectoriesToAlwaysStageAsUFS`).

To add 3D gaits with arm swing later, put the solution in `GAITS_3D` at the
top of `scripts/export_ue_gaits.py` and re-run: the arm segments are already
declared and dimensioned, and both the exporter and the renderer already
tolerate gaits that lack those bodies (the segments stay hidden).

## What is verified, and what is not

**Verified by running it** (`tests/test_ue_export.py`, 16 tests):

- the OpenSim → Unreal rotation conversion round-trips, and agrees exactly
  with the matrix conjugation `R_ue = M R M^T`;
- a rotation about the model's sagittal flexion axis becomes a *positive*
  Unreal pitch — the sign that decides whether the runner leans into a hill
  or out of it;
- for real exported frames, joint-to-joint distances in Unreal space equal
  the OpenSim distances × 100, and the exported quaternions correctly place
  child joints when used to rotate a body-frame offset;
- capsule lengths sit in adult human ranges (thigh 39.7 cm, shank 41.6 cm,
  foot 16.4 cm, upper arm 28.7 cm, forearm 25.3 cm);
- the 3.0 m/s flat gait's cadence is 3.82 Hz (the M2 acceptance number).

**Verified by building and running it** (UE 5.8.2, 2026-08-30):

- everything in `Source/` compiles and links with zero errors and zero warnings;
- `/Engine/Maps/Entry` exists and `ARunsimGameMode` populates it — the game log
  reports `spawned runsim scene (terrain, runner, lights)`;
- the data path works end to end: `gaits_ue.json: 14 gaits, 13 segments,
  8 bodies, 48 frames, speed 1.20-5.00 m/s, arms absent`, and the four arm
  segments hide themselves as intended.

**Known cosmetic defect**: the engine logs

```
Material /Engine/BasicShapes/BasicShapeMaterial missing usage flag SplineMeshes!
Default Material will be used in game.
```

so the terrain ribbon renders in the engine default material rather than the
alternating dark-blue shades (the runner capsules are unaffected). The fix is to
tick `bUsedWithSplineMeshes` on a material **asset**, which this text-only repo
cannot express — see the deviations table above.

## M1 verification — geometry against OpenSim

The plan's first milestone is "limb lengths and axes correct vs an OpenSim
screenshot". Procedure:

1. Pause the sim on the first frame: press Play, then `Space` immediately.
   (The runner poses itself once in `BeginPlay`, so frame 0 is already the
   baked pose, not a T-pose.)
2. Orbit with the right mouse button to a pure side view (yaw 90°, pitch 0)
   and note the pose: trunk angle, both knees, both ankles.
3. Render the same instant in OpenSim:
   ```
   .venv\Scripts\python.exe scripts\watch_gait.py ^
       --motion experiments\phase3_2drunning\fullstride_v3_gp0_met.sto --no-follow
   ```
   and step to t = 0.
4. Compare. Limb *lengths* are already pinned numerically by the tests; what
   the screenshot adds is the **axis convention** — if a knee bends the wrong
   way, or the runner faces −X, or the whole figure is mirrored, the
   quaternion conversion has a sign error and
   `tests/test_ue_export.py::test_sagittal_flexion_becomes_positive_unreal_pitch`
   is the place to fix it.

## M2 acceptance — cadence

With the speed at 3.0 m/s on flat ground (press Play, leave the speed alone,
set hills to zero with `F`), the HUD must read **228 spm (3.80 Hz)**. That is
the 2D-sourced number: `2 / strideTime` with `strideTime = 0.524 s`. A 3D
seed, once one exists, would read 2.8 Hz instead.

If the number is right but the feet skate, the phase advance and the world
advance have come apart — both live in `ARunsimRunner::Tick`, and the rule is
that the body advances at `strideLen / strideTime` (what the baked stride
actually produces), never at the speed the user asked for.

## Deviations from plan

`docs/unreal_renderer_plan.md` assumes an editor is available to author small
binary assets. This machine has no engine at all, so every deviation below
trades an asset for text.

| Plan | Shipped | Why |
|---|---|---|
| Enhanced Input (§5) | Legacy axis/action mappings in `Config/DefaultInput.ini`, with `DefaultPlayerInputClass` forced back to `/Script/Engine.PlayerInput` | Enhanced Input needs `InputAction` and `InputMappingContext` `.uasset`s. Legacy bindings are pure ini. |
| UMG HUD widget (§6) | `ARunsimHUD::DrawHUD` on the Canvas | A UMG widget is a `.uasset`. |
| Blueprints for input and HUD (§2) | All C++ | Same reason. There are no Blueprints in this project. |
| A level with the actors placed | `ARunsimGameMode` spawns terrain, runner, player start and lights at `StartPlay`; default map is `/Engine/Maps/Entry` | A `.umap` is a binary asset. |
| Sky/lighting from the level | Two directional lights (key + fill), no sky light or sky atmosphere | A sky light needs a cubemap asset; a captured sky would be black. The background is therefore flat and dark — dragging a **Sky Atmosphere** and a **Sky Light** into the level in the editor is a 30-second visual upgrade that this repo cannot make for you. |
| Segment materials | Dynamic material instances of `/Engine/BasicShapes/BasicShapeMaterial`, setting `Color`/`BaseColor` | Per-segment colours would otherwise need a material asset. If that engine material exposes neither parameter, everything is grey until you make one. |
| Arms phase-locked to the legs from the 3D seed (§3) | Arm segments declared, dimensioned from `models/LaiUhlrich2022`, and **hidden** | The only 3D solution on disk (`seed3d_tracking_airborne.sto`) is a rejected, airborne solve. Shipping no arms beats shipping wrong ones. `GAITS_3D` in the exporter is the one-line extension point. |
| Grade blending as an additive delta (§3) | Additive for positions, *relative rotation* for orientations | The web viewer had no orientations; adding quaternion components is meaningless, so the grade term is applied as `Delta = GradeBlend ∘ Flat3⁻¹` on top of the speed-blended rotation. |
| `USplineMeshComponent` ribbon regenerated on change (§4) | Fixed ring buffer of 200 one-metre spline meshes re-anchored around the runner | An endless run must not allocate. Same height function, no per-frame rebuild. |

Two more notes, not deviations:

- The terrain height/grade functions live in exactly one file,
  `Public/RunsimTerrainMath.h`, included by both the terrain and the runner —
  the plan's requirement that ground and gait cannot disagree.
- Rotation composition goes through `FTransform` rather than `FQuat::operator*`
  wherever order matters. `FTransform`'s convention (`A * B` applies `A` then
  `B`) is unambiguous; the quaternion operator's is easy to get backwards, and
  a wrong guess could not have been caught by compiling on this machine.

## Milestone coverage

| # | Plan deliverable | Where it lives | Builds + runs? |
|---|---|---|---|
| M1 | Exporter + first-frame render | `scripts/export_ue_gaits.py`, `ARunsimRunner::BeginPlay` | yes |
| M2 | Single gait looping | `URunsimGaitData::SampleGait`, `ARunsimRunner::Tick` | yes |
| M3 | Speed blending + input | `URunsimGaitData::GetBlendedPose`, `ARunsimPawn` | yes |
| M4 | Terrain + slope blending + chase camera | `RunsimTerrainMath.h`, `ARunsimTerrain`, `ARunsimPawn` | yes |
| M5 | HUD + orbit camera | `ARunsimHUD`, `ARunsimPawn::InputTurn` | yes |

"Builds + runs" means the code compiles and the scene loads with the gait data;
the M1 pose comparison and the M2 cadence readout are eyeball checks, described
above.
