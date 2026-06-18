param(
  [ValidateSet("nvidia", "intel")]
  [string]$LadaVariant = "nvidia",

  [string]$LadaVersion = "v0.11.0",

  [switch]$Offline,

  [switch]$SkipLadaDownload,

  [switch]$SkipArchive
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $projectRoot "dist"
$bundleRoot = Join-Path $distRoot "mosaic-portable"
$appBuild = Join-Path $distRoot "mosaic"
$ladaSource = Join-Path $projectRoot "vendor\lada\$LadaVariant"
$ladaTarget = Join-Path $bundleRoot "lada"

if (-not $SkipLadaDownload) {
  & (Join-Path $PSScriptRoot "download-lada.ps1") -Variant $LadaVariant -Version $LadaVersion -Offline:$Offline
}

if (-not (Test-Path (Join-Path $ladaSource "lada-cli.exe"))) {
  throw "Missing Lada runtime at $ladaSource. Run scripts\download-lada.ps1 first."
}

python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to update pip (exit code $LASTEXITCODE)." }
python -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Failed to install PyInstaller (exit code $LASTEXITCODE)." }
python -m pip install -e ($projectRoot + "[beauty]")
if ($LASTEXITCODE -ne 0) { throw "Failed to install mosaic dependencies (exit code $LASTEXITCODE)." }
python -m PyInstaller `
  --noconfirm `
  --windowed `
  --name mosaic `
  --paths (Join-Path $projectRoot "src") `
  --collect-submodules mosaic `
  --collect-all cv2 `
  --collect-submodules numpy `
  (Join-Path $projectRoot "src\mosaic\app.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit code $LASTEXITCODE)." }

if (Test-Path $bundleRoot) {
  Remove-Item -LiteralPath $bundleRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $bundleRoot | Out-Null

Copy-Item -Path (Join-Path $appBuild "*") -Destination $bundleRoot -Recurse -Force
Copy-Item -Path $ladaSource -Destination $ladaTarget -Recurse -Force
Copy-Item -Path (Join-Path $PSScriptRoot "mosaic-install.ps1") -Destination $bundleRoot -Force
Copy-Item -Path (Join-Path $PSScriptRoot "mosaic-uninstall.ps1") -Destination $bundleRoot -Force
Copy-Item -Path (Join-Path $projectRoot "THIRD_PARTY_NOTICES.md") -Destination $bundleRoot -Force

$readmePath = Join-Path $bundleRoot "README-install.txt"
@"
mosaic Windows portable package

Run mosaic.exe to open the app.

To install into the current user profile:
1. Right-click mosaic-install.ps1
2. Choose "Run with PowerShell"
3. A desktop shortcut named mosaic will be created.

Lada is bundled in the lada directory. The app will auto-detect lada\lada-cli.exe.
"@ | Set-Content -Path $readmePath -Encoding UTF8

if (-not $SkipArchive) {
  $zipPath = Join-Path $distRoot "mosaic-portable-$LadaVariant.zip"
  if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
  }

  $tar = Get-Command "tar.exe" -ErrorAction SilentlyContinue
  if ($tar) {
    Write-Host "Creating portable zip with tar.exe"
    & $tar.Source -a -cf $zipPath -C $bundleRoot .
    if ($LASTEXITCODE -ne 0) {
      throw "tar.exe failed to create portable zip with exit code $LASTEXITCODE."
    }
  } else {
    Write-Host "Creating portable zip with Compress-Archive"
    Compress-Archive -Path (Join-Path $bundleRoot "*") -DestinationPath $zipPath -Force
  }

  $genericZipPath = Join-Path $distRoot "mosaic-portable.zip"
  Copy-Item -Path $zipPath -Destination $genericZipPath -Force
  Write-Host "Portable zip: $zipPath"
}

Write-Host "Portable bundle: $bundleRoot"
