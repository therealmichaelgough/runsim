<#
Launch run_continuation.py detached (effort -> metabolic continuation on
the v6 formulation), with its own log pair. Mirrors launch_legs.ps1.

Usage:
  powershell -File experiments\phase3_3drunning\launch_continuation.ps1 `
      -Start met_leg03.sto -LogName cont1 -Threads 64 `
      -Blends "10,3,1,0.3,0" -StageLegs 3 -LegIters 150
  -Start is relative to experiments\phase3_3drunning (or absolute) and
  should be a converged (or near-feasible) EFFORT gait on the v6 model.
#>
param(
    [Parameter(Mandatory = $true)][string]$Start,
    [string]$LogName = "cont1",
    [int]$Threads = 64,
    [string]$Blends = "10,3,1,0.3,0",
    [int]$StageLegs = 3,
    [int]$LegIters = 150,
    [double]$TorqueWeight = 50,
    [double]$Power = 0.01,
    [string]$PowerOn = "lumbar",
    [double]$TorquePrice = 0.006,
    [string[]]$IpoptOpts = @()
)
$root = "D:\runsim"
$d3 = Join-Path $root "experiments\phase3_3drunning"
$startPath = if ([System.IO.Path]::IsPathRooted($Start)) { $Start } else { Join-Path $d3 $Start }
if (-not (Test-Path $startPath)) { throw "start solution missing: $startPath" }

$optFile = Join-Path $root "ipopt.opt"
if ($IpoptOpts.Count -gt 0) {
    [System.IO.File]::WriteAllText($optFile, "# written by launch_continuation.ps1 $(Get-Date -Format s) for $LogName`n" + ($IpoptOpts -join "`n") + "`n")
    "ipopt.opt: $($IpoptOpts -join '; ')"
} elseif (Test-Path $optFile) {
    Remove-Item -Confirm:$false $optFile; "ipopt.opt removed (Moco defaults)"
}

$env:OPENSIM_MOCO_PARALLEL = "$Threads"
$py = Join-Path $root ".venv\Scripts\python.exe"
$args = @("experiments\phase3_3drunning\run_continuation.py", $startPath,
          "--blends=$Blends", "--stage-legs=$StageLegs", "--leg-iters=$LegIters",
          "--torque-weight=$TorqueWeight", "--power=$Power", "--power-on=$PowerOn",
          "--torque-price=$TorquePrice")
$out = Join-Path $d3 "$LogName.log"
$err = Join-Path $d3 "$LogName`_err.log"
if (Test-Path $out) { throw "log exists, pick another -LogName: $out" }
$p = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $root `
    -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
"launched shim PID $($p.Id) at $(Get-Date -Format HH:mm:ss): threads=$Threads start=$(Split-Path -Leaf $startPath) blends=$Blends stage_legs=$StageLegs x $LegIters"
"driver args: $($args -join ' ')"
"log: $out"
