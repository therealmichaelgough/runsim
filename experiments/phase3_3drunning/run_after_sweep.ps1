# Chain runner: wait for the cadence sweep (PID passed as arg) to exit,
# then launch the full 3D tracking-seed solve. Detach-safe.
param([int]$WaitPid = 0)

if ($WaitPid -gt 0) {
    while (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) {
        Start-Sleep -Seconds 60
    }
}

Set-Location $PSScriptRoot\..\..
& .\.venv\Scripts\python.exe experiments\phase3_3drunning\make_seed_3d.py *> experiments\phase3_3drunning\seed3d_full_stdout.log
