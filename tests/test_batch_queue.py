from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from mosaic.app import (
    QUALITY_PRESETS,
    MosaicApp,
    _append_unique_paths,
    _available_output_path,
    _encoding_preset_for_device,
    _extract_percent,
)
from mosaic.beauty_filter import _beauty_worker_count
from mosaic.lada_engine import LadaSettings, build_lada_command
from mosaic.processor import _settings_for_cpu


class BatchQueueTests(unittest.TestCase):
    def test_beauty_worker_count_limits_high_resolution_memory(self) -> None:
        self.assertEqual(_beauty_worker_count(1280, 720, logical_cpus=16), 8)
        self.assertEqual(_beauty_worker_count(1920, 1080, logical_cpus=16), 6)
        self.assertEqual(_beauty_worker_count(3840, 2160, logical_cpus=16), 4)

    def test_available_output_path_avoids_reserved_names(self) -> None:
        path = Path("clip.restored.mp4")
        reserved = {path.resolve(), path.with_name("clip.restored-2.mp4").resolve()}

        result = _available_output_path(path, reserved)

        self.assertEqual(result.name, "clip.restored-3.mp4")

    def test_extract_percent(self) -> None:
        self.assertEqual(_extract_percent("Processing video 42%| frame 5/12"), 42)
        self.assertIsNone(_extract_percent("Starting video processing"))

    def test_repeated_video_selection_appends_without_duplicates(self) -> None:
        first = Path("first.mp4")
        second = Path("second.mp4")

        result = _append_unique_paths([first], [first, second])

        self.assertEqual(result, [first, second])

    def test_best_quality_uses_uhq_gpu_encoding_and_fp32(self) -> None:
        preset = QUALITY_PRESETS["best"]

        self.assertEqual(preset["detection_model"], "v4-accurate")
        self.assertEqual(preset["encoding_preset"], "hevc-nvidia-gpu-uhq")
        self.assertEqual(
            _encoding_preset_for_device(str(preset["encoding_preset"]), "cpu"),
            "h264-cpu-uhq",
        )

    def test_cuda_fallback_also_switches_gpu_encoder(self) -> None:
        settings = LadaSettings(
            lada_cli_path=None,
            input_path=Path("input.mp4"),
            output_path=Path("output.mp4"),
            temporary_directory=Path("temp"),
            device="cuda",
            encoding_preset="hevc-nvidia-gpu-uhq",
            fp16=None,
        )

        result = _settings_for_cpu(settings)

        self.assertEqual(result.device, "cpu")
        self.assertEqual(result.encoding_preset, "h264-cpu-uhq")
        self.assertFalse(result.fp16)

    def test_high_quality_command_explicitly_disables_fp16(self) -> None:
        lada_cli = Path("vendor/lada/nvidia/lada-cli.exe").resolve()
        settings = LadaSettings(
            lada_cli_path=lada_cli,
            input_path=Path("input.mp4"),
            output_path=Path("output.mp4"),
            temporary_directory=Path("temp"),
            device="cuda",
            encoding_preset="hevc-nvidia-gpu-uhq",
            detection_model="v4-accurate",
            restoration_model="basicvsrpp-v1.2",
            fp16=False,
        )

        command = build_lada_command(settings)

        self.assertIn("--no-fp16", command)

    def test_two_beauty_jobs_run_sequentially(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            inputs = [root / "first.mp4", root / "second.mp4"]
            output_dir = root / "outputs"
            for index, input_path in enumerate(inputs):
                self._write_test_video(input_path, index * 30)

            app = MosaicApp()
            app.withdraw()

            with (
                patch(
                    "mosaic.app.filedialog.askopenfilenames",
                    side_effect=[(str(inputs[0]),), (str(inputs[1]), str(inputs[0]))],
                ),
                patch("mosaic.app.messagebox.showinfo"),
                patch("mosaic.app.messagebox.showwarning"),
                patch("mosaic.app.messagebox.showerror"),
            ):
                app._choose_input()
                app._choose_input()
                self.assertEqual(app._selected_inputs, inputs)
                self.assertEqual(app.input_var.get(), "2 videos selected")
                self.assertEqual(app.log_text.master.cget("text"), "Execution log")
                self.assertEqual(app.log_text.master.winfo_manager(), "panedwindow")

                app.output_dir_var.set(str(output_dir))
                app.process_mode_var.set("beauty")
                app.beauty_preserve_audio_var.set(False)
                app._start()
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    app.update()
                    if (
                        app._batch_jobs
                        and app._process is None
                        and all(job.status == "Completed" for job in app._batch_jobs)
                    ):
                        break
                    time.sleep(0.02)

            try:
                self.assertEqual(
                    [job.status for job in app._batch_jobs], ["Completed", "Completed"]
                )
                self.assertEqual(app._completed_jobs, 2)
                self.assertTrue((output_dir / "first.beauty.mp4").is_file())
                self.assertTrue((output_dir / "second.beauty.mp4").is_file())
            finally:
                app.destroy()

    @staticmethod
    def _write_test_video(path: Path, offset: int) -> None:
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 12, (64, 48))
        if not writer.isOpened():
            raise RuntimeError("Could not create integration test video")
        try:
            for frame_number in range(12):
                value = (offset + frame_number * 10) % 255
                frame = np.full((48, 64, 3), value, dtype=np.uint8)
                writer.write(frame)
        finally:
            writer.release()


if __name__ == "__main__":
    unittest.main()
