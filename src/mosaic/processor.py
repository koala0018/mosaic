"""Background process runner for long video restoration jobs."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from .lada_engine import LadaSettings, build_lada_command
from .text_encoding import decode_process_output
from .video_analyzer import analyze_restoration

LogCallback = Callable[[str], None]
DoneCallback = Callable[[int, Path], None]


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
            self.on_log("Stopping current restoration process...")
            self._process.terminate()

    def _run(self) -> None:
        self.settings.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.temporary_directory.mkdir(parents=True, exist_ok=True)
        self._log_file = self.settings.temporary_directory / "mosaic-run.log"

        try:
            returncode = self._run_once(self.settings)
            if returncode != 0 and _should_retry_on_cpu(self.settings, self._recent_output):
                self.on_log("CUDA is not available or the NVIDIA driver is too old. Retrying on CPU...")
                cpu_settings = replace(self.settings, device="cpu", fp16=False)
                returncode = self._run_once(cpu_settings)
            if self._cancelled and returncode != 0:
                self.on_log("Restoration was cancelled.")
            elif returncode == 0:
                self.on_log(f"Finished: {self.settings.output_path}")
                self._analyze_successful_output()
            else:
                self.on_log(f"Lada exited with code {returncode}.")
            self.on_done(returncode, self.settings.output_path)
        except Exception as exc:
            self.on_log(f"Failed to run restoration: {exc}")
            self.on_done(1, self.settings.output_path)
        finally:
            self._process = None

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
        self.on_log("Starting Lada engine.")
        self.on_log(" ".join(_quote_arg(arg) for arg in command))
        if settings.device == "cpu":
            self.on_log("Running on CPU. This is expected to be much slower than CUDA.")

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")

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
        output_queue: queue.Queue[str] = queue.Queue()
        reader = threading.Thread(
            target=_read_output_lines,
            args=(self._process.stdout, output_queue),
            name="lada-output-reader",
            daemon=True,
        )
        reader.start()

        started_at = time.monotonic()
        last_activity = started_at
        while self._process.poll() is None:
            try:
                clean_line = output_queue.get(timeout=1)
            except queue.Empty:
                elapsed = int(time.monotonic() - started_at)
                idle = int(time.monotonic() - last_activity)
                if idle > 0 and idle % 60 == 0:
                    self._emit_log(
                        f"Lada is still running on {settings.device}; elapsed {elapsed}s, no new output for {idle}s."
                    )
                    time.sleep(1)
                continue

            last_activity = time.monotonic()
            self._handle_process_line(settings, clean_line)

        while not output_queue.empty():
            self._handle_process_line(settings, output_queue.get())

        return self._process.wait()

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


def _quote_arg(value: str) -> str:
    if not value or any(ch.isspace() for ch in value):
        return f'"{value}"'
    return value


def _read_output_lines(stream, output_queue: queue.Queue[str]) -> None:
    for line in stream:
        text = decode_process_output(line)
        parts = text.replace("\r", "\n").splitlines()
        if not parts:
            continue
        for part in parts:
            clean = part.rstrip()
            if clean:
                output_queue.put(clean)


def _should_retry_on_cpu(settings: LadaSettings, output_lines: list[str]) -> bool:
    if settings.device == "cpu":
        return False
    text = "\n".join(output_lines).lower()
    cuda_markers = (
        "cuda initialization",
        "driver on your system is too old",
        "cuda is not available",
    )
    return any(marker in text for marker in cuda_markers)


def _should_skip_log_line(settings: LadaSettings, line: str) -> bool:
    if settings.device != "cpu":
        return False
    lower = line.lower()
    return (
        "cuda initialization" in lower
        or "driver on your system is too old" in lower
        or "return torch._c._cuda_getdevicecount() > 0" in lower
    )
