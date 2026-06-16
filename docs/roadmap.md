# Roadmap

## Phase 0: Repository foundation

- Define project scope, ethical use, and technical direction.
- Add Python package skeleton.
- Initialize Git repository and GitHub remote.

## Phase 1: Video planning

- Read video metadata with FFprobe.
- Estimate frame count, duration, resolution, bitrate, and disk usage.
- Generate chunk plan with overlap frames.
- Store job manifests for resume support.

## Phase 2: Baseline enhancement

- Extract chunks with FFmpeg.
- Add Real-ESRGAN or SwinIR adapter.
- Render a short comparison clip.
- Preserve audio track during final muxing.

## Phase 3: ROI and masks

- Add manual mask import.
- Add simple rectangle/blur-region detector.
- Support per-region enhancement strength.

## Phase 4: Long-video reliability

- Add checkpointing.
- Add crash recovery.
- Add GPU memory presets.
- Add batch queue.

## Phase 5: Local UI

- Add Gradio preview.
- Add before/after comparison.
- Add parameter presets.
- Add progress and logs.
