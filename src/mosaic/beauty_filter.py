"""OpenCV based skin whitening filter for local videos."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .lada_engine import find_lada_tool

LogCallback = Callable[[str], None]
DoneCallback = Callable[[int, Path], None]


@dataclass(frozen=True)
class BeautyFilterSettings:
    input_path: Path
    output_path: Path
    temporary_directory: Path
    strength: int = 55
    preserve_audio: bool = True


class BeautyFilterProcess:
    def __init__(
        self,
        settings: BeautyFilterSettings,
        on_log: LogCallback,
        on_done: DoneCallback,
    ) -> None:
        self.settings = settings
        self.on_log = on_log
        self.on_done = on_done
        self._thread: threading.Thread | None = None
        self._cancelled = False
        self._log_file: Path | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            raise RuntimeError("A beauty filter process is already running.")
        self._cancelled = False
        self._thread = threading.Thread(target=self._run, name="mosaic-beauty-filter", daemon=True)
        self._thread.start()

    def run_blocking(self) -> None:
        if self.is_running:
            raise RuntimeError("A beauty filter process is already running.")
        self._cancelled = False
        self._run()

    def cancel(self) -> None:
        self._cancelled = True
        self._emit_log("Stopping current beauty filter process...")

    def _run(self) -> None:
        self.settings.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.temporary_directory.mkdir(parents=True, exist_ok=True)
        self._log_file = self.settings.temporary_directory / "beauty-filter.log"
        self._emit_log(f"Log file: {self._log_file}")
        self._emit_log(f"Temporary directory: {self.settings.temporary_directory}")

        try:
            returncode = self._run_filter()
            if self._cancelled and returncode != 0:
                self._emit_log("Beauty filter was cancelled.")
            elif returncode == 0:
                self._emit_log(f"Finished: {self.settings.output_path}")
            self.on_done(returncode, self.settings.output_path)
        except Exception as exc:
            self._emit_log(f"Failed to run beauty filter: {exc}")
            for line in traceback.format_exc().rstrip().splitlines():
                self._emit_log(line)
            self.on_done(1, self.settings.output_path)

    def _run_filter(self) -> int:
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            self._emit_log(
                "OpenCV/numpy is not installed. Install the optional beauty dependencies with "
                "`pip install -e .[beauty]` before using this filter."
            )
            self._emit_log(str(exc))
            return 1

        input_path = self.settings.input_path
        output_path = self.settings.output_path
        if not input_path.is_file():
            self._emit_log(f"Input video does not exist: {input_path}")
            return 1

        cap = cv2.VideoCapture(str(input_path))
        if not cap.isOpened():
            self._emit_log(f"OpenCV could not open input video: {input_path}")
            return 1

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if width <= 0 or height <= 0:
            cap.release()
            self._emit_log("OpenCV could not read the input video size.")
            return 1

        self._emit_log("Starting OpenCV beauty whitening filter.")
        self._emit_log(f"Input path: {input_path}")
        self._emit_log(f"Output path: {output_path}")
        self._emit_log(f"Video: {width}x{height}, fps={fps:.3f}, frames={frame_count or 'unknown'}")
        self._emit_log(
            "Settings: "
            f"strength={self.settings.strength}, preserve_audio={self.settings.preserve_audio}"
        )

        detector_available = _load_face_detector(cv2) is not None
        if not detector_available:
            self._emit_log(
                "OpenCV Haar face detector was not available; using skin color mask only."
            )
        else:
            self._emit_log("OpenCV Haar face detector loaded for adaptive skin masking.")

        worker_count = _beauty_worker_count(width, height)
        previous_cv_threads = cv2.getNumThreads()
        cv2.setNumThreads(1)
        self._emit_log(
            f"Parallel frame processing: workers={worker_count}, ordered output enabled."
        )
        worker_state = threading.local()

        def process_frame(frame):
            if not hasattr(worker_state, "face_detector"):
                worker_state.face_detector = _load_face_detector(cv2)
            return _beautify_frame(
                cv2,
                np,
                frame,
                worker_state.face_detector,
                strength,
            )

        temp_video = self.settings.temporary_directory / f"{output_path.stem}.beauty-video.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(temp_video), fourcc, fps, (width, height))
        if not writer.isOpened():
            cap.release()
            self._emit_log(f"OpenCV could not create temporary output video: {temp_video}")
            return 1

        processed = 0
        last_percent = -1
        started_at = time.monotonic()
        strength = max(0.0, min(1.0, self.settings.strength / 100.0))

        try:
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="beauty-frame",
            ) as executor:
                reached_end = False
                while not reached_end:
                    if self._cancelled:
                        return 130
                    frames = []
                    for _ in range(worker_count):
                        ok, frame = cap.read()
                        if not ok:
                            reached_end = True
                            break
                        frames.append(frame)
                    if not frames:
                        break

                    for filtered in executor.map(process_frame, frames):
                        if self._cancelled:
                            return 130
                        writer.write(filtered)
                        processed += 1

                        if frame_count > 0:
                            percent = int(processed * 100 / frame_count)
                            if percent != last_percent:
                                last_percent = percent
                                self._emit_progress(percent, processed, frame_count, started_at)
                        elif processed % 30 == 0:
                            elapsed = max(0.001, time.monotonic() - started_at)
                            self._emit_log(
                                f"Processing video frame {processed}; "
                                f"speed={processed / elapsed:.2f} fps"
                            )
        finally:
            cap.release()
            writer.release()
            cv2.setNumThreads(previous_cv_threads)

        if processed == 0:
            self._emit_log("No frames were decoded from the input video.")
            return 1

        if self._cancelled:
            return 130

        if frame_count <= 0:
            self._emit_log(f"Processing video 100%| frame {processed}/{processed}")

        return self._finalize_output(temp_video, output_path)

    def _finalize_output(self, temp_video: Path, output_path: Path) -> int:
        if not self.settings.preserve_audio:
            shutil.copyfile(temp_video, output_path)
            self._emit_log("Audio preservation is disabled; wrote video-only output.")
            return 0

        ffmpeg = _find_ffmpeg()
        if ffmpeg is None:
            shutil.copyfile(temp_video, output_path)
            self._emit_log("ffmpeg was not found; wrote video-only output without original audio.")
            return 0

        self._emit_log(f"Remuxing original audio with ffmpeg: {ffmpeg}")
        command = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(temp_video),
            "-i",
            str(self.settings.input_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a?",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-shortest",
            str(output_path),
        ]
        result = subprocess.run(command, capture_output=True, check=False)
        if result.returncode == 0:
            self._emit_log("Original audio track was preserved.")
            return 0

        shutil.copyfile(temp_video, output_path)
        stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        self._emit_log(
            f"ffmpeg remux failed with exit code {result.returncode}; wrote video-only output."
        )
        if stderr:
            self._emit_log(stderr)
        return 0

    def _emit_progress(
        self,
        percent: int,
        processed: int,
        frame_count: int,
        started_at: float,
    ) -> None:
        elapsed = max(0.001, time.monotonic() - started_at)
        speed = processed / elapsed
        self._emit_log(
            f"Processing video {percent}%| frame {processed}/{frame_count}, speed={speed:.2f} fps"
        )

    def _emit_log(self, line: str) -> None:
        self.on_log(line)
        if self._log_file is not None:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with self._log_file.open("a", encoding="utf-8") as log:
                log.write(f"[{timestamp}] {line}\n")


def default_beauty_output_path(input_path: Path, output_directory: Path) -> Path:
    return output_directory / f"{input_path.stem}.beauty.mp4"


def check_beauty_dependencies() -> tuple[bool, str]:
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as exc:
        return (
            False,
            "OpenCV/numpy is not installed. Activate the project environment and run "
            '`pip install -e ".[beauty]"`, then restart the app.',
        )
    return True, ""


def _load_face_detector(cv2):
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if not cascade_path.is_file():
        return None
    detector = cv2.CascadeClassifier(str(cascade_path))
    if detector.empty():
        return None
    return detector


def _beauty_worker_count(width: int, height: int, logical_cpus: int | None = None) -> int:
    logical_cpus = logical_cpus or os.cpu_count() or 4
    available = max(1, logical_cpus // 2)
    pixels = width * height
    if pixels >= 3840 * 2160:
        return min(4, available)
    if pixels >= 1920 * 1080:
        return min(6, available)
    return min(8, available)


def _beautify_frame(cv2, np, frame, face_detector, strength: float):
    skin_mask = _skin_mask(cv2, np, frame, face_detector)
    if not skin_mask.any():
        return frame

    enhanced = _whiten_candidate(cv2, np, frame, strength)
    smooth = cv2.bilateralFilter(enhanced, d=5, sigmaColor=25 + 35 * strength, sigmaSpace=7)
    candidate = cv2.addWeighted(enhanced, 0.82, smooth, 0.18, 0)

    alpha = (skin_mask.astype("float32") / 255.0) * min(0.92, 0.35 + strength * 0.65)
    alpha = alpha[:, :, None]
    output = frame.astype("float32") * (1.0 - alpha) + candidate.astype("float32") * alpha
    return np.clip(output, 0, 255).astype("uint8")


def _skin_mask(cv2, np, frame, face_detector):
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    base_ycrcb = cv2.inRange(ycrcb, np.array([35, 133, 77]), np.array([255, 173, 127]))
    base_hsv = cv2.inRange(hsv, np.array([0, 12, 45]), np.array([25, 170, 255]))
    mask = cv2.bitwise_or(base_ycrcb, base_hsv)

    face_mask = _face_guided_mask(cv2, np, frame, ycrcb, hsv, face_detector)
    if face_mask is not None:
        mask = cv2.bitwise_or(mask, face_mask)

    mask = _remove_feature_like_regions(cv2, np, mask, ycrcb, hsv)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    return cv2.GaussianBlur(mask, (21, 21), 0)


def _face_guided_mask(cv2, np, frame, ycrcb, hsv, face_detector):
    if face_detector is None:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_detector.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(40, 40))
    if len(faces) == 0:
        return None

    h, w = frame.shape[:2]
    sample_mask = np.zeros((h, w), dtype="uint8")
    for x, y, fw, fh in faces[:8]:
        center = (int(x + fw * 0.5), int(y + fh * 0.54))
        axes = (max(1, int(fw * 0.38)), max(1, int(fh * 0.46)))
        cv2.ellipse(sample_mask, center, axes, 0, 0, 360, 255, -1)

    y_channel, cr_channel, cb_channel = cv2.split(ycrcb)
    saturation = hsv[:, :, 1]
    valid = (sample_mask > 0) & (y_channel > 45) & (saturation < 170)
    if int(valid.sum()) < 80:
        return None

    cr_median = float(np.median(cr_channel[valid]))
    cb_median = float(np.median(cb_channel[valid]))
    lower = np.array([35, max(0, cr_median - 18), max(0, cb_median - 20)])
    upper = np.array([255, min(255, cr_median + 18), min(255, cb_median + 20)])
    adaptive = cv2.inRange(ycrcb, lower.astype("uint8"), upper.astype("uint8"))
    clean_face_area = cv2.dilate(sample_mask, np.ones((35, 35), dtype="uint8"), iterations=1)
    return cv2.bitwise_and(adaptive, clean_face_area)


def _remove_feature_like_regions(cv2, np, mask, ycrcb, hsv):
    y_channel = ycrcb[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    hue = hsv[:, :, 0]

    dark_details = ((y_channel < 55) | (value < 50)).astype("uint8") * 255
    vivid_lips = ((saturation > 105) & ((hue < 8) | (hue > 165))).astype("uint8") * 255
    vivid_makeup = ((saturation > 150) & (value > 80)).astype("uint8") * 255
    features = cv2.bitwise_or(dark_details, cv2.bitwise_or(vivid_lips, vivid_makeup))
    features = cv2.dilate(features, np.ones((3, 3), dtype="uint8"), iterations=1)
    return cv2.bitwise_and(mask, cv2.bitwise_not(features))


def _whiten_candidate(cv2, np, frame, strength: float):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype("float32")
    hsv[:, :, 1] *= 1.0 - 0.10 * strength
    hsv[:, :, 2] = hsv[:, :, 2] + (255.0 - hsv[:, :, 2]) * (0.10 + 0.24 * strength)
    hsv = np.clip(hsv, 0, 255).astype("uint8")
    bright = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.1 + strength * 1.2, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    contrast = cv2.cvtColor(cv2.merge((l_channel, a_channel, b_channel)), cv2.COLOR_LAB2BGR)

    return cv2.addWeighted(bright, 0.72, contrast, 0.28, 0)


def _find_ffmpeg() -> Path | None:
    return (
        find_lada_tool("ffmpeg.exe")
        or find_lada_tool("ffmpeg")
        or _which_path("ffmpeg.exe")
        or _which_path("ffmpeg")
    )


def _which_path(name: str) -> Path | None:
    found = shutil.which(name)
    return Path(found).resolve() if found else None
