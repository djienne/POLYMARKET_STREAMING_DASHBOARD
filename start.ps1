[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSCommandPath
$BotRoot = (Resolve-Path (Join-Path $Root "..\BTC_pricer_15m")).Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"

function Write-Step {
  param([string]$Message)
  Write-Host "[start] $Message"
}

function Test-PortListening {
  param([int]$Port)
  try {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
  } catch {
    $pattern = ":{0}\s+.*LISTENING" -f $Port
    return [bool](& netstat.exe -ano | Select-String -Pattern $pattern)
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

function Quote-PowerShellLiteral {
  param([string]$Value)
  return "'" + ($Value -replace "'", "''") + "'"
}

function Start-MinimizedShell {
  param(
    [string]$Title,
    [string]$WorkingDirectory,
    [string]$Command
  )
  $quotedDir = Quote-PowerShellLiteral $WorkingDirectory
  $fullCommand = "`$host.UI.RawUI.WindowTitle = '$($Title -replace "'", "''")'; Set-Location -LiteralPath $quotedDir; $Command"
  Start-Process -FilePath "powershell.exe" -WindowStyle Minimized -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $fullCommand
  ) | Out-Null
}

Write-Step "docker compose up -d grid ..."
Invoke-BotCompose @("up", "-d", "grid")

if (Test-PortListening 8799) {
  Write-Step "backend already listening on :8799"
} else {
  Write-Step "launching backend uvicorn on :8799 ..."
  Start-MinimizedShell `
    -Title "Dashboard Backend (uvicorn :8799)" `
    -WorkingDirectory $BackendDir `
    -Command "python -m uvicorn app.main:app --host 127.0.0.1 --port 8799 --reload"
}

if (Test-PortListening 5174) {
  Write-Step "frontend already listening on :5174"
} else {
  Write-Step "launching frontend vite on :5174 ..."
  Start-MinimizedShell `
    -Title "Dashboard Frontend (vite :5174)" `
    -WorkingDirectory $FrontendDir `
    -Command "npm run dev"
}

Write-Step "done. Dashboard: http://127.0.0.1:5174  (backend API: :8799)"
