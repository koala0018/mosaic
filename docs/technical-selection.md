# Technical Selection

## Product Goal

Build a Windows-accessible local application for long video mosaic restoration.

The user workflow is:

1. Open a Windows app.
2. Select a local video, commonly around 2 hours and no more than about 3 hours.
3. Select an output folder.
4. Click start.
5. Let the app automatically detect mosaic regions and restore them.
6. Preserve original clarity, timing, frame behavior, and audio as much as possible.
7. Show a completion notification and write the final video to disk.

## Engine Choice

The first engine is [Lada](https://github.com/ladaapp/lada).

This is better than implementing our own detection/restoration model first because Lada already contains:

- automatic mosaic detection,
- restoration models,
- a CLI,
- Windows release artifacts,
- audio remuxing,
- preservation of input video width, height, FPS, and frame timestamps in its writer path.

## Application Architecture

```text
Tkinter Windows app
  -> validates input/output settings
  -> builds Lada CLI command
  -> starts background process
  -> streams logs
  -> notifies completion

CLI
  -> mosaic app
  -> mosaic lada-info
  -> mosaic process

Engine adapter
  -> finds lada-cli.exe
  -> maps quality presets
  -> builds commands
```

## Why External Process Integration

Lada is AGPL-3.0. The current repository is MIT, so the first integration keeps Lada as a separate executable.

Benefits:

- no source-code license mixing,
- easier upgrades when Lada releases new builds,
- fewer Python dependency conflicts,
- user can use the official Windows release package.

## Preset Strategy

`fast`:

- Lada detection model: `v4-fast`
- Lada restoration model: `basicvsrpp-v1.2`
- encode preset: `h264-nvidia-gpu-fast` on NVIDIA, with `h264-cpu-fast` fallback
- max clip length: `120`
- inference precision: FP16 on CUDA/XPU

`balanced`:

- detection: `v4-fast`
- restoration: `basicvsrpp-v1.2`
- encode preset: `hevc-nvidia-gpu-hq` on NVIDIA, with `h264-cpu-uhq` fallback
- max clip length: `180`
- inference precision: FP16 on CUDA/XPU

`accelerated`:

- detection: `v4-fast`
- restoration: `basicvsrpp-v1.2`
- encode preset: `hevc-nvidia-gpu-uhq` on NVIDIA, with `h264-cpu-uhq` fallback
- max clip length: `180`
- inference precision: FP16 on CUDA/XPU

`best`:

- detection: `v4-accurate`
- restoration: `basicvsrpp-v1.2`
- encode preset: `hevc-nvidia-gpu-uhq` on NVIDIA, with `h264-cpu-uhq` fallback
- max clip length: `240`
- inference precision: FP32 by default

## Long Video Risks

- 2-3 hour videos can take a very long time.
- GPU memory can be the limiting factor.
- Temporary files can be large.
- Higher temporal stability settings require more memory.
- Strong privacy masking cannot be truly recovered; the model generates plausible content.

## Near-term Engineering Work

- Query `lada-cli.exe --list-devices`.
- Query `--list-encoding-presets`.
- Parse progress output.
- Validate output duration/FPS/audio after completion.
- Add user settings persistence.
- Add queue and retry support.
