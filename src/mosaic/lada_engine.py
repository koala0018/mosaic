"""Lada CLI integration helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .text_encoding import decode_process_output


DEFAULT_OUTPUT_PATTERN = "{stem}.restored.mp4"


@dataclass(frozen=True)
class LadaSettings:
    lada_cli_path: Path | None
    input_path: Path
    output_path: Path
    temporary_directory: Path
    device: str = "auto"
    encoding_preset: str = "auto"
    max_clip_length: int = 180
    detection_model: str = "v4-fast"
    restoration_model: str = "basicvsrpp-v1.2"
    detect_face_mosaics: bool | None = None
    fp16: bool | None = None
    mp4_fast_start: bool = False


def default_output_path(input_path: Path, output_directory: Path) -> Path:
    return output_directory / DEFAULT_OUTPUT_PATTERN.format(stem=input_path.stem)


def find_lada_cli(explicit_path: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(explicit_path)

    env_path = os.environ.get("LADA_CLI_PATH")
    if env_path:
        candidates.append(Path(env_path))

    for name in ("lada-cli.exe", "lada-cli"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    app_dir = Path(sys_executable_dir())
    candidates.extend(
        [
            app_dir / "lada" / "lada-cli.exe",
            app_dir / "lada" / "lada-cli",
            app_dir / "tools" / "lada" / "lada-cli.exe",
            app_dir / "tools" / "lada" / "lada-cli",
        ]
    )

    project_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            project_root / "tools" / "lada" / "lada-cli.exe",
            project_root / "tools" / "lada" / "lada-cli",
        ]
    )

    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.is_file():
            return candidate.resolve()
    return None


def find_lada_tool(tool_name: str, lada_cli_path: Path | None = None) -> Path | None:
    lada_cli = find_lada_cli(lada_cli_path)
    candidates: list[Path] = []
    if lada_cli:
        lada_root = lada_cli.parent
        candidates.extend(
            [
                lada_root / "_internal" / "bin" / tool_name,
                lada_root / "_internal" / tool_name,
                lada_root / tool_name,
            ]
        )

    found = shutil.which(tool_name)
    if found:
        candidates.append(Path(found))

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def sys_executable_dir() -> str:
    import sys

    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent)
    return str(Path.cwd())


def build_lada_command(settings: LadaSettings) -> list[str]:
    lada_cli = find_lada_cli(settings.lada_cli_path)
    if lada_cli is None:
        raise FileNotFoundError(
            "lada-cli was not found. Select lada-cli.exe, put it on PATH, or set LADA_CLI_PATH."
        )

    command = [
        str(lada_cli),
        "--input",
        str(settings.input_path),
        "--output",
        str(settings.output_path),
        "--temporary-directory",
        str(settings.temporary_directory),
        "--max-clip-length",
        str(settings.max_clip_length),
        "--mosaic-detection-model",
        settings.detection_model,
        "--mosaic-restoration-model",
        settings.restoration_model,
    ]

    if settings.device != "auto":
        command.extend(["--device", settings.device])
    if settings.encoding_preset != "auto":
        command.extend(["--encoding-preset", settings.encoding_preset])
    if settings.fp16 is True and supports_fp16_device(settings.device):
        command.append("--fp16")
    elif settings.fp16 is False:
        command.append("--no-fp16")
    if settings.mp4_fast_start:
        command.append("--mp4-fast-start")
    if settings.detect_face_mosaics is True:
        command.append("--detect-face-mosaics")
    elif settings.detect_face_mosaics is False:
        command.append("--no-detect-face-mosaics")

    return command


def _device_family(device: str) -> str:
    return device.strip().lower().split(":", 1)[0]


def supports_fp16_device(device: str) -> bool:
    return _device_family(device) in {"auto", "cuda", "xpu"}


def run_lada_probe(lada_cli_path: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
    lada_cli = find_lada_cli(lada_cli_path)
    if lada_cli is None:
        raise FileNotFoundError(
            "lada-cli was not found. Select lada-cli.exe, put it on PATH, or set LADA_CLI_PATH."
        )

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    result = subprocess.run(
        [str(lada_cli), *args],
        check=False,
        capture_output=True,
        env=env,
    )
    return subprocess.CompletedProcess(
        args=result.args,
        returncode=result.returncode,
        stdout=decode_process_output(result.stdout or b""),
        stderr=decode_process_output(result.stderr or b""),
    )
