param(
  [string]$InstallDir = "$env:LOCALAPPDATA\mosaic"
)

$ErrorActionPreference = "Stop"

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "mosaic.lnk"

if (Test-Path $shortcutPath) {
  Remove-Item -LiteralPath $shortcutPath -Force
}

if (Test-Path $InstallDir) {
  Remove-Item -LiteralPath $InstallDir -Recurse -Force
}

Write-Host "mosaic removed."
