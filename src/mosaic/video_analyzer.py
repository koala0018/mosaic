"""Output quality diagnostics for restored videos."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .lada_engine import find_lada_tool
from .text_encoding import decode_process_output


@dataclass(frozen=True)
class FrameDifference:
    time_seconds: float
    mean_abs_diff: float
    changed_ratio: float


@dataclass(frozen=True)
class VideoAnalysis:
    input_path: str
    output_path: str
    duration_seconds: float
    frame_samples: list[FrameDifference]
    mean_abs_diff: float
    max_abs_diff: float
    mean_changed_ratio: float
    likely_no_visible_change: bool
    conclusion: str


def analyze_restoration(
    input_path: Path,
    output_path: Path,
    temporary_directory: Path,
    lada_cli_path: Path | None,
) -> VideoAnalysis | None:
    ffmpeg = find_lada_tool("ffmpeg.exe", lada_cli_path) or find_lada_tool("ffmpeg", lada_cli_path)
    ffprobe = find_lada_tool("ffprobe.exe", lada_cli_path) or find_lada_tool("ffprobe", lada_cli_path)
    if ffmpeg is None or ffprobe is None:
        return None

    duration = _probe_duration(ffprobe, input_path)
    if duration <= 0:
        return None

    sample_times = _sample_times(duration)
    samples: list[FrameDifference] = []
    for sample_time in sample_times:
        before = _extract_gray_frame(ffmpeg, input_path, sample_time)
        after = _extract_gray_frame(ffmpeg, output_path, sample_time)
        if before is None or after is None or len(before) != len(after):
            continue
        samples.append(_frame_difference(sample_time, before, after))

    if not samples:
        return None

    mean_abs_diff = sum(sample.mean_abs_diff for sample in samples) / len(samples)
    max_abs_diff = max(sample.mean_abs_diff for sample in samples)
    mean_changed_ratio = sum(sample.changed_ratio for sample in samples) / len(samples)
    likely_no_visible_change = mean_abs_diff < 1.0 and mean_changed_ratio < 0.01

    if likely_no_visible_change:
        conclusion = (
            "输出与原视频抽样帧几乎没有差异。大概率是 Lada 没检测到可修复马赛克，"
            "或检测区域太小/修复结果不可见。"
        )
    elif mean_abs_diff < 3.0 and mean_changed_ratio < 0.05:
        conclusion = "输出有轻微变化，但变化很小；可能检测到少量区域，修复效果有限。"
    else:
        conclusion = "输出与原视频存在可测差异；如果观感仍差，问题更可能是修复模型效果不足。"

    analysis = VideoAnalysis(
        input_path=str(input_path),
        output_path=str(output_path),
        duration_seconds=duration,
        frame_samples=samples,
        mean_abs_diff=mean_abs_diff,
        max_abs_diff=max_abs_diff,
        mean_changed_ratio=mean_changed_ratio,
        likely_no_visible_change=likely_no_visible_change,
        conclusion=conclusion,
    )

    temporary_directory.mkdir(parents=True, exist_ok=True)
    report_path = temporary_directory / "mosaic-analysis.json"
    report_path.write_text(
        json.dumps(asdict(analysis), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return analysis


def _probe_duration(ffprobe: Path, video_path: Path) -> float:
    result = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return 0
    try:
        return float(decode_process_output(result.stdout).strip())
    except ValueError:
        return 0


def _sample_times(duration: float) -> list[float]:
    if duration < 5:
        return [max(0, duration / 2)]
    ratios = (0.1, 0.3, 0.5, 0.7, 0.9)
    return [max(0.5, min(duration - 0.5, duration * ratio)) for ratio in ratios]


def _extract_gray_frame(ffmpeg: Path, video_path: Path, time_seconds: float) -> bytes | None:
    result = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{time_seconds:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=160:90:flags=fast_bilinear,format=gray",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout


def _frame_difference(time_seconds: float, before: bytes, after: bytes) -> FrameDifference:
    total_diff = 0
    changed = 0
    for left, right in zip(before, after):
        diff = abs(left - right)
        total_diff += diff
        if diff >= 3:
            changed += 1
    count = max(1, len(before))
    return FrameDifference(
        time_seconds=time_seconds,
        mean_abs_diff=total_diff / count,
        changed_ratio=changed / count,
    )
