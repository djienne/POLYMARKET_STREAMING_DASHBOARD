[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSCommandPath
& python (Join-Path $Root "manage.py") restart @Arguments
exit $LASTEXITCODE
