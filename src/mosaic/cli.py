"""Command line entry point for mosaic."""

from __future__ import annotations

import argparse
from pathlib import Path

from .lada_engine import LadaSettings, default_output_path, find_lada_cli, run_lada_probe
from .processor import RestorationProcess


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mosaic",
        description="Plan long-video restoration jobs for compression artifacts and pixelation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Create a dry-run restoration plan.")
    plan.add_argument("input", type=Path, help="Input video path.")
    plan.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Planned output video path.",
    )
    plan.add_argument(
        "--quality",
        choices=("fast", "balanced", "best"),
        default="balanced",
        help="Processing preset.",
    )
    plan.set_defaults(handler=handle_plan)

    process = subparsers.add_parser("process", help="Run a Lada restoration job.")
    process.add_argument("input", type=Path, help="Input video path.")
    process.add_argument("--output", type=Path, default=None, help="Output video path.")
    process.add_argument("--output-dir", type=Path, default=None, help="Output directory.")
    process.add_argument("--lada-cli", type=Path, default=None, help="Path to lada-cli.exe.")
    process.add_argument(
        "--quality",
        choices=("fast", "balanced", "best"),
        default="balanced",
        help="Processing preset.",
    )
    process.add_argument("--device", default="auto", help="Lada device, e.g. auto, cuda, cpu, xpu.")
    process.add_argument("--fp16", action=argparse.BooleanOptionalAction, default=None)
    process.add_argument(
        "--detection-model",
        choices=("preset", "v4-fast", "v4-accurate", "v2"),
        default="preset",
    )
    process.add_argument(
        "--restoration-model",
        choices=("basicvsrpp-v1.2", "deepmosaics"),
        default="basicvsrpp-v1.2",
    )
    process.add_argument("--detect-face-mosaics", action=argparse.BooleanOptionalAction, default=None)
    process.add_argument("--temporary-directory", type=Path, default=None, help="Temporary directory.")
    process.set_defaults(handler=handle_process)

    info = subparsers.add_parser("lada-info", help="Check the configured Lada CLI.")
    info.add_argument("--lada-cli", type=Path, default=None, help="Path to lada-cli.exe.")
    info.set_defaults(handler=handle_lada_info)

    app = subparsers.add_parser("app", help="Open the Windows desktop application.")
    app.set_defaults(handler=handle_app)

    return parser


def handle_plan(args: argparse.Namespace) -> int:
    output = args.output or args.input.with_name(f"{args.input.stem}-restored{args.input.suffix}")
    print("mosaic restoration plan")
    print(f"input:   {args.input}")
    print(f"output:  {output}")
    print(f"quality: {args.quality}")
    print("status:  dry run only; model adapters will be added in later phases")
    return 0


def handle_lada_info(args: argparse.Namespace) -> int:
    lada_cli = find_lada_cli(args.lada_cli)
    if lada_cli is None:
        print("lada-cli was not found. Select it in the app or set LADA_CLI_PATH.")
        return 1
    print(f"lada-cli: {lada_cli}")
    result = run_lada_probe(lada_cli, "--version")
    output = (result.stdout + result.stderr).strip()
    if output:
        print(output)
    return result.returncode


def handle_process(args: argparse.Namespace) -> int:
    output_dir = args.output_dir or args.input.parent
    output = args.output or default_output_path(args.input, output_dir)
    preset = _quality_preset(args.quality)
    detection_model = args.detection_model
    if detection_model == "preset":
        detection_model = str(preset["detection_model"])
    settings = LadaSettings(
        lada_cli_path=args.lada_cli,
        input_path=args.input,
        output_path=output,
        temporary_directory=args.temporary_directory or output.parent / ".mosaic-temp",
        device=args.device,
        encoding_preset=preset["encoding_preset"],
        max_clip_length=int(preset["max_clip_length"]),
        detection_model=detection_model,
        restoration_model=args.restoration_model,
        detect_face_mosaics=args.detect_face_mosaics,
        fp16=args.fp16,
    )
    return_code = 1

    def on_done(code: int, _output_path: Path) -> None:
        nonlocal return_code
        return_code = code

    process = RestorationProcess(settings, on_log=print, on_done=on_done)
    process.run_blocking()
    return return_code


def handle_app(_args: argparse.Namespace) -> int:
    from .app import main as app_main

    app_main()
    return 0


def _quality_preset(name: str) -> dict[str, str | int]:
    presets = {
        "fast": {
            "encoding_preset": "h264-cpu-fast",
            "max_clip_length": 120,
            "detection_model": "v4-fast",
        },
        "balanced": {
            "encoding_preset": "auto",
            "max_clip_length": 180,
            "detection_model": "v4-fast",
        },
        "best": {
            "encoding_preset": "h264-cpu-uhq",
            "max_clip_length": 240,
            "detection_model": "v4-accurate",
        },
    }
    return presets[name]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
