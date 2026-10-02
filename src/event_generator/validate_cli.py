"""Validate an NDJSON file against the order-created v1 business contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .validation import validate_order_event


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate order-event NDJSON")
    parser.add_argument("--input", type=Path, required=True, help="NDJSON input path")
    parser.add_argument("--expected-count", type=int, help="required record count")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    records: list[dict[str, object]] = []
    failures: list[str] = []
    with args.input.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                failures.append(f"line {line_number}: invalid JSON: {error.msg}")
                continue
            records.append(event)
            failures.extend(
                f"line {line_number}: {message}" for message in validate_order_event(event)
            )

    if args.expected_count is not None and len(records) != args.expected_count:
        failures.append(
            f"expected {args.expected_count} records but found {len(records)}"
        )
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"validated {len(records)} order events from {args.input}")


if __name__ == "__main__":
    main()

