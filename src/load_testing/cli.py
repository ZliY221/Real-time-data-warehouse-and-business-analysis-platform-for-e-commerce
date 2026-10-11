"""CLI for load datasets and sanitized Flink runtime evidence."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from .experiment import write_load_plan
from .flink_runtime import FlinkRestClient, collect_runtime_snapshot
from .incidents import update_incident_state
from .notifications import write_notification_plan
from .load_dataset import generate_load_dataset
from .report import runtime_snapshot_markdown
from .series import collect_runtime_series, write_runtime_series
from .sink_completion import ClickHouseCountClient, wait_for_sink_completion
from .slo import write_slo_report
from .summary import write_experiment_summary
from .throttled import publish_file


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

    plan = subparsers.add_parser("plan", help="write the canonical low/medium/high load plan")
    plan.add_argument("--output", type=Path, required=True)

    publish = subparsers.add_parser("publish", help="stream NDJSON to stdout at a target rate")
    publish.add_argument("--input", type=Path, required=True)
    publish.add_argument("--target-rate", type=int, required=True)
    publish.add_argument("--report-output", type=Path, required=True)

    series = subparsers.add_parser("collect-series", help="collect repeated Flink REST snapshots")
    series.add_argument("--job-id", required=True)
    series.add_argument("--rest-url", default="http://127.0.0.1:8081")
    series.add_argument("--samples", type=int, default=12)
    series.add_argument("--interval-seconds", type=float, default=5.0)
    series.add_argument("--output", type=Path, required=True)

    sink = subparsers.add_parser("wait-sink", help="wait for ClickHouse order-count completion")
    sink.add_argument("--expected-records", type=int, required=True)
    sink.add_argument("--window-start", type=_timestamp, required=True)
    sink.add_argument("--window-end", type=_timestamp, required=True)
    sink.add_argument("--started-at", type=_timestamp, required=True)
    sink.add_argument("--timeout-seconds", type=float, default=120.0)
    sink.add_argument("--poll-interval-seconds", type=float, default=2.0)
    sink.add_argument("--clickhouse-url", default="http://127.0.0.1:8123")
    sink.add_argument("--database", default="ecommerce")
    sink.add_argument("--output", type=Path, required=True)

    summarize = subparsers.add_parser("summarize", help="validate and summarize all load tiers")
    summarize.add_argument("--plan", type=Path, required=True)
    summarize.add_argument("--evidence-root", type=Path, required=True)
    summarize.add_argument("--output", type=Path, required=True)

    evaluate_slo = subparsers.add_parser("evaluate-slo", help="evaluate operational SLO policy")
    evaluate_slo.add_argument("--summary", type=Path, required=True)
    evaluate_slo.add_argument("--policy", type=Path, required=True)
    evaluate_slo.add_argument("--output", type=Path, required=True)

    reconcile_alerts = subparsers.add_parser(
        "reconcile-alerts", help="update the durable lifecycle of SLO incidents"
    )
    reconcile_alerts.add_argument("--slo-report", type=Path, required=True)
    reconcile_alerts.add_argument("--state", type=Path, required=True)
    reconcile_alerts.add_argument("--observed-at", required=True)

    notification_plan = subparsers.add_parser(
        "plan-notifications", help="build an idempotent incident notification outbox"
    )
    notification_plan.add_argument("--state", type=Path, required=True)
    notification_plan.add_argument("--policy", type=Path, required=True)
    notification_plan.add_argument("--delivery-ledger", type=Path)
    notification_plan.add_argument("--output", type=Path, required=True)
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

    if args.command == "plan":
        plan = write_load_plan(args.output)
        print(f"wrote {len(plan['tiers'])} load tiers to {args.output}")
        return

    if args.command == "publish":
        publish_file(
            args.input,
            sys.stdout,
            args.report_output,
            target_rate=args.target_rate,
        )
        return

    if args.command == "collect-series":
        client = FlinkRestClient(args.rest_url)
        snapshots = collect_runtime_series(
            client,
            args.job_id,
            sample_count=args.samples,
            interval_seconds=args.interval_seconds,
        )
        write_runtime_series(args.output, snapshots)
        print(f"collected {len(snapshots)} Flink snapshots at {args.output}")
        return

    if args.command == "wait-sink":
        client = ClickHouseCountClient(args.clickhouse_url, args.database)
        report = wait_for_sink_completion(
            lambda: client.count_orders(args.window_start, args.window_end),
            expected_records=args.expected_records,
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            started_at=args.started_at,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"ClickHouse sink status={report['status']}; observed={report['observed_records']}")
        if report["status"] != "COMPLETE":
            raise SystemExit(1)
        return

    if args.command == "summarize":
        summary = write_experiment_summary(args.plan, args.evidence_root, args.output)
        print(f"summarized {len(summary['tiers'])} verified load tiers at {args.output}")
        return

    if args.command == "evaluate-slo":
        report = write_slo_report(args.summary, args.policy, args.output)
        print(f"load SLO status={report['status']}; alerts={len(report['alerts'])}")
        if report["status"] != "PASS":
            raise SystemExit(1)
        return

    if args.command == "reconcile-alerts":
        state = update_incident_state(args.slo_report, args.state, args.observed_at)
        print(
            f"active incidents={state['active_incident_count']}; "
            f"resolved incidents={state['resolved_incident_count']}"
        )
        return

    if args.command == "plan-notifications":
        outbox = write_notification_plan(
            args.state, args.policy, args.delivery_ledger, args.output
        )
        print(
            f"notification outbox status={outbox['status']}; "
            f"pending={outbox['pending_event_count']}"
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
