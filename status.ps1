[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $PSCommandPath
$BotRoot = (Resolve-Path (Join-Path $Root "..\BTC_pricer_15m")).Path
$LiveSwitch = Join-Path $Root "live_switch.ps1"

function Test-PortListening {
  param([int]$Port)
  try {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
  } catch {
    $pattern = ":{0}\s+.*LISTENING" -f $Port
    return [bool](& netstat.exe -ano | Select-String -Pattern $pattern)
  }
}

function Get-ContainerState {
  param([string]$Name)
  Push-Location $BotRoot
  try {
    $state = & docker.exe ps -a --filter "name=$Name" --format "{{.Status}}" 2>$null | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) { return "unknown (docker unavailable)" }
    if (-not $state) { return "not found" }
    return $state
  } finally {
    Pop-Location
  }
}

Write-Host "[status] dashboard backend: $(if (Test-PortListening 8799) { 'running (:8799)' } else { 'stopped' })"
Write-Host "[status] dashboard frontend: $(if (Test-PortListening 5174) { 'running (:5174)' } else { 'stopped' })"
Write-Host "[status] grid container:     $(Get-ContainerState 'btc_pricer_15m_grid')"

if (Test-Path $LiveSwitch) {
  Write-Host ""
  Write-Host "[status] live switch:"
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $LiveSwitch status
} else {
  Write-Warning "live switch script not found: $LiveSwitch"
}
