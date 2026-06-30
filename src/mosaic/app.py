"""Windows-friendly Tkinter application for mosaic restoration."""

from __future__ import annotations

import queue
import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from .beauty_filter import (
        BeautyFilterProcess,
        BeautyFilterSettings,
        check_beauty_dependencies,
        default_beauty_output_path,
    )
    from .lada_engine import (
        LadaSettings,
        default_output_path,
        find_lada_cli,
        run_lada_probe,
        supports_fp16_device,
    )
    from .processor import RestorationProcess
except ImportError:
    from mosaic.beauty_filter import (
        BeautyFilterProcess,
        BeautyFilterSettings,
        check_beauty_dependencies,
        default_beauty_output_path,
    )
    from mosaic.lada_engine import (
        LadaSettings,
        default_output_path,
        find_lada_cli,
        run_lada_probe,
        supports_fp16_device,
    )
    from mosaic.processor import RestorationProcess


QUALITY_PRESETS = {
    "fast": {
        "label": "Fast",
        "encoding_preset": "h264-nvidia-gpu-fast",
        "max_clip_length": 120,
        "detection_model": "v4-fast",
        "fp16": True,
    },
    "balanced": {
        "label": "Balanced",
        "encoding_preset": "hevc-nvidia-gpu-hq",
        "max_clip_length": 180,
        "detection_model": "v4-fast",
        "fp16": True,
    },
    "accelerated": {
        "label": "High quality accelerated",
        "encoding_preset": "hevc-nvidia-gpu-uhq",
        "max_clip_length": 180,
        "detection_model": "v4-fast",
        "fp16": True,
    },
    "best": {
        "label": "Best",
        "encoding_preset": "hevc-nvidia-gpu-uhq",
        "max_clip_length": 240,
        "detection_model": "v4-accurate",
        "fp16": False,
    },
}

DETECTION_MODELS = ("preset", "v4-fast", "v4-accurate", "v2")
RESTORATION_MODELS = ("basicvsrpp-v1.2", "deepmosaics")


@dataclass
class BatchJob:
    settings: LadaSettings | BeautyFilterSettings
    tree_id: str
    status: str = "Waiting"
    progress: float = 0.0


class MosaicApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("mosaic - Lada video restoration")
        self.geometry("980x780")
        self.minsize(820, 680)

        self.input_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.output_name_var = tk.StringVar()
        self.process_mode_var = tk.StringVar(value="restore")
        self.lada_cli_var = tk.StringVar(value=str(find_lada_cli() or ""))
        self.device_var = tk.StringVar(value="cuda:0")
        self.quality_var = tk.StringVar(value="accelerated")
        self.detection_model_var = tk.StringVar(value="preset")
        self.restoration_model_var = tk.StringVar(value="basicvsrpp-v1.2")
        self.detect_face_mosaics_var = tk.BooleanVar(value=False)
        self.fp16_var = tk.BooleanVar(value=True)
        self.fast_start_var = tk.BooleanVar(value=False)
        self.beauty_strength_var = tk.IntVar(value=55)
        self.beauty_preserve_audio_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Select a video and Lada CLI to begin.")
        self.progress_var = tk.StringVar(value="")
        self.progress_value_var = tk.DoubleVar(value=0)

        self._log_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._process: RestorationProcess | BeautyFilterProcess | None = None
        self._selected_inputs: list[Path] = []
        self._batch_jobs: list[BatchJob] = []
        self._current_job_index = -1
        self._batch_cancelled = False
        self._completed_jobs = 0
        self._failed_jobs = 0
        self._tree_input_paths: dict[str, Path] = {}
        self._restore_widgets: list[tk.Widget] = []
        self._beauty_widgets: list[tk.Widget] = []
        self._widget_states: dict[str, str] = {}

        self._build_ui()
        self.after(120, self._drain_log_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        title = ttk.Label(root, text="Long video mosaic restoration", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 14))

        file_frame = ttk.LabelFrame(root, text="Files", padding=12)
        file_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        file_frame.columnconfigure(1, weight=1)

        self._path_row(
            file_frame, 0, "Videos", self.input_var, self._choose_input, button_text="Add videos"
        )
        ttk.Button(file_frame, text="Clear", command=self._clear_inputs).grid(
            row=0, column=3, sticky="ew", padx=(8, 0)
        )
        self._path_row(file_frame, 1, "Output folder", self.output_dir_var, self._choose_output_dir)
        self._restore_widgets.extend(
            self._path_row(file_frame, 2, "Lada CLI", self.lada_cli_var, self._choose_lada_cli)
        )

        ttk.Label(file_frame, text="Output name (single video)").grid(
            row=3, column=0, sticky="w", padx=(0, 10), pady=5
        )
        ttk.Entry(file_frame, textvariable=self.output_name_var).grid(
            row=3, column=1, sticky="ew", pady=5
        )

        ttk.Label(file_frame, text="Task").grid(row=4, column=0, sticky="w", padx=(0, 10), pady=5)
        task_frame = ttk.Frame(file_frame)
        task_frame.grid(row=4, column=1, columnspan=2, sticky="w", pady=5)
        ttk.Radiobutton(
            task_frame,
            text="Restore mosaic",
            value="restore",
            variable=self.process_mode_var,
            command=self._on_mode_changed,
        ).grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Radiobutton(
            task_frame,
            text="Beauty whitening",
            value="beauty",
            variable=self.process_mode_var,
            command=self._on_mode_changed,
        ).grid(row=0, column=1, sticky="w")

        options = ttk.LabelFrame(root, text="Processing", padding=12)
        options.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        for column in range(6):
            options.columnconfigure(column, weight=1)

        quality_label = ttk.Label(options, text="Quality")
        quality_label.grid(row=0, column=0, sticky="w")
        quality = ttk.Combobox(
            options,
            textvariable=self.quality_var,
            values=list(QUALITY_PRESETS),
            state="readonly",
            width=12,
        )
        quality.bind("<<ComboboxSelected>>", self._on_quality_changed)
        quality.grid(row=1, column=0, sticky="ew", padx=(0, 10))

        device_label = ttk.Label(options, text="Device")
        device_label.grid(row=0, column=1, sticky="w")
        device = ttk.Combobox(
            options,
            textvariable=self.device_var,
            values=("auto", "cuda:0", "cuda", "xpu", "cpu"),
            width=12,
        )
        device.grid(row=1, column=1, sticky="ew", padx=(0, 10))

        fp16 = ttk.Checkbutton(
            options, text="FP16 (faster, slight quality loss)", variable=self.fp16_var
        )
        fp16.grid(row=1, column=2, sticky="w", padx=(0, 10))
        fast_start = ttk.Checkbutton(options, text="MP4 fast start", variable=self.fast_start_var)
        fast_start.grid(row=1, column=3, sticky="w", padx=(0, 10))
        check_lada = ttk.Button(options, text="Check Lada", command=self._check_lada)
        check_lada.grid(row=1, column=4, sticky="ew", padx=(0, 10))
        self.start_button = ttk.Button(options, text="Start queue", command=self._start)
        self.start_button.grid(row=1, column=5, sticky="ew")

        detection_label = ttk.Label(options, text="Detection")
        detection_label.grid(row=2, column=0, sticky="w", pady=(10, 0))
        detection = ttk.Combobox(
            options,
            textvariable=self.detection_model_var,
            values=DETECTION_MODELS,
            state="readonly",
            width=14,
        )
        detection.grid(row=3, column=0, sticky="ew", padx=(0, 10))

        restoration_label = ttk.Label(options, text="Restoration")
        restoration_label.grid(row=2, column=1, sticky="w", pady=(10, 0))
        restoration = ttk.Combobox(
            options,
            textvariable=self.restoration_model_var,
            values=RESTORATION_MODELS,
            state="readonly",
            width=18,
        )
        restoration.grid(row=3, column=1, sticky="ew", padx=(0, 10))

        detect_face = ttk.Checkbutton(
            options,
            text="Detect face mosaics",
            variable=self.detect_face_mosaics_var,
        )
        detect_face.grid(row=3, column=2, columnspan=2, sticky="w", padx=(0, 10))

        self._restore_widgets.extend(
            [
                quality_label,
                quality,
                device_label,
                device,
                fp16,
                fast_start,
                check_lada,
                detection_label,
                detection,
                restoration_label,
                restoration,
                detect_face,
            ]
        )

        beauty_label = ttk.Label(options, text="Beauty intensity")
        beauty_label.grid(row=4, column=0, sticky="w", pady=(12, 0))
        beauty_strength = ttk.Scale(
            options,
            from_=10,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.beauty_strength_var,
        )
        beauty_strength.grid(row=5, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        beauty_value = ttk.Label(options, textvariable=self.beauty_strength_var, width=4)
        beauty_value.grid(row=5, column=2, sticky="w", padx=(0, 10))
        preserve_audio = ttk.Checkbutton(
            options,
            text="Preserve original audio",
            variable=self.beauty_preserve_audio_var,
        )
        preserve_audio.grid(row=5, column=3, columnspan=3, sticky="w", padx=(0, 10))
        self._beauty_widgets.extend([beauty_label, beauty_strength, beauty_value, preserve_audio])

        work_pane = ttk.Panedwindow(root, orient=tk.VERTICAL)
        work_pane.grid(row=3, column=0, sticky="nsew", pady=(0, 10))

        queue_frame = ttk.LabelFrame(work_pane, text="Task queue", padding=8)
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(1, weight=1)
        queue_actions = ttk.Frame(queue_frame)
        queue_actions.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        queue_actions.columnconfigure(0, weight=1)
        ttk.Button(
            queue_actions, text="Remove selected", command=self._remove_selected_inputs
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(queue_actions, text="Clear queue", command=self._clear_inputs).grid(
            row=0, column=2
        )
        self.task_tree = ttk.Treeview(
            queue_frame,
            columns=("file", "status", "progress", "output"),
            show="headings",
            height=5,
        )
        self.task_tree.heading("file", text="Video")
        self.task_tree.heading("status", text="Status")
        self.task_tree.heading("progress", text="Progress")
        self.task_tree.heading("output", text="Output")
        self.task_tree.column("file", width=220, minwidth=140)
        self.task_tree.column("status", width=90, minwidth=80, anchor=tk.CENTER)
        self.task_tree.column("progress", width=90, minwidth=75, anchor=tk.CENTER)
        self.task_tree.column("output", width=390, minwidth=180)
        self.task_tree.grid(row=1, column=0, sticky="nsew")
        queue_scrollbar = ttk.Scrollbar(queue_frame, command=self.task_tree.yview)
        queue_scrollbar.grid(row=1, column=1, sticky="ns")
        self.task_tree.configure(yscrollcommand=queue_scrollbar.set)
        work_pane.add(queue_frame, weight=1)

        controls = ttk.Frame(root)
        controls.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.cancel_button = ttk.Button(
            controls, text="Cancel queue", command=self._cancel, state=tk.DISABLED
        )
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

        log_frame = ttk.LabelFrame(work_pane, text="Execution log", padding=8)
        log_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)

        log_actions = ttk.Frame(log_frame)
        log_actions.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        log_actions.columnconfigure(0, weight=1)
        ttk.Button(log_actions, text="Copy Log", command=self._copy_log).grid(
            row=0, column=1, sticky="e"
        )

        self.log_text = tk.Text(log_frame, wrap="word", height=8, undo=False)
        self.log_text.grid(row=1, column=0, sticky="nsew")
        self.log_text.bind("<KeyPress>", self._block_log_edit)
        self.log_text.bind("<Control-a>", self._select_all_log)
        self.log_text.bind("<Control-A>", self._select_all_log)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        work_pane.add(log_frame, weight=2)
        self._on_mode_changed()
        self.status_var.set("Select a video and Lada CLI to begin.")

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command,
        button_text: str = "Browse",
    ) -> list[tk.Widget]:
        text_label = ttk.Label(parent, text=label)
        text_label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        button = ttk.Button(parent, text=button_text, command=command)
        button.grid(row=row, column=2, sticky="ew", padx=(10, 0))
        return [text_label, entry, button]

    def _choose_input(self) -> None:
        if self._process and self._process.is_running:
            messagebox.showinfo("mosaic", "The current queue is still processing.")
            return
        paths = filedialog.askopenfilenames(
            title="Select videos",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.mov *.avi *.webm"),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return
        self._selected_inputs = _append_unique_paths(
            self._selected_inputs, [Path(path) for path in paths]
        )
        input_path = self._selected_inputs[0]
        if len(self._selected_inputs) == 1:
            self.input_var.set(str(input_path))
        else:
            self.input_var.set(f"{len(self._selected_inputs)} videos selected")
        if not self.output_dir_var.get():
            self.output_dir_var.set(str(input_path.parent))
        if len(self._selected_inputs) == 1:
            self.output_name_var.set(self._default_output_path(input_path, input_path.parent).name)
        else:
            self.output_name_var.set("")
        self._preview_selected_jobs()

    def _remove_selected_inputs(self) -> None:
        if self._process and self._process.is_running:
            messagebox.showinfo("mosaic", "The current queue is still processing.")
            return
        selected_paths = {
            self._tree_input_paths[item_id]
            for item_id in self.task_tree.selection()
            if item_id in self._tree_input_paths
        }
        if not selected_paths:
            return
        self._selected_inputs = [
            path for path in self._selected_inputs if path not in selected_paths
        ]
        self._sync_input_summary()
        self._preview_selected_jobs()

    def _clear_inputs(self) -> None:
        if self._process and self._process.is_running:
            messagebox.showinfo("mosaic", "The current queue is still processing.")
            return
        self._selected_inputs = []
        self.input_var.set("")
        self.output_name_var.set("")
        self._preview_selected_jobs()

    def _sync_input_summary(self) -> None:
        if not self._selected_inputs:
            self.input_var.set("")
            self.output_name_var.set("")
        elif len(self._selected_inputs) == 1:
            input_path = self._selected_inputs[0]
            self.input_var.set(str(input_path))
            if self.output_dir_var.get().strip():
                output_dir = Path(self.output_dir_var.get()).expanduser()
                self.output_name_var.set(self._default_output_path(input_path, output_dir).name)
        else:
            self.input_var.set(f"{len(self._selected_inputs)} videos selected")
            self.output_name_var.set("")

    def _choose_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_dir_var.set(path)
            self._preview_selected_jobs()

    def _choose_lada_cli(self) -> None:
        path = filedialog.askopenfilename(
            title="Select lada-cli.exe",
            filetypes=[("Lada CLI", "lada-cli.exe lada-cli"), ("All files", "*.*")],
        )
        if path:
            self.lada_cli_var.set(path)

    def _check_lada(self) -> None:
        self._append_log("Checking Lada CLI...")
        try:
            result = run_lada_probe(_optional_path(self.lada_cli_var.get()), "--version")
        except Exception as exc:
            self._append_log(f"Lada check failed: {exc}")
            messagebox.showerror("Lada check failed", str(exc))
            return
        output = (result.stdout + result.stderr).strip() or f"Exit code: {result.returncode}"
        self._append_log(f"Lada check exit code: {result.returncode}")
        for line in output.splitlines():
            self._append_log(line)
        messagebox.showinfo("Lada", output)

    def _start(self) -> None:
        try:
            settings_list = self._settings_list_from_form()
        except ValueError as exc:
            self._append_log(f"Cannot start processing: {exc}")
            messagebox.showwarning("Missing setting", str(exc))
            return

        first_settings = settings_list[0]
        if isinstance(first_settings, LadaSettings) and not self._confirm_lada_setting_warnings(
            first_settings
        ):
            self.status_var.set("Start cancelled.")
            return

        task_name = (
            "beauty filter" if isinstance(first_settings, BeautyFilterSettings) else "restoration"
        )
        if isinstance(first_settings, BeautyFilterSettings):
            available, message = check_beauty_dependencies()
            if not available:
                self._append_log(message)
                messagebox.showerror("Beauty filter dependency missing", message)
                return

        self._batch_jobs = []
        self.task_tree.delete(*self.task_tree.get_children())
        self._tree_input_paths.clear()
        for index, settings in enumerate(settings_list, start=1):
            tree_id = self.task_tree.insert(
                "",
                tk.END,
                values=(settings.input_path.name, "Waiting", "0%", str(settings.output_path)),
            )
            self._tree_input_paths[tree_id] = settings.input_path
            self._batch_jobs.append(BatchJob(settings=settings, tree_id=tree_id))
            self._append_log(
                f"Queued {task_name} job {index}/{len(settings_list)}: {settings.input_path}"
            )
        self._current_job_index = -1
        self._batch_cancelled = False
        self._completed_jobs = 0
        self._failed_jobs = 0
        self.status_var.set(f"Queue ready: {len(self._batch_jobs)} video(s).")
        self.progress_var.set("")
        self.progress_value_var.set(0)
        self.start_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)

        self._start_next_job()

    def _start_next_job(self) -> None:
        if self._batch_cancelled:
            self._finish_batch()
            return
        self._current_job_index += 1
        if self._current_job_index >= len(self._batch_jobs):
            self._finish_batch()
            return

        job = self._batch_jobs[self._current_job_index]
        job.status = "Processing"
        self._update_job_row(job)
        position = self._current_job_index + 1
        total = len(self._batch_jobs)
        self.status_var.set(f"Processing {position}/{total}: {job.settings.input_path.name}")
        self.progress_var.set(f"Current video 0% | Overall {self._overall_percent():.0f}%")
        self._append_log(f"Starting job {position}/{total}: {job.settings.input_path}")
        self._append_log(f"Output: {job.settings.output_path}")

        callback = lambda code, output: self._log_queue.put(("done", (code, output)))
        log_callback = lambda line: self._log_queue.put(("log", line))
        if isinstance(job.settings, BeautyFilterSettings):
            self._process = BeautyFilterProcess(job.settings, log_callback, callback)
        else:
            self._process = RestorationProcess(job.settings, log_callback, callback)
        try:
            self._process.start()
        except Exception as exc:
            self._append_log(f"Failed to start job: {exc}")
            self._on_done(1, job.settings.output_path)

    def _confirm_lada_setting_warnings(self, settings: LadaSettings) -> bool:
        warnings: list[str] = []
        if settings.fp16 is True and not supports_fp16_device(settings.device):
            warnings.append(
                "Force FP16 only applies when Device is auto, cuda, cuda:0, or xpu. "
                f"Current Device is {settings.device}, so --fp16 will not be sent to Lada."
            )

        if not warnings:
            return True

        message = "\n\n".join(warnings)
        for line in message.splitlines():
            self._append_log(f"Configuration warning: {line}")
        return messagebox.askyesno(
            "Configuration warning",
            f"{message}\n\nContinue with FP16 disabled for this run?",
        )

    def _on_quality_changed(self, _event: tk.Event | None = None) -> None:
        preset = QUALITY_PRESETS[self.quality_var.get()]
        self.fp16_var.set(bool(preset["fp16"]))
        self._preview_selected_jobs()

    def _cancel(self) -> None:
        self._batch_cancelled = True
        if self._process:
            self._process.cancel()
        for job in self._batch_jobs[self._current_job_index + 1 :]:
            job.status = "Cancelled"
            self._update_job_row(job)
        self.cancel_button.configure(state=tk.DISABLED)
        self.status_var.set("Stopping current task and cancelling queue...")

    def _settings_from_form(self) -> LadaSettings | BeautyFilterSettings:
        if self.process_mode_var.get() == "beauty":
            return self._beauty_settings_from_form()
        return self._lada_settings_from_form()

    def _settings_list_from_form(self) -> list[LadaSettings | BeautyFilterSettings]:
        inputs = self._input_paths_from_form()
        output_dir_text = self.output_dir_var.get().strip()
        if not output_dir_text:
            raise ValueError("Select an output folder.")
        output_dir = Path(output_dir_text).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        reserved: set[Path] = set()
        settings_list: list[LadaSettings | BeautyFilterSettings] = []
        for input_path in inputs:
            if len(inputs) == 1 and self.output_name_var.get().strip():
                output_name = self.output_name_var.get().strip()
                if not output_name.lower().endswith((".mp4", ".mkv", ".mov")):
                    output_name += ".mp4"
                output_path = output_dir / output_name
            else:
                output_path = self._default_output_path(input_path, output_dir)
                output_path = _available_output_path(output_path, reserved)
            reserved.add(output_path.resolve())
            settings_list.append(self._settings_for_paths(input_path, output_dir, output_path))
        return settings_list

    def _input_paths_from_form(self) -> list[Path]:
        if self._selected_inputs:
            inputs = self._selected_inputs
        else:
            value = self.input_var.get().strip()
            inputs = [Path(value).expanduser()] if value else []
        if not inputs or any(not path.is_file() for path in inputs):
            raise ValueError("Select one or more valid input videos.")
        return inputs

    def _settings_for_paths(
        self, input_path: Path, output_dir: Path, output_path: Path
    ) -> LadaSettings | BeautyFilterSettings:
        if self.process_mode_var.get() == "beauty":
            return BeautyFilterSettings(
                input_path=input_path,
                output_path=output_path,
                temporary_directory=output_dir / ".mosaic-temp",
                strength=int(self.beauty_strength_var.get()),
                preserve_audio=self.beauty_preserve_audio_var.get(),
            )
        preset = QUALITY_PRESETS[self.quality_var.get()]
        detection_model = self.detection_model_var.get()
        if detection_model == "preset":
            detection_model = str(preset["detection_model"])
        return LadaSettings(
            lada_cli_path=_optional_path(self.lada_cli_var.get()),
            input_path=input_path,
            output_path=output_path,
            temporary_directory=output_dir / ".mosaic-temp",
            device=self.device_var.get().strip() or "auto",
            encoding_preset=_encoding_preset_for_device(
                str(preset["encoding_preset"]), self.device_var.get()
            ),
            max_clip_length=int(preset["max_clip_length"]),
            detection_model=detection_model,
            restoration_model=self.restoration_model_var.get(),
            detect_face_mosaics=True if self.detect_face_mosaics_var.get() else None,
            fp16=self.fp16_var.get(),
            mp4_fast_start=self.fast_start_var.get(),
        )

    def _lada_settings_from_form(self) -> LadaSettings:
        input_path, output_dir, output_path = self._common_paths_from_form()
        preset = QUALITY_PRESETS[self.quality_var.get()]
        detection_model = self.detection_model_var.get()
        if detection_model == "preset":
            detection_model = str(preset["detection_model"])
        return LadaSettings(
            lada_cli_path=_optional_path(self.lada_cli_var.get()),
            input_path=input_path,
            output_path=output_path,
            temporary_directory=output_dir / ".mosaic-temp",
            device=self.device_var.get().strip() or "auto",
            encoding_preset=_encoding_preset_for_device(
                str(preset["encoding_preset"]), self.device_var.get()
            ),
            max_clip_length=int(preset["max_clip_length"]),
            detection_model=detection_model,
            restoration_model=self.restoration_model_var.get(),
            detect_face_mosaics=True if self.detect_face_mosaics_var.get() else None,
            fp16=self.fp16_var.get(),
            mp4_fast_start=self.fast_start_var.get(),
        )

    def _beauty_settings_from_form(self) -> BeautyFilterSettings:
        input_path, output_dir, output_path = self._common_paths_from_form()
        return BeautyFilterSettings(
            input_path=input_path,
            output_path=output_path,
            temporary_directory=output_dir / ".mosaic-temp",
            strength=int(self.beauty_strength_var.get()),
            preserve_audio=self.beauty_preserve_audio_var.get(),
        )

    def _common_paths_from_form(self) -> tuple[Path, Path, Path]:
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
        return input_path, output_dir, output_dir / output_name

    def _default_output_path(self, input_path: Path, output_dir: Path) -> Path:
        if self.process_mode_var.get() == "beauty":
            return default_beauty_output_path(input_path, output_dir)
        return default_output_path(input_path, output_dir)

    def _on_mode_changed(self) -> None:
        input_value = self.input_var.get().strip()
        output_dir_value = self.output_dir_var.get().strip()
        if len(self._selected_inputs) == 1 and output_dir_value:
            input_path = self._selected_inputs[0]
            output_dir = Path(output_dir_value)
            current_name = self.output_name_var.get().strip()
            restore_name = default_output_path(input_path, output_dir).name
            beauty_name = default_beauty_output_path(input_path, output_dir).name
            if current_name in {"", restore_name, beauty_name}:
                self.output_name_var.set(self._default_output_path(input_path, output_dir).name)
        elif not self._selected_inputs and input_value and output_dir_value:
            input_path = Path(input_value)
            output_dir = Path(output_dir_value)
            current_name = self.output_name_var.get().strip()
            restore_name = default_output_path(input_path, output_dir).name
            beauty_name = default_beauty_output_path(input_path, output_dir).name
            if current_name in {"", restore_name, beauty_name}:
                self.output_name_var.set(self._default_output_path(input_path, output_dir).name)
        if self.process_mode_var.get() == "beauty":
            self._set_widgets_enabled(self._restore_widgets, False)
            self._set_widgets_enabled(self._beauty_widgets, True)
            self.status_var.set("Beauty whitening uses OpenCV and writes a local output video.")
        else:
            self._set_widgets_enabled(self._restore_widgets, True)
            self._set_widgets_enabled(self._beauty_widgets, False)
            self.status_var.set("Mosaic restoration uses the configured Lada CLI.")
        self._preview_selected_jobs()

    def _set_widgets_enabled(self, widgets: list[tk.Widget], enabled: bool) -> None:
        for widget in widgets:
            try:
                key = str(widget)
                if enabled:
                    widget.configure(state=self._widget_states.pop(key, tk.NORMAL))
                else:
                    self._widget_states.setdefault(key, str(widget.cget("state")))
                    widget.configure(state=tk.DISABLED)
            except tk.TclError:
                pass

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
            compact_line = _compact_progress_line(line)
            self.progress_var.set(compact_line)
            percent = _extract_percent(line)
            if percent is not None:
                if 0 <= self._current_job_index < len(self._batch_jobs):
                    job = self._batch_jobs[self._current_job_index]
                    job.progress = percent
                    self._update_job_row(job)
                overall = self._overall_percent()
                self.progress_value_var.set(overall)
                self.progress_var.set(f"Current video {percent:.0f}% | Overall {overall:.0f}%")
            self._append_log(compact_line)
            return
        self._append_log(line)

    def _append_log(self, line: str) -> None:
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)

    def _copy_log(self) -> None:
        log_text = self.log_text.get("1.0", tk.END).strip()
        self.clipboard_clear()
        self.clipboard_append(log_text)
        self.status_var.set("Log copied to clipboard.")

    def _select_all_log(self, _event: tk.Event) -> str:
        self.log_text.tag_add(tk.SEL, "1.0", tk.END)
        self.log_text.mark_set(tk.INSERT, "1.0")
        self.log_text.see(tk.INSERT)
        return "break"

    def _block_log_edit(self, event: tk.Event) -> str | None:
        if event.state & 0x4 and event.keysym.lower() in {"a", "c"}:
            return None
        return "break"

    def _on_done(self, code: int, output_path: Path) -> None:
        if not (0 <= self._current_job_index < len(self._batch_jobs)):
            return
        job = self._batch_jobs[self._current_job_index]
        if code == 0:
            job.status = "Completed"
            job.progress = 100
            self._completed_jobs += 1
            self._append_log(f"Completed job: {output_path}")
        else:
            job.status = "Cancelled" if self._batch_cancelled or code == 130 else "Failed"
            if job.status == "Failed":
                self._failed_jobs += 1
            self._append_log(
                f"Job {job.status.lower()} (exit code {code}): {job.settings.input_path}"
            )
        self._update_job_row(job)
        self.progress_value_var.set(self._overall_percent())
        self.after(150, self._start_next_job)

    def _update_job_row(self, job: BatchJob) -> None:
        self.task_tree.item(
            job.tree_id,
            values=(
                job.settings.input_path.name,
                job.status,
                f"{job.progress:.0f}%",
                str(job.settings.output_path),
            ),
        )
        self.task_tree.see(job.tree_id)

    def _overall_percent(self) -> float:
        if not self._batch_jobs:
            return 0.0
        return sum(job.progress for job in self._batch_jobs) / len(self._batch_jobs)

    def _finish_batch(self) -> None:
        self._process = None
        self.start_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        total = len(self._batch_jobs)
        cancelled = sum(job.status == "Cancelled" for job in self._batch_jobs)
        summary = (
            f"Queue finished: {self._completed_jobs} completed, "
            f"{self._failed_jobs} failed, {cancelled} cancelled."
        )
        self.status_var.set(summary)
        self.progress_var.set(summary)
        self.progress_value_var.set(self._overall_percent())
        self._append_log(summary)
        if self._failed_jobs:
            messagebox.showwarning("mosaic", summary + "\n\nCheck the log for failed tasks.")
        elif self._batch_cancelled:
            messagebox.showinfo("mosaic", summary)
        elif total:
            messagebox.showinfo("mosaic", summary)

    def _preview_selected_jobs(self) -> None:
        self.task_tree.delete(*self.task_tree.get_children())
        self._tree_input_paths.clear()
        output_dir_text = self.output_dir_var.get().strip()
        output_dir = Path(output_dir_text) if output_dir_text else None
        for path in self._selected_inputs:
            output = self._default_output_path(path, output_dir) if output_dir else ""
            tree_id = self.task_tree.insert(
                "", tk.END, values=(path.name, "Ready", "0%", str(output))
            )
            self._tree_input_paths[tree_id] = path


def _optional_path(value: str) -> Path | None:
    value = value.strip()
    return Path(value) if value else None


def _available_output_path(path: Path, reserved: set[Path]) -> Path:
    candidate = path
    number = 2
    while candidate.exists() or candidate.resolve() in reserved:
        candidate = path.with_name(f"{path.stem}-{number}{path.suffix}")
        number += 1
    return candidate


def _append_unique_paths(existing: list[Path], additions: list[Path]) -> list[Path]:
    result = list(existing)
    known = {path.resolve() for path in existing}
    for path in additions:
        resolved = path.resolve()
        if resolved not in known:
            known.add(resolved)
            result.append(path)
    return result


def _encoding_preset_for_device(preset: str, device: str) -> str:
    if device.strip().lower() == "cpu" and "nvidia-gpu" in preset:
        return "h264-cpu-uhq" if preset.endswith(("-hq", "-uhq")) else "h264-cpu-fast"
    return preset


def _is_progress_line(line: str) -> bool:
    return (
        "%|" in line
        or line.startswith("正在处理视频")
        or line.startswith("姝ｅ湪澶勭悊瑙嗛")
        or line.lower().startswith("processing video")
    )


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
