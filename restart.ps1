[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSCommandPath

& (Join-Path $Root "stop.ps1")
Start-Sleep -Seconds 2
& (Join-Path $Root "start.ps1")
