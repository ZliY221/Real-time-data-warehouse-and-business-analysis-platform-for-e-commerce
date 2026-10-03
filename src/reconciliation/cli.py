from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .engine import (
    ReconciliationInputError,
    build_batch_baseline,
    load_late_event_ids,
    load_metric_rows,
    reconcile_metrics,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or compare minute-metric baselines")
    commands = parser.add_subparsers(dest="command", required=True)

    baseline = commands.add_parser("baseline", help="build expected metrics from order events")
    baseline.add_argument("--events", type=Path, required=True, help="order-event NDJSON path")
    baseline.add_argument("--late-events", type=Path, help="optional late-event JSONEachRow path")
    baseline.add_argument("--output", type=Path, required=True, help="expected metric NDJSON path")

    compare = commands.add_parser("compare", help="compare batch baseline with stream metrics")
    compare.add_argument("--events", type=Path, required=True, help="order-event NDJSON path")
    compare.add_argument(
        "--actual", type=Path, required=True, help="actual metric JSONEachRow path"
    )
    compare.add_argument("--late-events", type=Path, help="optional late-event JSONEachRow path")
    compare.add_argument("--json-output", type=Path, help="machine-readable report path")
    compare.add_argument("--markdown-output", type=Path, help="reviewer-friendly report path")
    return parser


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _late_event_ids(path: Path | None) -> set[str]:
    if path is None:
        return set()
    with path.open("r", encoding="utf-8-sig") as stream:
        return load_late_event_ids(stream)


def _baseline(events: Path, late_events: Path | None):
    late_event_ids = _late_event_ids(late_events)
    with events.open("r", encoding="utf-8-sig") as stream:
        return build_batch_baseline(stream, late_event_ids=late_event_ids)


def main() -> None:
    args = build_parser().parse_args()
    try:
        baseline = _baseline(args.events, args.late_events)
        if args.command == "baseline":
            content = "".join(
                json.dumps(metric.to_dict(), ensure_ascii=False) + "\n"
                for metric in baseline.metrics
            )
            _write(args.output, content)
            print(
                f"batch baseline PASS: {baseline.accepted_records} accepted events, "
                f"{len(baseline.metrics)} metric keys"
            )
            raise SystemExit(0)

        with args.actual.open("r", encoding="utf-8-sig") as stream:
            actual_metrics = load_metric_rows(stream)
        report = reconcile_metrics(
            baseline,
            actual_metrics,
            events_input=str(args.events),
            actual_input=str(args.actual),
        )
    except (FileNotFoundError, OSError, ReconciliationInputError, ValueError) as error:
        print(f"metric reconciliation input error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    if args.json_output:
        _write(
            args.json_output,
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        )
    if args.markdown_output:
        _write(args.markdown_output, report.to_markdown())

    status = "PASS" if report.passed else "FAIL"
    print(
        f"metric reconciliation {status}: {report.matched_metric_keys} matched, "
        f"{len(report.differences)} mismatched metric keys"
    )
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
