[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [string]$Command = "status",
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSCommandPath
$BotRoot = (Resolve-Path (Join-Path $Root "..\BTC_pricer_15m")).Path
$ResultsDir = Join-Path $BotRoot "results"
$LocationFile = Join-Path $ResultsDir ".live_location"
$SyncPidFile = Join-Path $ResultsDir ".vps_sync.pid"
$SyncLastFile = Join-Path $ResultsDir ".vps_sync_last"

function Write-Step {
  param([string]$Message)
  Write-Host "[live_switch] $Message"
}

function Get-DockerExe {
  $cmd = Get-Command "docker.exe" -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $fallback = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
  if (Test-Path $fallback) { return $fallback }
  throw "docker.exe not found. Start Docker Desktop and make sure Docker is available from Windows PowerShell."
}

function Invoke-BotCompose {
  param([string[]]$Args)
  $docker = Get-DockerExe
  Push-Location $BotRoot
  try {
    & $docker compose @Args
    if ($LASTEXITCODE -ne 0) {
      throw "docker compose $($Args -join ' ') failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

function Get-ContainerStatus {
  param([string]$Name)
  try {
    $docker = Get-DockerExe
    $status = & $docker ps -a --filter "name=$Name" --format "{{.Status}}" 2>$null | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) { return "unknown (docker unavailable)" }
    if (-not $status) { return "not found" }
    return $status
  } catch {
    return "unknown (docker unavailable)"
  }
}

function Test-ContainerRunning {
  param([string]$Name)
  $docker = Get-DockerExe
  $names = & $docker ps --filter "name=$Name" --format "{{.Names}}" 2>$null
  if ($LASTEXITCODE -ne 0) {
    throw "docker ps failed with exit code $LASTEXITCODE"
  }
  return @($names) -contains $Name
}

function Get-LocationMarker {
  if (Test-Path $LocationFile) {
    $value = (Get-Content -LiteralPath $LocationFile -Raw).Trim()
    if ($value) { return $value }
  }
  return "stopped"
}

function Set-LocationMarker {
  param([string]$Location)
  New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null
  Set-Content -LiteralPath $LocationFile -Value $Location -Encoding ascii
}

function Stop-SyncLoop {
  if (Test-Path $SyncPidFile) {
    $pidText = (Get-Content -LiteralPath $SyncPidFile -Raw).Trim()
    if ($pidText -match "^\d+$") {
      $proc = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
      if ($proc) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Write-Step "stopped stale VPS sync loop (pid=$pidText)"
      }
    }
    Remove-Item -LiteralPath $SyncPidFile -Force -ErrorAction SilentlyContinue
  }
}

function Stop-LocalOffload {
  try {
    if (Test-ContainerRunning "btc_pricer_15m_offload") {
      $docker = Get-DockerExe
      & $docker stop "btc_pricer_15m_offload" | Out-Null
      if ($LASTEXITCODE -eq 0) {
        Write-Step "stopped local calibration offload container"
      }
    }
  } catch {
    Write-Step "local offload status unavailable: $($_.Exception.Message)"
  }
}

function Show-Status {
  $location = Get-LocationMarker
  Write-Host "location:         $location"
  Write-Host "local live:       $(Get-ContainerStatus 'btc_pricer_15m_live')"
  Write-Host "local offload:    $(Get-ContainerStatus 'btc_pricer_15m_offload')"

  if (Test-Path $SyncPidFile) {
    $pidText = (Get-Content -LiteralPath $SyncPidFile -Raw).Trim()
    if ($pidText -match "^\d+$" -and (Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue)) {
      Write-Host "vps sync loop:    running (pid=$pidText)"
    } else {
      Write-Host "vps sync loop:    stopped (stale pid file)"
    }
  } else {
    Write-Host "vps sync loop:    stopped"
  }

  if (Test-Path $SyncLastFile) {
    $last = [int64](Get-Content -LiteralPath $SyncLastFile -Raw)
    $age = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $last
    Write-Host "last vps sync:    ${age}s ago"
  }

  if ($location -like "vps*") {
    Write-Host "remote target:    unavailable (US East VPS was deleted)"
    Write-Host "next action:      .\live_switch.ps1 local"
  }
}

function Switch-Local {
  $location = Get-LocationMarker
  Write-Step "switching to LOCAL"
  if ($location -like "vps*") {
    Write-Step "marker was '$location'; skipping remote stop/pull because the US East VPS was deleted"
  }
  Stop-SyncLoop
  Stop-LocalOffload
  Invoke-BotCompose @("--profile", "local-live", "up", "-d", "live")
  Set-LocationMarker "local"
  Write-Step "LIVE is now LOCAL"
}

function Switch-Stop {
  Write-Step "stopping local live"
  try {
    Invoke-BotCompose @("--profile", "local-live", "stop", "live")
  } catch {
    Write-Step "local live stop unavailable: $($_.Exception.Message)"
  }
  Stop-SyncLoop
  Stop-LocalOffload
  Set-LocationMarker "stopped"
  Write-Step "LIVE is now STOPPED locally. No remote VPS target is configured."
}

function Show-Help {
  Write-Host "usage:"
  Write-Host "  .\live_switch.ps1 status"
  Write-Host "  .\live_switch.ps1 local     # start/restart local live"
  Write-Host "  .\live_switch.ps1 stop      # stop local live"
  Write-Host ""
  Write-Host "VPS switching is disabled because the US East VPS was deleted."
}

switch ($Command.ToLowerInvariant()) {
  "status" { Show-Status }
  "local" { Switch-Local }
  "start" { Switch-Local }
  "stop" { Switch-Stop }
  "help" { Show-Help }
  "-h" { Show-Help }
  "--help" { Show-Help }
  "vps" {
    throw "VPS switching is disabled because the US East VPS was deleted. Use .\live_switch.ps1 local or add a new VPS profile first."
  }
  "us_east" {
    throw "The US East VPS was deleted. Use .\live_switch.ps1 local."
  }
  default {
    Show-Help
    throw "unknown command: $Command"
  }
}
