param(
  [string]$PortableDirectory = "dist\mosaic-portable",
  [string]$InstallDir = (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "mosaic")
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$portablePath = Join-Path $projectRoot $PortableDirectory
$installScript = Join-Path $portablePath "mosaic-install.ps1"

if (-not (Test-Path $installScript)) {
  throw "Portable package is missing install script: $installScript"
}

& powershell.exe -ExecutionPolicy Bypass -File $installScript -InstallDir $InstallDir
