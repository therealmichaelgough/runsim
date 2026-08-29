# Stop the sequential sweep (PID passed) once its 2.9 Hz entry is logged,
# so it cannot duplicate the parallel batch. Detach-safe, idempotent.
param([int]$SweepPid)

$log = Join-Path $PSScriptRoot "cadence_sweep_log.json"
while (Get-Process -Id $SweepPid -ErrorAction SilentlyContinue) {
    try {
        $entries = Get-Content $log -Raw | ConvertFrom-Json
        $found = $false
        foreach ($e in $entries) { if ([math]::Abs($e.imposed_step_freq_hz - 2.9) -lt 0.01) { $found = $true } }
        if ($found) {
            Stop-Process -Id $SweepPid -Force -ErrorAction SilentlyContinue
            break
        }
    } catch {}
    Start-Sleep -Seconds 5
}
