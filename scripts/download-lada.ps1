param(
  [ValidateSet("nvidia", "intel")]
  [string]$Variant = "nvidia",

  [string]$Version = "v0.11.0",

  [string]$Destination = "vendor\lada",

  [string]$LocalArchiveDirectory = "vendor\downloads",

  [switch]$Offline,

  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Get-ProjectRoot {
  Split-Path -Parent $PSScriptRoot
}

function Get-SevenZip {
  $system7z = Get-Command "7z.exe" -ErrorAction SilentlyContinue
  if ($system7z) {
    return $system7z.Source
  }

  $toolsDir = Join-Path $projectRoot "vendor\tools"
  $local7zr = Join-Path $toolsDir "7zr.exe"
  if (Test-Path $local7zr) {
    return $local7zr
  }

  New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
  $url = "https://www.7-zip.org/a/7zr.exe"
  Write-Host "Downloading $url"
  try {
    curl.exe -L --fail --retry 3 --output $local7zr $url
    if ($LASTEXITCODE -ne 0) {
      throw "curl failed with exit code $LASTEXITCODE"
    }
  } catch {
    Write-Host "curl failed, retrying with Invoke-WebRequest"
    Invoke-WebRequest -Uri $url -OutFile $local7zr
  }

  if (-not (Test-Path $local7zr)) {
    throw "Could not download 7zr.exe."
  }
  return $local7zr
}

function Download-FileWithResume($Url, $Target, $ExpectedSize = 0) {
  $attempt = 0
  $maxAttempts = 30

  while ($attempt -lt $maxAttempts) {
    $attempt += 1
    $currentSize = 0
    if (Test-Path $Target) {
      $currentSize = (Get-Item $Target).Length
      if ($ExpectedSize -gt 0 -and $currentSize -eq $ExpectedSize) {
        Write-Host "Already downloaded: $Target"
        return
      }
      Write-Host "Resuming $Target at $currentSize bytes (attempt $attempt/$maxAttempts)"
    } else {
      Write-Host "Downloading $Url (attempt $attempt/$maxAttempts)"
    }

    curl.exe `
      -L `
      --fail `
      --retry 5 `
      --retry-all-errors `
      --connect-timeout 30 `
      --speed-time 180 `
      --speed-limit 1024 `
      -C - `
      --output $Target `
      $Url

    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0 -and (Test-Path $Target)) {
      $newSize = (Get-Item $Target).Length
      if ($ExpectedSize -eq 0 -or $newSize -eq $ExpectedSize) {
        return
      }
      Write-Host "Size mismatch: expected $ExpectedSize bytes, got $newSize bytes."
    } else {
      Write-Host "Download failed with exit code $exitCode."
    }

    Start-Sleep -Seconds ([Math]::Min(60, 2 * $attempt))
  }

  throw "Failed to download $Url after $maxAttempts attempts."
}

function Invoke-ArchiveExtract($Archive, $Destination) {
  $tar = Get-Command "tar.exe" -ErrorAction SilentlyContinue
  if ($tar) {
    Write-Host "Extracting with tar: $Archive"
    & $tar.Source -xf $Archive -C $Destination
    if ($LASTEXITCODE -eq 0) {
      return
    }
    Write-Host "tar extraction failed with exit code $LASTEXITCODE."
  }

  $sevenZip = Get-SevenZip
  Write-Host "Extracting with 7-Zip: $Archive"
  & $sevenZip x $Archive "-o$Destination" -y
  if ($LASTEXITCODE -ne 0) {
    throw "Archive extraction failed with exit code $LASTEXITCODE."
  }
}

function Get-LadaReleaseFiles($Variant, $Version) {
  $githubBase = "https://github.com/ladaapp/lada/releases/download/$Version"
  $ghProxyBase = "https://gh-proxy.com/$githubBase"
  if ($Variant -eq "intel") {
    return @{
      Options = @(
        @{
          Name = "gh-proxy.com accelerated single archive"
          Files = @(
            @{
              Name = "lada-$($Version)_windows_intel.7z"
              Size = 1312253117
              Sha256 = "405d053f76e5f773b8b27bbaf921a44fdcf2c59c9fc91ed3f68f1a8daa3a8511"
              Url = "$ghProxyBase/lada-$($Version)_windows_intel.7z"
            }
          )
        },
        @{
          Name = "Pixeldrain single archive"
          Files = @(
            @{
              Name = "lada-$($Version)_windows_intel.7z"
              Size = 0
              Sha256 = "405d053f76e5f773b8b27bbaf921a44fdcf2c59c9fc91ed3f68f1a8daa3a8511"
              Url = "https://pixeldrain.com/api/file/YAZgG4Pw?download"
            }
          )
        },
        @{
          Name = "GitHub single archive"
          Files = @(
            @{
              Name = "lada-$($Version)_windows_intel.7z"
              Size = 1312253117
              Sha256 = "405d053f76e5f773b8b27bbaf921a44fdcf2c59c9fc91ed3f68f1a8daa3a8511"
              Url = "$githubBase/lada-$($Version)_windows_intel.7z"
            }
          )
        }
      )
    }
  }

  return @{
    Options = @(
      @{
        Name = "gh-proxy.com accelerated split archive"
        Files = @(
          @{
            Name = "lada-$($Version)_windows_nvidia.7z.001"
            Size = 2096103424
            Sha256 = "861caf4bc3fb08bb4f145a0ef53172d051d39401e9f5b1c6cbab7206b32e518b"
            Url = "$ghProxyBase/lada-$($Version)_windows_nvidia.7z.001"
          },
          @{
            Name = "lada-$($Version)_windows_nvidia.7z.002"
            Size = 401197306
            Sha256 = "472b8012f676cca0ef0eb6af9a69ba1256370dbe6c1c84740ab34d4c2650b796"
            Url = "$ghProxyBase/lada-$($Version)_windows_nvidia.7z.002"
          }
        )
      },
      @{
        Name = "Pixeldrain single archive"
        Files = @(
          @{
            Name = "lada-$($Version)_windows_nvidia.7z"
            Size = 0
            Sha256 = "fa0f571964a947402cfaad564180cffd3ef61526c739b5278e64fd0ddec5ca13"
            Url = "https://pixeldrain.com/api/file/vWJKV7X5?download"
          }
        )
      },
      @{
        Name = "GitHub split archive"
        Files = @(
          @{
            Name = "lada-$($Version)_windows_nvidia.7z.001"
            Size = 2096103424
            Sha256 = "861caf4bc3fb08bb4f145a0ef53172d051d39401e9f5b1c6cbab7206b32e518b"
            Url = "$githubBase/lada-$($Version)_windows_nvidia.7z.001"
          },
          @{
            Name = "lada-$($Version)_windows_nvidia.7z.002"
            Size = 401197306
            Sha256 = "472b8012f676cca0ef0eb6af9a69ba1256370dbe6c1c84740ab34d4c2650b796"
            Url = "$githubBase/lada-$($Version)_windows_nvidia.7z.002"
          }
        )
      }
    )
  }
}

function Use-LocalArchiveSet($ReleaseFiles, $ArchivePath, $Variant) {
  foreach ($option in $ReleaseFiles.Options) {
    $ok = $true
    foreach ($fileInfo in $option.Files) {
      $path = Join-Path $ArchivePath $fileInfo.Name
      if (-not (Test-Path $path)) {
        $ok = $false
        break
      }
      $actualSize = (Get-Item $path).Length
      if ($fileInfo.Size -gt 0 -and $actualSize -ne $fileInfo.Size) {
        Write-Host "Ignoring $path because size is $actualSize but expected $($fileInfo.Size)."
        $ok = $false
        break
      }
      $actualSha = (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToLowerInvariant()
      if ($actualSha -ne $fileInfo.Sha256) {
        Write-Host "Ignoring $path because sha256 mismatch."
        Write-Host "  expected: $($fileInfo.Sha256)"
        Write-Host "  actual:   $actualSha"
        $ok = $false
        break
      }
    }
    if ($ok) {
      Set-Content -Path (Join-Path $ArchivePath ".selected-$Variant.txt") -Value $option.Files[0].Name -Encoding ASCII
      Write-Host "Using local Lada package: $($option.Name)"
      return $true
    }
  }
  return $false
}

function Get-SelectedArchivePath($ReleaseFiles, $ArchivePath) {
  foreach ($option in $ReleaseFiles.Options) {
    $first = Join-Path $ArchivePath $option.Files[0].Name
    $allExist = $true
    foreach ($fileInfo in $option.Files) {
      if (-not (Test-Path (Join-Path $ArchivePath $fileInfo.Name))) {
        $allExist = $false
        break
      }
    }
    if ($allExist) {
      return $first
    }
  }
  throw "No selected Lada archive found."
}

$projectRoot = Get-ProjectRoot
$destinationPath = Join-Path $projectRoot $Destination
$archivePath = Join-Path $projectRoot $LocalArchiveDirectory
$extractPath = Join-Path $destinationPath $Variant

New-Item -ItemType Directory -Force -Path $archivePath | Out-Null
New-Item -ItemType Directory -Force -Path $destinationPath | Out-Null

if ((Test-Path (Join-Path $extractPath "lada-cli.exe")) -and -not $Force) {
  Write-Host "Lada already exists: $extractPath"
  exit 0
}

$releaseFiles = Get-LadaReleaseFiles $Variant $Version

if (-not (Use-LocalArchiveSet $releaseFiles $archivePath $Variant)) {
  if ($Offline) {
    Write-Host ""
    Write-Host "Missing local Lada package."
    Write-Host "Download one of these official packages and put it in:"
    Write-Host "  $archivePath"
    Write-Host ""
    foreach ($option in $releaseFiles.Options) {
      Write-Host "Option: $($option.Name)"
      foreach ($file in $option.Files) {
        Write-Host "  $($file.Name)"
        Write-Host "  url: $($file.Url)"
        Write-Host "  sha256: $($file.Sha256)"
      }
      Write-Host ""
    }
    throw "Offline mode requires a complete local Lada package."
  }

  $downloadOption = $releaseFiles.Options[0]
  foreach ($fileInfo in $downloadOption.Files) {
    $target = Join-Path $archivePath $fileInfo.Name
    if ($Force -and (Test-Path $target)) {
      Remove-Item -LiteralPath $target -Force
    }

    Download-FileWithResume $fileInfo.Url $target $fileInfo.Size
  }

  if (-not (Use-LocalArchiveSet $releaseFiles $archivePath $Variant)) {
    throw "Downloaded files did not pass validation."
  }
}

if (Test-Path $extractPath) {
  Remove-Item -LiteralPath $extractPath -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $extractPath | Out-Null

$firstArchive = Get-SelectedArchivePath $releaseFiles $archivePath

Write-Host "Extracting $firstArchive"
Invoke-ArchiveExtract $firstArchive $extractPath

$cli = Get-ChildItem -Path $extractPath -Filter "lada-cli.exe" -Recurse | Select-Object -First 1
if (-not $cli) {
  throw "Could not find lada-cli.exe after extraction."
}

$cliDir = Split-Path -Parent $cli.FullName
if ($cliDir -ne $extractPath) {
  Write-Host "Flattening Lada directory from $cliDir"
  Get-ChildItem -Path $cliDir -Force | Move-Item -Destination $extractPath -Force
}

Write-Host "Lada ready: $extractPath"
