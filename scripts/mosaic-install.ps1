param(
  [string]$InstallDir = (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "mosaic")
)

$ErrorActionPreference = "Stop"

$source = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

Copy-Item -Path (Join-Path $source "*") -Destination $InstallDir -Recurse -Force

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "mosaic.lnk"
$exePath = Join-Path $InstallDir "mosaic.exe"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $InstallDir
$shortcut.Description = "mosaic long-video restoration"
$shortcut.Save()

Write-Host "mosaic installed to $InstallDir"
Write-Host "Desktop shortcut: $shortcutPath"
