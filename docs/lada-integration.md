# Lada Integration

## Decision

Use [Lada](https://github.com/ladaapp/lada) as the first mosaic detection and restoration engine.

Reasons:

- It already provides automatic mosaic detection.
- It already provides video restoration models and a CLI.
- It has Windows release artifacts with `lada.exe` and `lada-cli.exe`.
- Its pipeline preserves video size and timing metadata through its writer and audio remux step.

## License Boundary

Lada is licensed as AGPL-3.0. This repository currently remains MIT and does not vendor or copy Lada source code.

The integration is an external process adapter:

```text
mosaic app / CLI
  -> build lada-cli.exe command
  -> run external process
  -> stream logs
  -> report completion
```

If future work directly imports or modifies Lada code, the licensing plan must be reviewed first.

## Current Command Shape

The app builds commands like:

```powershell
lada-cli.exe `
  --input input.mp4 `
  --output output.restored.mp4 `
  --temporary-directory D:\Videos\.mosaic-temp `
  --max-clip-length 180 `
  --mosaic-detection-model v4-fast `
  --mosaic-restoration-model basicvsrpp-v1.2 `
  --fp16
```

For the balanced preset, the app does not force `--encoding-preset`; Lada chooses its default for the machine.

## Presets

| mosaic preset | Lada settings |
| --- | --- |
| fast | `h264-cpu-fast`, `v4-fast`, `max-clip-length=120` |
| balanced | Lada default encoder, `v4-fast`, `max-clip-length=180` |
| best | `h264-cpu-uhq`, `v4`, `max-clip-length=240` |

Higher `max-clip-length` can improve temporal stability but needs more memory. For weak GPUs or CPU-only machines, lower it.

## Windows App Responsibilities

- Select video file.
- Select output directory.
- Select `lada-cli.exe`.
- Configure quality/device/FP16.
- Start long-running process without freezing the UI.
- Stream logs.
- Cancel the child process.
- Show completion/failure message box.

## Next Improvements

- Query `lada-cli.exe --list-devices` and populate devices automatically.
- Query `--list-encoding-presets` and expose real encoder choices.
- Parse progress output into a progress bar.
- Save user settings in a local config file.
- Add queue support for multiple videos.
- Package the app shell with PyInstaller.

## Offline Packaging

Large Lada release files can be slow to download from some networks. The packaging scripts support an offline workflow:

1. Download the official Lada Windows package manually.
2. Put the file or split files in `vendor/downloads`.
3. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -Installer -LadaVariant nvidia -Offline
```

For NVIDIA, either provide the Pixeldrain single archive:

```text
lada-v0.11.0_windows_nvidia.7z
```

or the GitHub split archive:

```text
lada-v0.11.0_windows_nvidia.7z.001
lada-v0.11.0_windows_nvidia.7z.002
```

For Intel Arc:

```text
lada-v0.11.0_windows_intel.7z
```

The script validates sha256 before extracting.
