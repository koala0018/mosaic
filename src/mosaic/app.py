"""Windows-friendly Tkinter application for mosaic restoration."""

from __future__ import annotations

import queue
import re
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from .lada_engine import LadaSettings, default_output_path, find_lada_cli, run_lada_probe
    from .processor import RestorationProcess
except ImportError:
    from mosaic.lada_engine import LadaSettings, default_output_path, find_lada_cli, run_lada_probe
    from mosaic.processor import RestorationProcess


QUALITY_PRESETS = {
    "fast": {
        "label": "Fast",
        "encoding_preset": "h264-cpu-fast",
        "max_clip_length": 120,
        "detection_model": "v4-fast",
    },
    "balanced": {
        "label": "Balanced",
        "encoding_preset": "auto",
        "max_clip_length": 180,
        "detection_model": "v4-fast",
    },
    "best": {
        "label": "Best",
        "encoding_preset": "h264-cpu-uhq",
        "max_clip_length": 240,
        "detection_model": "v4-accurate",
    },
}

DETECTION_MODELS = ("preset", "v4-fast", "v4-accurate", "v2")
RESTORATION_MODELS = ("basicvsrpp-v1.2", "deepmosaics")


class MosaicApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("mosaic - Lada video restoration")
        self.geometry("860x640")
        self.minsize(760, 560)

        self.input_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.output_name_var = tk.StringVar()
        self.lada_cli_var = tk.StringVar(value=str(find_lada_cli() or ""))
        self.device_var = tk.StringVar(value="auto")
        self.quality_var = tk.StringVar(value="balanced")
        self.detection_model_var = tk.StringVar(value="preset")
        self.restoration_model_var = tk.StringVar(value="basicvsrpp-v1.2")
        self.detect_face_mosaics_var = tk.BooleanVar(value=False)
        self.fp16_var = tk.BooleanVar(value=False)
        self.fast_start_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Select a video and Lada CLI to begin.")
        self.progress_var = tk.StringVar(value="")
        self.progress_value_var = tk.DoubleVar(value=0)

        self._log_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._process: RestorationProcess | None = None
        self._last_progress_log_at = 0.0

        self._build_ui()
        self.after(120, self._drain_log_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)

        title = ttk.Label(root, text="Long video mosaic restoration", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 14))

        file_frame = ttk.LabelFrame(root, text="Files", padding=12)
        file_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        file_frame.columnconfigure(1, weight=1)

        self._path_row(file_frame, 0, "Video", self.input_var, self._choose_input)
        self._path_row(file_frame, 1, "Output folder", self.output_dir_var, self._choose_output_dir)
        self._path_row(file_frame, 2, "Lada CLI", self.lada_cli_var, self._choose_lada_cli)

        ttk.Label(file_frame, text="Output name").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(file_frame, textvariable=self.output_name_var).grid(row=3, column=1, sticky="ew", pady=5)

        options = ttk.LabelFrame(root, text="Processing", padding=12)
        options.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        for column in range(6):
            options.columnconfigure(column, weight=1)

        ttk.Label(options, text="Quality").grid(row=0, column=0, sticky="w")
        quality = ttk.Combobox(
            options,
            textvariable=self.quality_var,
            values=list(QUALITY_PRESETS),
            state="readonly",
            width=12,
        )
        quality.grid(row=1, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(options, text="Device").grid(row=0, column=1, sticky="w")
        ttk.Combobox(
            options,
            textvariable=self.device_var,
            values=("auto", "cuda", "xpu", "cpu"),
            width=12,
        ).grid(row=1, column=1, sticky="ew", padx=(0, 10))

        ttk.Checkbutton(options, text="Force FP16", variable=self.fp16_var).grid(
            row=1, column=2, sticky="w", padx=(0, 10)
        )
        ttk.Checkbutton(options, text="MP4 fast start", variable=self.fast_start_var).grid(
            row=1, column=3, sticky="w", padx=(0, 10)
        )
        ttk.Button(options, text="Check Lada", command=self._check_lada).grid(
            row=1, column=4, sticky="ew", padx=(0, 10)
        )
        self.start_button = ttk.Button(options, text="Start", command=self._start)
        self.start_button.grid(row=1, column=5, sticky="ew")

        ttk.Label(options, text="Detection").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(
            options,
            textvariable=self.detection_model_var,
            values=DETECTION_MODELS,
            state="readonly",
            width=14,
        ).grid(row=3, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(options, text="Restoration").grid(row=2, column=1, sticky="w", pady=(10, 0))
        ttk.Combobox(
            options,
            textvariable=self.restoration_model_var,
            values=RESTORATION_MODELS,
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky="ew", padx=(0, 10))

        ttk.Checkbutton(
            options,
            text="Detect face mosaics",
            variable=self.detect_face_mosaics_var,
        ).grid(row=3, column=2, columnspan=2, sticky="w", padx=(0, 10))

        controls = ttk.Frame(root)
        controls.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.cancel_button = ttk.Button(controls, text="Cancel", command=self._cancel, state=tk.DISABLED)
        self.cancel_button.grid(row=0, column=1, sticky="e")
        ttk.Progressbar(
            controls,
            variable=self.progress_value_var,
            maximum=100,
            mode="determinate",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        ttk.Label(controls, textvariable=self.progress_var).grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

        log_frame = ttk.LabelFrame(root, text="Log", padding=8)
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", height=16, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Button(parent, text="Browse", command=command).grid(row=row, column=2, sticky="ew", padx=(10, 0))

    def _choose_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Select video",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.mov *.avi *.webm"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        input_path = Path(path)
        self.input_var.set(str(input_path))
        if not self.output_dir_var.get():
            self.output_dir_var.set(str(input_path.parent))
        if not self.output_name_var.get():
            self.output_name_var.set(default_output_path(input_path, input_path.parent).name)

    def _choose_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_dir_var.set(path)

    def _choose_lada_cli(self) -> None:
        path = filedialog.askopenfilename(
            title="Select lada-cli.exe",
            filetypes=[("Lada CLI", "lada-cli.exe lada-cli"), ("All files", "*.*")],
        )
        if path:
            self.lada_cli_var.set(path)

    def _check_lada(self) -> None:
        try:
            result = run_lada_probe(_optional_path(self.lada_cli_var.get()), "--version")
        except Exception as exc:
            messagebox.showerror("Lada check failed", str(exc))
            return
        output = (result.stdout + result.stderr).strip() or f"Exit code: {result.returncode}"
        messagebox.showinfo("Lada", output)

    def _start(self) -> None:
        try:
            settings = self._settings_from_form()
        except ValueError as exc:
            messagebox.showwarning("Missing setting", str(exc))
            return

        self._append_log("Queued restoration job.")
        self._append_log(f"Input: {settings.input_path}")
        self._append_log(f"Output: {settings.output_path}")
        self.status_var.set("Processing. Long videos can take a long time.")
        self.progress_var.set("")
        self.progress_value_var.set(0)
        self._last_progress_log_at = 0.0
        self.start_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)

        self._process = RestorationProcess(
            settings=settings,
            on_log=lambda line: self._log_queue.put(("log", line)),
            on_done=lambda code, output: self._log_queue.put(("done", (code, output))),
        )
        self._process.start()

    def _cancel(self) -> None:
        if self._process:
            self._process.cancel()
            self.cancel_button.configure(state=tk.DISABLED)
            self.status_var.set("Stopping...")

    def _settings_from_form(self) -> LadaSettings:
        input_path = Path(self.input_var.get()).expanduser()
        output_dir = Path(self.output_dir_var.get()).expanduser()
        output_name = self.output_name_var.get().strip()
        if not input_path.is_file():
            raise ValueError("Select a valid input video.")
        if not output_dir:
            raise ValueError("Select an output folder.")
        if not output_name:
            raise ValueError("Set an output file name.")
        if not output_name.lower().endswith((".mp4", ".mkv", ".mov")):
            output_name += ".mp4"

        preset = QUALITY_PRESETS[self.quality_var.get()]
        detection_model = self.detection_model_var.get()
        if detection_model == "preset":
            detection_model = str(preset["detection_model"])
        output_path = output_dir / output_name
        return LadaSettings(
            lada_cli_path=_optional_path(self.lada_cli_var.get()),
            input_path=input_path,
            output_path=output_path,
            temporary_directory=output_dir / ".mosaic-temp",
            device=self.device_var.get().strip() or "auto",
            encoding_preset=preset["encoding_preset"],
            max_clip_length=int(preset["max_clip_length"]),
            detection_model=detection_model,
            restoration_model=self.restoration_model_var.get(),
            detect_face_mosaics=True if self.detect_face_mosaics_var.get() else None,
            fp16=True if self.fp16_var.get() else None,
            mp4_fast_start=self.fast_start_var.get(),
        )

    def _drain_log_queue(self) -> None:
        try:
            while True:
                kind, payload = self._log_queue.get_nowait()
                if kind == "log":
                    self._route_log_line(str(payload))
                elif kind == "done":
                    code, output = payload
                    self._on_done(int(code), Path(output))
        except queue.Empty:
            pass
        self.after(120, self._drain_log_queue)

    def _route_log_line(self, line: str) -> None:
        if _is_progress_line(line):
            self.progress_var.set(_compact_progress_line(line))
            percent = _extract_percent(line)
            if percent is not None:
                self.progress_value_var.set(percent)
            now = time.monotonic()
            if now - self._last_progress_log_at >= 5:
                self._append_log(_compact_progress_line(line))
                self._last_progress_log_at = now
            return
        self._append_log(line)

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _on_done(self, code: int, output_path: Path) -> None:
        self.start_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        if code == 0:
            self.status_var.set("Done.")
            self.progress_value_var.set(100)
            messagebox.showinfo("mosaic", f"Finished processing.\n\n{output_path}")
        else:
            self.status_var.set("Stopped or failed. Check the log.")
            messagebox.showerror("mosaic", "Processing did not finish successfully. Check the log.")


def _optional_path(value: str) -> Path | None:
    value = value.strip()
    return Path(value) if value else None


def _is_progress_line(line: str) -> bool:
    return "%|" in line or line.startswith("正在处理视频")


def _compact_progress_line(line: str) -> str:
    return " ".join(line.replace("\r", " ").split())


def _extract_percent(line: str) -> float | None:
    match = re.search(r"(\d{1,3})%\|", line)
    if not match:
        return None
    return max(0.0, min(100.0, float(match.group(1))))


def main() -> None:
    app = MosaicApp()
    app.mainloop()


if __name__ == "__main__":
    main()
