<#
Launch the segmented metabolic leg driver (run_met_legs.py) detached, with
its own log pair and an explicit IPOPT option file. One place to get the
launch right: the driver's CWD is the repo root, IPOPT reads .\ipopt.opt
from there at every solver start, and Moco's stop sentinels land there.

Usage (from anywhere):
  powershell -File experiments\phase3_3drunning\launch_legs.ps1 `
      -Start screen\base\solution_screen_base.sto -TorqueWeight 50 `
      -LogName met_legs5 -Threads 64 -IpoptOpts @("mu_strategy monotone")
  -Start is relative to experiments\phase3_3drunning (or absolute).
  -IpoptOpts @() removes any ipopt.opt so Moco defaults apply.
Prints the shim PID; watch the log for liveness, not the PID (the venv
python.exe is a launcher shim whose child does the work).
#>
param(
    [Parameter(Mandatory = $true)][string]$Start,
    [double]$TorqueWeight = 50,
    [string]$LogName = "met_legs5",
    [int]$Threads = 64,
    [int]$LegIters = 300,
    [int]$MaxLegs = 12,
    [int]$Mesh = 50,
    [switch]$Passive,
    [switch]$Strength,
    [double]$Power = -1,   # >= 0: price squared torque-actuator power at this weight
    [string]$PowerOn = "",  # e.g. "lumbar" — actuator name prefixes to power-price (all if empty)
    [string[]]$IpoptOpts = @()
)
$root = "D:\runsim"
$d3 = Join-Path $root "experiments\phase3_3drunning"
$startPath = if ([System.IO.Path]::IsPathRooted($Start)) { $Start } else { Join-Path $d3 $Start }
if (-not (Test-Path $startPath)) { throw "start solution missing: $startPath" }

$optFile = Join-Path $root "ipopt.opt"
if ($IpoptOpts.Count -gt 0) {
    $body = "# written by launch_legs.ps1 $(Get-Date -Format s) for $LogName`n" + (($IpoptOpts | ForEach-Object { $_ }) -join "`n") + "`n"
    [System.IO.File]::WriteAllText($optFile, $body)   # LF, no BOM
    "ipopt.opt: $($IpoptOpts -join '; ')"
} elseif (Test-Path $optFile) {
    Remove-Item -Confirm:$false $optFile; "ipopt.opt removed (Moco defaults)"
}

$env:OPENSIM_MOCO_PARALLEL = "$Threads"
$py = Join-Path $root ".venv\Scripts\python.exe"
$args = @("experiments\phase3_3drunning\run_met_legs.py", $startPath, "$LegIters", "$MaxLegs", "$TorqueWeight", "$Mesh")
if ($Passive) { $args += "--passive" }
if ($Strength) { $args += "--strength" }
if ($Power -ge 0) { $args += "--power=$Power" }
if ($PowerOn -ne "") { $args += "--power-on=$PowerOn" }
$out = Join-Path $d3 "$LogName.log"
$err = Join-Path $d3 "$LogName`_err.log"
if (Test-Path $out) { throw "log exists, pick another -LogName: $out" }
$p = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $root `
    -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
"launched shim PID $($p.Id) at $(Get-Date -Format HH:mm:ss): threads=$Threads start=$(Split-Path -Leaf $startPath) w=$TorqueWeight legs=$MaxLegs x $LegIters mesh=$Mesh passive=$Passive strength=$Strength"
"log: $out"
