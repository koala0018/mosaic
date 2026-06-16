"""Command line entry point for mosaic."""

from __future__ import annotations

import argparse
from pathlib import Path


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

    return parser


def handle_plan(args: argparse.Namespace) -> int:
    output = args.output or args.input.with_name(f"{args.input.stem}-restored{args.input.suffix}")
    print("mosaic restoration plan")
    print(f"input:   {args.input}")
    print(f"output:  {output}")
    print(f"quality: {args.quality}")
    print("status:  dry run only; model adapters will be added in later phases")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
