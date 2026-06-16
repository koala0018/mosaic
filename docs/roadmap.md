# Roadmap

## Phase 0: Repository foundation

- Define project scope, ethical use, and technical direction.
- Add Python package skeleton.
- Initialize Git repository and GitHub remote.

## Phase 1: Lada-powered MVP

- Add an external Lada CLI adapter.
- Add a Windows Tkinter desktop app.
- Select input video, output folder, and `lada-cli.exe`.
- Run long restoration jobs in a background thread.
- Stream logs into the UI.
- Support cancellation and completion pop-ups.

## Phase 2: Better Windows Product

- Package `mosaic.exe` with PyInstaller.
- Save recent paths and preferences.
- Query Lada devices and encoding presets dynamically.
- Add a real progress bar by parsing Lada progress output.
- Add disk-space estimation before starting a 2-3 hour video.

## Phase 3: Long-video Reliability

- Add job manifests.
- Add resume/retry support where possible.
- Add a batch queue.
- Add failure reports with command, exit code, and last log lines.
- Add output validation for duration, frame rate, and audio presence.

## Phase 4: Advanced Restoration Options

- Expose Lada model selection.
- Add optional face-mosaic detection toggle.
- Add custom encoder settings.
- Add preview clips for quick parameter testing.

## Phase 5: Alternative Engines

- Keep Lada as the primary free engine.
- Add optional adapters for other open-source restoration engines if they are license-compatible and useful.
- Avoid hand-rolling model inference unless an existing project cannot satisfy the workflow.
