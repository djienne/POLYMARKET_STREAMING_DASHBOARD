[CmdletBinding()]
param(
  [string]$Profile = "infos",
  [string]$BotRoot = "",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSCommandPath
$pyArgs = @("setup-vps", "--profile", $Profile)
if ($BotRoot) {
  $pyArgs += @("--bot-root", $BotRoot)
}
if ($SkipBuild) {
  $pyArgs += "--skip-build"
}
& python (Join-Path $Root "manage.py") @pyArgs
exit $LASTEXITCODE
