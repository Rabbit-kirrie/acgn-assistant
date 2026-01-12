# One-click dev launcher for Windows PowerShell
# - Loads ENV=dev and PYTHONPATH=...\src
# - Runs uvicorn with --reload on a port (default 8000)
# - Detects port conflicts and can stop the owning process(es)
# - Uses the workspace venv Python if present

param(
  [int]$Port = 8000,
  [switch]$KillPortUsers,
  [string]$BindHost = '0.0.0.0',
  [bool]$AutoPort = $true,
  [int]$AutoPortScan = 200
)

$ErrorActionPreference = 'Stop'

# Go to repo root (scripts/ -> ..)
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

# Env for FastAPI app
$env:ENV = 'dev'
$env:PYTHONPATH = (Join-Path $repoRoot 'src')

# Pick python executable
$py = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
  Write-Host "[start_dev.ps1] .venv not found. Please create venv first: python -m venv .venv" -ForegroundColor Yellow
  $py = 'python'
}

Write-Host "[start_dev.ps1] Repo: $repoRoot"
Write-Host "[start_dev.ps1] ENV=$($env:ENV)"
Write-Host "[start_dev.ps1] PYTHONPATH=$($env:PYTHONPATH)"
Write-Host "[start_dev.ps1] BindHost=$BindHost"
Write-Host "[start_dev.ps1] Port=$Port" 

function Get-PortOwningPids([int]$p) {
  # Prefer Get-NetTCPConnection (object-based), but fall back to parsing netstat.
  # Only consider LISTENING sockets to avoid false positives from TIME_WAIT, etc.
  try {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction Stop
    return @(
      $conns |
        Select-Object -ExpandProperty OwningProcess -Unique |
        Where-Object { $_ -and $_ -ne 0 }
    )
  } catch {
    try {
      $lines = netstat -ano | Select-String -Pattern (":$p\s+")
      $pids = @()
      foreach ($m in $lines) {
        $line = [string]$m.Line
        if ($line -notmatch 'LISTENING') { continue }
        if ($line -match '\s+(\d+)\s*$') {
          $foundPid = [int]$Matches[1]
          if ($foundPid -ne 0) { $pids += $foundPid }
        }
      }
      return @($pids | Select-Object -Unique)
    } catch {
      return @()
    }
  }
}

function Test-PortFree([int]$p) {
  $pids = Get-PortOwningPids $p
  return ($pids.Count -eq 0)
}

function Stop-Pids([int[]]$pids) {
  foreach ($procId in $pids) {
    if ($procId -eq 4) {
      Write-Host ("[start_dev.ps1] PID 4 (System) owns the port; cannot be stopped.") -ForegroundColor Yellow
      continue
    }
    try {
      $proc = Get-Process -Id $procId -ErrorAction Stop
      Write-Host ("[start_dev.ps1] Stopping PID {0} ({1})" -f $procId, $proc.ProcessName) -ForegroundColor Yellow
    } catch {
      Write-Host ("[start_dev.ps1] Stopping PID {0}" -f $procId) -ForegroundColor Yellow
    }
    try {
      Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    } catch {}
  }
}


function Find-NextFreePort([int]$start, [int]$scan) {
  $scan2 = [Math]::Max(1, [Math]::Min(500, $scan))
  for ($i = 0; $i -le $scan2; $i++) {
    $p = $start + $i
    if (Test-PortFree $p) { return $p }
  }
  return $null
}

function Get-LanIPv4Candidates() {
  try {
    $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
      Where-Object {
        $_.IPAddress -and
        $_.IPAddress -ne '127.0.0.1' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.PrefixOrigin -ne 'WellKnown'
      } |
      Select-Object -ExpandProperty IPAddress
    return @($ips | Select-Object -Unique)
  } catch {
    return @()
  }
}
$pids = Get-PortOwningPids $Port
if ($pids.Count -gt 0) {
  Write-Host ("[start_dev.ps1] Port {0} is in use by PID(s): {1}" -f $Port, ($pids -join ', ')) -ForegroundColor Yellow
  try {
    Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop | Select-Object -First 5 | Format-Table -AutoSize | Out-String | Write-Host
  } catch {}

  $shouldKill = $false
  if ($KillPortUsers) {
    $shouldKill = $true
  } else {
    $ans = Read-Host "Stop these process(es) now? (y/N)"
    if ($ans -match '^(y|yes)$') { $shouldKill = $true }
  }

  if ($shouldKill) {
    Stop-Pids $pids
    Start-Sleep -Seconds 1
    $pids2 = Get-PortOwningPids $Port
    if ($pids2.Count -gt 0) {
      if ($AutoPort) {
        $next = Find-NextFreePort ($Port + 1) $AutoPortScan
        if ($null -ne $next) {
          Write-Host ("[start_dev.ps1] Port {0} is still in use. Falling back to free port: {1}" -f $Port, $next) -ForegroundColor Yellow
          $Port = [int]$next
        } else {
          Write-Host ("[start_dev.ps1] Port {0} is still in use and no free port found. Please free it manually and retry." -f $Port) -ForegroundColor Red
          exit 1
        }
      } else {
        Write-Host ("[start_dev.ps1] Port {0} is still in use. Please free it manually and retry." -f $Port) -ForegroundColor Red
        exit 1
      }
    }
  } else {
    Write-Host "[start_dev.ps1] Aborted due to port conflict." -ForegroundColor Red
    exit 1
  }
}

if (-not (Test-PortFree $Port)) {
  if ($AutoPort) {
    $next = Find-NextFreePort $Port $AutoPortScan
    if ($null -ne $next) {
      Write-Host ("[start_dev.ps1] Requested port {0} is not free. Using free port: {1}" -f $Port, $next) -ForegroundColor Yellow
      $Port = [int]$next
    }
  }
}

if ($BindHost -eq '0.0.0.0' -or $BindHost -eq '::' -or $BindHost -eq '::0') {
  Write-Host ("[start_dev.ps1] Starting uvicorn on http://0.0.0.0:{0} (LAN enabled)" -f $Port) -ForegroundColor Cyan
  $ips = Get-LanIPv4Candidates
  if ($ips.Count -gt 0) {
    Write-Host "[start_dev.ps1] Open from another device:" -ForegroundColor Cyan
    foreach ($ip in ($ips | Select-Object -First 3)) {
      Write-Host ("  http://{0}:{1}/app" -f $ip, $Port) -ForegroundColor Cyan
    }
  }
} else {
  Write-Host ("[start_dev.ps1] Starting uvicorn on http://{0}:{1} (Ctrl+C to stop)" -f $BindHost, $Port) -ForegroundColor Cyan
}

& $py -m uvicorn acgn_assistant.main:app --reload --host $BindHost --port $Port
