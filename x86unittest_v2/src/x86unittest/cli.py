from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import __version__
from .app import X86UniTestApp
from .compat.legacy_cli import translate_legacy_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="x86uni",
        description="X86UniTest v2 profile-driven test platform skeleton.",
    )
    parser.add_argument("--version", action="version", version=f"x86uni {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="Check profile and environment readiness.")
    add_profile_args(doctor)

    plan = subparsers.add_parser("plan", help="Preview selected test packs and test cases.")
    add_profile_args(plan)
    plan.add_argument("--output", default="", help="Optional JSON file path for the generated plan.")

    run = subparsers.add_parser("run", help="Create a v2 run directory and collect initial artifacts.")
    add_profile_args(run)
    run.add_argument("--output", default="output/v2_runs", help="Base output directory for v2 runs.")
    run.add_argument("--collect-only", action="store_true", help="Collect baseline evidence without active tests.")
    run.add_argument(
        "--target-config",
        default="",
        help="Optional SSH target config path to record in the run manifest.",
    )

    review = subparsers.add_parser("review", help="Analyze a run and render JSON plus HTML review outputs.")
    review.add_argument("--run", required=True, help="Path to a v2 run directory.")

    export = subparsers.add_parser("export", help="Package a run directory as a ZIP artifact.")
    export.add_argument("--run", required=True, help="Path to a v2 run directory.")
    export.add_argument("--format", default="zip", choices=["zip"], help="Export format.")

    legacy = subparsers.add_parser("legacy", help="Translate selected legacy x86UniTest flags.")
    legacy.add_argument("legacy_args", nargs=argparse.REMAINDER)

    return parser


def add_profile_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", default="fwa6083", help="Profile id or JSON profile path.")
    parser.add_argument(
        "--pack",
        action="append",
        default=[],
        help="Pack id or pack prefix to include. Repeatable.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    app = X86UniTestApp()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "legacy":
        translated = translate_legacy_args(args.legacy_args)
        if not translated:
            print("No supported legacy command was provided.")
            return 2
        return main(translated)

    if args.command == "doctor":
        return print_payload(app.doctor(args.profile, args.pack))
    if args.command == "plan":
        payload = app.plan(args.profile, args.pack)
        if args.output:
            write_json(Path(args.output), payload)
            print(f"Plan saved to {args.output}")
            return 0
        return print_payload(payload)
    if args.command == "run":
        payload = app.run(
            profile_ref=args.profile,
            selected_packs=args.pack,
            output_dir=Path(args.output),
            collect_only=args.collect_only,
            target_config=args.target_config,
        )
        print(f"Run created at {payload['run_dir']}")
        return 0
    if args.command == "review":
        payload = app.review(Path(args.run))
        print(f"Review saved to {payload['analysis_path']}")
        print(f"HTML report: {payload['html_path']}")
        return 0
    if args.command == "export":
        payload = app.export(Path(args.run), args.format)
        print(f"Export saved to {payload['export_path']}")
        return 0

    parser.print_help()
    return 2


def print_payload(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
