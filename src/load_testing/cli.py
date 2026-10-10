"""CLI for load datasets and sanitized Flink runtime evidence."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from .flink_runtime import FlinkRestClient, collect_runtime_snapshot
from .load_dataset import generate_load_dataset
from .report import runtime_snapshot_markdown


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("timestamp must be ISO 8601") from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset or Z")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build load inputs and collect Flink evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="create a deterministic load dataset")
    generate.add_argument("--count", type=int, required=True)
    generate.add_argument("--seed", type=int, default=2027)
    generate.add_argument("--event-time-rate", type=int, required=True)
    generate.add_argument("--profile", default="baseline")
    generate.add_argument(
        "--start-time",
        type=_timestamp,
        default=_timestamp("2026-10-02T10:00:00Z"),
    )
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--manifest-output", type=Path, required=True)

    collect = subparsers.add_parser("collect", help="collect one Flink REST snapshot")
    collect.add_argument("--job-id", required=True)
    collect.add_argument("--rest-url", default="http://127.0.0.1:8081")
    collect.add_argument("--allow-remote", action="store_true")
    collect.add_argument("--metrics-wait-seconds", type=float, default=0.0)
    collect.add_argument("--json-output", type=Path, required=True)
    collect.add_argument("--markdown-output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "generate":
        manifest = generate_load_dataset(
            args.output,
            args.manifest_output,
            count=args.count,
            seed=args.seed,
            start_time=args.start_time,
            event_time_rate=args.event_time_rate,
            profile=args.profile,
        )
        print(
            f"generated {manifest['generator']['count']} events; "
            f"manifest: {args.manifest_output}"
        )
        return

    client = FlinkRestClient(args.rest_url, allow_remote=args.allow_remote)
    snapshot = collect_runtime_snapshot(
        client,
        args.job_id,
        metrics_wait_seconds=args.metrics_wait_seconds,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(runtime_snapshot_markdown(snapshot), encoding="utf-8")
    print(f"collected Flink runtime evidence at {args.json_output}")


if __name__ == "__main__":
    main()
