"""Background process runner for long video restoration jobs."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .lada_engine import LadaSettings, build_lada_command
from .text_encoding import decode_process_output

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

        try:
            command = build_lada_command(self.settings)
            self.on_log("Starting Lada engine.")
            self.on_log(" ".join(_quote_arg(arg) for arg in command))

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
                bufsize=1,
                env=env,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )

            assert self._process.stdout is not None
            for line in self._process.stdout:
                clean_line = decode_process_output(line).rstrip()
                if clean_line:
                    self.on_log(clean_line)

            returncode = self._process.wait()
            if self._cancelled and returncode != 0:
                self.on_log("Restoration was cancelled.")
            elif returncode == 0:
                self.on_log(f"Finished: {self.settings.output_path}")
            else:
                self.on_log(f"Lada exited with code {returncode}.")
            self.on_done(returncode, self.settings.output_path)
        except Exception as exc:
            self.on_log(f"Failed to run restoration: {exc}")
            self.on_done(1, self.settings.output_path)
        finally:
            self._process = None


def _quote_arg(value: str) -> str:
    if not value or any(ch.isspace() for ch in value):
        return f'"{value}"'
    return value
