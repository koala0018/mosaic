"""Background process runner for long video restoration jobs."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from .lada_engine import (
    LadaSettings,
    build_lada_command,
    run_lada_probe,
    supports_fp16_device,
)
from .text_encoding import decode_process_output
from .video_analyzer import analyze_restoration

LogCallback = Callable[[str], None]
DoneCallback = Callable[[int, Path], None]
_OUTPUT_DONE = object()


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    output_path: Path


class RestorationProcess:
    def __init__(
        self,
        settings: LadaSettings,
        on_log: LogCallback,
        on_done: DoneCallback,
    ) -> None:
        self.settings = settings
        self.on_log = on_log
        self.on_done = on_done
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._recent_output: list[str] = []
        self._log_file: Path | None = None
        self._cancelled = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            raise RuntimeError("A restoration process is already running.")
        self._cancelled = False
        self._thread = threading.Thread(target=self._run, name="mosaic-restoration", daemon=True)
        self._thread.start()

    def run_blocking(self) -> None:
        if self.is_running:
            raise RuntimeError("A restoration process is already running.")
        self._cancelled = False
        self._run()

    def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.poll() is None:
            self._emit_log("Stopping current restoration process...")
            self._process.terminate()

    def _run(self) -> None:
        self.settings.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.temporary_directory.mkdir(parents=True, exist_ok=True)
        self._log_file = self.settings.temporary_directory / "mosaic-run.log"
        self._emit_log(f"Log file: {self._log_file}")
        self._emit_log(f"Temporary directory: {self.settings.temporary_directory}")

        try:
            active_settings = self._prepare_settings(self.settings)
            returncode = self._run_once(active_settings)
            if returncode != 0 and _should_retry_on_cpu(active_settings, self._recent_output):
                self._emit_log("CUDA is not available or the NVIDIA driver is too old. Retrying on CPU...")
                cpu_settings = _settings_for_cpu(active_settings)
                returncode = self._run_once(cpu_settings)
            if self._cancelled and returncode != 0:
                self._emit_log("Restoration was cancelled.")
            elif returncode == 0:
                self._emit_log(f"Finished: {self.settings.output_path}")
                self._analyze_successful_output()
            else:
                self._emit_log(f"Lada exited with code {returncode}.")
                self._emit_recent_output_summary()
            self.on_done(returncode, self.settings.output_path)
        except Exception as exc:
            self._emit_log(f"Failed to run restoration: {exc}")
            for line in traceback.format_exc().rstrip().splitlines():
                self._emit_log(line)
            self.on_done(1, self.settings.output_path)
        finally:
            self._process = None

    def _prepare_settings(self, settings: LadaSettings) -> LadaSettings:
        prepared = settings
        if settings.fp16 is True and not supports_fp16_device(settings.device):
            self._emit_log(
                "Configuration warning: Force FP16 only applies when Device is explicitly "
                f"set to auto, cuda, cuda:0, or xpu. Current Device is {settings.device}, so --fp16 "
                "will not be sent to Lada."
            )
            prepared = replace(prepared, fp16=False)

        if prepared.device != "auto":
            return prepared

        self._emit_log("Preflight: checking Lada version and CUDA availability...")
        try:
            result = run_lada_probe(prepared.lada_cli_path, "--version")
        except Exception as exc:
            self._emit_log(f"Preflight check failed; continuing with selected settings: {exc}")
            return prepared

        probe_output = (result.stdout + result.stderr).strip()
        self._emit_log(f"Preflight exit code: {result.returncode}")
        for line in probe_output.splitlines():
            self._emit_log(f"Preflight: {line}")

        if _contains_cuda_problem(probe_output):
            self._emit_log(
                "CUDA preflight warning detected. Switching this run from auto to CPU "
                "and disabling FP16 to avoid a stalled CUDA fallback path."
            )
            return _settings_for_cpu(prepared)

        return prepared

    def _analyze_successful_output(self) -> None:
        self._emit_log("Analyzing output difference...")
        try:
            analysis = analyze_restoration(
                self.settings.input_path,
                self.settings.output_path,
                self.settings.temporary_directory,
                self.settings.lada_cli_path,
            )
        except Exception as exc:
            self._emit_log(f"Output analysis failed: {exc}")
            return

        if analysis is None:
            self._emit_log("Output analysis skipped: ffmpeg/ffprobe or readable frames were not available.")
            return

        self._emit_log(
            "Output difference: "
            f"mean_abs_diff={analysis.mean_abs_diff:.3f}, "
            f"changed_ratio={analysis.mean_changed_ratio:.2%}, "
            f"max_sample_diff={analysis.max_abs_diff:.3f}"
        )
        self._emit_log(analysis.conclusion)
        self._emit_log(f"Analysis report: {self.settings.temporary_directory / 'mosaic-analysis.json'}")

    def _run_once(self, settings: LadaSettings) -> int:
        self._recent_output: list[str] = []
        command = build_lada_command(settings)
        self._emit_log("Starting Lada engine.")
        self._emit_log(f"Resolved Lada CLI: {command[0]}")
        self._emit_log(f"Input path: {settings.input_path}")
        self._emit_log(f"Input exists: {settings.input_path.is_file()}")
        if settings.input_path.is_file():
            self._emit_log(f"Input size: {_format_size(settings.input_path.stat().st_size)}")
        self._emit_log(f"Output path: {settings.output_path}")
        self._emit_log(f"Output exists before run: {settings.output_path.exists()}")
        self._emit_log(f"Output directory: {settings.output_path.parent}")
        self._emit_log(
            "Settings: "
            f"device={settings.device}, "
            f"encoding={settings.encoding_preset}, "
            f"max_clip_length={settings.max_clip_length}, "
            f"detection={settings.detection_model}, "
            f"restoration={settings.restoration_model}, "
            f"fp16={settings.fp16}, "
            f"mp4_fast_start={settings.mp4_fast_start}, "
            f"detect_face_mosaics={settings.detect_face_mosaics}"
        )
        self._emit_log(" ".join(_quote_arg(arg) for arg in command))
        if settings.device == "cpu":
            self._emit_log("Running on CPU. This is expected to be much slower than CUDA.")

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("TQDM_MININTERVAL", "1")
        env.setdefault("TQDM_MINITERS", "1")
        self._emit_log("Launching Lada process and capturing stdout/stderr...")

        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            env=env,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

        assert self._process.stdout is not None
        self._emit_log(f"Lada process started. PID: {self._process.pid}")
        output_queue: queue.Queue[str | object] = queue.Queue()
        reader = threading.Thread(
            target=_read_output_records,
            args=(self._process.stdout, output_queue),
            name="lada-output-reader",
            daemon=True,
        )
        reader.start()

        started_at = time.monotonic()
        last_activity = started_at
        returncode: int | None = None
        process_exit_logged = False
        reader_finished = False
        while not (reader_finished and returncode is not None):
            try:
                item = output_queue.get(timeout=1)
            except queue.Empty:
                if returncode is None:
                    returncode = self._process.poll()
                if returncode is not None:
                    if not process_exit_logged:
                        self._emit_log(f"Lada process exited with code {returncode}. Collecting final output...")
                        process_exit_logged = True
                    continue

                elapsed = int(time.monotonic() - started_at)
                idle = int(time.monotonic() - last_activity)
                if idle > 0 and idle % 60 == 0:
                    self._emit_log(
                        f"Lada is still running on {settings.device}; elapsed {elapsed}s, no new output for {idle}s."
                    )
                    self._emit_idle_hint(settings, idle)
                    time.sleep(1)
                continue

            if item is _OUTPUT_DONE:
                reader_finished = True
                continue

            last_activity = time.monotonic()
            self._handle_process_line(settings, str(item))
            if returncode is None:
                returncode = self._process.poll()
                if returncode is not None and not process_exit_logged:
                    self._emit_log(f"Lada process exited with code {returncode}. Collecting final output...")
                    process_exit_logged = True

        while not output_queue.empty():
            item = output_queue.get()
            if item is not _OUTPUT_DONE:
                self._handle_process_line(settings, str(item))

        if returncode is None:
            returncode = self._process.wait()
        else:
            self._process.wait()
        reader.join(timeout=2)
        self._emit_log(f"Lada process finished with exit code {returncode}.")
        return returncode

    def _handle_process_line(self, settings: LadaSettings, clean_line: str) -> None:
        if _should_skip_log_line(settings, clean_line):
            return
        if clean_line:
            self._recent_output.append(clean_line)
            self._recent_output = self._recent_output[-80:]
            self._emit_log(clean_line)

    def _emit_log(self, line: str) -> None:
        self.on_log(line)
        if self._log_file is not None:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with self._log_file.open("a", encoding="utf-8") as log:
                log.write(f"[{timestamp}] {line}\n")

    def _emit_recent_output_summary(self) -> None:
        if not self._recent_output:
            self._emit_log("No Lada output was captured before failure.")
            return
        self._emit_log("Recent Lada output before failure:")
        for line in self._recent_output[-20:]:
            self._emit_log(f"  {line}")

    def _emit_idle_hint(self, settings: LadaSettings, idle: int) -> None:
        if idle not in {60, 180, 300, 600}:
            return
        if settings.device == "cpu":
            self._emit_log(
                "Hint: CPU processing can be very slow. If it remains at 0 frames, "
                "try Quality=fast or balanced, uncheck Force FP16, or update the NVIDIA driver and use CUDA."
            )
        elif settings.device == "auto" and _contains_cuda_problem("\n".join(self._recent_output)):
            self._emit_log(
                "Hint: CUDA initialization warnings were seen while Device=auto. "
                "Use Device=cpu for this machine, or update the NVIDIA driver before using CUDA/FP16."
            )


def _quote_arg(value: str) -> str:
    if not value or any(ch.isspace() for ch in value):
        return f'"{value}"'
    return value


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{size} B"
        value /= 1024
    return f"{size} B"


def _read_output_records(stream, output_queue: queue.Queue[str | object]) -> None:
    pending = bytearray()
    try:
        while True:
            chunk = stream.read(1)
            if not chunk:
                break
            byte = chunk[0]
            if byte in (10, 13):
                _queue_decoded_record(output_queue, bytes(pending))
                pending.clear()
                continue
            pending.append(byte)
        _queue_decoded_record(output_queue, bytes(pending))
    finally:
        output_queue.put(_OUTPUT_DONE)


def _queue_decoded_record(output_queue: queue.Queue[str | object], data: bytes) -> None:
    if not data:
        return
    text = decode_process_output(data)
    for part in text.splitlines():
        clean = part.rstrip()
        if clean:
            output_queue.put(clean)


def _should_retry_on_cpu(settings: LadaSettings, output_lines: list[str]) -> bool:
    if settings.device == "cpu":
        return False
    text = "\n".join(output_lines).lower()
    return _contains_cuda_problem(text)


def _settings_for_cpu(settings: LadaSettings) -> LadaSettings:
    encoding_preset = settings.encoding_preset
    if "nvidia-gpu" in encoding_preset:
        encoding_preset = (
            "h264-cpu-uhq"
            if encoding_preset.endswith(("-hq", "-uhq"))
            else "h264-cpu-fast"
        )
    return replace(settings, device="cpu", fp16=False, encoding_preset=encoding_preset)


def _contains_cuda_problem(text: str) -> bool:
    lower = text.lower()
    cuda_markers = (
        "cuda initialization",
        "driver on your system is too old",
        "cuda is not available",
    )
    return any(marker in lower for marker in cuda_markers)


def _should_skip_log_line(settings: LadaSettings, line: str) -> bool:
    return False
