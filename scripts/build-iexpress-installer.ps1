param(
  [ValidateSet("nvidia", "intel")]
  [string]$LadaVariant = "nvidia",

  [string]$LadaVersion = "v0.11.0",

  [switch]$Offline,

  [switch]$SkipLadaDownload
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $projectRoot "dist"
$setupPath = Join-Path $distRoot "mosaic-setup-$LadaVariant.exe"
$sedPath = Join-Path $distRoot "mosaic-iexpress-$LadaVariant.sed"
$payloadZip = Join-Path $distRoot "mosaic-portable.zip"
$bootstrap = Join-Path $PSScriptRoot "setup-bootstrap.ps1"

& (Join-Path $PSScriptRoot "build-portable.ps1") -LadaVariant $LadaVariant -LadaVersion $LadaVersion -Offline:$Offline -SkipLadaDownload:$SkipLadaDownload

if (-not (Test-Path $payloadZip)) {
  throw "Missing payload zip: $payloadZip"
}

@"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=Install mosaic to the current user profile?
DisplayLicense=
FinishMessage=mosaic installation finished.
TargetName=$setupPath
FriendlyName=mosaic
AppLaunched=powershell.exe -ExecutionPolicy Bypass -File setup-bootstrap.ps1
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles
[Strings]
FILE_COUNT=2
[SourceFiles]
SourceFiles0=$distRoot
SourceFiles1=$PSScriptRoot
[SourceFiles0]
%FILE1%=mosaic-portable.zip
[SourceFiles1]
%FILE2%=setup-bootstrap.ps1
%FILE1%=$payloadZip
%FILE2%=$bootstrap
"@ | Set-Content -Path $sedPath -Encoding ASCII

iexpress.exe /N /Q $sedPath

Write-Host "Installer: $setupPath"
