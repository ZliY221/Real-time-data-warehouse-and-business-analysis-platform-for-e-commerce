"""Command-line entry point for generating newline-delimited JSON events."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from .generator import generate_order_events
from .validation import validate_order_event


def _parse_start_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("start time must include a UTC offset or Z")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate deterministic order events")
    parser.add_argument("--count", type=int, default=20, help="number of events")
    parser.add_argument("--seed", type=int, default=2027, help="random seed")
    parser.add_argument(
        "--events-per-second",
        type=int,
        help="event-time density for load datasets; omitted keeps one event every 3 seconds",
    )
    parser.add_argument(
        "--start-time",
        type=_parse_start_time,
        default=_parse_start_time("2026-10-02T10:00:00Z"),
        help="event start time in ISO 8601 format",
    )
    parser.add_argument("--output", type=Path, required=True, help="NDJSON output path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    events = generate_order_events(
        args.count,
        seed=args.seed,
        start_time=args.start_time,
        events_per_second=args.events_per_second,
    )
    violations = [
        (index, errors)
        for index, event in enumerate(events)
        if (errors := validate_order_event(event))
    ]
    if violations:
        raise ValueError(f"generated events violate the contract: {violations}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        for event in events:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
    print(f"generated {len(events)} events at {args.output}")


if __name__ == "__main__":
    main()

