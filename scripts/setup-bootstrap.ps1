param(
  [string]$InstallDir = "$env:LOCALAPPDATA\mosaic"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$zip = Join-Path $root "mosaic-portable.zip"
$extractDir = Join-Path $env:TEMP ("mosaic-install-" + [guid]::NewGuid().ToString("N"))

if (-not (Test-Path $zip)) {
  throw "Installer payload is missing: $zip"
}

New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
Expand-Archive -Path $zip -DestinationPath $extractDir -Force

$installScript = Join-Path $extractDir "mosaic-install.ps1"
if (-not (Test-Path $installScript)) {
  throw "Install script is missing from payload."
}

& powershell.exe -ExecutionPolicy Bypass -File $installScript -InstallDir $InstallDir

Remove-Item -LiteralPath $extractDir -Recurse -Force
