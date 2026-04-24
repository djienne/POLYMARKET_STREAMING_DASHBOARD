[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSCommandPath
& python (Join-Path $Root "manage.py") start @Arguments
exit $LASTEXITCODE
