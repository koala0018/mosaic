param(
  [ValidateSet("nvidia", "intel")]
  [string]$LadaVariant = "nvidia",

  [string]$LadaVersion = "v0.11.0",

  [switch]$Offline,

  [switch]$Installer,

  [switch]$UseExistingPayload,

  [switch]$SkipLadaDownload,

  [switch]$SkipArchive
)

$ErrorActionPreference = "Stop"

if ($Installer) {
  & (Join-Path $PSScriptRoot "build-iexpress-installer.ps1") -LadaVariant $LadaVariant -LadaVersion $LadaVersion -Offline:$Offline -UseExistingPayload:$UseExistingPayload -SkipLadaDownload:$SkipLadaDownload
} else {
  & (Join-Path $PSScriptRoot "build-portable.ps1") -LadaVariant $LadaVariant -LadaVersion $LadaVersion -Offline:$Offline -SkipLadaDownload:$SkipLadaDownload -SkipArchive:$SkipArchive
}
