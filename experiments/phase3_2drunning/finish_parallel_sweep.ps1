# Chain finisher for the parallelized cadence sweep: wait for the listed
# solver PIDs to exit, merge fragments into cadence_sweep_log.json, then
# launch the full 3D tracking-seed solve. Detach-safe.
param([int[]]$SolverPids = @())

foreach ($solverPid in $SolverPids) {
    while (Get-Process -Id $solverPid -ErrorAction SilentlyContinue) {
        Start-Sleep -Seconds 30
    }
}

Set-Location $PSScriptRoot\..\..
& .\.venv\Scripts\python.exe experiments\phase3_2drunning\merge_cadence_fragments.py *> experiments\phase3_2drunning\merge_log.txt
& .\.venv\Scripts\python.exe experiments\phase3_3drunning\make_seed_3d.py *> experiments\phase3_3drunning\seed3d_full_stdout.log
