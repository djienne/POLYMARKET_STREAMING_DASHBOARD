[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSCommandPath
$BotRoot = (Resolve-Path (Join-Path $Root "..\BTC_pricer_15m")).Path

function Write-Step {
  param([string]$Message)
  Write-Host "[stop] $Message"
}

function Get-ListeningProcessIds {
  param([int]$Port)
  try {
    return @(
      Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    )
  } catch {
    return @(
      & netstat.exe -ano |
        Select-String -Pattern (":{0}\s+.*LISTENING" -f $Port) |
        ForEach-Object {
          $parts = ($_ -split "\s+") | Where-Object { $_ }
          if ($parts.Count -gt 0) { [int]$parts[-1] }
        } |
        Select-Object -Unique
    )
  }
}

function Stop-ListenersOnPort {
  param(
    [int]$Port,
    [string]$Name
  )
  $processIds = @(Get-ListeningProcessIds $Port | Where-Object { $_ -and $_ -ne $PID })
  if ($processIds.Count -eq 0) {
    Write-Step "$Name not listening on :$Port"
    return
  }
  foreach ($processId in $processIds) {
    Write-Step "stopping $Name listener pid=$processId on :$Port"
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
  }
}

function Invoke-BotCompose {
  param([string[]]$Args)
  Push-Location $BotRoot
  try {
    & docker.exe compose @Args
    if ($LASTEXITCODE -ne 0) {
      throw "docker compose $($Args -join ' ') failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

Stop-ListenersOnPort -Port 8799 -Name "backend"
Stop-ListenersOnPort -Port 5174 -Name "frontend"

Write-Step "docker compose stop grid ..."
Invoke-BotCompose @("stop", "grid")

Write-Step "done. Live trading was not touched."
